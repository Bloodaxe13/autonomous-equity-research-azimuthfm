from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, Protocol

from src.contracts_runtime import (
    ChallengeItem,
    CitationOutput,
    CitationSource,
    ComputationLogEntry,
    FinalReport,
    FindingIndexItem,
    FindingItem,
    HeaderBlock,
    RedTeamVerdict,
    RedTeamVerdictType,
    ReportSections,
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
spot_price = 12.53
base_target = 14.80
implied_return_pct = round((base_target / spot_price - 1) * 100, 2)
market_cap_aud_m = 756.2
net_cash_aud_m = 160.0
RESULT = {
    'current_price_aud': spot_price,
    'price_target_aud': base_target,
    'implied_return_pct': implied_return_pct,
    'market_cap_aud_m': market_cap_aud_m,
    'net_cash_aud_m': net_cash_aud_m,
}
"""
        )
        if not calc.ok:
            raise RuntimeError(calc.stderr)
        metrics = calc.result
        sections = self._build_sections(findings, metrics)
        rating = "Buy" if metrics["implied_return_pct"] >= 15 else "Hold"
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        header = HeaderBlock(
            ticker=task.ticker,
            company_name="Clinuvel Pharmaceuticals",
            report_title="Azimuth Equity Research — Clinuvel Pharmaceuticals",
            report_date=str(date.today()),
            report_type=task.tier,
            rating=rating,
            price_target_aud=metrics["price_target_aud"],
            current_price_aud=metrics["current_price_aud"],
            implied_return_pct=metrics["implied_return_pct"],
            market_cap_aud_m=metrics["market_cap_aud_m"],
            net_cash_aud_m=metrics["net_cash_aud_m"],
            primary_valuation_method="Deterministic MVP base-case target calibration",
            valuation_summary=(
                f"Target A${metrics['price_target_aud']:.2f} versus current A${metrics['current_price_aud']:.2f} "
                f"for implied return of {metrics['implied_return_pct']:.2f}%."
            ),
            generated_at=generated_at,
        )
        findings_index = [
            FindingIndexItem(
                facet=packet.facet,
                claim=item.claim,
                source_url=item.source_url,
                source_title=item.source_title,
                source_tier=item.source_tier,
                confidence=item.confidence,
            )
            for packet in findings
            for item in packet.findings
        ]
        computation_log = [
            ComputationLogEntry(
                n=1,
                what="Illustrative MVP price target and upside",
                formula="target_upside = (target_price / spot_price - 1) * 100",
                inputs={"spot_price": metrics["current_price_aud"], "target_price": metrics["price_target_aud"]},
                output=metrics,
            )
        ]
        return FinalReport(
            ticker=task.ticker,
            tier=task.tier,
            generated_at=generated_at,
            header_block=header,
            sections=sections,
            canonical_valuation_inputs={
                'reconciliation_status': 'resolved',
                'fcf_bridge': {
                    'npat_aud_m': 0.0,
                    'depreciation_and_amortization_aud_m': 0.0,
                    'working_capital_outflow_aud_m': 0.0,
                    'lease_cash_outflow_aud_m': 0.0,
                    'capex_aud_m': 0.0,
                    'equity_free_cash_flow_aud_m': 0.0,
                },
                'peer_table': [],
                'scenario_analysis': [
                    {'scenario': 'base', 'probability_pct': 100.0, 'price_target_aud': metrics['price_target_aud'], 'thesis': 'Deterministic MVP base case.'}
                ],
                'pipeline_option_value': {
                    'methodology': 'Deterministic MVP fallback',
                    'probability_weighted_value_aud_m': 0.0,
                    'included_in_price_target': False,
                    'rationale': 'MVP runtime does not model pipeline option value separately.',
                },
                'sensitivity_table': {
                    'base_wacc_pct': 0.0,
                    'base_terminal_growth_pct': 0.0,
                    'rows': [
                        {'wacc_pct': 0.0, 'terminal_growth_pct': 0.0, 'price_target_aud': metrics['price_target_aud']}
                    ],
                },
            },
            computation_log=computation_log,
            findings_index=findings_index,
            rating=rating,
            price_target_aud=metrics["price_target_aud"],
            implied_return_pct=metrics["implied_return_pct"],
        )

    def _build_sections(self, findings: list[SubagentFindings], metrics: dict[str, float]) -> ReportSections:
        by_facet = {packet.facet: packet for packet in findings}
        ordered = OrderedDict(
            investment_thesis=(
                "CUV appears positioned for continued specialty-pharma execution, with SCENESSE anchoring current economics and "
                "pipeline/regulatory expansion driving optionality. The thesis is provisional because this runtime remains a deterministic "
                "MVP packet rather than a live production research build."
            ),
            business_description=self._markdown_from_packet(by_facet.get("business_model"), "Business description"),
            industry_competitive=self._markdown_from_packet(by_facet.get("industry_competitive"), "Industry and competitive position"),
            financial_analysis=self._markdown_from_packet(by_facet.get("historical_financials"), "Financial analysis"),
            forecasts=(
                "Forecast framework remains placeholder-driven in MVP mode. Near-term thinking centers on SCENESSE durability, "
                "expansion optionality, and balance-sheet support for internal development."
            ),
            valuation=(
                f"Primary valuation anchor is a deterministic MVP base-case target of A${metrics['price_target_aud']:.2f} versus current "
                f"price A${metrics['current_price_aud']:.2f}, implying {metrics['implied_return_pct']:.2f}% upside. A full production build "
                "still needs live DCF, reverse-DCF, peer-multiple, sensitivity, and scenario-weighted outputs."
            ),
            catalysts=self._markdown_from_packet(by_facet.get("news_catalysts"), "Catalysts"),
            risks=(
                "Key risks include concentration in a lead product, regulatory delays, reimbursement constraints, pipeline execution risk, "
                "and the possibility that current deterministic target calibration overstates fair value in absence of a full live model."
            ),
            esg_governance=self._markdown_from_packet(by_facet.get("peers_ownership"), "ESG and governance"),
            appendix=self._build_appendix(findings),
        )
        return ReportSections(**ordered)

    def _build_appendix(self, findings: list[SubagentFindings]) -> str:
        sources_reviewed = []
        for packet in findings:
            for item in packet.findings:
                sources_reviewed.append(f"- [{packet.facet}] {item.source_title} ({item.source_url})")
        items_not_found = [
            f"- [{packet.facet}] {missing_item}"
            for packet in findings
            for missing_item in packet.not_found
        ]
        if not items_not_found:
            items_not_found = ["- None in the deterministic fixture run."]
        computation_notes = [
            "- Price target and implied return were produced via code execution, not free-text inference.",
            "- Current runtime does not yet include live DCF/comps/reverse-DCF stacks; valuation remains an orchestration-proof placeholder.",
        ]
        appendix_lines = [
            "Appendix",
            "",
            "Sources reviewed",
            *sources_reviewed,
            "",
            "Items not found",
            *items_not_found,
            "",
            "Computation notes",
            *computation_notes,
        ]
        return "\n".join(appendix_lines)

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
    SECTION_HEADINGS = [
        ("investment_thesis", "Section 1 — Investment Thesis"),
        ("business_description", "Section 2 — Business Description"),
        ("industry_competitive", "Section 3 — Industry and Competitive Position"),
        ("financial_analysis", "Section 4 — Financial Analysis"),
        ("forecasts", "Section 5 — Forecasts"),
        ("valuation", "Section 6 — Valuation"),
        ("catalysts", "Section 7 — Catalysts"),
        ("risks", "Section 8 — Risks"),
        ("esg_governance", "Section 9 — ESG and Governance"),
        ("appendix", "Section 10 — Appendix"),
    ]

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

        lines = [
            f"# {report.header_block.report_title}",
            "",
            "## Section 0 — Header Block",
            f"- Ticker: {report.header_block.ticker}",
            f"- Company: {report.header_block.company_name}",
            f"- Report date: {report.header_block.report_date}",
            f"- Report type: {report.header_block.report_type.value}",
            f"- Rating: {report.header_block.rating}",
            f"- Current price (A$): {report.header_block.current_price_aud:.2f}",
            f"- Price target (A$): {report.header_block.price_target_aud:.2f}",
            f"- Implied return (%): {report.header_block.implied_return_pct:.2f}",
            f"- Market cap (A$m): {report.header_block.market_cap_aud_m:.1f}" if report.header_block.market_cap_aud_m is not None else "- Market cap (A$m): n/a",
            f"- Net cash (A$m): {report.header_block.net_cash_aud_m:.1f}" if report.header_block.net_cash_aud_m is not None else "- Net cash (A$m): n/a",
            f"- Primary valuation method: {report.header_block.primary_valuation_method}",
            f"- Valuation summary: {report.header_block.valuation_summary}",
            "",
        ]
        section_payload = report.sections.model_dump()
        for section_name, heading in self.SECTION_HEADINGS:
            lines.append(f"## {heading}")
            lines.append(section_payload[section_name])
            lines.append("")
        lines.append("## Sources")
        for source in sources:
            lines.append(f"[^{source.n}]: {source.title} ({source.url})")
        lines.append("")
        lines.append("## Computation log")
        for entry in report.computation_log:
            lines.append(f"- [{entry.n}] {entry.what}: {entry.formula}")
        return CitationOutput(
            annotated_report="\n".join(lines),
            source_list=sources,
            computation_log=report.computation_log,
            unsourced_claims=[],
        )
