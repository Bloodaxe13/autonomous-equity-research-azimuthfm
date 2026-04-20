from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.memory.json_store_runtime import JsonMemoryStore
import pytest

from src.responses_agent_runtime import AgentLoopIncomplete, build_default_prompt_executor
from src.tools.code_execution_runtime import CodeExecutionTool
from src.tools.runtime_web import StaticFetchAdapter, StaticSearchAdapter, WebFetchTool, WebSearchTool


@dataclass
class FakeResponse:
    payload: dict
    output_text: str = ""
    id: str | None = None

    def __post_init__(self):
        if self.id is not None:
            self.payload.setdefault("id", self.id)

    def model_dump(self) -> dict:
        return self.payload


class FakeResponsesAPI:
    def __init__(self, scripted_responses: list[FakeResponse]):
        self.scripted_responses = list(scripted_responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.scripted_responses:
            raise AssertionError("No scripted responses left for FakeResponsesAPI")
        return self.scripted_responses.pop(0)


class FakeClient:
    def __init__(self, scripted_responses: list[FakeResponse]):
        self.responses = FakeResponsesAPI(scripted_responses)


def _tools(memory_store: JsonMemoryStore, *, client: FakeClient, subagent_runner=None, document_query_tool=None):
    search = WebSearchTool(
        StaticSearchAdapter(
            {
                "ACME overview": [
                    {
                        "title": "ACME filing",
                        "url": "https://example.test/acme/filing",
                        "snippet": "Annual report",
                    }
                ]
            }
        )
    )
    fetch = WebFetchTool(
        StaticFetchAdapter(
            {
                "https://example.test/acme/filing": {
                    "status_code": 200,
                    "content_type": "text/html",
                    "text": "ACME filing body",
                }
            }
        )
    )
    return build_default_prompt_executor(
        memory_store=memory_store,
        web_search=search,
        web_fetch=fetch,
        code_execution=CodeExecutionTool(),
        subagent_runner=subagent_runner,
        client=client,
        default_model="gpt-5-mini",
        document_query_tool=document_query_tool,
    )


def test_prompt_executor_runs_responses_loop_until_complete(tmp_path: Path):
    prompt_file = tmp_path / "agent.md"
    prompt_file.write_text("Today is {{.CurrentDate}}. Ticker {{.Ticker}}.", encoding="utf-8")

    client = FakeClient(
        [
            FakeResponse(
                {
                    "id": "resp_1",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "web_search",
                            "call_id": "call_1",
                            "arguments": json.dumps({"query": "ACME overview", "limit": 3}),
                        }
                    ],
                }
            ),
            FakeResponse(
                {
                    "id": "resp_2",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "complete_task",
                            "call_id": "call_2",
                            "arguments": json.dumps({"payload": {"status": "done", "company": "ACME"}}),
                        }
                    ],
                },
                output_text="finished",
            ),
        ]
    )

    executor = _tools(JsonMemoryStore(tmp_path / "memory"), client=client)
    result = executor.run_prompt_file(
        prompt_file,
        user_input={"ticker": "ACME"},
        prompt_context={"Ticker": "ACME"},
        tool_names=["web_search", "complete_task"],
        run_id="run-1",
    )

    assert result.final_output == {"status": "done", "company": "ACME"}
    assert result.completed_via_tool == "complete_task"
    assert result.turns == 2
    assert result.tool_history[0]["tool"] == "web_search"
    assert "Ticker ACME" in client.responses.calls[0]["instructions"]
    assert client.responses.calls[0]["max_output_tokens"] == 100000
    assert client.responses.calls[1]["previous_response_id"] == "resp_1"
    assert client.responses.calls[1]["input"][0]["type"] == "function_call_output"


