"""Stage 6: Integration Planner.

Turns the approved opportunities and documented facts into an operational
risk register and a phased 100-day plan.
"""

from __future__ import annotations

from pydantic import BaseModel

from agent.llm import run_structured
from schemas.analysis_models import IntegrationPlan, Risk, ValueOpportunity

PLANNER_INSTRUCTIONS = """You are an integration planning lead for an M&A analysis tool.
Ground every risk and every action in the company profiles, strategic rationale, and approved
opportunities you are given — do not introduce new financial claims. Each integration action
must have a single accountable owner_role, fall into exactly one 100-day phase, and where it
implements an opportunity, name it in linked_opportunity. Flag risks even where mitigation is
uncertain; do not omit a known risk because the mitigation is unclear. For every risk, set both
severity (impact if it materializes) and likelihood (how likely it is to occur) — these are
often different: a low-likelihood risk can still be high-severity, and vice versa."""


class _RiskBatch(BaseModel):
    risks: list[Risk]


def identify_risks(context_summary: str, opportunities: list[ValueOpportunity], vector_store_id: str) -> list[Risk]:
    opp_text = "\n".join(f"- {o.title} ({o.category.value}): {o.rationale}" for o in opportunities)
    prompt = (
        f"Deal context:\n{context_summary}\n\nApproved opportunities:\n{opp_text}\n\n"
        "Identify operational and organizational risks to this integration: culture clash, key "
        "talent attrition, customer/channel disruption, systems integration, regulatory, and any "
        "risk directly tied to executing the opportunities above. Cite supporting evidence where "
        "the documents mention a related factor (e.g. unionized workforce, overlapping facilities)."
    )
    result = run_structured(PLANNER_INSTRUCTIONS, prompt, _RiskBatch, vector_store_id)
    return result.risks


def build_integration_plan(
    context_summary: str, opportunities: list[ValueOpportunity], risks: list[Risk], vector_store_id: str
) -> IntegrationPlan:
    opp_text = "\n".join(f"- {o.title} ({o.time_horizon})" for o in opportunities)
    risk_text = "\n".join(f"- {r.title} ({r.severity.value}): {r.mitigation}" for r in risks)
    prompt = (
        f"Deal context:\n{context_summary}\n\nApproved opportunities:\n{opp_text}\n\n"
        f"Risk register:\n{risk_text}\n\n"
        "Build a 100-day integration plan split into 0-30, 31-60, and 61-100 day phases. Prioritize "
        "actions that unlock the opportunities above or mitigate the highest-severity risks. Include "
        "a governance model (e.g. integration management office, steering committee cadence) and 3-5 "
        "guiding principles for the integration."
    )
    return run_structured(PLANNER_INSTRUCTIONS, prompt, IntegrationPlan, vector_store_id)
