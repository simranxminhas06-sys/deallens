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
    source_document: str = Field(description="File name of the source document, or the page title for a web source")
    location: str = Field(description="Page, section, or table reference within the document; 'web' for a web source")
    source_url: Optional[str] = Field(
        default=None, description="URL, if this citation came from web search rather than an uploaded document"
    )
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
    calculation_inputs: dict = Field(
        default_factory=dict,
        description="Exact keyword arguments passed to calculation_method, so the estimate can be recomputed live from adjusted assumptions",
    )
    cost_to_achieve: float = Field(
        default=0.0, description="One-time cost to capture this opportunity (integration, systems, severance, etc.)"
    )
    year_1_pct: float = Field(default=1.0, description="Fraction of full run-rate value realized in year 1")
    year_2_pct: float = Field(default=1.0, description="Fraction of full run-rate value realized in year 2")
    year_3_pct: float = Field(default=1.0, description="Fraction of full run-rate value realized in year 3 (usually 1.0 = full run-rate)")


_SEVERITY_WEIGHT = {RiskSeverity.LOW: 1, RiskSeverity.MEDIUM: 2, RiskSeverity.HIGH: 3}


class Risk(BaseModel):
    title: str
    description: str
    category: str = Field(description="e.g. operational, cultural, regulatory, financial, customer")
    severity: RiskSeverity = Field(description="Impact if the risk materializes")
    likelihood: RiskSeverity = Field(default=RiskSeverity.MEDIUM, description="How likely the risk is to occur")
    mitigation: str
    evidence: list[EvidenceItem] = Field(default_factory=list)

    @property
    def score(self) -> int:
        """Likelihood x impact, 1-9. A composite risk register is sorted by this, not by a
        single severity label, since a low-likelihood risk can still be high-impact and vice versa.
        """
        return _SEVERITY_WEIGHT[self.likelihood] * _SEVERITY_WEIGHT[self.severity]


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


class VerdictLevel(str, Enum):
    PROCEED = "proceed"
    PROCEED_WITH_CONDITIONS = "proceed_with_conditions"
    FURTHER_DILIGENCE = "further_diligence"
    DO_NOT_PROCEED = "do_not_proceed"


class Verdict(BaseModel):
    level: VerdictLevel
    reasons: list[str] = Field(default_factory=list, description="Deterministic facts that drove the verdict")
    conditions: list[str] = Field(
        default_factory=list, description="Specific items to resolve before proceeding, if level is proceed_with_conditions"
    )


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


class FinancingStructure(BaseModel):
    """How the deal value is actually funded — feeds the accretion/dilution calculation.
    Optional on TransactionAssumptions so existing records/fixtures without it are unaffected.
    """

    cash_pct: float = Field(description="Fraction of deal_value paid in cash; cash_pct + stock_pct + debt_pct == 1.0")
    stock_pct: float
    debt_pct: float
    new_debt_interest_rate: float = Field(default=0.0, description="Annual rate on new acquisition debt")
    foregone_interest_rate: float = Field(
        default=0.0, description="Rate the cash used would otherwise have earned (opportunity cost)"
    )
    acquirer_tax_rate: float = Field(default=0.21, description="Applied to interest expense and foregone interest")
    acquirer_share_price: float
    acquirer_shares_outstanding: float
    acquirer_net_income: float
    target_net_income: Optional[float] = Field(
        default=None, description="Target's standalone net income, added into pro forma combined net income"
    )
    note: Optional[str] = Field(
        default=None,
        description="Disclosure when the financing mix is illustrative rather than the actual historical deal terms",
    )


class TransactionAssumptions(BaseModel):
    acquirer_name: str
    target_name: str
    announcement_date: Optional[str] = None
    deal_value: Optional[float] = None
    deal_structure: Optional[str] = None
    financing: Optional[FinancingStructure] = None
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
