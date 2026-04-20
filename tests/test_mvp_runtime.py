from __future__ import annotations

import json
from pathlib import Path

from src.contracts_runtime import ReportTier
from src.cuv_runtime_entrypoint import build_cuv_orchestrator
from src.memory.json_store_runtime import JsonMemoryStore
from src.orchestration_runtime import build_default_cuv_task
from src.tools.code_execution_runtime import CodeExecutionTool


def test_json_memory_store_persists_and_reads(tmp_path: Path):
    store = JsonMemoryStore(tmp_path)
    assert store.write("run-1", "plan", {"ticker": "CUV"}) is True
    store.append_event("run-1", "waves", {"n": 1})
    assert store.read("run-1", "plan") == {"ticker": "CUV"}
    assert store.read("run-1", "waves") == [{"n": 1}]


def test_code_execution_tool_returns_result():
    tool = CodeExecutionTool()
    result = tool("""
a = 12.53
b = 14.80
RESULT = round((b / a - 1) * 100, 2)
print(RESULT)
""")
    assert result.ok is True
    assert result.result == 18.12
    assert "18.12" in result.stdout


def test_cuv_orchestrator_produces_report_packet(tmp_path: Path):
    orchestrator = build_cuv_orchestrator(tmp_path)
    task = build_default_cuv_task("cuv-test-run")
    packet = orchestrator.run(task)

    assert packet.task.ticker == "CUV"
    assert packet.task.tier == ReportTier.INITIATION
    assert packet.report.header_block.rating in {"Buy", "Hold"}
    assert packet.red_team.verdict.value in {"weak_counter_case", "covered_ground"}
    assert len(packet.subagent_findings) == 5
    assert len(packet.citation.source_list) >= 4

    run_dir = tmp_path / "runs" / "cuv-test-run"
    assert (run_dir / "report_packet.json").exists()
    payload = json.loads((run_dir / "report_packet.json").read_text(encoding="utf-8"))
    assert payload["report"]["ticker"] == "CUV"
    assert (tmp_path / "memory" / "cuv-test-run" / "memory.json").exists()
    assert (tmp_path / "trace.jsonl").exists()
