from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


SECTION_ORDER = [
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


class ReportTier(str, Enum):
    INITIATION = "initiation"
    QUARTERLY = "quarterly"
    FLASH = "flash"


class FindingConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RedTeamVerdictType(str, Enum):
    STRONG_COUNTER_CASE = "strong_counter_case"
    WEAK_COUNTER_CASE = "weak_counter_case"
    COVERED_GROUND = "covered_ground"


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    source: Optional[str] = None


class SearchResults(BaseModel):
    query: str
    results: List[SearchResult] = Field(default_factory=list)


class FetchResult(BaseModel):
    url: str
    status_code: int
    content_type: str = "text/plain"
    text: str


class CodeExecutionResult(BaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    locals_snapshot: Dict[str, Any] = Field(default_factory=dict)


class TaskInput(BaseModel):
    ticker: str
    tier: ReportTier
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    triggering_event: str = "manual_run"
    prior_report: Optional[Dict[str, Any]] = None


class SubagentBrief(BaseModel):
    facet: str
    ticker: str
    objective: str
    required_fields: List[str] = Field(default_factory=list)
    source_guidance: str
    task_boundaries: str
    research_budget_hint: int = 8
    time_bounds: str = "current"
    context_from_prior_waves: str = ""


class FindingItem(BaseModel):
    claim: str
    data: Any
    source_url: str
    source_tier: int
    source_title: str
    source_date: Optional[str] = None
    retrieval_date: str
    confidence: FindingConfidence
    notes: str = ""


class ContradictionItem(BaseModel):
    topic: str
    source_a: str
    source_a_claim: str
    source_b: str
    source_b_claim: str
    notes: str = ""


class SubagentFindings(BaseModel):
    facet: str
    ticker: str
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
    tool_calls_used: int = 0
    findings: List[FindingItem] = Field(default_factory=list)
    not_found: List[str] = Field(default_factory=list)
    contradictions: List[ContradictionItem] = Field(default_factory=list)
    summary: str


class HeaderBlock(BaseModel):
    ticker: str
    company_name: str
    report_title: str
    report_date: str
    report_type: ReportTier
    rating: Literal["Buy", "Hold", "Sell"]
    price_target_aud: float
    current_price_aud: float
    implied_return_pct: float
    market_cap_aud_m: Optional[float] = None
    net_cash_aud_m: Optional[float] = None
    primary_valuation_method: str
    valuation_summary: str
    generated_at: str


class ReportSections(BaseModel):
    investment_thesis: str
    business_description: str
    industry_competitive: str
    financial_analysis: str
    forecasts: str
    valuation: str
    catalysts: str
    risks: str
    esg_governance: str
    appendix: str

    @model_validator(mode="after")
    def appendix_must_contain_required_subsections(self) -> "ReportSections":
        appendix = self.appendix
        required_labels = ["Sources reviewed", "Items not found", "Computation notes"]
        missing = [label for label in required_labels if label not in appendix]
        if missing:
            raise ValueError(f"appendix missing required subsections: {', '.join(missing)}")
        return self


class ComputationLogEntry(BaseModel):
    n: int
    what: str
    formula: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    output: Any = None


class FindingIndexItem(BaseModel):
    facet: str
    claim: str
    source_url: str
    source_title: str
    source_tier: int
    confidence: FindingConfidence


class FinalReport(BaseModel):
    ticker: str
    tier: ReportTier
    generated_at: str
    version: str = "0.1.0"
    header_block: HeaderBlock
    sections: ReportSections
    computation_log: List[ComputationLogEntry] = Field(default_factory=list)
    findings_index: List[FindingIndexItem] = Field(default_factory=list)
    rating: Literal["Buy", "Hold", "Sell"]
    price_target_aud: float
    implied_return_pct: float

    @model_validator(mode="after")
    def enforce_consistency(self) -> "FinalReport":
        if self.header_block.ticker != self.ticker:
            raise ValueError("header_block.ticker must match report ticker")
        if self.header_block.report_type != self.tier:
            raise ValueError("header_block.report_type must match report tier")
        if self.header_block.rating != self.rating:
            raise ValueError("header_block.rating must match report rating")
        if round(self.header_block.price_target_aud, 4) != round(self.price_target_aud, 4):
            raise ValueError("header_block.price_target_aud must match report price_target_aud")
        if round(self.header_block.implied_return_pct, 4) != round(self.implied_return_pct, 4):
            raise ValueError("header_block.implied_return_pct must match report implied_return_pct")
        if round(self.header_block.current_price_aud, 4) <= 0:
            raise ValueError("header_block.current_price_aud must be positive")
        if self.tier == ReportTier.INITIATION and not self.findings_index:
            raise ValueError("initiation reports must include a findings_index")
        expected_sequence = list(range(1, len(self.computation_log) + 1))
        actual_sequence = [entry.n for entry in self.computation_log]
        if actual_sequence != expected_sequence:
            raise ValueError("computation_log entries must have contiguous n values starting at 1")
        section_keys = list(self.sections.model_dump().keys())
        if section_keys != SECTION_ORDER:
            raise ValueError("report sections must follow the canonical 10-section order")
        return self


class ChallengeItem(BaseModel):
    challenge: str
    evidence_or_logic: str
    where_report_fails: str
    severity: Literal["critical", "material", "minor"]


class RedTeamVerdict(BaseModel):
    ticker: str
    report_rating: Literal["Buy", "Hold", "Sell"]
    red_team_counter_rating: Literal["Buy", "Hold", "Sell"]
    verdict: RedTeamVerdictType
    counter_thesis: str
    three_strongest_challenges: List[ChallengeItem] = Field(default_factory=list)
    missed_risks: List[str] = Field(default_factory=list)
    disagreements_with_calculations: List[Dict[str, str]] = Field(default_factory=list)
    verdict_reasoning: str


class CitationSource(BaseModel):
    n: int
    title: str
    url: str
    retrieval_date: str
    source_tier: int
    claim_refs: List[str] = Field(default_factory=list)


class CitationOutput(BaseModel):
    annotated_report: str
    source_list: List[CitationSource] = Field(default_factory=list)
    computation_log: List[ComputationLogEntry] = Field(default_factory=list)
    unsourced_claims: List[str] = Field(default_factory=list)


class ReportPacket(BaseModel):
    task: TaskInput
    plan: Dict[str, Any]
    subagent_briefs: List[SubagentBrief]
    subagent_findings: List[SubagentFindings]
    report: FinalReport
    red_team: RedTeamVerdict
    citation: CitationOutput
    artifacts: Dict[str, str] = Field(default_factory=dict)
