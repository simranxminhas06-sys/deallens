"""No-API-key demo/test mode.

Runs the full DealRoom AI pipeline — company profiles, three-agent war room
debate, risk register, 100-day plan, and reviewer — using hand-authored
fixture data for the Amazon/Whole Foods case instead of live OpenAI calls.

Every dollar figure below is still produced by the real financial_calculator
functions (not hardcoded), and the record still runs through the real,
deterministic reviewer — so this exercises the same math and the same
quality gate a live run would, just with fixture evidence instead of a
file-search call. It deliberately includes one under-evidenced opportunity
so the reviewer has something real to catch (see REVENUE_OPP below) rather
than presenting an implausibly perfect demo.
"""

from __future__ import annotations

from schemas.analysis_models import (
    AgentAssessment,
    AgentRole,
    AnalysisRecord,
    Category,
    Challenge,
    Citation,
    ClaimType,
    CompanyProfile,
    Difficulty,
    EstimatedValue,
    EvidenceItem,
    FinancialBaseline,
    IntegrationAction,
    IntegrationPlan,
    Risk,
    RiskSeverity,
    StrategicRationale,
    TransactionAssumptions,
    ValueOpportunity,
)
from tools.financial_calculator import (
    calculate_combined_metric,
    calculate_growth_rate,
    calculate_margin,
    calculate_revenue_scenario,
    calculate_savings_scenario,
)

DOCUMENT_NAMES = {
    "acquirer_amazon_overview.md",
    "target_whole_foods_overview.md",
    "transaction_assumptions.md",
}


def _acquirer_profile() -> CompanyProfile:
    growth = calculate_growth_rate(107_000_000_000, 136_000_000_000, periods=1)
    margin = calculate_margin(136_000_000_000, 4_200_000_000, "operating")
    return CompanyProfile(
        company_name="Amazon.com, Inc.",
        role="acquirer",
        business_description=(
            "Online retailer and cloud infrastructure company (AWS), reinvesting operating cash "
            "flow into fulfillment capacity and new growth categories including early physical "
            "retail pilots."
        ),
        fiscal_year="FY2016",
        revenue=136_000_000_000,
        revenue_growth_rate=growth["growth_rate"],
        operating_margin=margin["margin"],
        employee_count=341_000,
        key_segments=["North America retail", "International retail", "AWS"],
        evidence=[
            EvidenceItem(
                claim="Amazon FY2016 net sales were approximately $136.0 billion, up roughly 27% year over year.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="acquirer_amazon_overview.md", location="Section 2: Financial Highlights")],
            ),
            EvidenceItem(
                claim=f"Revenue growth rate calculated at {growth['growth_rate_pct']}% from FY2015 to FY2016.",
                claim_type=ClaimType.CALCULATED_RESULT,
                citations=[Citation(source_document="acquirer_amazon_overview.md", location="Section 2: Financial Highlights")],
                notes=growth["method"],
            ),
        ],
    )


def _target_profile() -> CompanyProfile:
    margin = calculate_margin(15_700_000_000, 675_000_000, "operating")
    return CompanyProfile(
        company_name="Whole Foods Market, Inc.",
        role="target",
        business_description=(
            "Natural and organic grocery retailer with a premium brand position, facing increasing "
            "price competition from conventional grocers and online entrants."
        ),
        fiscal_year="FY2016",
        revenue=15_700_000_000,
        revenue_growth_rate=-0.025,
        operating_margin=margin["margin"],
        employee_count=87_000,
        key_segments=["U.S. grocery", "Canada", "United Kingdom"],
        evidence=[
            EvidenceItem(
                claim="Whole Foods operates approximately 431 stores concentrated in affluent urban and suburban U.S. markets.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="target_whole_foods_overview.md", location="Section 2: Financial Highlights")],
            ),
            EvidenceItem(
                claim="Comparable store sales declined approximately 2.5% in FY2016, the target's own reported figure.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="target_whole_foods_overview.md", location="Section 2: Financial Highlights")],
            ),
        ],
    )