def test_default_tools_support_memory_code_and_subagent(tmp_path: Path):
    prompt_file = tmp_path / "lead.md"
    prompt_file.write_text("Lead agent prompt.", encoding="utf-8")
    subagent_calls: list[dict] = []

    def subagent_runner(brief: dict, context):
        subagent_calls.append({"brief": brief, "run_id": context.run_id})
        return {"facet": brief["facet"], "summary": "subagent ok"}

    client = FakeClient(
        [
            FakeResponse(
                {
                    "id": "resp_a",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "memory_write",
                            "call_id": "call_a1",
                            "arguments": json.dumps({"key": "plan", "value": {"steps": 2}}),
                        },
                        {
                            "type": "function_call",
                            "name": "run_subagent",
                            "call_id": "call_a2",
                            "arguments": json.dumps({"brief": {"facet": "news"}}),
                        },
                    ],
                }
            ),
            FakeResponse(
                {
                    "id": "resp_b",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "memory_read",
                            "call_id": "call_b1",
                            "arguments": json.dumps({"key": "plan"}),
                        },
                        {
                            "type": "function_call",
                            "name": "code_execution",
                            "call_id": "call_b2",
                            "arguments": json.dumps({"python_code": "RESULT = 6 * 7"}),
                        },
                    ],
                }
            ),
            FakeResponse(
                {
                    "id": "resp_c",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "complete_task",
                            "call_id": "call_c1",
                            "arguments": json.dumps({"payload": {"report": "ok"}}),
                        }
                    ],
                }
            ),
        ]
    )

    memory_store = JsonMemoryStore(tmp_path / "memory")
    executor = _tools(memory_store, client=client, subagent_runner=subagent_runner)
    result = executor.run_prompt_file(
        prompt_file,
        user_input="start",
        run_id="run-42",
        tool_names=[
            "memory_write",
            "memory_read",
            "code_execution",
            "run_subagent",
            "complete_task",
        ],
    )

    assert result.final_output == {"report": "ok"}
    assert memory_store.read("run-42", "plan") == {"steps": 2}
    assert subagent_calls == [{"brief": {"facet": "news"}, "run_id": "run-42"}]
    memory_read_result = next(item["result"] for item in result.tool_history if item["tool"] == "memory_read")
    assert memory_read_result == {"key": "plan", "value": {"steps": 2}}
    code_result = next(item["result"] for item in result.tool_history if item["tool"] == "code_execution")
    assert code_result["ok"] is True
    assert code_result["result"] == 42


def test_agent_loop_incomplete_carries_raw_responses_and_timing(tmp_path: Path):
    prompt_file = tmp_path / "agent.md"
    prompt_file.write_text("Looping prompt.", encoding="utf-8")
    client = FakeClient(
        [
            FakeResponse(
                {
                    "id": "resp_1",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "web_search",
                            "call_id": "call_1",
                            "arguments": json.dumps({"query": "ACME overview", "limit": 1}),
                        }
                    ],
                },
                output_text="partial progress",
            )
        ]
    )
    executor = _tools(JsonMemoryStore(tmp_path / "memory"), client=client)

    with pytest.raises(AgentLoopIncomplete) as exc_info:
        executor.run_prompt_file(
            prompt_file,
            user_input={"ticker": "ACME"},
            tool_names=["web_search"],
            run_id="run-incomplete",
            max_turns=1,
        )

    exc = exc_info.value
    assert exc.prompt_path == str(prompt_file)
    assert exc.response_ids == ["resp_1"]
    assert exc.raw_responses[0]["response"]["id"] == "resp_1"
    assert exc.final_text == "partial progress"
    assert exc.started_at
    assert exc.completed_at
    assert exc.duration_ms >= 0


def test_run_subagent_accepts_json_string_brief_payload(tmp_path: Path):
    prompt_file = tmp_path / "lead.md"
    prompt_file.write_text("Lead agent prompt.", encoding="utf-8")
    subagent_calls: list[dict] = []

    def subagent_runner(brief: dict, context):
        subagent_calls.append({"brief": brief, "run_id": context.run_id})
        return {"facet": brief["facet"], "summary": "subagent ok"}

    client = FakeClient(
        [
            FakeResponse(
                {
                    "id": "resp_1",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "run_subagent",
                            "call_id": "call_1",
                            "arguments": json.dumps({"brief": json.dumps({"facet": "news", "ticker": "ACME"})}),
                        },
                    ],
                }
            ),
            FakeResponse(
                {
                    "id": "resp_2",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "complete_task",
                            "call_id": "call_2",
                            "arguments": json.dumps({"payload": {"ok": True}}),
                        }
                    ],
                }
            ),
        ]
    )

    executor = _tools(JsonMemoryStore(tmp_path / "memory"), client=client, subagent_runner=subagent_runner)
    result = executor.run_prompt_file(
        prompt_file,
        user_input="start",
        run_id="run-json-brief",
        tool_names=["run_subagent", "complete_task"],
    )

    assert result.final_output == {"ok": True}
    assert subagent_calls == [{"brief": {"facet": "news", "ticker": "ACME"}, "run_id": "run-json-brief"}]


