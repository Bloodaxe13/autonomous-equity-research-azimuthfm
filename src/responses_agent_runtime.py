from __future__ import annotations

import ast
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from src.contracts_runtime import SubagentBrief
from src.memory.json_store_runtime import JsonMemoryStore
from src.tools.code_execution_runtime import CodeExecutionTool
from src.tools.runtime_web import WebFetchTool, WebSearchTool

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - exercised via injected client in tests
    OpenAI = None


JSONDict = dict[str, Any]
ToolHandler = Callable[[JSONDict, "AgentRunContext"], Any]
MAX_TOOL_OUTPUT_CHARS = 12000


class AgentLoopIncomplete(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        prompt_path: str = '',
        final_text: str = '',
        tool_history: list[JSONDict] | None = None,
        turns: int = 0,
        response_ids: list[str] | None = None,
        raw_responses: list[JSONDict] | None = None,
        started_at: str = '',
        completed_at: str = '',
        duration_ms: int = 0,
    ):
        super().__init__(message)
        self.prompt_path = prompt_path
        self.final_text = final_text
        self.tool_history = tool_history or []
        self.turns = turns
        self.response_ids = response_ids or []
        self.raw_responses = raw_responses or []
        self.started_at = started_at
        self.completed_at = completed_at
        self.duration_ms = duration_ms


PARALLEL_SAFE_TOOLS = {'run_subagent', 'web_search', 'web_fetch', 'code_execution'}


class ResponsesClientProtocol(Protocol):
    class responses:  # pragma: no cover - structural typing helper
        @staticmethod
        def create(**kwargs: Any) -> Any: ...


@dataclass
class AgentRunContext:
    prompt_path: Path
    run_id: str | None = None
    metadata: JSONDict = field(default_factory=dict)


@dataclass
class AgentTool:
    name: str
    description: str
    parameters: JSONDict
    handler: ToolHandler

    def as_openai_tool(self) -> JSONDict:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": False,
        }


@dataclass
class AgentRunResult:
    prompt_path: str
    instructions: str
    final_output: Any
    response_text: str
    turns: int
    completed_via_tool: str | None
    tool_history: list[JSONDict] = field(default_factory=list)
    response_ids: list[str] = field(default_factory=list)
    raw_responses: list[JSONDict] = field(default_factory=list)
    started_at: str = ''
    completed_at: str = ''
    duration_ms: int = 0
    tool_counts: JSONDict = field(default_factory=dict)


