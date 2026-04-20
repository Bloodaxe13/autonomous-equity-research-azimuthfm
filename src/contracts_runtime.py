from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


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
    rating: Literal["Buy", "Hold", "Sell"]
    price_target_aud: float
    implied_return_pct: float
    last_close_aud: Optional[float] = None
    market_cap_aud_m: Optional[float] = None
    generated_at: str


class FinalReport(BaseModel):
    ticker: str
    tier: ReportTier
    generated_at: str
    version: str = "0.1.0"
    header_block: HeaderBlock
    sections: Dict[str, str]
    computation_log: List[Dict[str, Any]] = Field(default_factory=list)
    findings_index: List[Dict[str, Any]] = Field(default_factory=list)
    rating: Literal["Buy", "Hold", "Sell"]
    price_target_aud: float
    implied_return_pct: float


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
    computation_log: List[Dict[str, Any]] = Field(default_factory=list)
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
