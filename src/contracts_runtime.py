from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


class SourceAuthorityClass(str, Enum):
    PRIMARY_TRUTH = "primary_truth"
    TRUSTED_STRUCTURED_SECONDARY = "trusted_structured_secondary"
    NARRATIVE_SECONDARY = "narrative_secondary"
    LOW_TRUST_TERTIARY = "low_trust_tertiary"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED_PRIMARY_MATCH = "verified_primary_match"
    VERIFIED_WITH_CAVEAT = "verified_with_caveat"
    CONFLICTED = "conflicted"


class SourceMetadata(StrictBaseModel):
    authority_class: SourceAuthorityClass = SourceAuthorityClass.PRIMARY_TRUTH
    source_family: str = "company_primary"
    source_type: str = "filing"
    origin: str = "direct"
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    captured_at: Optional[str] = None
    raw_payload_path: Optional[str] = None
    quality_flags: List[str] = Field(default_factory=list)
    comparability_flags: List[str] = Field(default_factory=list)

    @field_validator('authority_class', mode='before')
    @classmethod
    def normalize_authority_class(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower().replace('-', '_').replace(' ', '_')
        alias_map = {
            'primary': 'primary_truth',
            'primary_source': 'primary_truth',
            'secondary': 'trusted_structured_secondary',
            'structured_secondary': 'trusted_structured_secondary',
            'trusted_secondary': 'trusted_structured_secondary',
            'narrative': 'narrative_secondary',
            'tertiary': 'low_trust_tertiary',
            'low_trust': 'low_trust_tertiary',
        }
        return alias_map.get(normalized, normalized)

    @field_validator('verification_status', mode='before')
    @classmethod
    def normalize_verification_status(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower().replace('-', '_').replace(' ', '_')
        alias_map = {
            'verified': 'verified_primary_match',
            'verified_match': 'verified_primary_match',
            'caveated': 'verified_with_caveat',
            'with_caveat': 'verified_with_caveat',
            'conflict': 'conflicted',
        }
        return alias_map.get(normalized, normalized)


class SearchResult(StrictBaseModel):
    title: str
    url: str
    snippet: str = ""
    source: Optional[str] = None


class SearchResults(StrictBaseModel):
    query: str
    results: List[SearchResult] = Field(default_factory=list)


class FetchResult(StrictBaseModel):
    url: str
    status_code: int
    content_type: str = "text/plain"
    text: str


class CodeExecutionResult(StrictBaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    locals_snapshot: Dict[str, Any] = Field(default_factory=dict)


class TaskInput(StrictBaseModel):
    ticker: str
    tier: ReportTier
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    triggering_event: str = "manual_run"
    prior_report: Optional[Dict[str, Any]] = None


class SubagentBrief(StrictBaseModel):
    facet: str
    ticker: str
    objective: str
    required_fields: List[str]
    source_guidance: str
    task_boundaries: str
    research_budget_hint: int = 8
    time_bounds: str = "current"
    context_from_prior_waves: str = ""


class FindingItem(StrictBaseModel):
    claim: str
    data: Any
    source_url: str
    source_tier: int
    source_title: str
    source_date: Optional[str] = None
    data_as_of: Optional[str] = None
    period_label: Optional[str] = None
    retrieval_date: str
    confidence: FindingConfidence
    notes: str = ""
    source_metadata: Optional[SourceMetadata] = None


class ContradictionItem(StrictBaseModel):
    topic: str
    source_a: str
    source_a_claim: str
    source_b: str
    source_b_claim: str
    notes: str = ""


class SubagentFindings(StrictBaseModel):
    facet: str
    ticker: str
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
    tool_calls_used: int = 0
    findings: List[FindingItem] = Field(default_factory=list)
    not_found: List[str] = Field(default_factory=list)
    contradictions: List[ContradictionItem] = Field(default_factory=list)
    summary: str


class HeaderBlock(StrictBaseModel):
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


class ReportSections(StrictBaseModel):
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


class ComputationLogEntry(StrictBaseModel):
    n: int
    what: str
    formula: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    output: Any = None


class FindingIndexItem(StrictBaseModel):
    facet: str
    claim: str
    source_url: str
    source_title: str
    source_tier: int
    source_date: Optional[str] = None
    data_as_of: Optional[str] = None
    period_label: Optional[str] = None
    confidence: FindingConfidence
    source_metadata: Optional[SourceMetadata] = None


class StructuredSecondaryMetric(StrictBaseModel):
    ticker: str
    metric: Literal["roic_pct", "eps_revision_3m_pct"]
    value: float
    unit: str
    source_url: str
    source_title: str
    source_tier: int = 2
    source_metadata: SourceMetadata


class CanonicalFcfBridge(StrictBaseModel):
    npat_aud_m: float
    depreciation_and_amortization_aud_m: float
    working_capital_outflow_aud_m: float
    lease_cash_outflow_aud_m: float
    capex_aud_m: float
    equity_free_cash_flow_aud_m: float


class CanonicalPeerRow(StrictBaseModel):
    peer_name: str
    ticker: str
    business_fit: str
    pe_ntm: Optional[float] = None
    ev_revenue_ntm: Optional[float] = None
    ev_ebitda_ntm: Optional[float] = None
    notes: str = ""


class CanonicalScenarioRow(StrictBaseModel):
    scenario: str
    probability_pct: float
    price_target_aud: float
    thesis: str


class CanonicalPipelineOptionValue(StrictBaseModel):
    methodology: str
    probability_weighted_value_aud_m: float
    included_in_price_target: bool
    rationale: str


class CanonicalSensitivityRow(StrictBaseModel):
    wacc_pct: float
    terminal_growth_pct: float
    price_target_aud: float


class CanonicalSensitivityTable(StrictBaseModel):
    base_wacc_pct: float
    base_terminal_growth_pct: float
    rows: List[CanonicalSensitivityRow] = Field(default_factory=list)


class CanonicalValuationInputs(StrictBaseModel):
    reconciliation_status: Literal["resolved", "unresolved"]
    fcf_bridge: CanonicalFcfBridge
    peer_table: List[CanonicalPeerRow]
    scenario_analysis: List[CanonicalScenarioRow]
    pipeline_option_value: CanonicalPipelineOptionValue
    sensitivity_table: CanonicalSensitivityTable


class FinalReport(StrictBaseModel):
    ticker: str
    tier: ReportTier
    generated_at: str
    version: str = "0.1.0"
    header_block: HeaderBlock
    sections: ReportSections
    canonical_valuation_inputs: CanonicalValuationInputs
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


class ChallengeItem(StrictBaseModel):
    challenge: str
    evidence_or_logic: str
    where_report_fails: str
    severity: Literal["critical", "material", "minor"]


class RedTeamVerdict(StrictBaseModel):
    ticker: str
    report_rating: Literal["Buy", "Hold", "Sell"]
    red_team_counter_rating: Literal["Buy", "Hold", "Sell"]
    verdict: RedTeamVerdictType
    counter_thesis: str
    three_strongest_challenges: List[ChallengeItem] = Field(default_factory=list)
    missed_risks: List[str] = Field(default_factory=list)
    disagreements_with_calculations: List[Dict[str, str]] = Field(default_factory=list)
    verdict_reasoning: str


class CitationSource(StrictBaseModel):
    n: int
    title: str
    url: str
    retrieval_date: str
    source_tier: int
    claim_refs: List[str] = Field(default_factory=list)


class CitationOutput(StrictBaseModel):
    annotated_report: str
    source_list: List[CitationSource] = Field(default_factory=list)
    computation_log: List[ComputationLogEntry] = Field(default_factory=list)
    unsourced_claims: List[str] = Field(default_factory=list)


class ReportPacket(StrictBaseModel):
    task: TaskInput
    plan: Dict[str, Any]
    subagent_briefs: List[SubagentBrief]
    subagent_findings: List[SubagentFindings]
    report: FinalReport
    red_team: RedTeamVerdict
    citation: CitationOutput
    artifacts: Dict[str, str] = Field(default_factory=dict)