class ResponsesAgentLoop:
    def __init__(
        self,
        *,
        client: ResponsesClientProtocol | None = None,
        tools: Mapping[str, AgentTool] | None = None,
        default_model: str = "gpt-5.4",
        max_turns: int = 20,
        max_output_tokens: int = 100000,
    ):
        self.client = client or self._build_default_client()
        self.tools = dict(tools or {})
        self.default_model = default_model
        self.max_turns = max_turns
        self.max_output_tokens = max_output_tokens

    def run_prompt_file(
        self,
        prompt_path: str | Path,
        *,
        user_input: str | JSONDict,
        model: str | None = None,
        prompt_context: Mapping[str, Any] | None = None,
        tool_names: list[str] | None = None,
        max_turns: int | None = None,
        run_id: str | None = None,
        metadata: JSONDict | None = None,
        response_overrides: Mapping[str, Any] | None = None,
    ) -> AgentRunResult:
        prompt_file = Path(prompt_path)
        instructions = render_prompt_template(prompt_file.read_text(encoding="utf-8"), prompt_context)
        context = AgentRunContext(prompt_path=prompt_file, run_id=run_id, metadata=dict(metadata or {}))
        selected_tools = self._select_tools(tool_names)
        response_ids: list[str] = []
        raw_responses: list[JSONDict] = []
        tool_history: list[JSONDict] = []
        previous_response_id: str | None = None
        next_input: Any = self._normalize_input(user_input)
        turn_limit = max_turns or self.max_turns
        final_output: Any = None
        final_text = ""
        completed_via_tool: str | None = None
        started_at = datetime.now(timezone.utc)

        for turn in range(1, turn_limit + 1):
            request = {
                "model": model or self.default_model,
                "instructions": instructions,
                "input": next_input,
                "tools": [tool.as_openai_tool() for tool in selected_tools.values()],
                "max_output_tokens": self.max_output_tokens,
            }
            if previous_response_id:
                request["previous_response_id"] = previous_response_id
            if response_overrides:
                request.update(dict(response_overrides))

            response = self.client.responses.create(**request)
            payload = self._response_payload(response)
            raw_responses.append({
                "turn": turn,
                "request": request,
                "response": payload,
            })
            response_id = payload.get("id") or getattr(response, "id", None)
            if response_id:
                response_ids.append(str(response_id))
            previous_response_id = str(response_id) if response_id else previous_response_id
            function_calls = self._extract_function_calls(payload)
            final_text = self._extract_response_text(payload, response)

            if not function_calls:
                final_output = final_text
                break

            tool_outputs: list[JSONDict] = []
            if self._can_parallelize(function_calls):
                with ThreadPoolExecutor(max_workers=min(len(function_calls), 8)) as executor:
                    futures = [
                        executor.submit(self._execute_tool_call, call, selected_tools, context, turn)
                        for call in function_calls
                    ]
                    execution_results = [future.result() for future in futures]
            else:
                execution_results = [
                    self._execute_tool_call(call, selected_tools, context, turn)
                    for call in function_calls
                ]

            for item in execution_results:
                tool_history.append(item["history_item"])
                if item["name"] == "complete_task":
                    final_output = item["result"]
                    completed_via_tool = item["name"]
                    finished_at = datetime.now(timezone.utc)
                    return AgentRunResult(
                        prompt_path=str(prompt_file),
                        instructions=instructions,
                        final_output=final_output,
                        response_text=final_text,
                        turns=turn,
                        completed_via_tool=completed_via_tool,
                        tool_history=tool_history,
                        response_ids=response_ids,
                        raw_responses=raw_responses,
                        started_at=started_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                        completed_at=finished_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                        duration_ms=int((finished_at - started_at).total_seconds() * 1000),
                        tool_counts=_tool_counts(tool_history),
                    )
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": item["call_id"],
                        "output": self._serialize_tool_output(item["result"]),
                    }
                )
            next_input = tool_outputs
        else:
            finished_at = datetime.now(timezone.utc)
            raise AgentLoopIncomplete(
                f"Agent loop exceeded max_turns={turn_limit} without completion",
                prompt_path=str(prompt_file),
                final_text=final_text,
                tool_history=tool_history,
                turns=turn_limit,
                response_ids=response_ids,
                raw_responses=raw_responses,
                started_at=started_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                completed_at=finished_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            )

        finished_at = datetime.now(timezone.utc)
        return AgentRunResult(
            prompt_path=str(prompt_file),
            instructions=instructions,
            final_output=final_output,
            response_text=final_text,
            turns=turn,
            completed_via_tool=completed_via_tool,
            tool_history=tool_history,
            response_ids=response_ids,
            raw_responses=raw_responses,
            started_at=started_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
            completed_at=finished_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            tool_counts=_tool_counts(tool_history),
        )

    def _select_tools(self, tool_names: list[str] | None) -> dict[str, AgentTool]:
        if tool_names is None:
            return dict(self.tools)
        missing = [name for name in tool_names if name not in self.tools]
        if missing:
            raise KeyError(f"Requested unknown tools: {', '.join(missing)}")
        return {name: self.tools[name] for name in tool_names}

    @staticmethod
    def _normalize_input(user_input: str | JSONDict) -> str:
        if isinstance(user_input, str):
            return user_input
        return json.dumps(user_input, indent=2, ensure_ascii=False)

    @staticmethod
    def _parse_json_arguments(raw: Any) -> JSONDict:
        if raw in (None, ""):
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            return json.loads(raw)
        raise TypeError(f"Unsupported function arguments payload: {type(raw)!r}")

    @staticmethod
    def _serialize_tool_output(value: Any) -> str:
        prepared = _truncate_for_model(value, max_chars=MAX_TOOL_OUTPUT_CHARS)
        if isinstance(prepared, str):
            return prepared
        return json.dumps(prepared, indent=2, ensure_ascii=False, default=str)

    @staticmethod
    def _response_payload(response: Any) -> JSONDict:
        if hasattr(response, "model_dump"):
            payload = response.model_dump()
            if isinstance(payload, dict):
                return payload
        if isinstance(response, dict):
            return response
        return {}

    @staticmethod
    def _extract_response_text(payload: JSONDict, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        texts: list[str] = []
        for item in payload.get("output", []) or []:
            item_type = item.get("type")
            if item_type == "message":
                for content in item.get("content", []) or []:
                    if content.get("type") in {"output_text", "text"}:
                        text = (content.get("text") or "").strip()
                        if text:
                            texts.append(text)
            elif item_type in {"output_text", "text"}:
                text = (item.get("text") or "").strip()
                if text:
                    texts.append(text)
        return "\n".join(texts).strip()

    @staticmethod
    def _extract_function_calls(payload: JSONDict) -> list[JSONDict]:
        calls: list[JSONDict] = []
        for item in payload.get("output", []) or []:
            if item.get("type") in {"function_call", "tool_call"}:
                calls.append(
                    {
                        "name": item.get("name"),
                        "arguments": item.get("arguments"),
                        "call_id": item.get("call_id") or item.get("id"),
                    }
                )
        return calls

    def _can_parallelize(self, function_calls: list[JSONDict]) -> bool:
        if len(function_calls) <= 1:
            return False
        names = [call.get("name") for call in function_calls]
        if any(name == "complete_task" for name in names):
            return False
        return all(name in PARALLEL_SAFE_TOOLS for name in names)

    def _execute_tool_call(
        self,
        call: JSONDict,
        selected_tools: Mapping[str, AgentTool],
        context: AgentRunContext,
        turn: int,
    ) -> JSONDict:
        name = call["name"]
        arguments = self._parse_json_arguments(call.get("arguments"))
        if name not in selected_tools:
            raise KeyError(f"Tool '{name}' was requested by the model but is not registered")
        try:
            result = selected_tools[name].handler(arguments, context)
        except Exception as exc:
            result = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "tool": name,
            }
        history_item = {
            "turn": turn,
            "tool": name,
            "call_id": call.get("call_id"),
            "arguments": arguments,
            "result": result,
        }
        return {
            "name": name,
            "call_id": call.get("call_id"),
            "result": result,
            "history_item": history_item,
        }

    @staticmethod
    def _build_default_client() -> ResponsesClientProtocol:
        if OpenAI is None:
            raise RuntimeError("openai package is unavailable; pass an injected client for testing")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        return OpenAI(api_key=api_key)


