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

    if len(high_review_issues) >= 2 and high_challenges:
        reasons = [f"Reviewer: {i.stage} — {i.problem}" for i in high_review_issues]
        reasons += [
            f"Red-Team, challenging {ROLE_LABEL.get(c.target_agent, c.target_agent.value)}'s "
            f'"{c.target_claim}": {c.critique}'
            for c in high_challenges
        ]
        if economics_note:
            reasons.append(economics_note)
        return Verdict(level=VerdictLevel.DO_NOT_PROCEED, reasons=reasons)

    if high_review_issues:
        reasons = [f"{i.stage}: {i.problem}" for i in high_review_issues]
        if economics_note:
            reasons.append(economics_note)
        return Verdict(level=VerdictLevel.FURTHER_DILIGENCE, reasons=reasons)

    if review.citation_coverage_pct is not None and review.citation_coverage_pct < coverage_floor_pct:
        reasons = [
            f"Citation coverage is {review.citation_coverage_pct:.1f}%, below the "
            f"{coverage_floor_pct:.0f}% bar for a decision-grade analysis."
        ]
        if economics_note:
            reasons.append(economics_note)
        return Verdict(level=VerdictLevel.FURTHER_DILIGENCE, reasons=reasons)

    if high_challenges:
        reasons = ["No unresolved high-severity reviewer issues; citation coverage meets the bar."]
        if economics_note:
            reasons.append(economics_note)
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
    return Verdict(level=VerdictLevel.PROCEED, reasons=reasons)
