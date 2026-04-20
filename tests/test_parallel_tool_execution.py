from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from src.memory.json_store_runtime import JsonMemoryStore
from src.responses_agent_runtime import AgentTool, ResponsesAgentLoop
from tests.test_responses_agent_runtime import FakeClient, FakeResponse


def test_parallel_safe_tool_calls_execute_in_same_turn(tmp_path: Path):
    prompt_file = tmp_path / 'agent.md'
    prompt_file.write_text('Parallel tool test', encoding='utf-8')
    events: list[tuple[str, float]] = []

    def sleeper(name: str):
        def _run(arguments, context):
            events.append((f'start-{name}', time.monotonic()))
            time.sleep(0.2)
            events.append((f'end-{name}', time.monotonic()))
            return {"name": name}
        return _run

    tools = {
        'web_search': AgentTool('web_search', 'search', {"type": "object", "properties": {}}, sleeper('a')),
        'web_fetch': AgentTool('web_fetch', 'fetch', {"type": "object", "properties": {}}, sleeper('b')),
        'complete_task': AgentTool('complete_task', 'complete', {"type": "object", "properties": {"payload": {}}}, lambda args, ctx: args.get('payload')),
    }
    client = FakeClient([
        FakeResponse({
            'id': 'resp1',
            'output': [
                {'type': 'function_call', 'name': 'web_search', 'call_id': 'c1', 'arguments': '{}'},
                {'type': 'function_call', 'name': 'web_fetch', 'call_id': 'c2', 'arguments': '{}'},
            ],
        }),
        FakeResponse({
            'id': 'resp2',
            'output': [
                {'type': 'function_call', 'name': 'complete_task', 'call_id': 'c3', 'arguments': json.dumps({'payload': {'ok': True}})},
            ],
        }),
    ])
    loop = ResponsesAgentLoop(client=client, tools=tools, default_model='gpt-5.4-mini')
    start = time.monotonic()
    result = loop.run_prompt_file(prompt_file, user_input='go', run_id='run-1', tool_names=['web_search', 'web_fetch', 'complete_task'])
    elapsed = time.monotonic() - start
    assert result.final_output == {'ok': True}
    assert elapsed < 0.35, elapsed