def _strategy_assessment() -> AgentAssessment:
    return AgentAssessment(
        role=AgentRole.STRATEGY,
        position=(
            "The acquisition creates an attractive new customer channel: Whole Foods' urban, "
            "affluent-market real estate gives Amazon physical grocery reach and last-mile "
            "distribution nodes it doesn't have today. But comparable sales were already declining "
            "before the deal, so Amazon is buying a brand under price pressure, not a growth asset "
            "on its own — the strategic case rests on what Amazon does with the stores, not on "
            "Whole Foods' standalone trajectory."
        ),
        key_findings=[
            EvidenceItem(
                claim="Whole Foods faced an activist investor (Jana Partners) pushing for strategic alternatives ahead of the deal.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="target_whole_foods_overview.md", location="Section 3: Strategic Context")],
            ),
            EvidenceItem(
                claim="Amazon had already begun piloting physical retail formats (Amazon Books, an early Amazon Go concept) before this deal, suggesting the acquisition accelerates an existing strategy rather than starting a new one.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="acquirer_amazon_overview.md", location="Section 1: Business Description")],
            ),
        ],
    )


def _cost_opportunity() -> tuple[ValueOpportunity, dict]:
    calc = calculate_savings_scenario(1_500_000_000, 0.10, 0.15, 0.20)
    opp = ValueOpportunity(
        title="Consolidate overlapping distribution and cold-chain logistics",
        category=Category.COST_SYNERGY,
        rationale="Both companies operate independent perishables distribution networks in overlapping metro markets; combining cold-chain routing and warehouse capacity reduces duplicated fixed costs.",
        evidence=[
            EvidenceItem(
                claim="Whole Foods' store footprint is concentrated in the same affluent urban markets where Amazon has been building fulfillment capacity.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="target_whole_foods_overview.md", location="Section 3: Strategic Context")],
            )
        ],
        estimated_value=EstimatedValue(low=calc["low"], base=calc["base"], high=calc["high"]),
        assumptions=["Combined distribution facility cost base of ~$1.5B/year", "Facility costs can be reduced 10-20% within 18 months without store-level service disruption"],
        implementation_difficulty=Difficulty.MEDIUM,
        time_horizon="12-18 months",
        key_risks=["Perishables service-level disruption during consolidation", "Union or labor-relations friction at affected distribution sites"],
        calculation_method="calculate_savings_scenario",
    )
    tool_call = {"name": "calculate_savings_scenario", "arguments": {"baseline_cost": 1_500_000_000, "reduction_pct_low": 0.10, "reduction_pct_base": 0.15, "reduction_pct_high": 0.20}, "result": calc}
    return opp, tool_call


def _revenue_opportunity() -> tuple[ValueOpportunity, dict]:
    """Deliberately under-evidenced — no citation — so the reviewer and Red Team have something real to flag."""
    calc = calculate_revenue_scenario(800_000_000, 0.01, 0.015, 0.02, incremental_margin_pct=1.0)
    opp = ValueOpportunity(
        title="Cross-sell Amazon Prime members into Whole Foods grocery delivery",
        category=Category.REVENUE_SYNERGY,
        rationale="Amazon's Prime membership base is a large pool of existing customers who could be converted to Whole Foods grocery delivery if offered a bundled incentive.",
        evidence=[
            EvidenceItem(
                claim="A subset of Prime members in Whole Foods' trade areas would try grocery delivery if offered a Prime-linked discount.",
                claim_type=ClaimType.HYPOTHESIS,
                citations=[],
                notes="No pilot data or documented attach rate exists yet to support this.",
            )
        ],
        estimated_value=EstimatedValue(low=calc["low"], base=calc["base"], high=calc["high"]),
        assumptions=["Baseline addressable delivery revenue of ~$800M/year in overlapping trade areas", "1.0-2.0% incremental uplift from a Prime-linked promotion"],
        implementation_difficulty=Difficulty.LOW,
        time_horizon="0-6 months",
        key_risks=["Cannibalizes existing Whole Foods in-store sales", "No pilot data to validate the assumed uplift rate"],
        calculation_method="calculate_revenue_scenario",
    )
    tool_call = {"name": "calculate_revenue_scenario", "arguments": {"baseline_revenue": 800_000_000, "uplift_pct_low": 0.01, "uplift_pct_base": 0.015, "uplift_pct_high": 0.02, "incremental_margin_pct": 1.0}, "result": calc}
    return opp, tool_call


