from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, Protocol

from src.contracts_runtime import (
    ChallengeItem,
    CitationOutput,
    CitationSource,
    FinalReport,
    FindingItem,
    HeaderBlock,
    RedTeamVerdict,
    RedTeamVerdictType,
    ReportPacket,
    SubagentBrief,
    SubagentFindings,
    TaskInput,
)
from src.tools.code_execution_runtime import CodeExecutionTool
from src.tools.runtime_web import WebFetchTool, WebSearchTool


class ResearchSubagentProtocol(Protocol):
    def run(self, brief: SubagentBrief) -> SubagentFindings: ...


@dataclass
class TemplateSubagentRunner:
    web_search: WebSearchTool
    web_fetch: WebFetchTool
    canned_findings: dict[str, list[dict]]

    def run(self, brief: SubagentBrief) -> SubagentFindings:
        results = self.web_search(f"{brief.ticker} {brief.facet}")
        tool_calls = 1
        findings: list[FindingItem] = []
        for item in self.canned_findings.get(brief.facet, []):
            source_url = item["source_url"]
            if any(result.url == source_url for result in results.results):
                self.web_fetch(source_url)
                tool_calls += 1
            findings.append(FindingItem.model_validate(item))
        found_claim_labels = {finding.claim for finding in findings}
        not_found = [field for field in brief.required_fields if field not in found_claim_labels]
        summary = "; ".join(finding.claim for finding in findings[:3]) or f"No findings captured for {brief.facet}."
        return SubagentFindings(
            facet=brief.facet,
            ticker=brief.ticker,
            tool_calls_used=tool_calls,
            findings=findings,
            not_found=not_found,
            summary=summary,
        )


@dataclass
class SubagentDispatcher:
    runner: ResearchSubagentProtocol

    def dispatch(self, brief: SubagentBrief) -> SubagentFindings:
        return self.runner.run(brief)

    def dispatch_many(self, briefs: Iterable[SubagentBrief]) -> list[SubagentFindings]:
        return [self.dispatch(brief) for brief in briefs]


@dataclass
class LeadAnalystRunner:
    code_execution: CodeExecutionTool

    def build_plan(self, task: TaskInput) -> dict:
        facets = [
            "business_model",
            "historical_financials",
            "news_catalysts",
            "industry_competitive",
            "peers_ownership",
        ]
        return {
            "ticker": task.ticker,
            "tier": task.tier.value,
            "complexity": "high" if task.tier.value == "initiation" else "medium",
            "facets": facets,
            "notes": "CUV-only MVP plan using deterministic subagent stubs and code execution.",
        }

    def build_briefs(self, task: TaskInput, plan: dict) -> list[SubagentBrief]:
        defaults = {
            "business_model": "Describe CUV's drug/device model and commercial focus.",
            "historical_financials": "Capture key historical revenue, cash, and profitability datapoints.",
            "news_catalysts": "Identify recent clinical/commercial catalysts and notable announcements.",
            "industry_competitive": "Summarise treatment landscape and competitive positioning.",
            "peers_ownership": "List peer context and major ownership/governance datapoints.",
        }
        required_map = {
            "business_model": ["CUV commercialises SCENESSE for erythropoietic protoporphyria (EPP)."],
            "historical_financials": ["FY24 revenue"],
            "news_catalysts": ["Recent catalyst"],
            "industry_competitive": ["Competitive position"],
            "peers_ownership": ["Peer context"],
        }
        return [
            SubagentBrief(
                facet=facet,
                ticker=task.ticker,
                objective=defaults[facet],
                required_fields=required_map[facet],
                source_guidance="Prefer company filings, investor presentations, and ASX announcements.",
                task_boundaries="Return findings only; do not draft prose sections or valuation opinions.",
                research_budget_hint=8,
                time_bounds="5 years historical where relevant",
            )
            for facet in plan["facets"]
        ]

    def synthesize(self, task: TaskInput, findings: list[SubagentFindings]) -> FinalReport:
        flat_findings = [item for packet in findings for item in packet.findings]
        calc = self.code_execution(
            """
price = 12.53
base_target = 14.80
upside = round((base_target / price - 1) * 100, 2)
RESULT = {
    'last_close_aud': price,
    'price_target_aud': base_target,
    'implied_return_pct': upside,
    'market_cap_aud_m': 756.2,
}
"""
        )
        if not calc.ok:
            raise RuntimeError(calc.stderr)
        metrics = calc.result
        sections = self._build_sections(findings)
        rating = "Buy" if metrics["implied_return_pct"] >= 15 else "Hold"
        header = HeaderBlock(
            ticker=task.ticker,
            company_name="Clinuvel Pharmaceuticals",
            rating=rating,
            price_target_aud=metrics["price_target_aud"],
            implied_return_pct=metrics["implied_return_pct"],
            last_close_aud=metrics["last_close_aud"],
            market_cap_aud_m=metrics["market_cap_aud_m"],
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        )
        findings_index = [
            {
                "facet": packet.facet,
                "claim": item.claim,
                "source_url": item.source_url,
                "source_title": item.source_title,
            }
            for packet in findings
            for item in packet.findings
        ]
        return FinalReport(
            ticker=task.ticker,
            tier=task.tier,
            generated_at=header.generated_at,
            header_block=header,
            sections=sections,
            computation_log=[
                {
                    "n": 1,
                    "what": "Illustrative MVP price target and upside",
                    "formula": "target_upside = (target_price / spot_price - 1) * 100",
                    "inputs": {"spot_price": metrics["last_close_aud"], "target_price": metrics["price_target_aud"]},
                    "output": metrics,
                }
            ],
            findings_index=findings_index,
            rating=rating,
            price_target_aud=metrics["price_target_aud"],
            implied_return_pct=metrics["implied_return_pct"],
        )

    def _build_sections(self, findings: list[SubagentFindings]) -> dict[str, str]:
        by_facet = {packet.facet: packet for packet in findings}
        thesis = (
            "CUV appears positioned for continued specialty-pharma execution, with SCENESSE anchoring current economics and pipeline/regulatory expansion driving optionality. "
            "The MVP view remains preliminary and should be upgraded to live-web evidence before investment use."
        )
        return OrderedDict(
            investment_thesis=thesis,
            business_description=self._markdown_from_packet(by_facet.get("business_model"), "Business description"),
            industry_competitive=self._markdown_from_packet(by_facet.get("industry_competitive"), "Industry and competitive position"),
            financial_analysis=self._markdown_from_packet(by_facet.get("historical_financials"), "Financial analysis"),
            forecasts="Forecast framework pending live-model integration; current MVP uses deterministic placeholders for CUV-only testing.",
            valuation="Valuation currently uses deterministic code_execution inputs to prove orchestration wiring, not a full live DCF/comps stack.",
            catalysts=self._markdown_from_packet(by_facet.get("news_catalysts"), "Catalysts"),
            risks="Key risks include concentration in a lead product, regulatory delays, reimbursement constraints, and pipeline execution uncertainty.",
            esg_governance=self._markdown_from_packet(by_facet.get("peers_ownership"), "ESG and governance"),
            appendix="MVP appendix: findings were assembled from stubbed search/fetch wrappers scoped to CUV test fixtures.",
        )

    @staticmethod
    def _markdown_from_packet(packet: SubagentFindings | None, heading: str) -> str:
        if packet is None or not packet.findings:
            return f"{heading}: no findings available."
        bullets = [f"- {item.claim}: {item.data}" for item in packet.findings]
        return "\n".join([f"{heading}:", *bullets])


