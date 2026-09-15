"""A second, distinctly different demo case (large-cap pharma acquiring a clinical/
commercial biotech, instead of e-commerce acquiring grocery retail) — verifies it's
internally consistent AND lands on a different outcome than the Amazon/Whole Foods
case (a clean review with proceed_with_conditions, not further_diligence), so the
two demo cases actually exercise different parts of the tool, not just different
company names on the same numbers.
"""

from agent.demo_fixtures import PFIZER_SEAGEN_DOCUMENT_NAMES, run_pfizer_seagen_pipeline
from agent.reviewer import review_analysis
from agent.verdict import compute_verdict
from schemas.analysis_models import AgentRole, VerdictLevel


def _reviewed_pfizer_seagen_record():
    record, tool_call_log = run_pfizer_seagen_pipeline()
    review = review_analysis(record, tool_call_log, PFIZER_SEAGEN_DOCUMENT_NAMES)
    return record, tool_call_log, review


def test_pipeline_produces_complete_record():
    record, _ = run_pfizer_seagen_pipeline()
    assert record.acquirer_profile is not None
    assert record.target_profile is not None
    assert record.strategic_rationale is not None
    assert len(record.financial_baselines) == 3
    assert len(record.opportunities) == 2
    assert record.risks
    assert record.integration_plan is not None
    assert record.assumptions_approved is True


def test_pipeline_has_all_three_assessment_agents():
    record, _ = run_pfizer_seagen_pipeline()
    roles = {a.role for a in record.agent_assessments}
    assert roles == {AgentRole.STRATEGY, AgentRole.FINANCIAL, AgentRole.RED_TEAM}


def test_red_team_challenges_the_financial_agent():
    record, _ = run_pfizer_seagen_pipeline()
    red_team = next(a for a in record.agent_assessments if a.role == AgentRole.RED_TEAM)
    assert any(c.target_agent == AgentRole.FINANCIAL for c in red_team.challenges)


def test_review_passes_cleanly_unlike_the_amazon_case():
    """Unlike Whole Foods' revenue opportunity (zero citations), this one is cited, so
    the reviewer's document-grounding check has nothing to flag — Red-Team's objection
    to the assumed uplift rate is the only real challenge, not a missing-citation gap.
    """
    _, _, review = _reviewed_pfizer_seagen_record()
    assert review.passed is True
    assert review.citation_coverage_pct == 100.0
    assert review.issues == []


def test_verdict_is_proceed_with_conditions_not_further_diligence():
    record, _, review = _reviewed_pfizer_seagen_record()
    total_value = sum(o.estimated_value.base for o in record.opportunities)
    verdict = compute_verdict(review, record.agent_assessments, total_value, record.transaction)
    assert verdict.level == VerdictLevel.PROCEED_WITH_CONDITIONS
    assert verdict.conditions


def test_pipeline_runs_deterministically():
    record_a, _ = run_pfizer_seagen_pipeline()
    record_b, _ = run_pfizer_seagen_pipeline()
    assert [o.title for o in record_a.opportunities] == [o.title for o in record_b.opportunities]
    assert [o.estimated_value.base for o in record_a.opportunities] == [o.estimated_value.base for o in record_b.opportunities]
