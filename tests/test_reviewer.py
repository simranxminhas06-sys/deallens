from agent.reviewer import review_analysis
from schemas.analysis_models import (
    AnalysisRecord,
    Citation,
    ClaimType,
    Difficulty,
    EstimatedValue,
    EvidenceItem,
    TransactionAssumptions,
    ValueOpportunity,
)


def _record(opportunities=None) -> AnalysisRecord:
    return AnalysisRecord(
        transaction=TransactionAssumptions(acquirer_name="Acme Co", target_name="Target Co"),
        opportunities=opportunities or [],
    )


def _opportunity(title, low, base, high, cited=True, calc_method="calculate_savings_scenario"):
    citations = [Citation(source_document="target_10k.md", location="p.4")] if cited else []
    return ValueOpportunity(
        title=title,
        category="cost_synergy",
        rationale="Overlapping distribution centers can be consolidated.",
        evidence=[
            EvidenceItem(
                claim="Both companies operate distribution centers in the same region.",
                claim_type=ClaimType.DOCUMENTED_FACT,
                citations=citations,
            )
        ],
        estimated_value=EstimatedValue(low=low, base=base, high=high),
        assumptions=["Facility costs can be reduced by 15%"],
        implementation_difficulty=Difficulty.MEDIUM,
        time_horizon="12-18 months",
        key_risks=["Service disruption"],
        calculation_method=calc_method,
    )


def test_flags_missing_citation():
    opp = _opportunity("Consolidate distribution", 2_000_000, 3_500_000, 5_000_000, cited=False)
    result = review_analysis(_record([opp]))
    assert any("no citation" in i.problem.lower() for i in result.issues)
    assert result.passed is False


def test_passes_with_citation_and_matching_calculation():
    opp = _opportunity("Consolidate distribution", 2_000_000, 3_500_000, 5_000_000, cited=True)
    tool_log = [
        {
            "name": "calculate_savings_scenario",
            "arguments": {},
            "result": {"low": 2_000_000, "base": 3_500_000, "high": 5_000_000},
        }
    ]
    result = review_analysis(_record([opp]), tool_call_log=tool_log)
    high_severity = [i for i in result.issues if i.severity == "high"]
    assert high_severity == []
    assert result.passed is True


def test_flags_calculation_mismatch():
    opp = _opportunity("Consolidate distribution", 2_000_000, 3_500_000, 5_000_000, cited=True)
    tool_log = [
        {
            "name": "calculate_savings_scenario",
            "arguments": {},
            "result": {"low": 100, "base": 200, "high": 300},
        }
    ]
    result = review_analysis(_record([opp]), tool_call_log=tool_log)
    assert any("does not match" in i.problem for i in result.issues)
    assert result.passed is False


def test_flags_duplicate_opportunities():
    opp_a = _opportunity("Consolidate distribution centers", 2_000_000, 3_500_000, 5_000_000)
    opp_b = _opportunity("Consolidate distribution center operations", 2_000_000, 3_500_000, 5_000_000)
    result = review_analysis(_record([opp_a, opp_b]))
    assert any("duplicate" in i.problem.lower() for i in result.issues)


def test_flags_false_precision():
    opp = _opportunity("Consolidate distribution", 2_487_213, 3_512_984, 5_998_112)
    result = review_analysis(_record([opp]))
    assert any("more precision" in i.problem for i in result.issues)


def test_citation_coverage_percentage():
    cited = _opportunity("A", 1, 2, 3, cited=True)
    uncited = _opportunity("B totally different lever name", 1, 2, 3, cited=False)
    result = review_analysis(_record([cited, uncited]))
    assert result.citation_coverage_pct == 50.0


def test_flags_document_grounding():
    opp = _opportunity("Consolidate distribution", 2_000_000, 3_500_000, 5_000_000, cited=True)
    result = review_analysis(_record([opp]), valid_document_names={"other_document.md"})
    assert any("unrelated to supplied evidence" in i.problem for i in result.issues)
