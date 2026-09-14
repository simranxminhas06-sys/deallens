"""Pydantic models shared by every stage of the DealLens pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    DOCUMENTED_FACT = "documented_fact"
    CALCULATED_RESULT = "calculated_result"
    ASSUMPTION = "assumption"
    HYPOTHESIS = "hypothesis"


class Category(str, Enum):
    REVENUE_SYNERGY = "revenue_synergy"
    COST_SYNERGY = "cost_synergy"


class Difficulty(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentRole(str, Enum):
    STRATEGY = "strategy"
    FINANCIAL = "financial"
    RED_TEAM = "red_team"


class Citation(BaseModel):
    source_document: str = Field(description="File name of the source document")
    location: str = Field(description="Page, section, or table reference within the document")
    quoted_text: Optional[str] = Field(
        default=None, description="Short (<25 word) supporting excerpt, if directly quoted"
    )


class EvidenceItem(BaseModel):
    claim: str
    claim_type: ClaimType
    citations: list[Citation] = Field(default_factory=list)
    notes: Optional[str] = None


class CompanyProfile(BaseModel):
    company_name: str
    role: str = Field(description="'acquirer' or 'target'")
    business_description: str
    fiscal_year: Optional[str] = None
    revenue: Optional[float] = None
    revenue_growth_rate: Optional[float] = None
    operating_margin: Optional[float] = None
    employee_count: Optional[int] = None
    key_segments: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class StrategicRationale(BaseModel):
    summary: str
    supporting_points: list[EvidenceItem] = Field(default_factory=list)


class EstimatedValue(BaseModel):
    low: float
    base: float
    high: float
    currency: str = "USD"

    def as_range_string(self) -> str:
        return f"${self.low:,.0f} - ${self.high:,.0f} (base ${self.base:,.0f})"


class ValueOpportunity(BaseModel):
    title: str
    category: Category
    rationale: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    estimated_value: EstimatedValue
    assumptions: list[str] = Field(default_factory=list)
    implementation_difficulty: Difficulty
    time_horizon: str
    key_risks: list[str] = Field(default_factory=list)
    calculation_method: Optional[str] = Field(
        default=None, description="Name of the financial_calculator function used, if any"
    )


class Risk(BaseModel):
    title: str
    description: str
    category: str = Field(description="e.g. operational, cultural, regulatory, financial, customer")
    severity: RiskSeverity
    mitigation: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


class IntegrationAction(BaseModel):
    title: str
    phase: str = Field(description="'0-30 days', '31-60 days', or '61-100 days'")
    owner_role: str = Field(description="Functional owner, e.g. 'Head of Integration Management Office'")
    description: str
    linked_opportunity: Optional[str] = Field(
        default=None, description="Title of the related ValueOpportunity, if any"
    )
    success_metric: Optional[str] = None
    risks: list[str] = Field(default_factory=list)


class IntegrationPlan(BaseModel):
    guiding_principles: list[str] = Field(default_factory=list)
    actions: list[IntegrationAction] = Field(default_factory=list)
    governance: str = Field(description="How integration progress is tracked and escalated")


class FinancialBaseline(BaseModel):
    metric: str
    value: float
    unit: str
    method: str
    inputs: dict = Field(default_factory=dict)


class ReviewIssue(BaseModel):
    severity: RiskSeverity
    stage: str
    item_title: str
    problem: str
    recommendation: str


class ReviewResult(BaseModel):
    passed: bool
    issues: list[ReviewIssue] = Field(default_factory=list)
    claim_type_coverage: dict[str, int] = Field(default_factory=dict)
    citation_coverage_pct: Optional[float] = None


class Challenge(BaseModel):
    target_agent: AgentRole
    target_claim: str = Field(description="The opportunity title or claim text being challenged")
    critique: str
    severity: RiskSeverity


class AgentAssessment(BaseModel):
    role: AgentRole
    position: str = Field(description="One-paragraph stance in the agent's voice, e.g. 'The revenue opportunity is plausible, but...'")
    key_findings: list[EvidenceItem] = Field(default_factory=list)
    opportunities: list[ValueOpportunity] = Field(default_factory=list, description="Populated by the Financial Agent")
    challenges: list[Challenge] = Field(default_factory=list, description="Populated by the Red-Team Agent")


class TransactionAssumptions(BaseModel):
    acquirer_name: str
    target_name: str
    announcement_date: Optional[str] = None
    deal_value: Optional[float] = None
    deal_structure: Optional[str] = None
    user_notes: Optional[str] = None


class AnalysisRecord(BaseModel):
    id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    transaction: TransactionAssumptions
    acquirer_profile: Optional[CompanyProfile] = None
    target_profile: Optional[CompanyProfile] = None
    strategic_rationale: Optional[StrategicRationale] = None
    financial_baselines: list[FinancialBaseline] = Field(default_factory=list)
    opportunities: list[ValueOpportunity] = Field(default_factory=list)
    agent_assessments: list[AgentAssessment] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    integration_plan: Optional[IntegrationPlan] = None
    review: Optional[ReviewResult] = None
    executive_summary: Optional[str] = None
    assumptions_approved: bool = False
