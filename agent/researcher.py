"""Stage 2-3: Document Researcher.

Identifies what's available in the uploaded documents and extracts company
profiles and strategic rationale as structured, cited output.
"""

from __future__ import annotations

from agent.llm import get_client, run_structured
from schemas.analysis_models import CompanyProfile, StrategicRationale

RESEARCHER_INSTRUCTIONS = """You are a due-diligence researcher for an M&A analysis tool. You only
state facts that are directly supported by an available tool: uploaded documents via file_search,
or public sources via web_search. Every fact you report must carry a citation. For a document
citation, give the source document name and a page/section reference. For a web citation, give the
page title as source_document, its URL as source_url, and set location to "web". If a figure or
claim is not directly supported by a document or a web source, do not invent it — omit it or mark
it as unavailable. Never mix assumptions into fields meant for documented facts."""


def identify_available_information(vector_store_id: str) -> str:
    """Plain-text stage: what documents are present and what they seem to cover."""
    client = get_client()
    response = client.responses.create(
        model="gpt-4.1",
        instructions=RESEARCHER_INSTRUCTIONS,
        input=(
            "List the documents available via file_search and, for each, summarize in 1-2 "
            "sentences what kind of information it contains (financials, strategy, risk factors, "
            "segment detail, etc). This is a scoping step, not final analysis."
        ),
        tools=[{"type": "file_search", "vector_store_ids": [vector_store_id]}],
    )
    return response.output_text


def extract_company_profile(
    company_name: str,
    role: str,
    vector_store_id: str | None = None,
    enable_web_search: bool = False,
) -> CompanyProfile:
    source_note = (
        "Use the uploaded documents and public web sources, preferring the uploaded documents "
        "when both cover the same fact."
        if vector_store_id and enable_web_search
        else "Use the uploaded documents."
        if vector_store_id
        else "Use public web sources."
    )
    prompt = (
        f"Build a company profile for {company_name}, which is the {role} in this transaction. "
        "Extract business description, most recent fiscal year revenue, revenue growth rate, "
        f"operating margin, employee count, and key business segments, wherever available. {source_note} "
        "Attach an EvidenceItem with citations for every populated financial field."
    )
    return run_structured(RESEARCHER_INSTRUCTIONS, prompt, CompanyProfile, vector_store_id, enable_web_search)


def extract_strategic_rationale(
    acquirer_name: str,
    target_name: str,
    vector_store_id: str | None = None,
    enable_web_search: bool = False,
) -> StrategicRationale:
    source_note = (
        "Use the uploaded documents and public web sources, preferring the uploaded documents "
        "when both cover the same point."
        if vector_store_id and enable_web_search
        else "Use the uploaded documents."
        if vector_store_id
        else "Use public web sources."
    )
    prompt = (
        f"Explain the strategic rationale for {acquirer_name} acquiring {target_name}: what "
        f"capability, market, or asset gap this closes, and why now. {source_note} Support each "
        "point with an EvidenceItem citing the source."
    )
    return run_structured(RESEARCHER_INSTRUCTIONS, prompt, StrategicRationale, vector_store_id, enable_web_search)


def search_uploaded_documents(query: str, vector_store_id: str, max_results: int = 5) -> dict:
    """Ad hoc semantic search over the uploaded documents; used as a function tool by later stages."""
    client = get_client()
    results = client.vector_stores.search(vector_store_id=vector_store_id, query=query, max_num_results=max_results)
    return {
        "query": query,
        "matches": [
            {
                "file_name": getattr(r, "filename", None),
                "score": getattr(r, "score", None),
                "text": "".join(c.text for c in getattr(r, "content", []))[:1000],
            }
            for r in results.data
        ],
    }


SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "name": "search_uploaded_documents",
    "description": "Semantic search over the uploaded deal documents. Use to find supporting evidence before making a claim.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "vector_store_id": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["query", "vector_store_id", "max_results"],
        "additionalProperties": False,
    },
}