def test_run_subagent_accepts_brief_embedded_in_text(tmp_path: Path):
    prompt_file = tmp_path / "lead.md"
    prompt_file.write_text("Lead agent prompt.", encoding="utf-8")
    subagent_calls: list[dict] = []

    def subagent_runner(brief: dict, context):
        subagent_calls.append({"brief": brief, "run_id": context.run_id})
        return {"facet": brief["facet"], "summary": "subagent ok"}

    raw_brief = "Use this brief: {'facet': 'news', 'ticker': 'ACME', 'objective': 'find catalysts'}"
    client = FakeClient(
        [
            FakeResponse(
                {
                    "id": "resp_1",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "run_subagent",
                            "call_id": "call_1",
                            "arguments": json.dumps({"brief": raw_brief}),
                        },
                    ],
                }
            ),
            FakeResponse(
                {
                    "id": "resp_2",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "complete_task",
                            "call_id": "call_2",
                            "arguments": json.dumps({"payload": {"ok": True}}),
                        }
                    ],
                }
            ),
        ]
    )

    executor = _tools(JsonMemoryStore(tmp_path / "memory"), client=client, subagent_runner=subagent_runner)
    result = executor.run_prompt_file(
        prompt_file,
        user_input="start",
        run_id="run-text-brief",
        tool_names=["run_subagent", "complete_task"],
    )

    assert result.final_output == {"ok": True}
    assert subagent_calls == [{"brief": {"facet": "news", "ticker": "ACME", "objective": "find catalysts"}, "run_id": "run-text-brief"}]


def test_tool_errors_are_returned_to_model_and_do_not_crash_loop(tmp_path: Path):
    prompt_file = tmp_path / "lead.md"
    prompt_file.write_text("Lead agent prompt.", encoding="utf-8")
    client = FakeClient(
        [
            FakeResponse(
                {
                    "id": "resp_1",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "run_subagent",
                            "call_id": "call_1",
                            "arguments": json.dumps({"brief": "not even close to json"}),
                        },
                    ],
                }
            ),
            FakeResponse(
                {
                    "id": "resp_2",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "complete_task",
                            "call_id": "call_2",
                            "arguments": json.dumps({"payload": {"ok": True, "recovered": True}}),
                        }
                    ],
                }
            ),
        ]
    )

    executor = _tools(JsonMemoryStore(tmp_path / "memory"), client=client, subagent_runner=lambda brief, context: brief)
    result = executor.run_prompt_file(
        prompt_file,
        user_input="start",
        run_id="run-tool-error",
        tool_names=["run_subagent", "complete_task"],
    )

    assert result.final_output == {"ok": True, "recovered": True}
    assert result.tool_history[0]["tool"] == "run_subagent"
    assert result.tool_history[0]["result"]["ok"] is False
    assert result.tool_history[0]["result"]["error_type"] == 'TypeError'


def test_default_tools_support_document_query_tool(tmp_path: Path):
    prompt_file = tmp_path / "subagent.md"
    prompt_file.write_text("Research prompt.", encoding="utf-8")

    def document_query_tool(arguments, context):
        return {
            "mode_used": "direct_pdf",
            "answer": f"document answer for {arguments['question']}",
            "run_id": context.run_id,
        }

    client = FakeClient(
        [
            FakeResponse(
                {
                    "id": "resp_doc_1",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "document_query",
                            "call_id": "call_doc_1",
                            "arguments": json.dumps(
                                {
                                    "question": "Summarize the filing",
                                    "document_urls": ["https://example.test/report.pdf"],
                                    "task_type": "summarize",
                                }
                            ),
                        }
                    ],
                }
            ),
            FakeResponse(
                {
                    "id": "resp_doc_2",
                    "output": [
                        {
                            "type": "function_call",
                            "name": "complete_task",
                            "call_id": "call_doc_2",
                            "arguments": json.dumps({"payload": {"ok": True}}),
                        }
                    ],
                }
            ),
        ]
    )

    executor = _tools(
        JsonMemoryStore(tmp_path / "memory"),
        client=client,
        document_query_tool=document_query_tool,
    )
    result = executor.run_prompt_file(
        prompt_file,
        user_input="start",
        run_id="run-doc-1",
        tool_names=["document_query", "complete_task"],
    )

    assert result.final_output == {"ok": True}
    doc_result = next(item["result"] for item in result.tool_history if item["tool"] == "document_query")
    assert doc_result["mode_used"] == "direct_pdf"
    assert doc_result["run_id"] == "run-doc-1"