def render_prompt_template(template: str, context: Mapping[str, Any] | None = None) -> str:
    values = {"CurrentDate": datetime.now(timezone.utc).date().isoformat(), **dict(context or {})}

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(values.get(key, match.group(0)))

    return re.sub(r"\{\{\.([A-Za-z0-9_]+)\}\}", _replace, template)


def build_default_agent_tools(
    *,
    web_search: WebSearchTool,
    web_fetch: WebFetchTool,
    code_execution: CodeExecutionTool,
    memory_store: JsonMemoryStore,
    subagent_runner: Callable[[JSONDict, AgentRunContext], Any] | None = None,
    document_query_tool: Callable[[JSONDict, AgentRunContext], Any] | None = None,
) -> dict[str, AgentTool]:
    def _complete_task(arguments: JSONDict, _: AgentRunContext) -> Any:
        return _first_present(arguments, "payload", "result", "final_report", "findings_json", default=arguments)

    def _web_search(arguments: JSONDict, _: AgentRunContext) -> JSONDict:
        query = str(_first_present(arguments, "query", default=""))
        limit = int(_first_present(arguments, "limit", default=5))
        return web_search(query=query, limit=limit).model_dump(mode="json")

    def _web_fetch(arguments: JSONDict, _: AgentRunContext) -> JSONDict:
        url = str(_first_present(arguments, "url"))
        timeout = float(_first_present(arguments, "timeout", default=20.0))
        payload = web_fetch(url=url, timeout=timeout).model_dump(mode="json")
        return _truncate_for_model(payload, max_chars=10000)

    def _code_execution(arguments: JSONDict, _: AgentRunContext) -> JSONDict:
        python_code = str(_first_present(arguments, "python_code", "code"))
        return code_execution(python_code).model_dump(mode="json")

    def _memory_write(arguments: JSONDict, context: AgentRunContext) -> JSONDict:
        run_id = _require_run_id(context)
        key = str(_first_present(arguments, "key"))
        value = _first_present(arguments, "value", "payload")
        memory_store.write(run_id, key, value)
        return {"ok": True, "key": key, "value": value}

    def _memory_read(arguments: JSONDict, context: AgentRunContext) -> JSONDict:
        run_id = _require_run_id(context)
        key = str(_first_present(arguments, "key"))
        default = arguments.get("default")
        return {"key": key, "value": memory_store.read(run_id, key, default)}

    def _run_subagent(arguments: JSONDict, context: AgentRunContext) -> Any:
        if subagent_runner is None:
            raise RuntimeError("run_subagent tool requested but no subagent_runner was configured")
        brief = _first_present(arguments, "brief", "brief_json", "task", default=arguments)
        if isinstance(brief, str):
            brief = _coerce_subagent_brief_string(brief)
        if not isinstance(brief, dict):
            raise TypeError("run_subagent expects a JSON object brief")
        return subagent_runner(brief, context)

    def _document_query(arguments: JSONDict, context: AgentRunContext) -> Any:
        if document_query_tool is None:
            raise RuntimeError("document_query tool requested but no document_query_tool was configured")
        return document_query_tool(arguments, context)

    def _coerce_subagent_brief_string(raw: str) -> JSONDict:
        text = (raw or '').strip()
        if not text:
            raise TypeError("run_subagent string brief was empty")
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            candidate = match.group(0)
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                try:
                    parsed = ast.literal_eval(candidate)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass
        raise TypeError("run_subagent string brief was not valid JSON")

    any_schema = {}
    tools = {
        "complete_task": AgentTool(
            name="complete_task",
            description="Return the final payload and terminate the agent loop.",
            parameters={"type": "object", "properties": {"payload": any_schema}},
            handler=_complete_task,
        ),
        "web_search": AgentTool(
            name="web_search",
            description="Search the web for relevant sources.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
            handler=_web_search,
        ),
        "web_fetch": AgentTool(
            name="web_fetch",
            description="Fetch the full content of a URL.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "timeout": {"type": "number", "minimum": 1},
                },
                "required": ["url"],
            },
            handler=_web_fetch,
        ),
        "code_execution": AgentTool(
            name="code_execution",
            description="Execute Python code and return stdout, stderr, RESULT, and locals.",
            parameters={
                "type": "object",
                "properties": {
                    "python_code": {"type": "string"},
                },
                "required": ["python_code"],
            },
            handler=_code_execution,
        ),
        "memory_write": AgentTool(
            name="memory_write",
            description="Persist a key/value pair into the external memory store for the current run.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": any_schema,
                },
                "required": ["key", "value"],
            },
            handler=_memory_write,
        ),
        "memory_read": AgentTool(
            name="memory_read",
            description="Read a value from the external memory store for the current run.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "default": any_schema,
                },
                "required": ["key"],
            },
            handler=_memory_read,
        ),
        "run_subagent": AgentTool(
            name="run_subagent",
            description="Execute a delegated subagent task and return its structured result.",
            parameters={
                "type": "object",
                "properties": {
                    "brief": SubagentBrief.model_json_schema(),
                },
                "required": ["brief"],
                "additionalProperties": False,
            },
            handler=_run_subagent,
        ),
    }
    if document_query_tool is not None:
        tools["document_query"] = AgentTool(
            name="document_query",
            description="Analyze one or more primary documents using OpenAI Responses API native PDF input or hosted file search.",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "document_urls": {"type": "array", "items": {"type": "string"}},
                    "document_paths": {"type": "array", "items": {"type": "string"}},
                    "mode": {"type": "string", "enum": ["auto", "direct_pdf", "file_search"]},
                    "task_type": {"type": "string", "enum": ["summarize", "extract", "critique", "qa", "search"]},
                    "max_num_results": {"type": "integer", "minimum": 1, "maximum": 20},
                    "debug": {"type": "boolean"},
                },
                "required": ["question"],
            },
            handler=_document_query,
        )
    return tools