def _financial_assessment() -> tuple[AgentAssessment, list[dict], list[FinancialBaseline]]:
    combined = calculate_combined_metric(136_000_000_000, 15_700_000_000, adjustment_pct=0.0)
    baselines = [
        FinancialBaseline(metric="Amazon revenue growth (FY15->FY16)", value=0.271, unit="fraction", method="CAGR", inputs={"beginning": 107_000_000_000, "ending": 136_000_000_000}),
        FinancialBaseline(metric="Whole Foods operating margin (FY16)", value=0.043, unit="fraction", method="operating_margin = operating_income / revenue", inputs={"revenue": 15_700_000_000, "operating_income": 675_000_000}),
        FinancialBaseline(metric="Pro-forma combined revenue", value=combined["combined_value"], unit="USD", method=combined["method"], inputs={"acquirer": 136_000_000_000, "target": 15_700_000_000}),
    ]
    cost_opp, cost_call = _cost_opportunity()
    revenue_opp, revenue_call = _revenue_opportunity()
    assessment = AgentAssessment(
        role=AgentRole.FINANCIAL,
        position=(
            "The cost-synergy case for distribution consolidation is grounded in the two companies' "
            "overlapping geographic footprint and produces a defensible $150-300M range. "
            "The revenue opportunity is plausible — Amazon's Prime base is real and large — but there "
            "is insufficient evidence to support the proposed $12 million estimate. No pilot or "
            "attach-rate data exists yet; this should be tracked as a hypothesis, not a base-case "
            "number, until a real test is run."
        ),
        key_findings=[
            EvidenceItem(
                claim=f"Pro-forma combined revenue calculated at ${combined['combined_value']:,.0f}.",
                claim_type=ClaimType.CALCULATED_RESULT,
                notes=combined["method"],
            )
        ],
        opportunities=[cost_opp, revenue_opp],
    )
    return assessment, [cost_call, revenue_call], baselines


def _red_team_assessment(financial_opps: list[ValueOpportunity]) -> AgentAssessment:
    return AgentAssessment(
        role=AgentRole.RED_TEAM,
        position=(
            "The analysis ignores brand cannibalization and integration costs. Whole Foods' premium "
            "positioning depends on being perceived as different from a discount retailer — an "
            "aggressive Prime-linked delivery push risks accelerating exactly the price-sensitive "
            "shift that was already eroding comparable sales before the deal. The revenue-synergy "
            "estimate has no supporting citation and should not be treated as a base case."
        ),
        challenges=[
            Challenge(
                target_agent=AgentRole.FINANCIAL,
                target_claim="Cross-sell Amazon Prime members into Whole Foods grocery delivery",
                critique="No cited evidence supports the assumed 1-2% uplift rate; treat as a hypothesis pending a real pilot, not a scenario ready for approval.",
                severity=RiskSeverity.HIGH,
            ),
            Challenge(
                target_agent=AgentRole.STRATEGY,
                target_claim="The acquisition creates an attractive new customer channel",
                critique="Doesn't address the cultural integration risk between Whole Foods' decentralized, team-based store culture and Amazon's centralized operating model, or the cost of that integration.",
                severity=RiskSeverity.MEDIUM,
            ),
        ],
    )


def _strategic_rationale() -> StrategicRationale:
    return StrategicRationale(
        summary=(
            "Amazon gains an established physical grocery footprint and last-mile distribution "
            "nodes in affluent urban markets, accelerating a physical-retail strategy it had already "
            "begun piloting; Whole Foods gains capital and technology investment at a moment when "
            "its standalone comparable sales were under pressure."
        ),
        supporting_points=[
            EvidenceItem(
                claim="Whole Foods' real estate footprint skews toward dense, affluent urban markets, attractive as potential last-mile distribution nodes.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="target_whole_foods_overview.md", location="Section 3: Strategic Context")],
            )
        ],
    )


