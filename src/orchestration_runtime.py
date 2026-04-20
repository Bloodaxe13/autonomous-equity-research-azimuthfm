from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agents.runtime_agents import CitationRunner, LeadAnalystRunner, RedTeamRunner, SubagentDispatcher
from src.contracts_runtime import ReportPacket, ReportTier, TaskInput
from src.memory.json_store_runtime import JsonMemoryStore
from src.tracing.jsonl_runtime_logger import JsonlTraceLogger


class AzimuthOrchestrator:
    def __init__(
        self,
        *,
        memory_store: JsonMemoryStore,
        tracer: JsonlTraceLogger,
        dispatcher: SubagentDispatcher,
        lead: LeadAnalystRunner,
        red_team: RedTeamRunner,
        citation: CitationRunner,
        artifact_root: str | Path,
    ):
        self.memory_store = memory_store
        self.tracer = tracer
        self.dispatcher = dispatcher
        self.lead = lead
        self.red_team = red_team
        self.citation = citation
        self.artifact_root = Path(artifact_root)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def run(self, task: TaskInput) -> ReportPacket:
        run_dir = self.artifact_root / task.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self.tracer.log("run_started", run_id=task.run_id, ticker=task.ticker, tier=task.tier.value)
        plan = self.lead.build_plan(task)
        self.memory_store.write(task.run_id, "plan", plan)
        self.tracer.log("plan_saved", run_id=task.run_id, plan=plan)

        briefs = self.lead.build_briefs(task, plan)
        self.memory_store.write(task.run_id, "subagent_briefs", [brief.model_dump(mode="json") for brief in briefs])
        self.tracer.log("subagent_dispatch", run_id=task.run_id, count=len(briefs), facets=[brief.facet for brief in briefs])

        findings = self.dispatcher.dispatch_many(briefs)
        self.memory_store.write(task.run_id, "findings_wave_1", [packet.model_dump(mode="json") for packet in findings])
        self.memory_store.write(task.run_id, "findings_index", [item.model_dump(mode="json") for packet in findings for item in packet.findings])
        self.memory_store.append_event(task.run_id, "checkpoints", {"stage": "after_findings_wave_1", "packets": len(findings)})
        self.tracer.log("subagent_completed", run_id=task.run_id, packets=len(findings))

        report = self.lead.synthesize(task, findings)
        self.memory_store.write(task.run_id, "computation_log", report.computation_log)
        self.memory_store.write(task.run_id, "draft_report", report.model_dump(mode="json"))
        self.memory_store.append_event(task.run_id, "checkpoints", {"stage": "before_red_team", "rating": report.rating, "price_target_aud": report.price_target_aud})
        self.tracer.log("report_synthesized", run_id=task.run_id, rating=report.rating, price_target=report.price_target_aud)

        red_team = self.red_team.review(report)
        self.memory_store.write(task.run_id, "red_team", red_team.model_dump(mode="json"))
        self.tracer.log("red_team_completed", run_id=task.run_id, verdict=red_team.verdict.value)

        citation = self.citation.annotate(report, findings)
        self.memory_store.write(task.run_id, "citation", citation.model_dump(mode="json"))
        self.memory_store.append_event(task.run_id, "checkpoints", {"stage": "finalized", "sources": len(citation.source_list)})
        self.tracer.log("citation_completed", run_id=task.run_id, sources=len(citation.source_list))

        packet = ReportPacket(
            task=task,
            plan=plan,
            subagent_briefs=briefs,
            subagent_findings=findings,
            report=report,
            red_team=red_team,
            citation=citation,
            artifacts={},
        )
        artifacts = {
            "request": str((run_dir / "request.json").relative_to(self.artifact_root)),
            "report_packet": str((run_dir / "report_packet.json").relative_to(self.artifact_root)),
            "annotated_report": str((run_dir / "annotated_report.md").relative_to(self.artifact_root)),
            "memory": str((Path(task.run_id) / "memory.json")),
            "trace": str(Path("trace.jsonl")),
        }
        packet.artifacts = artifacts
        (run_dir / "request.json").write_text(json.dumps(task.model_dump(mode="json"), indent=2), encoding="utf-8")
        (run_dir / "report_packet.json").write_text(json.dumps(packet.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "annotated_report.md").write_text(packet.citation.annotated_report, encoding="utf-8")
        self.tracer.log("run_completed", run_id=task.run_id, artifact_dir=str(run_dir), completed_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
        return packet


def build_default_cuv_task(run_id: str = "cuv-mvp") -> TaskInput:
    return TaskInput(
        ticker="CUV",
        tier=ReportTier.INITIATION,
        run_id=run_id,
        triggering_event="targeted CUV MVP runtime verification",
    )