class RedTeamRunner:
    def review(self, report: FinalReport) -> RedTeamVerdict:
        upside = report.implied_return_pct
        if upside >= 15:
            verdict = RedTeamVerdictType.WEAK_COUNTER_CASE
            counter_rating = "Hold"
            counter_thesis = "The upside case may depend too heavily on successful expansion beyond the current SCENESSE base, so execution slippage could compress the premium."
        else:
            verdict = RedTeamVerdictType.COVERED_GROUND
            counter_rating = report.rating
            counter_thesis = "The report already reflects a balanced stance relative to current evidence."
        return RedTeamVerdict(
            ticker=report.ticker,
            report_rating=report.rating,
            red_team_counter_rating=counter_rating,
            verdict=verdict,
            counter_thesis=counter_thesis,
            three_strongest_challenges=[
                ChallengeItem(
                    challenge="Forecast confidence is limited in MVP mode.",
                    evidence_or_logic="The current runtime uses deterministic placeholder valuation inputs instead of a live full-stack model.",
                    where_report_fails="Forecasts / Valuation",
                    severity="material",
                )
            ],
            missed_risks=["Limited live-web validation in offline MVP mode."],
            disagreements_with_calculations=[{"what": "Price target calibration", "why": "Illustrative rather than derived from a complete DCF/comps workbook."}],
            verdict_reasoning="The runtime proves orchestration and packet assembly, but valuation depth remains below production standard.",
        )


class CitationRunner:
    def annotate(self, report: FinalReport, findings: list[SubagentFindings]) -> CitationOutput:
        sources: list[CitationSource] = []
        source_index: dict[str, int] = {}
        claim_map: dict[str, list[str]] = {}
        for packet in findings:
            for finding in packet.findings:
                if finding.source_url not in source_index:
                    source_index[finding.source_url] = len(source_index) + 1
                    sources.append(
                        CitationSource(
                            n=source_index[finding.source_url],
                            title=finding.source_title,
                            url=finding.source_url,
                            retrieval_date=finding.retrieval_date,
                            source_tier=finding.source_tier,
                            claim_refs=[],
                        )
                    )
                claim_map.setdefault(finding.source_url, []).append(finding.claim[:80])
        for source in sources:
            source.claim_refs = claim_map.get(source.url, [])

        lines = [f"# {report.ticker} report", ""]
        for section_name, content in report.sections.items():
            lines.append(f"## {section_name}")
            lines.append(content)
            lines.append("")
        lines.append("## Sources")
        for source in sources:
            lines.append(f"[^${source.n}]: {source.title} ({source.url})")
        return CitationOutput(
            annotated_report="\n".join(lines),
            source_list=sources,
            computation_log=report.computation_log,
            unsourced_claims=[],
        )
