from pathlib import Path

from src.memory.json_store_runtime import JsonMemoryStore
from src.responses_agent_runtime import _truncate_for_model, build_default_agent_tools
from src.tools.code_execution_runtime import CodeExecutionTool
from src.tools.runtime_web import StaticFetchAdapter, StaticSearchAdapter, WebFetchTool, WebSearchTool


def test_truncate_for_model_limits_large_strings():
    value = {"text": "x" * 50000}
    truncated = _truncate_for_model(value, max_chars=1000)
    assert len(truncated["text"]) < 1100
    assert "[TRUNCATED" in truncated["text"]


def test_web_fetch_tool_output_is_truncated_before_return(tmp_path: Path):
    tools = build_default_agent_tools(
        web_search=WebSearchTool(StaticSearchAdapter({})),
        web_fetch=WebFetchTool(StaticFetchAdapter({
            'https://example.test/long': {
                'status_code': 200,
                'content_type': 'text/html',
                'text': 'y' * 50000,
            }
        })),
        code_execution=CodeExecutionTool(),
        memory_store=JsonMemoryStore(tmp_path / 'memory'),
    )
    result = tools['web_fetch'].handler({'url': 'https://example.test/long'}, None)  # type: ignore[arg-type]
    assert len(result['text']) < 11000
    assert '[TRUNCATED' in result['text']
