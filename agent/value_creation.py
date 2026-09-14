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
describe the same underlying lever."""

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
    """category is 'revenue_synergy' or 'cost_synergy'."""
    calc_fn = "calculate_revenue_scenario" if category == "revenue_synergy" else "calculate_savings_scenario"
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
