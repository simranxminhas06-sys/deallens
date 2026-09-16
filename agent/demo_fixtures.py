"""No-API-key demo/test mode.

Runs the full DealRoom AI pipeline — company profiles, three-agent independent
assessments, risk register, 100-day plan, and reviewer — using hand-authored
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
    calc_inputs = {
        "baseline_cost": 1_500_000_000,
        "reduction_pct_low": 0.10,
        "reduction_pct_base": 0.15,
        "reduction_pct_high": 0.20,
    }
    calc = calculate_savings_scenario(**calc_inputs)
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
        calculation_inputs=calc_inputs,
        cost_to_achieve=60_000_000,
        year_1_pct=0.40,
        year_2_pct=0.85,
        year_3_pct=1.0,
    )
    tool_call = {"name": "calculate_savings_scenario", "arguments": calc_inputs, "result": calc}
    return opp, tool_call


def _revenue_opportunity() -> tuple[ValueOpportunity, dict]:
    """Deliberately under-evidenced — no citation — so the reviewer and Red Team have something real to flag."""
    calc_inputs = {
        "baseline_revenue": 800_000_000,
        "uplift_pct_low": 0.01,
        "uplift_pct_base": 0.015,
        "uplift_pct_high": 0.02,
        "incremental_margin_pct": 1.0,
    }
    calc = calculate_revenue_scenario(**calc_inputs)
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
        calculation_inputs=calc_inputs,
        cost_to_achieve=2_000_000,
        year_1_pct=0.30,
        year_2_pct=0.70,
        year_3_pct=1.0,
    )
    tool_call = {"name": "calculate_revenue_scenario", "arguments": calc_inputs, "result": calc}
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
            likelihood=RiskSeverity.HIGH,
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
            likelihood=RiskSeverity.MEDIUM,
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


PFIZER_SEAGEN_DOCUMENT_NAMES = {
    "acquirer_pfizer_overview.md",
    "target_seagen_overview.md",
    "transaction_assumptions_pfizer_seagen.md",
}


def _pfizer_profile() -> CompanyProfile:
    growth = calculate_growth_rate(81_300_000_000, 100_300_000_000, periods=1)
    margin = calculate_margin(100_300_000_000, 30_000_000_000, "operating")
    return CompanyProfile(
        company_name="Pfizer Inc.",
        role="acquirer",
        business_description=(
            "Global biopharmaceutical company reinvesting cash generated during the COVID-19 "
            "vaccine/treatment cycle into oncology, ahead of an expected step-down in COVID-related "
            "revenue as demand normalizes."
        ),
        fiscal_year="FY2022",
        revenue=100_300_000_000,
        revenue_growth_rate=growth["growth_rate"],
        operating_margin=margin["margin"],
        employee_count=83_000,
        key_segments=["Biopharma", "Oncology", "Vaccines"],
        evidence=[
            EvidenceItem(
                claim="Pfizer FY2022 revenue was approximately $100.3 billion, up roughly 23% year over year, driven substantially by COVID-19 products.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="acquirer_pfizer_overview.md", location="Section 2: Financial Highlights")],
            ),
            EvidenceItem(
                claim=f"Revenue growth rate calculated at {growth['growth_rate_pct']}% from FY2021 to FY2022.",
                claim_type=ClaimType.CALCULATED_RESULT,
                citations=[Citation(source_document="acquirer_pfizer_overview.md", location="Section 2: Financial Highlights")],
                notes=growth["method"],
            ),
        ],
    )


def _seagen_profile() -> CompanyProfile:
    margin = calculate_margin(2_000_000_000, -100_000_000, "operating")
    return CompanyProfile(
        company_name="Seagen Inc.",
        role="target",
        business_description=(
            "Clinical- and commercial-stage biotechnology company focused on antibody-drug conjugate "
            "(ADC) therapies for oncology, with several approved therapies sold primarily in the U.S. "
            "and a pipeline of earlier-stage programs."
        ),
        fiscal_year="FY2022",
        revenue=2_000_000_000,
        revenue_growth_rate=0.22,
        operating_margin=margin["margin"],
        employee_count=2_400,
        key_segments=["Oncology therapeutics", "Antibody-drug conjugates (ADCs)"],
        evidence=[
            EvidenceItem(
                claim="Seagen markets its approved ADC therapies primarily in the United States and has limited ex-U.S. commercial infrastructure of its own.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="target_seagen_overview.md", location="Section 2: Financial Highlights")],
            ),
            EvidenceItem(
                claim="Seagen's FY2022 operating margin was negative, consistent with a clinical/commercial-stage biotech still scaling its launched therapies and funding pipeline R&D.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="target_seagen_overview.md", location="Section 2: Financial Highlights")],
            ),
        ],
    )


def _pfizer_strategy_assessment() -> AgentAssessment:
    return AgentAssessment(
        role=AgentRole.STRATEGY,
        position=(
            "Seagen's approved ADC portfolio and pipeline give Pfizer an immediate, de-risked "
            "diversification away from COVID-dependent revenue and into oncology, a strategic "
            "priority Pfizer has stated publicly. But the strategic case leans heavily on retaining "
            "the scientific and clinical talent that built Seagen's ADC platform — the acquisition "
            "buys a platform and a pipeline, not just currently-marketed products, and platforms "
            "walk out the door if the people who run them leave."
        ),
        key_findings=[
            EvidenceItem(
                claim="Seagen's ADC platform is the basis for its approved therapies and its earlier-stage pipeline alike, making the underlying R&D organization, not just current product revenue, central to the deal's value.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="target_seagen_overview.md", location="Section 3: Strategic Context")],
            ),
            EvidenceItem(
                claim="Pfizer has publicly stated a strategic priority of diversifying into oncology ahead of an expected decline in COVID-related revenue.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="acquirer_pfizer_overview.md", location="Section 1: Business Description")],
            ),
        ],
    )


def _seagen_cost_opportunity() -> tuple[ValueOpportunity, dict]:
    calc_inputs = {
        "baseline_cost": 800_000_000,
        "reduction_pct_low": 0.10,
        "reduction_pct_base": 0.18,
        "reduction_pct_high": 0.25,
    }
    calc = calculate_savings_scenario(**calc_inputs)
    opp = ValueOpportunity(
        title="Consolidate duplicate G&A and ex-U.S. commercial infrastructure",
        category=Category.COST_SYNERGY,
        rationale="Seagen has built limited commercial infrastructure outside the U.S.; folding its G&A and any nascent ex-U.S. commercial buildout into Pfizer's existing global infrastructure removes duplicated fixed cost rather than requiring Seagen to build its own.",
        evidence=[
            EvidenceItem(
                claim="Seagen markets its approved ADC therapies primarily in the United States and has limited ex-U.S. commercial infrastructure of its own.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="target_seagen_overview.md", location="Section 2: Financial Highlights")],
            )
        ],
        estimated_value=EstimatedValue(low=calc["low"], base=calc["base"], high=calc["high"]),
        assumptions=["Combined G&A / early ex-U.S. commercial cost base of ~$800M/year", "Costs can be reduced 10-25% within 18-24 months by routing through Pfizer's existing infrastructure"],
        implementation_difficulty=Difficulty.MEDIUM,
        time_horizon="18-24 months",
        key_risks=["Regulatory approval timelines for combined ex-U.S. filings", "Disruption to existing Seagen commercial operations during transition"],
        calculation_method="calculate_savings_scenario",
        calculation_inputs=calc_inputs,
        cost_to_achieve=90_000_000,
        year_1_pct=0.25,
        year_2_pct=0.70,
        year_3_pct=1.0,
    )
    tool_call = {"name": "calculate_savings_scenario", "arguments": calc_inputs, "result": calc}
    return opp, tool_call


def _seagen_revenue_opportunity() -> tuple[ValueOpportunity, dict]:
    """Deliberately weak (hypothesis, no pilot data) even though it carries a citation — the
    citation grounds it in an uploaded document (so it isn't flagged as unrelated evidence),
    but Red-Team still has a real, separate basis to challenge the assumed uplift rate itself.
    """
    calc_inputs = {
        "baseline_revenue": 600_000_000,
        "uplift_pct_low": 0.05,
        "uplift_pct_base": 0.08,
        "uplift_pct_high": 0.12,
        "incremental_margin_pct": 0.5,
    }
    calc = calculate_revenue_scenario(**calc_inputs)
    opp = ValueOpportunity(
        title="Accelerate Seagen ADC launches into Pfizer's ex-U.S. oncology markets",
        category=Category.REVENUE_SYNERGY,
        rationale="Pfizer's existing global regulatory and commercial infrastructure could accelerate ex-U.S. launches of Seagen's approved and near-term-pipeline ADC therapies beyond what Seagen could achieve alone.",
        evidence=[
            EvidenceItem(
                claim="Pfizer's global regulatory and commercial infrastructure could plausibly accelerate ex-U.S. launch timelines for Seagen's therapies, though no comparable prior launch-acceleration case is cited yet.",
                claim_type=ClaimType.HYPOTHESIS,
                citations=[Citation(source_document="target_seagen_overview.md", location="Section 3: Strategic Context")],
                notes="No comparable prior launch or attach-rate data exists yet to support the specific uplift assumed here.",
            )
        ],
        estimated_value=EstimatedValue(low=calc["low"], base=calc["base"], high=calc["high"]),
        assumptions=["Addressable ex-U.S. oncology revenue base of ~$600M/year", "5-12% incremental uplift from faster ex-U.S. launch timing"],
        implementation_difficulty=Difficulty.HIGH,
        time_horizon="12-24 months",
        key_risks=["No comparable prior case to validate the assumed uplift rate", "Ex-U.S. regulatory timelines are outside Pfizer's direct control"],
        calculation_method="calculate_revenue_scenario",
        calculation_inputs=calc_inputs,
        cost_to_achieve=15_000_000,
        year_1_pct=0.20,
        year_2_pct=0.60,
        year_3_pct=1.0,
    )
    tool_call = {"name": "calculate_revenue_scenario", "arguments": calc_inputs, "result": calc}
    return opp, tool_call


def _pfizer_financial_assessment() -> tuple[AgentAssessment, list[dict], list[FinancialBaseline]]:
    combined = calculate_combined_metric(100_300_000_000, 2_000_000_000, adjustment_pct=0.0)
    baselines = [
        FinancialBaseline(metric="Pfizer revenue growth (FY21->FY22)", value=0.2337, unit="fraction", method="CAGR", inputs={"beginning": 81_300_000_000, "ending": 100_300_000_000}),
        FinancialBaseline(metric="Seagen operating margin (FY22)", value=-0.05, unit="fraction", method="operating_margin = operating_income / revenue", inputs={"revenue": 2_000_000_000, "operating_income": -100_000_000}),
        FinancialBaseline(metric="Pro-forma combined revenue", value=combined["combined_value"], unit="USD", method=combined["method"], inputs={"acquirer": 100_300_000_000, "target": 2_000_000_000}),
    ]
    cost_opp, cost_call = _seagen_cost_opportunity()
    revenue_opp, revenue_call = _seagen_revenue_opportunity()
    assessment = AgentAssessment(
        role=AgentRole.FINANCIAL,
        position=(
            "The cost-synergy case for routing Seagen's G&A and any ex-U.S. commercial buildout "
            "through Pfizer's existing infrastructure is grounded in Seagen's own limited ex-U.S. "
            "footprint and produces a defensible $80-200M range. The ex-U.S. launch-acceleration "
            "revenue opportunity is directionally plausible — Pfizer's global infrastructure is real "
            "— but the specific 5-12% uplift has no comparable prior case behind it and should be "
            "tracked as a hypothesis pending an actual launch, not treated as a base-case number."
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


def _seagen_red_team_assessment() -> AgentAssessment:
    return AgentAssessment(
        role=AgentRole.RED_TEAM,
        position=(
            "The analysis treats Seagen's ADC platform as a stable asset, but biotech acquisitions "
            "of this kind live or die on retaining the scientists and clinicians who built the "
            "pipeline — that risk isn't priced into the strategic case. Separately, the ex-U.S. "
            "launch-acceleration revenue estimate rests on an assumed uplift rate with no comparable "
            "prior launch to validate it; it should be a pending hypothesis, not a base-case number "
            "used in the total value-creation figure."
        ),
        challenges=[
            Challenge(
                target_agent=AgentRole.FINANCIAL,
                target_claim="Accelerate Seagen ADC launches into Pfizer's ex-U.S. oncology markets",
                critique="The assumed 5-12% uplift rate has no comparable prior launch-acceleration case behind it; treat as a hypothesis pending an actual launch, not a scenario ready for approval.",
                severity=RiskSeverity.HIGH,
            ),
            Challenge(
                target_agent=AgentRole.STRATEGY,
                target_claim="Seagen's approved ADC portfolio and pipeline give Pfizer an immediate, de-risked diversification away from COVID-dependent revenue",
                critique="Doesn't address the risk that key Seagen scientists and clinical leaders leave post-close, which would erode the pipeline value the strategic case depends on.",
                severity=RiskSeverity.MEDIUM,
            ),
        ],
    )


def _pfizer_seagen_strategic_rationale() -> StrategicRationale:
    return StrategicRationale(
        summary=(
            "Pfizer gains an approved oncology ADC portfolio and pipeline, diversifying away from "
            "COVID-dependent revenue ahead of its expected decline, while Seagen gains Pfizer's "
            "global regulatory and commercial infrastructure to accelerate its therapies into "
            "markets it could not efficiently reach on its own."
        ),
        supporting_points=[
            EvidenceItem(
                claim="Seagen's ADC platform is the basis for its approved therapies and its earlier-stage pipeline alike, making the underlying R&D organization, not just current product revenue, central to the deal's value.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=[Citation(source_document="target_seagen_overview.md", location="Section 3: Strategic Context")],
            )
        ],
    )


def _pfizer_seagen_risks() -> list[Risk]:
    return [
        Risk(
            title="Key scientist and R&D talent attrition",
            description="Seagen's ADC platform depends on a concentrated group of scientists and clinical leaders; biotech acquirers routinely see meaningful post-close attrition among exactly this group.",
            category="people",
            severity=RiskSeverity.HIGH,
            likelihood=RiskSeverity.HIGH,
            mitigation="Put retention packages in place for named key scientists and clinical leaders before close; keep the R&D organization operating semi-autonomously through year one.",
            evidence=[
                EvidenceItem(
                    claim="Seagen's ADC platform is the basis for its approved therapies and its earlier-stage pipeline alike, making the underlying R&D organization, not just current product revenue, central to the deal's value.",
                    claim_type=ClaimType.DOCUMENTED_FACT,
                    citations=[Citation(source_document="target_seagen_overview.md", location="Section 3: Strategic Context")],
                )
            ],
        ),
        Risk(
            title="Clinical trial and regulatory delay for pipeline programs",
            description="Seagen's earlier-stage pipeline programs carry ordinary clinical and regulatory timeline risk, which a combined entity does not eliminate.",
            category="regulatory",
            severity=RiskSeverity.HIGH,
            likelihood=RiskSeverity.MEDIUM,
            mitigation="Align regulatory submission strategy across both companies' teams within the first 60 days rather than deferring it to post-integration.",
        ),
    ]


def _pfizer_seagen_integration_plan() -> IntegrationPlan:
    return IntegrationPlan(
        guiding_principles=[
            "Keep Seagen's R&D organization operating semi-autonomously through year one",
            "Put key-scientist retention packages in place before close, not after",
            "Pilot the ex-U.S. launch-acceleration thesis on one program before assuming it across the pipeline",
        ],
        actions=[
            IntegrationAction(title="Stand up integration management office", phase="0-30 days", owner_role="Head of Integration Management Office", description="Establish joint steering committee and weekly cadence.", success_metric="IMO operating within 2 weeks of close"),
            IntegrationAction(title="Finalize retention packages for named key scientists and clinical leaders", phase="0-30 days", owner_role="Head of R&D Integration", description="Identify and lock in retention terms for the R&D and clinical leaders the ADC platform depends on before uncertainty drives attrition.", linked_opportunity=None, success_metric="Retention agreements signed for all named key personnel", risks=["Key personnel identified too late, after attrition risk has already materialized"]),
            IntegrationAction(title="Align global regulatory submission strategy", phase="31-60 days", owner_role="VP Regulatory Affairs", description="Merge regulatory filing plans for Seagen's pipeline programs into Pfizer's global submission calendar.", success_metric="Joint regulatory calendar published", risks=["Clinical trial or regulatory delays"]),
            IntegrationAction(title="Pilot an accelerated ex-U.S. launch for one approved therapy", phase="61-100 days", owner_role="VP Oncology Commercial", description="Test the assumed launch-acceleration uplift on a single approved therapy in one ex-U.S. market before committing to the revenue scenario across the portfolio.", linked_opportunity="Accelerate Seagen ADC launches into Pfizer's ex-U.S. oncology markets", success_metric="Measured launch-timeline acceleration vs. Seagen's standalone baseline", risks=["No comparable prior case to benchmark against"]),
        ],
        governance="Joint steering committee (Pfizer + Seagen leadership) meets weekly for the first 100 days; IMO reports variances against this plan.",
    )


def run_pfizer_seagen_pipeline() -> tuple[AnalysisRecord, list[dict]]:
    """A second, distinctly different demo case — large-cap pharma acquiring a clinical/commercial
    biotech, instead of e-commerce acquiring grocery retail — so the demo isn't just one industry's
    story. Deliberately lands on a different verdict (proceed with conditions, not further diligence)
    by giving the weak revenue opportunity a citation (so it isn't flagged as ungrounded) while still
    giving Red-Team a real, separate basis — the unvalidated uplift rate — to challenge it on.
    """
    transaction = TransactionAssumptions(
        acquirer_name="Pfizer Inc.",
        target_name="Seagen Inc.",
        announcement_date="2023-03-13",
        deal_value=43_000_000_000,
        deal_structure="All-cash merger",
        user_notes="Demo mode: synthetic sample documents, no live OpenAI calls.",
    )
    financial_assessment, tool_call_log, baselines = _pfizer_financial_assessment()
    strategy_assessment = _pfizer_strategy_assessment()
    red_team_assessment = _seagen_red_team_assessment()

    record = AnalysisRecord(
        transaction=transaction,
        acquirer_profile=_pfizer_profile(),
        target_profile=_seagen_profile(),
        strategic_rationale=_pfizer_seagen_strategic_rationale(),
        financial_baselines=baselines,
        opportunities=financial_assessment.opportunities,
        agent_assessments=[strategy_assessment, financial_assessment, red_team_assessment],
        risks=_pfizer_seagen_risks(),
        integration_plan=_pfizer_seagen_integration_plan(),
        assumptions_approved=True,
        executive_summary=(
            "[DEMO MODE — synthetic sample documents, not a live analysis] Pfizer's acquisition of "
            "Seagen pairs an approved, if still-unprofitable, oncology ADC platform with Pfizer's "
            "global regulatory and commercial infrastructure. The Strategy and Financial agents see "
            "a credible cost-synergy case in ex-U.S. infrastructure consolidation; the Red-Team "
            "agent's strongest objections are unaddressed key-scientist retention risk and an "
            "ex-U.S. launch-acceleration revenue estimate that rests on an unvalidated uplift rate."
        ),
    )
    return record, tool_call_log


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


DEMO_CASES = [
    {
        "label": "Amazon acquires Whole Foods",
        "subtitle": "E-commerce → grocery retail · $13.7B · 2017",
        "teaser": "Would you sign off on this one?",
        "run": run_demo_pipeline,
        "document_names": DOCUMENT_NAMES,
    },
    {
        "label": "Pfizer acquires Seagen",
        "subtitle": "Pharma → oncology biotech · $43B · 2023",
        "teaser": "A very different deal, a very different verdict.",
        "run": run_pfizer_seagen_pipeline,
        "document_names": PFIZER_SEAGEN_DOCUMENT_NAMES,
    },
]
