"""Red-Team Agent: argues against the transaction, hunts for unsupported
claims, and challenges the other agents' estimates and risk blind spots.

Combines an LLM pass (grounded via search_uploaded_documents) with a
deterministic pass that reuses the same precision/citation heuristics as
agent/reviewer.py — the red team should catch what a spreadsheet-literal
check catches, not just what reads persuasively.
"""

from __future__ import annotations

from agent.llm import run_with_tools
from agent.researcher import SEARCH_TOOL_SCHEMA, search_uploaded_documents
from schemas.analysis_models import AgentAssessment, AgentRole, Challenge, RiskSeverity
from tools.financial_calculator import calculate_precision_flag

RED_TEAM_INSTRUCTIONS = """You are the Red-Team Agent in an M&A investment committee. Your job is
to argue against the transaction as proposed: find unsupported claims, challenge financial
estimates that lack evidence, and surface risks the Strategy and Financial agents overlooked
(cannibalization, integration cost, execution risk, competitive response). Use
search_uploaded_documents to check whether a claim is actually supported before challenging it —
a challenge grounded in a missing citation is stronger than a generic objection. State your
overall position as one direct paragraph, then list specific challenges, each naming which agent
and which exact claim/opportunity title you are challenging."""


def _deterministic_challenges(financial_opportunities) -> list[Challenge]:
    challenges = []
    for o in financial_opportunities:
        if not o.evidence or not any(e.citations for e in o.evidence):
            challenges.append(
                Challenge(
                    target_agent=AgentRole.FINANCIAL,
                    target_claim=o.title,
                    critique="No cited evidence supports this opportunity — it should be treated as a hypothesis, not a scenario ready for approval.",
                    severity=RiskSeverity.HIGH,
                )
            )
        flag = calculate_precision_flag(o.estimated_value.base)
        if flag["flagged"]:
            challenges.append(
                Challenge(
                    target_agent=AgentRole.FINANCIAL,
                    target_claim=o.title,
                    critique=f"Base estimate (${o.estimated_value.base:,.0f}) implies more precision than diligence-stage analysis supports.",
                    severity=RiskSeverity.LOW,
                )
            )
    return challenges


def assess(
    acquirer_name: str,
    target_name: str,
    strategy_assessment: AgentAssessment,
    financial_assessment: AgentAssessment,
    vector_store_id: str,
) -> AgentAssessment:
    opp_text = "\n".join(
        f"- [{o.title}] base ${o.estimated_value.base:,.0f}, assumptions: {'; '.join(o.assumptions)}"
        for o in financial_assessment.opportunities
    )
    prompt = (
        f"Strategy Agent's position on {acquirer_name} acquiring {target_name}:\n{strategy_assessment.position}\n\n"
        f"Financial Agent's position:\n{financial_assessment.position}\n\n"
        f"Financial Agent's opportunities:\n{opp_text}\n\n"
        "Challenge what deserves challenging. For each challenge, set target_agent to 'strategy' or "
        "'financial' and target_claim to the exact opportunity title or claim text you're disputing. "
        "Also check for risks neither agent raised (cannibalization, integration cost, execution "
        "risk) and add those as challenges against whichever agent's silence is most relevant. "
        "Return role='red_team'. Leave `opportunities` empty."
    )
    result, _ = run_with_tools(
        RED_TEAM_INSTRUCTIONS,
        prompt,
        AgentAssessment,
        [SEARCH_TOOL_SCHEMA],
        {"search_uploaded_documents": search_uploaded_documents},
        vector_store_id,
    )
    result.role = AgentRole.RED_TEAM
    result.challenges = result.challenges + _deterministic_challenges(financial_assessment.opportunities)
    return result
