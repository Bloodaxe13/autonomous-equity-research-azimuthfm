from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.contracts_runtime import FinalReport, ReportSections, ReportTier
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
    assert packet.report.header_block.current_price_aud > 0
    assert packet.report.header_block.price_target_aud == packet.report.price_target_aud
    assert packet.report.header_block.implied_return_pct == packet.report.implied_return_pct
    assert packet.report.header_block.report_type == ReportTier.INITIATION
    assert list(packet.report.sections.model_dump().keys()) == [
        "investment_thesis",
        "business_description",
        "industry_competitive",
        "financial_analysis",
        "forecasts",
        "valuation",
        "catalysts",
        "risks",
        "esg_governance",
        "appendix",
    ]
    assert "Sources reviewed" in packet.report.sections.appendix
    assert "Items not found" in packet.report.sections.appendix
    assert "Computation notes" in packet.report.sections.appendix
    assert packet.red_team.verdict.value in {"weak_counter_case", "covered_ground"}
    assert len(packet.subagent_findings) == 5
    assert len(packet.citation.source_list) >= 4
    assert "## Section 0 — Header Block" in packet.citation.annotated_report
    assert "## Section 10 — Appendix" in packet.citation.annotated_report
    assert "## Sources" in packet.citation.annotated_report
    assert "## Computation log" in packet.citation.annotated_report

    run_dir = tmp_path / "runs" / "cuv-test-run"
    assert (run_dir / "report_packet.json").exists()
    payload = json.loads((run_dir / "report_packet.json").read_text(encoding="utf-8"))
    assert payload["report"]["ticker"] == "CUV"
    assert payload["report"]["header_block"]["current_price_aud"] > 0
    assert payload["report"]["header_block"]["price_target_aud"] == payload["report"]["price_target_aud"]
    assert payload["report"]["sections"]["appendix"].count("Sources reviewed") == 1
    memory_path = tmp_path / "memory" / "cuv-test-run" / "memory.json"
    assert memory_path.exists()
    memory_payload = json.loads(memory_path.read_text(encoding="utf-8"))
    assert [entry["stage"] for entry in memory_payload["checkpoints"]] == [
        "after_findings_wave_1",
        "before_red_team",
        "finalized",
    ]
    assert (tmp_path / "trace.jsonl").exists()


def test_final_report_contract_rejects_inconsistent_header(tmp_path: Path):
    orchestrator = build_cuv_orchestrator(tmp_path)
    report = orchestrator.run(build_default_cuv_task("contract-test-run")).report.model_dump(mode="json")
    report["header_block"]["price_target_aud"] = report["price_target_aud"] + 1
    with pytest.raises(ValidationError):
        FinalReport.model_validate(report)


def test_report_sections_require_appendix_subsections():
    with pytest.raises(ValidationError):
        ReportSections(
            investment_thesis="a",
            business_description="b",
            industry_competitive="c",
            financial_analysis="d",
            forecasts="e",
            valuation="f",
            catalysts="g",
            risks="h",
            esg_governance="i",
            appendix="Appendix without required labels",
        )
