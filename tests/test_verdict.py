from agent.verdict import compute_verdict
from schemas.analysis_models import (
    AgentAssessment,
    AgentRole,
    Challenge,
    FinancingStructure,
    ReviewIssue,
    ReviewResult,
    RiskSeverity,
    TransactionAssumptions,
    VerdictLevel,
)

TRANSACTION = TransactionAssumptions(acquirer_name="A", target_name="B", deal_value=1_000_000_000)


def _assessment(role: AgentRole, challenges=None) -> AgentAssessment:
    return AgentAssessment(role=role, position="p", challenges=challenges or [])


def _clean_review(coverage: float = 95.0) -> ReviewResult:
    return ReviewResult(passed=True, issues=[], citation_coverage_pct=coverage)


def test_proceed_when_clean():
    verdict = compute_verdict(_clean_review(), [_assessment(AgentRole.FINANCIAL)], 50_000_000, TRANSACTION)
    assert verdict.level == VerdictLevel.PROCEED
    assert not verdict.conditions


def test_proceed_with_conditions_on_high_red_team_challenge_with_clean_review():
    challenge = Challenge(
        target_agent=AgentRole.FINANCIAL,
        target_claim="Cross-sell opportunity",
        critique="No cited evidence for the uplift rate.",
        severity=RiskSeverity.HIGH,
    )
    verdict = compute_verdict(
        _clean_review(), [_assessment(AgentRole.RED_TEAM, [challenge])], 50_000_000, TRANSACTION
    )
    assert verdict.level == VerdictLevel.PROCEED_WITH_CONDITIONS
    assert len(verdict.conditions) == 1
    assert "Cross-sell opportunity" in verdict.conditions[0]


def test_further_diligence_on_single_high_review_issue():
    review = ReviewResult(
        passed=False,
        issues=[
            ReviewIssue(
                severity=RiskSeverity.HIGH,
                stage="value_creation",
                item_title="Cross-sell",
                problem="No citation to any uploaded document.",
                recommendation="Ground it or remove it.",
            )
        ],
        citation_coverage_pct=90.0,
    )
    verdict = compute_verdict(review, [_assessment(AgentRole.FINANCIAL)], 50_000_000, TRANSACTION)
    assert verdict.level == VerdictLevel.FURTHER_DILIGENCE
    assert "No citation" in verdict.reasons[0]


def test_further_diligence_on_low_citation_coverage_alone():
    verdict = compute_verdict(_clean_review(coverage=40.0), [], 50_000_000, TRANSACTION)
    assert verdict.level == VerdictLevel.FURTHER_DILIGENCE


def test_proceed_still_proceeds_with_accretion_note_when_mildly_accretive():
    transaction = TransactionAssumptions(
        acquirer_name="A",
        target_name="B",
        deal_value=1_000_000_000,
        financing=FinancingStructure(
            cash_pct=1.0,
            stock_pct=0.0,
            debt_pct=0.0,
            foregone_interest_rate=0.04,
            acquirer_tax_rate=0.21,
            acquirer_share_price=100.0,
            acquirer_shares_outstanding=100_000_000,
            acquirer_net_income=500_000_000,
        ),
    )
    verdict = compute_verdict(_clean_review(), [_assessment(AgentRole.FINANCIAL)], 50_000_000, transaction)
    assert verdict.level == VerdictLevel.PROCEED
    assert any("accretive" in r for r in verdict.reasons)


def test_further_diligence_when_severely_dilutive_at_run_rate():
    transaction = TransactionAssumptions(
        acquirer_name="A",
        target_name="B",
        deal_value=1_000_000_000,
        financing=FinancingStructure(
            cash_pct=0.0,
            stock_pct=1.0,
            debt_pct=0.0,
            acquirer_tax_rate=0.21,
            acquirer_share_price=10.0,
            acquirer_shares_outstanding=10_000_000,
            acquirer_net_income=10_000_000,
        ),
    )
    verdict = compute_verdict(_clean_review(), [_assessment(AgentRole.FINANCIAL)], 5_000_000, transaction)
    assert verdict.level == VerdictLevel.FURTHER_DILIGENCE
    assert any("dilutive" in r for r in verdict.reasons)


def test_do_not_proceed_when_review_issues_and_red_team_both_compound():
    review = ReviewResult(
        passed=False,
        issues=[
            ReviewIssue(severity=RiskSeverity.HIGH, stage="s1", item_title="A", problem="p1", recommendation="r1"),
            ReviewIssue(severity=RiskSeverity.HIGH, stage="s2", item_title="B", problem="p2", recommendation="r2"),
        ],
        citation_coverage_pct=50.0,
    )
    challenge = Challenge(target_agent=AgentRole.FINANCIAL, target_claim="X", critique="bad", severity=RiskSeverity.HIGH)
    verdict = compute_verdict(review, [_assessment(AgentRole.RED_TEAM, [challenge])], 50_000_000, TRANSACTION)
    assert verdict.level == VerdictLevel.DO_NOT_PROCEED


def test_reasons_include_deal_economics_note_when_deal_value_present():
    verdict = compute_verdict(_clean_review(), [], 50_000_000, TRANSACTION)
    assert any("deal value" in r for r in verdict.reasons)


def test_reasons_omit_deal_economics_note_without_deal_value():
    no_deal_value = TransactionAssumptions(acquirer_name="A", target_name="B")
    verdict = compute_verdict(_clean_review(), [], 50_000_000, no_deal_value)
    assert not any("deal value" in r for r in verdict.reasons)


def test_medium_severity_challenge_does_not_trigger_conditions():
    challenge = Challenge(target_agent=AgentRole.FINANCIAL, target_claim="X", critique="minor", severity=RiskSeverity.MEDIUM)
    verdict = compute_verdict(_clean_review(), [_assessment(AgentRole.RED_TEAM, [challenge])], 50_000_000, TRANSACTION)
    assert verdict.level == VerdictLevel.PROCEED