def _risks() -> list[Risk]:
    return [
        Risk(
            title="Cultural integration friction",
            description="Whole Foods' decentralized, team-based store operating model differs materially from Amazon's centralized, metrics-driven culture.",
            category="cultural",
            severity=RiskSeverity.HIGH,
            mitigation="Retain Whole Foods store-level leadership through year one; phase in centralized systems rather than a single cutover.",
            evidence=[
                EvidenceItem(
                    claim="Whole Foods operates a largely non-unionized, decentralized team-based store model.",
                    claim_type=ClaimType.DOCUMENTED_FACT,
                    citations=[Citation(source_document="target_whole_foods_overview.md", location="Section 4: Risk Factors")],
                )
            ],
        ),
        Risk(
            title="Brand cannibalization from price cuts",
            description="Aggressive price cuts or delivery promotions risk eroding Whole Foods' premium brand positioning.",
            category="customer",
            severity=RiskSeverity.MEDIUM,
            mitigation="Pilot pricing/promotion changes in a limited set of stores before a full rollout.",
        ),
    ]


def _integration_plan() -> IntegrationPlan:
    return IntegrationPlan(
        guiding_principles=[
            "Preserve Whole Foods' quality-standards brand while integrating fulfillment infrastructure",
            "Pilot before scaling any pricing or promotional change",
            "Retain store-level leadership through the first year",
        ],
        actions=[
            IntegrationAction(title="Stand up integration management office", phase="0-30 days", owner_role="Head of Integration Management Office", description="Establish joint steering committee and weekly cadence.", success_metric="IMO operating within 2 weeks of close"),
            IntegrationAction(title="Pilot cold-chain distribution consolidation in one region", phase="31-60 days", owner_role="VP Supply Chain", description="Test combined routing in a single overlapping metro before wider rollout.", linked_opportunity="Consolidate overlapping distribution and cold-chain logistics", success_metric="Pilot cost-per-delivery reduced vs. baseline", risks=["Perishables service-level disruption"]),
            IntegrationAction(title="Run a limited Prime-linked delivery pilot with a control group", phase="61-100 days", owner_role="VP Grocery Delivery", description="Test the assumed cross-sell uplift in a small set of stores with a held-out control group before committing to the revenue scenario.", linked_opportunity="Cross-sell Amazon Prime members into Whole Foods grocery delivery", success_metric="Measured uplift vs. control, plus any comparable-sales cannibalization", risks=["Brand cannibalization", "No baseline data yet to validate assumptions"]),
        ],
        governance="Joint steering committee (Amazon + Whole Foods leadership) meets weekly for the first 100 days; IMO reports variances against this plan.",
    )


def run_demo_pipeline() -> tuple[AnalysisRecord, list[dict]]:
    """Builds a complete, internally-consistent AnalysisRecord with no API calls."""
    transaction = TransactionAssumptions(
        acquirer_name="Amazon.com, Inc.",
        target_name="Whole Foods Market, Inc.",
        announcement_date="2017-06-16",
        deal_value=13_700_000_000,
        deal_structure="All-cash merger",
        user_notes="Demo mode: synthetic sample documents, no live OpenAI calls.",
    )
    financial_assessment, tool_call_log, baselines = _financial_assessment()
    strategy_assessment = _strategy_assessment()
    red_team_assessment = _red_team_assessment(financial_assessment.opportunities)

    record = AnalysisRecord(
        transaction=transaction,
        acquirer_profile=_acquirer_profile(),
        target_profile=_target_profile(),
        strategic_rationale=_strategic_rationale(),
        financial_baselines=baselines,
        opportunities=financial_assessment.opportunities,
        agent_assessments=[strategy_assessment, financial_assessment, red_team_assessment],
        risks=_risks(),
        integration_plan=_integration_plan(),
        assumptions_approved=True,
        executive_summary=(
            "[DEMO MODE — synthetic sample documents, not a live analysis] Amazon's acquisition of "
            "Whole Foods pairs an established, if comparable-sales-challenged, grocery footprint with "
            "Amazon's fulfillment and Prime membership scale. The Strategy and Financial agents see a "
            "credible cost-synergy case in distribution consolidation; the Red-Team agent's strongest "
            "objection is that the proposed revenue-synergy estimate has no supporting citation and "
            "should be piloted, not assumed."
        ),
    )
    return record, tool_call_log
