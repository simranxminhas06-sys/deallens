"""Strategy Agent: tests the acquisition rationale from a market/competitive lens.

Assesses market attractiveness, growth opportunities, and competitive
positioning — deliberately independent of the Financial Agent so the two can
disagree independently rather than sharing one blended narrative.
"""

from __future__ import annotations

from agent.llm import run_structured
from schemas.analysis_models import AgentAssessment, AgentRole

STRATEGY_INSTRUCTIONS = """You are the Strategy Agent in an M&A investment committee. You argue the
strategic case for or against this acquisition based only on the uploaded documents. State your
position as a single direct paragraph, in your own voice, the way you would speak in a partner
meeting (e.g. "The acquisition creates an attractive new customer channel, but..."). Back every
factual claim with a citation. Distinguish documented facts from your own strategic judgment —
judgment calls should be marked as hypotheses, not documented facts."""


def assess(acquirer_name: str, target_name: str, vector_store_id: str) -> AgentAssessment:
    prompt = (
        f"Evaluate the strategic rationale for {acquirer_name} acquiring {target_name}:\n"
        "- Is the target market attractive (growth, competitive intensity, barriers to entry)?\n"
        "- Does the stated or implied acquisition rationale hold up against the documented facts?\n"
        "- What growth opportunities does this combination open up?\n"
        "- How does the combined company compare to key competitors mentioned in the documents?\n\n"
        "Return an AgentAssessment with role='strategy', a one-paragraph `position` stating your "
        "overall stance, and `key_findings` as cited EvidenceItems. Leave `opportunities` and "
        "`challenges` empty — those belong to other agents."
    )
    result = run_structured(STRATEGY_INSTRUCTIONS, prompt, AgentAssessment, vector_store_id)
    result.role = AgentRole.STRATEGY
    return result
