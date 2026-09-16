"""Stage 4-5: Financial baseline + Value Creation Analyst.

Computes baseline metrics with financial_calculator tools, then proposes
revenue and cost synergy opportunities, each grounded in evidence and backed
by an explicit calculation rather than a bare guess.
"""

from __future__ import annotations

from pydantic import BaseModel

from agent.llm import run_with_tools
from agent.researcher import SEARCH_TOOL_SCHEMA, search_uploaded_documents
from schemas.analysis_models import FinancialBaseline, ValueOpportunity
from tools.financial_calculator import FUNCTION_SCHEMAS, TOOL_FUNCTIONS

ANALYST_INSTRUCTIONS = """You are a value-creation analyst for an M&A analysis tool.
Use the financial_calculator functions for every numeric estimate — never do arithmetic in
prose. Use search_uploaded_documents to find the cost bases, revenue bases, or overlap evidence
that justify an opportunity before calculating its value. Every opportunity must cite the
document evidence it is based on and list the assumptions fed into its calculation explicitly.
Do not propose more than 6 opportunities per category. Do not duplicate opportunities that
describe the same underlying lever.

For every opportunity, also estimate: cost_to_achieve (a realistic one-time cost to capture
it — integration, systems, severance, etc.; 0 only if genuinely negligible), and year_1_pct /
year_2_pct / year_3_pct (the fraction of full run-rate value realized in each of the first
three years — most synergies ramp in rather than starting at 100%; year_3_pct is usually 1.0).
Base the ramp speed on implementation_difficulty and time_horizon: a low-difficulty, short-
horizon opportunity ramps faster than a high-difficulty, long-horizon one.

When asked for dis-synergies specifically: these are value DESTROYED (customer/revenue
attrition, disruption-driven losses), not value created. Use calculate_dis_synergy_scenario,
whose attrition_pct_low/base/high mean the least/most-likely/most attrition — the opposite
sense of a synergy's uplift_pct, since more attrition is worse, not better. Do not invent a
dis-synergy that has no basis in the documents just to "balance" the case — omit the category
entirely if nothing in the evidence supports one."""

CALC_FN_BY_CATEGORY = {
    "revenue_synergy": "calculate_revenue_scenario",
    "cost_synergy": "calculate_savings_scenario",
    "dis_synergy": "calculate_dis_synergy_scenario",
}

TOOL_SCHEMAS = FUNCTION_SCHEMAS + [SEARCH_TOOL_SCHEMA]
TOOL_FUNCS = {**TOOL_FUNCTIONS, "search_uploaded_documents": search_uploaded_documents}


class _BaselineBatch(BaseModel):
    baselines: list[FinancialBaseline]


class _OpportunityBatch(BaseModel):
    opportunities: list[ValueOpportunity]


def compute_financial_baseline(
    acquirer_name: str, target_name: str, vector_store_id: str
) -> tuple[list[FinancialBaseline], list[dict]]:
    prompt = (
        f"Using search_uploaded_documents to find the relevant figures for {acquirer_name} and "
        f"{target_name}, compute baseline metrics: each company's revenue growth rate "
        "(calculate_growth_rate), operating margin (calculate_margin), and the pro-forma combined "
        "revenue (calculate_combined_metric, adjustment_pct=0). Report each as a FinancialBaseline "
        "with the method and inputs used."
    )
    result, log = run_with_tools(
        ANALYST_INSTRUCTIONS, prompt, _BaselineBatch, TOOL_SCHEMAS, TOOL_FUNCS, vector_store_id
    )
    return result.baselines, log


def generate_opportunities(
    acquirer_name: str,
    target_name: str,
    vector_store_id: str,
    category: str,
    assumptions_note: str = "",
) -> tuple[list[ValueOpportunity], list[dict]]:
    """category is 'revenue_synergy', 'cost_synergy', or 'dis_synergy'."""
    calc_fn = CALC_FN_BY_CATEGORY[category]
    if category == "dis_synergy":
        prompt = (
            f"Identify dis-synergies — value DESTROYED, not created — from combining "
            f"{acquirer_name} and {target_name}, based only on evidence in the uploaded documents "
            "(e.g. customer attrition risk, brand/positioning conflict, disruption to an existing "
            "revenue stream). Only propose one if there is real evidence for it; it is fine to "
            "return none. For each one, use search_uploaded_documents to find the relevant baseline "
            f"revenue and the evidence for attrition risk, then call {calc_fn} to produce a "
            "low/base/high estimate — state the assumption behind each of the three scenarios. Set "
            f"category='{category}' and calculation_method='{calc_fn}' on every opportunity. Flag "
            "implementation_difficulty and time_horizon realistically."
        )
    else:
        prompt = (
            f"Identify {category.replace('_', ' ')} opportunities from combining {acquirer_name} and "
            f"{target_name}, based only on evidence in the uploaded documents. For each one, use "
            f"search_uploaded_documents to find the relevant baseline figure and overlap rationale, "
            f"then call {calc_fn} to produce a low/base/high estimate — state the assumption behind "
            f"each of the three scenarios. Set category='{category}' and calculation_method='{calc_fn}' "
            "on every opportunity. Flag implementation_difficulty and time_horizon realistically."
        )
    if assumptions_note:
        prompt += f"\n\nUser-provided transaction assumptions to account for: {assumptions_note}"
    result, log = run_with_tools(
        ANALYST_INSTRUCTIONS, prompt, _OpportunityBatch, TOOL_SCHEMAS, TOOL_FUNCS, vector_store_id
    )
    return result.opportunities, log
