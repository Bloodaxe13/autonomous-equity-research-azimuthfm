from __future__ import annotations

from pathlib import Path

from src.agents.runtime_agents import CitationRunner, LeadAnalystRunner, RedTeamRunner, SubagentDispatcher, TemplateSubagentRunner
from src.memory.json_store_runtime import JsonMemoryStore
from src.orchestration_runtime import AzimuthOrchestrator, build_default_cuv_task
from src.tools.code_execution_runtime import CodeExecutionTool
from src.tools.runtime_web import StaticFetchAdapter, StaticSearchAdapter, WebFetchTool, WebSearchTool
from src.tracing.jsonl_runtime_logger import JsonlTraceLogger


def _fixture_search_data() -> dict[str, list[dict]]:
    return {
        "CUV business_model": [
            {"title": "Clinuvel annual report", "url": "https://example.test/cuv/annual-report", "snippet": "SCENESSE and EPP overview"},
        ],
        "CUV historical_financials": [
            {"title": "Clinuvel FY24 results", "url": "https://example.test/cuv/fy24-results", "snippet": "Revenue and cash position"},
        ],
        "CUV news_catalysts": [
            {"title": "Clinuvel ASX update", "url": "https://example.test/cuv/asx-update", "snippet": "Pipeline and rollout milestones"},
        ],
        "CUV industry_competitive": [
            {"title": "Clinuvel investor deck", "url": "https://example.test/cuv/investor-deck", "snippet": "Competitive positioning"},
        ],
        "CUV peers_ownership": [
            {"title": "Clinuvel governance summary", "url": "https://example.test/cuv/governance", "snippet": "Ownership and governance"},
        ],
    }


def _fixture_fetch_data() -> dict[str, dict]:
    return {
        "https://example.test/cuv/annual-report": {"status_code": 200, "content_type": "text/html", "text": "Annual report content"},
        "https://example.test/cuv/fy24-results": {"status_code": 200, "content_type": "text/html", "text": "FY24 results content"},
        "https://example.test/cuv/asx-update": {"status_code": 200, "content_type": "text/html", "text": "ASX update content"},
        "https://example.test/cuv/investor-deck": {"status_code": 200, "content_type": "text/html", "text": "Investor deck content"},
        "https://example.test/cuv/governance": {"status_code": 200, "content_type": "text/html", "text": "Governance content"},
    }


def _canned_findings() -> dict[str, list[dict]]:
    retrieval_date = "2026-04-20"
    return {
        "business_model": [
            {
                "claim": "CUV commercialises SCENESSE for erythropoietic protoporphyria (EPP).",
                "data": "Lead commercial product for rare phototoxic disorder patients.",
                "source_url": "https://example.test/cuv/annual-report",
                "source_tier": 1,
                "source_title": "Clinuvel annual report",
                "source_date": "2024-08-30",
                "retrieval_date": retrieval_date,
                "confidence": "high",
                "notes": "Stubbed from fixture annual report.",
            }
        ],
        "historical_financials": [
            {
                "claim": "FY24 revenue",
                "data": "AUD 74.6m",
                "source_url": "https://example.test/cuv/fy24-results",
                "source_tier": 1,
                "source_title": "Clinuvel FY24 results",
                "source_date": "2024-08-30",
                "retrieval_date": retrieval_date,
                "confidence": "high",
                "notes": "Illustrative fixture datapoint for MVP runtime validation.",
            },
            {
                "claim": "Net cash position remained positive",
                "data": "AUD 160m+ cash and no financial debt",
                "source_url": "https://example.test/cuv/fy24-results",
                "source_tier": 1,
                "source_title": "Clinuvel FY24 results",
                "source_date": "2024-08-30",
                "retrieval_date": retrieval_date,
                "confidence": "medium",
                "notes": "Illustrative fixture datapoint.",
            }
        ],
        "news_catalysts": [
            {
                "claim": "Recent catalyst",
                "data": "Progress on label expansion and new product initiatives can alter medium-term growth expectations.",
                "source_url": "https://example.test/cuv/asx-update",
                "source_tier": 1,
                "source_title": "Clinuvel ASX update",
                "source_date": "2026-03-14",
                "retrieval_date": retrieval_date,
                "confidence": "medium",
                "notes": "Catalyst framing for MVP test packet.",
            }
        ],
        "industry_competitive": [
            {
                "claim": "Competitive position",
                "data": "CUV operates in a rare-disease niche with specialist prescriber concentration and regulatory barriers.",
                "source_url": "https://example.test/cuv/investor-deck",
                "source_tier": 1,
                "source_title": "Clinuvel investor deck",
                "source_date": "2025-11-01",
                "retrieval_date": retrieval_date,
                "confidence": "medium",
                "notes": "Investor-material based summary.",
            }
        ],
        "peers_ownership": [
            {
                "claim": "Peer context",
                "data": "Peer framing should focus on niche specialty-pharma and rare-disease commercial models rather than broad biotech screens.",
                "source_url": "https://example.test/cuv/governance",
                "source_tier": 2,
                "source_title": "Clinuvel governance summary",
                "source_date": "2025-10-01",
                "retrieval_date": retrieval_date,
                "confidence": "medium",
                "notes": "Governance and ownership context placeholder.",
            }
        ],
    }


def build_cuv_orchestrator(artifact_root: str | Path) -> AzimuthOrchestrator:
    artifact_root = Path(artifact_root)
    memory_store = JsonMemoryStore(artifact_root / "memory")
    tracer = JsonlTraceLogger(artifact_root / "trace.jsonl")
    search_tool = WebSearchTool(StaticSearchAdapter(_fixture_search_data()))
    fetch_tool = WebFetchTool(StaticFetchAdapter(_fixture_fetch_data()))
    dispatcher = SubagentDispatcher(TemplateSubagentRunner(search_tool, fetch_tool, _canned_findings()))
    lead = LeadAnalystRunner(CodeExecutionTool())
    return AzimuthOrchestrator(
        memory_store=memory_store,
        tracer=tracer,
        dispatcher=dispatcher,
        lead=lead,
        red_team=RedTeamRunner(),
        citation=CitationRunner(),
        artifact_root=artifact_root / "runs",
    )


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    orchestrator = build_cuv_orchestrator(repo_root / "artifacts_runtime")
    packet = orchestrator.run(build_default_cuv_task())
    print(packet.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
