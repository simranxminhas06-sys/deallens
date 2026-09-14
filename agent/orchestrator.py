"""Wires the pipeline stages together. Each function is a discrete, resumable
step so the Streamlit app can call them one at a time and show progress —
this is deliberately not a black-box multi-agent loop.
"""

from __future__ import annotations

from agent import financial_agent, integration_planner, red_team_agent, researcher, strategy_agent
from agent.llm import create_vector_store_with_files, get_client
from agent.reviewer import review_analysis
from schemas.analysis_models import AnalysisRecord, TransactionAssumptions


def ingest_documents(file_paths: list[str]) -> tuple[str, str]:
    """Returns (vector_store_id, availability_summary)."""
    vector_store_id = create_vector_store_with_files(file_paths)
    summary = researcher.identify_available_information(vector_store_id)
    return vector_store_id, summary


def start_analysis(transaction: TransactionAssumptions) -> AnalysisRecord:
    return AnalysisRecord(transaction=transaction)


def run_research_stage(
    record: AnalysisRecord, vector_store_id: str | None = None, enable_web_search: bool = False
) -> AnalysisRecord:
    """vector_store_id may be None if the user chose to research via web_search only —
    see the "Also use live web search" option on the Create Analysis page.
    """
    record.acquirer_profile = researcher.extract_company_profile(
        record.transaction.acquirer_name, "acquirer", vector_store_id, enable_web_search
    )
    record.target_profile = researcher.extract_company_profile(
        record.transaction.target_name, "target", vector_store_id, enable_web_search
    )
    record.strategic_rationale = researcher.extract_strategic_rationale(
        record.transaction.acquirer_name, record.transaction.target_name, vector_store_id, enable_web_search
    )
    return record


def run_assessment_stage(record: AnalysisRecord, vector_store_id: str) -> tuple[AnalysisRecord, list[dict]]:
    """Strategy, Financial, and Red-Team agents assess the deal independently, then the
    Red-Team agent challenges the other two — this is the debate shown on the Independent
    Assessments page.
    """
    if not record.assumptions_approved:
        raise ValueError("Assumptions must be approved before running financial scenario analysis.")

    strategy_assessment = strategy_agent.assess(
        record.transaction.acquirer_name, record.transaction.target_name, vector_store_id
    )
    financial_assessment, tool_call_log, baselines = financial_agent.assess(
        record.transaction.acquirer_name,
        record.transaction.target_name,
        vector_store_id,
        record.transaction.user_notes or "",
    )
    red_team_assessment = red_team_agent.assess(
        record.transaction.acquirer_name,
        record.transaction.target_name,
        strategy_assessment,
        financial_assessment,
        vector_store_id,
    )

    record.agent_assessments = [strategy_assessment, financial_assessment, red_team_assessment]
    record.opportunities = financial_assessment.opportunities
    record.financial_baselines = baselines
    return record, tool_call_log


def run_integration_stage(record: AnalysisRecord, vector_store_id: str) -> AnalysisRecord:
    context = (
        f"{record.transaction.acquirer_name} acquiring {record.transaction.target_name}. "
        f"Strategic rationale: {record.strategic_rationale.summary if record.strategic_rationale else 'n/a'}"
    )
    record.risks = integration_planner.identify_risks(context, record.opportunities, vector_store_id)
    record.integration_plan = integration_planner.build_integration_plan(
        context, record.opportunities, record.risks, vector_store_id
    )
    return record


def run_review_stage(
    record: AnalysisRecord, tool_call_log: list[dict], valid_document_names: set[str]
) -> AnalysisRecord:
    record.review = review_analysis(record, tool_call_log, valid_document_names)
    return record


def generate_executive_summary(record: AnalysisRecord, vector_store_id: str) -> AnalysisRecord:
    client = get_client()
    opp_lines = "\n".join(
        f"- {o.title}: ${o.estimated_value.base:,.0f} base ({o.category.value})" for o in record.opportunities
    )
    risk_lines = "\n".join(f"- {r.title} ({r.severity.value})" for r in record.risks)
    prompt = (
        f"Write a 200-300 word executive summary for a value-creation analysis of "
        f"{record.transaction.acquirer_name} acquiring {record.transaction.target_name}.\n\n"
        f"Strategic rationale: {record.strategic_rationale.summary if record.strategic_rationale else ''}\n\n"
        f"Opportunities:\n{opp_lines}\n\nTop risks:\n{risk_lines}\n\n"
        "Be direct about which figures are calculated estimates vs. documented facts. "
        "Do not introduce any new numbers not listed above."
    )
    response = client.responses.create(
        model="gpt-4.1",
        instructions="You are writing the executive summary section of an M&A value-creation report.",
        input=prompt,
        tools=[{"type": "file_search", "vector_store_ids": [vector_store_id]}],
    )
    record.executive_summary = response.output_text
    return record
