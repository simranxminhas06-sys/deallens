"""Optional stage: Investment Committee verdict.

Deterministic, rule-based synthesis of the reviewer's findings and the Red-Team's
challenges into a single recommendation — not another LLM call rendering its own
opinion. Every reason cited here traces to a specific ReviewIssue or Challenge already
in the record, the same "no invented evidence" discipline as the rest of the pipeline.
This is what lets the verdict work in Demo mode with no API key.
"""

from __future__ import annotations

from schemas.analysis_models import (
    AgentAssessment,
    AgentRole,
    Challenge,
    ReviewResult,
    RiskSeverity,
    TransactionAssumptions,
    Verdict,
    VerdictLevel,
)
from tools.financial_calculator import calculate_accretion_dilution

ROLE_LABEL = {AgentRole.STRATEGY: "Strategy Agent", AgentRole.FINANCIAL: "Financial Agent", AgentRole.RED_TEAM: "Red-Team Agent"}


def _high_severity_challenges(agent_assessments: list[AgentAssessment]) -> list[Challenge]:
    challenges = []
    for a in agent_assessments:
        challenges += [c for c in a.challenges if c.severity == RiskSeverity.HIGH]
    return challenges


def _deal_economics_note(total_value_creation: float, transaction: TransactionAssumptions) -> str | None:
    if not transaction.deal_value or transaction.deal_value <= 0:
        return None
    pct = total_value_creation / transaction.deal_value * 100
    return f"Identified value creation (${total_value_creation:,.0f}) is {pct:.1f}% of the ${transaction.deal_value:,.0f} deal value."


_SEVERE_DILUTION_THRESHOLD_PCT = -10.0


def _accretion_dilution_note(total_value_creation: float, transaction: TransactionAssumptions) -> tuple[str, bool] | None:
    """Returns (note, still_severely_dilutive_at_run_rate) if a financing structure is on the
    transaction, else None. total_value_creation is treated as the pre-tax run-rate synergy
    figure and taxed at the acquirer's rate to approximate an after-tax add to combined net income —
    the same figure the rest of the pipeline already uses everywhere else, just made after-tax here.
    """
    t = transaction
    if not t.deal_value or t.deal_value <= 0 or not t.financing:
        return None
    f = t.financing
    result = calculate_accretion_dilution(
        deal_value=t.deal_value,
        cash_pct=f.cash_pct,
        stock_pct=f.stock_pct,
        debt_pct=f.debt_pct,
        new_debt_interest_rate=f.new_debt_interest_rate,
        foregone_interest_rate=f.foregone_interest_rate,
        acquirer_tax_rate=f.acquirer_tax_rate,
        acquirer_share_price=f.acquirer_share_price,
        acquirer_shares_outstanding=f.acquirer_shares_outstanding,
        acquirer_net_income=f.acquirer_net_income,
        target_net_income=f.target_net_income or 0.0,
        synergies_after_tax_run_rate=total_value_creation * (1 - f.acquirer_tax_rate),
    )
    day1_pct = result["accretion_dilution_pct_day1"]
    run_rate_pct = result["accretion_dilution_pct_run_rate"]
    day1_word = "accretive" if day1_pct >= 0 else "dilutive"
    run_rate_word = "accretive" if run_rate_pct >= 0 else "dilutive"
    note = (
        f"EPS impact of the proposed financing mix: {abs(day1_pct):.1f}% {day1_word} on Day 1, "
        f"{abs(run_rate_pct):.1f}% {run_rate_word} once identified synergies reach full run-rate."
    )
    return note, run_rate_pct < _SEVERE_DILUTION_THRESHOLD_PCT


def compute_verdict(
    review: ReviewResult,
    agent_assessments: list[AgentAssessment],
    total_value_creation: float,
    transaction: TransactionAssumptions,
    coverage_floor_pct: float = 70.0,
) -> Verdict:
    high_review_issues = [i for i in review.issues if i.severity == RiskSeverity.HIGH]
    high_challenges = _high_severity_challenges(agent_assessments)
    economics_note = _deal_economics_note(total_value_creation, transaction)
    dilution_result = _accretion_dilution_note(total_value_creation, transaction)
    dilution_note = dilution_result[0] if dilution_result else None
    severely_dilutive = dilution_result[1] if dilution_result else False

    if len(high_review_issues) >= 2 and high_challenges:
        reasons = [f"Reviewer: {i.stage} — {i.problem}" for i in high_review_issues]
        reasons += [
            f"Red-Team, challenging {ROLE_LABEL.get(c.target_agent, c.target_agent.value)}'s "
            f'"{c.target_claim}": {c.critique}'
            for c in high_challenges
        ]
        if economics_note:
            reasons.append(economics_note)
        if dilution_note:
            reasons.append(dilution_note)
        return Verdict(level=VerdictLevel.DO_NOT_PROCEED, reasons=reasons)

    if high_review_issues:
        reasons = [f"{i.stage}: {i.problem}" for i in high_review_issues]
        if economics_note:
            reasons.append(economics_note)
        if dilution_note:
            reasons.append(dilution_note)
        return Verdict(level=VerdictLevel.FURTHER_DILIGENCE, reasons=reasons)

    if review.citation_coverage_pct is not None and review.citation_coverage_pct < coverage_floor_pct:
        reasons = [
            f"Citation coverage is {review.citation_coverage_pct:.1f}%, below the "
            f"{coverage_floor_pct:.0f}% bar for a decision-grade analysis."
        ]
        if economics_note:
            reasons.append(economics_note)
        if dilution_note:
            reasons.append(dilution_note)
        return Verdict(level=VerdictLevel.FURTHER_DILIGENCE, reasons=reasons)

    if high_challenges:
        reasons = ["No unresolved high-severity reviewer issues; citation coverage meets the bar."]
        if economics_note:
            reasons.append(economics_note)
        if dilution_note:
            reasons.append(dilution_note)
        conditions = [
            f'Resolve before proceeding — Red-Team on {ROLE_LABEL.get(c.target_agent, c.target_agent.value)}\'s '
            f'"{c.target_claim}": {c.critique}'
            for c in high_challenges
        ]
        return Verdict(level=VerdictLevel.PROCEED_WITH_CONDITIONS, reasons=reasons, conditions=conditions)

    reasons = [
        "No high-severity reviewer issues.",
        "No high-severity Red-Team challenges.",
    ]
    if review.citation_coverage_pct is not None:
        reasons.append(f"Citation coverage: {review.citation_coverage_pct:.1f}%.")
    if economics_note:
        reasons.append(economics_note)
    if dilution_note:
        reasons.append(dilution_note)

    if severely_dilutive:
        reasons.append(
            f"Still more than {abs(_SEVERE_DILUTION_THRESHOLD_PCT):.0f}% dilutive to EPS even after "
            "identified synergies reach full run-rate — financing structure needs further diligence."
        )
        return Verdict(level=VerdictLevel.FURTHER_DILIGENCE, reasons=reasons)

    return Verdict(level=VerdictLevel.PROCEED, reasons=reasons)
