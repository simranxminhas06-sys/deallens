"""Verifies the no-API-key demo pipeline produces a valid, internally
consistent AnalysisRecord and that the real reviewer catches the
deliberately under-evidenced opportunity — this is the test suite you can
run to sanity-check the app without an OPENAI_API_KEY.
"""

from agent.demo_fixtures import DOCUMENT_NAMES, run_demo_pipeline
from agent.reviewer import review_analysis
from schemas.analysis_models import AgentRole


def test_demo_pipeline_produces_complete_record():
    record, _ = run_demo_pipeline()
    assert record.acquirer_profile is not None
    assert record.target_profile is not None
    assert record.strategic_rationale is not None
    assert len(record.financial_baselines) == 3
    assert len(record.opportunities) == 3
    assert record.risks
    assert record.integration_plan is not None
    assert record.assumptions_approved is True


def test_demo_pipeline_has_all_three_assessment_agents():
    record, _ = run_demo_pipeline()
    roles = {a.role for a in record.agent_assessments}
    assert roles == {AgentRole.STRATEGY, AgentRole.FINANCIAL, AgentRole.RED_TEAM}


def test_demo_red_team_challenges_the_financial_agent():
    record, _ = run_demo_pipeline()
    red_team = next(a for a in record.agent_assessments if a.role == AgentRole.RED_TEAM)
    assert any(c.target_agent == AgentRole.FINANCIAL for c in red_team.challenges)


def test_demo_reviewer_flags_the_uncited_revenue_opportunity():
    record, tool_call_log = run_demo_pipeline()
    review = review_analysis(record, tool_call_log, DOCUMENT_NAMES)
    assert review.passed is False
    uncited_issue = [i for i in review.issues if "Cross-sell Amazon Prime" in i.item_title]
    assert uncited_issue


def test_demo_reviewer_does_not_flag_the_cited_cost_opportunity_calculation():
    record, tool_call_log = run_demo_pipeline()
    review = review_analysis(record, tool_call_log, DOCUMENT_NAMES)
    calc_issues = [
        i for i in review.issues
        if "Consolidate overlapping distribution" in i.item_title and "does not match" in i.problem
    ]
    assert calc_issues == []


def test_demo_pipeline_runs_deterministically():
    record_a, _ = run_demo_pipeline()
    record_b, _ = run_demo_pipeline()
    assert [o.title for o in record_a.opportunities] == [o.title for o in record_b.opportunities]
    assert [o.estimated_value.base for o in record_a.opportunities] == [o.estimated_value.base for o in record_b.opportunities]
