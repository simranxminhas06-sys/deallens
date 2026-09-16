"""Financial Agent: extracts figures, builds low/base/high scenarios, and
challenges unrealistic assumptions in its own numbers before they even reach
the Red-Team Agent.

This wraps the calculation logic in agent/value_creation.py — kept as a
separate module since financial_calculator is a shared tool other agents
could eventually call too — and packages the result as an AgentAssessment.
"""

from __future__ import annotations

from agent import value_creation
from agent.llm import get_client
from schemas.analysis_models import AgentAssessment, AgentRole, EvidenceItem, FinancialBaseline, ValueOpportunity

CALC_TOOL_NAMES = ("calculate_savings_scenario", "calculate_revenue_scenario", "calculate_dis_synergy_scenario")

FINANCIAL_INSTRUCTIONS = """You are the Financial Agent in an M&A investment committee. You are
skeptical by default: every dollar figure must trace to a financial_calculator tool call, and you
say so explicitly when an estimate rests on a thin or unsupported assumption. Speak in a single
direct paragraph the way you would in a partner meeting (e.g. "The revenue opportunity is
plausible, but there is insufficient evidence to support the proposed $X estimate.")."""


def _position_statement(
    acquirer_name: str, target_name: str, baselines: list[FinancialBaseline], opportunities
) -> str:
    client = get_client()
    baseline_text = "\n".join(f"- {b.metric}: {b.value:,.2f} {b.unit} ({b.method})" for b in baselines)
    opp_text = "\n".join(
        f"- {o.title} ({o.category.value}): base ${o.estimated_value.base:,.0f}, "
        f"assumptions: {'; '.join(o.assumptions)}"
        for o in opportunities
    )
    response = client.responses.create(
        model="gpt-4.1",
        instructions=FINANCIAL_INSTRUCTIONS,
        input=(
            f"Baseline metrics for {acquirer_name} / {target_name}:\n{baseline_text}\n\n"
            f"Opportunities generated:\n{opp_text}\n\n"
            "Write your one-paragraph position for the assessment transcript. Call out specifically "
            "which estimate(s), if any, rest on the weakest evidence."
        ),
    )
    return response.output_text


def _attach_calculation_inputs(opportunities: list[ValueOpportunity], tool_call_log: list[dict]) -> None:
    """Backfills calculation_inputs from the logged tool call that produced each opportunity's
    estimate, so the UI can recompute the estimate live from adjusted assumptions. Matched the same
    way agent/reviewer.py::_check_calculation_consistency cross-checks the value — deterministically,
    not by asking the model to retype the arguments it already passed to the tool.
    """
    calc_calls = [c for c in tool_call_log if c["name"] in CALC_TOOL_NAMES]
    for o in opportunities:
        if not o.calculation_method or o.calculation_inputs:
            continue
        match = next(
            (
                c
                for c in calc_calls
                if c["name"] == o.calculation_method
                and abs(c["result"].get("base", -1) - o.estimated_value.base) < max(1.0, 0.01 * abs(o.estimated_value.base))
            ),
            None,
        )
        if match:
            o.calculation_inputs = match["arguments"]


def assess(
    acquirer_name: str, target_name: str, vector_store_id: str, assumptions_note: str = ""
) -> tuple[AgentAssessment, list[dict], list[FinancialBaseline]]:
    baselines, baseline_log = value_creation.compute_financial_baseline(
        acquirer_name, target_name, vector_store_id
    )
    revenue_opps, revenue_log = value_creation.generate_opportunities(
        acquirer_name, target_name, vector_store_id, "revenue_synergy", assumptions_note
    )
    cost_opps, cost_log = value_creation.generate_opportunities(
        acquirer_name, target_name, vector_store_id, "cost_synergy", assumptions_note
    )
    dis_synergy_opps, dis_synergy_log = value_creation.generate_opportunities(
        acquirer_name, target_name, vector_store_id, "dis_synergy", assumptions_note
    )
    opportunities = revenue_opps + cost_opps + dis_synergy_opps
    tool_call_log = baseline_log + revenue_log + cost_log + dis_synergy_log
    _attach_calculation_inputs(opportunities, tool_call_log)

    position = _position_statement(acquirer_name, target_name, baselines, opportunities)
    key_findings = [
        EvidenceItem(
            claim=f"{b.metric} = {b.value:,.2f} {b.unit}",
            claim_type="calculated_result",
            notes=b.method,
        )
        for b in baselines
    ]
    assessment = AgentAssessment(
        role=AgentRole.FINANCIAL,
        position=position,
        key_findings=key_findings,
        opportunities=opportunities,
    )
    return assessment, tool_call_log, baselines