def build_default_prompt_executor(
    *,
    memory_store: JsonMemoryStore,
    web_search: WebSearchTool,
    web_fetch: WebFetchTool,
    code_execution: CodeExecutionTool | None = None,
    subagent_runner: Callable[[JSONDict, AgentRunContext], Any] | None = None,
    client: ResponsesClientProtocol | None = None,
    default_model: str = "gpt-5.4",
    max_turns: int = 20,
    max_output_tokens: int = 100000,
    document_query_tool: Callable[[JSONDict, AgentRunContext], Any] | None = None,
) -> ResponsesAgentLoop:
    return ResponsesAgentLoop(
        client=client,
        tools=build_default_agent_tools(
            web_search=web_search,
            web_fetch=web_fetch,
            code_execution=code_execution or CodeExecutionTool(),
            memory_store=memory_store,
            subagent_runner=subagent_runner,
            document_query_tool=document_query_tool,
        ),
        default_model=default_model,
        max_turns=max_turns,
        max_output_tokens=max_output_tokens,
    )


def _first_present(arguments: JSONDict, *keys: str, default: Any = ... ) -> Any:
    for key in keys:
        if key in arguments:
            return arguments[key]
    if default is not ...:
        return default
    raise KeyError(f"Missing required argument; expected one of: {', '.join(keys)}")


def _require_run_id(context: AgentRunContext) -> str:
    if context.run_id:
        return context.run_id
    raise RuntimeError("This tool requires run_id in the agent context")


def _truncate_for_model(value: Any, *, max_chars: int) -> Any:
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        head = max_chars - 64 if max_chars > 80 else max_chars
        omitted = len(value) - head
        return value[:head] + f"\n[TRUNCATED {omitted} chars]"
    if isinstance(value, dict):
        return {str(k): _truncate_for_model(v, max_chars=max_chars) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate_for_model(v, max_chars=max_chars) for v in value]
    return value


def _tool_counts(tool_history: list[JSONDict]) -> JSONDict:
    counts: dict[str, int] = {}
    for item in tool_history:
        name = str(item.get('tool'))
        counts[name] = counts.get(name, 0) + 1
    return counts
