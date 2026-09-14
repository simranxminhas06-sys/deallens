"""DealLens / DealRoom AI Streamlit app.

Two ways to run each page: "Demo (no API key)" loads a deterministic,
hand-authored Amazon/Whole Foods fixture (agent/demo_fixtures.py) — no
OpenAI calls, safe to click through with no cost. "Live (OpenAI)" runs the
real Responses API pipeline stage by stage.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

from agent import orchestrator
from agent.demo_fixtures import DOCUMENT_NAMES as DEMO_DOCUMENT_NAMES
from agent.demo_fixtures import run_demo_pipeline
from db.database import list_analyses, load_analysis, save_analysis
from schemas.analysis_models import AgentRole, TransactionAssumptions
from tools.report_generator import generate_report

st.set_page_config(page_title="DealLens", layout="wide")

for key, default in {
    "record": None,
    "vector_store_id": None,
    "document_names": set(),
    "tool_call_log": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.sidebar.title("DealLens")
analysis_mode = st.sidebar.radio("Analysis mode", ["Demo (no API key)", "Live (OpenAI)"], key="analysis_mode")
is_demo = analysis_mode.startswith("Demo")
if not is_demo and not os.environ.get("OPENAI_API_KEY"):
    st.sidebar.warning("OPENAI_API_KEY is not set. Set it in your environment, or switch to Demo mode.")

page = st.sidebar.radio(
    "Workflow",
    ["1. Create Analysis", "2. Evidence", "3. Agent War Room", "4. 100-Day Plan"],
)

with st.sidebar.expander("Saved analyses"):
    for row in list_analyses():
        if st.button(f"{row['acquirer_name']} / {row['target_name']} ({row['created_at'][:10]})", key=f"load_{row['id']}"):
            st.session_state.record = load_analysis(row["id"])
            st.rerun()


def _require_record():
    if st.session_state.record is None:
        st.info("Start an analysis on the 'Create Analysis' page first.")
        st.stop()


def _md(text: str) -> str:
    """Escapes '$' so Streamlit's markdown renderer doesn't mistake dollar amounts for LaTeX."""
    return text.replace("$", "\\$")


def _evidence_lines(evidence) -> None:
    for e in evidence:
        cites = "; ".join(f"{c.source_document} ({c.location})" for c in e.citations) or "no citation"
        st.markdown(f"- **[{e.claim_type.value}]** {_md(e.claim)}  \n  _{_md(cites)}_")


ROLE_LABEL = {AgentRole.STRATEGY: "Strategy Agent", AgentRole.FINANCIAL: "Financial Agent", AgentRole.RED_TEAM: "Red-Team Agent"}

# ---------------------------------------------------------------- Page 1
if page == "1. Create Analysis":
    st.header("Create Analysis")

    if is_demo:
        st.info(
            "Demo mode runs the full pipeline — company profiles, the Strategy/Financial/Red-Team "
            "war room debate, risk register, 100-day plan, and reviewer — against a hand-authored "
            "Amazon/Whole Foods fixture. No OpenAI calls, no cost. See agent/demo_fixtures.py."
        )
        if st.button("Load demo case (Amazon acquires Whole Foods)", type="primary"):
            with st.spinner("Running demo pipeline..."):
                record, tool_call_log = run_demo_pipeline()
                record = orchestrator.run_review_stage(record, tool_call_log, DEMO_DOCUMENT_NAMES)
            st.session_state.record = record
            st.session_state.tool_call_log = tool_call_log
            st.session_state.document_names = DEMO_DOCUMENT_NAMES
            st.session_state.vector_store_id = None
            save_analysis(record)
            st.success("Demo analysis loaded. Continue on Evidence, Agent War Room, or 100-Day Plan.")
    else:
        col1, col2 = st.columns(2)
        acquirer_name = col1.text_input("Acquiring company", value="Amazon.com, Inc.")
        target_name = col2.text_input("Target company", value="Whole Foods Market, Inc.")

        deal_value = col1.number_input("Deal value (USD, optional)", min_value=0.0, value=13_700_000_000.0, step=1_000_000.0)
        announcement_date = col2.text_input("Announcement date (optional)", value="2017-06-16")
        deal_structure = col1.text_input("Deal structure (optional)", value="All-cash merger")
        user_notes = st.text_area(
            "Optional assumptions about the transaction",
            value="Assume no material regulatory divestitures required.",
        )

        st.subheader("Upload documents")
        default_dir = Path("sample_data")
        use_sample = st.checkbox("Use bundled Amazon / Whole Foods sample documents", value=True)
        uploaded_files = st.file_uploader(
            "Annual reports, investor presentations, financial statements (PDF or text)",
            accept_multiple_files=True,
        )

        if st.button("Ingest documents & run research stage", type="primary"):
            file_paths: list[str] = []
            document_names: set[str] = set()
            if use_sample:
                for name in ("acquirer_amazon_overview.md", "target_whole_foods_overview.md", "transaction_assumptions.md"):
                    p = default_dir / name
                    file_paths.append(str(p))
                    document_names.add(name)
            if uploaded_files:
                tmp_dir = tempfile.mkdtemp(prefix="deallens_")
                for f in uploaded_files:
                    dest = Path(tmp_dir) / f.name
                    dest.write_bytes(f.getbuffer())
                    file_paths.append(str(dest))
                    document_names.add(f.name)

            if not file_paths:
                st.error("Upload at least one document or keep the sample documents enabled.")
            else:
                with st.spinner("Uploading documents and scoping available information..."):
                    vector_store_id, summary = orchestrator.ingest_documents(file_paths)
                    transaction = TransactionAssumptions(
                        acquirer_name=acquirer_name,
                        target_name=target_name,
                        announcement_date=announcement_date or None,
                        deal_value=deal_value or None,
                        deal_structure=deal_structure or None,
                        user_notes=user_notes or None,
                    )
                    record = orchestrator.start_analysis(transaction)
                st.session_state.vector_store_id = vector_store_id
                st.session_state.document_names = document_names
                st.session_state.availability_summary = summary

                with st.spinner("Researcher extracting company profiles and strategic rationale..."):
                    record = orchestrator.run_research_stage(record, vector_store_id)
                st.session_state.record = record
                save_analysis(record)
                st.success("Research stage complete. Continue on the Evidence page.")

        if st.session_state.get("availability_summary"):
            st.subheader("Documents available")
            st.write(st.session_state.availability_summary)

# ---------------------------------------------------------------- Page 2
elif page == "2. Evidence":
    _require_record()
    record = st.session_state.record
    st.header("Evidence")

    for label, profile in (("Acquirer", record.acquirer_profile), ("Target", record.target_profile)):
        if not profile:
            continue
        st.subheader(f"{label}: {profile.company_name}")
        st.markdown(_md(profile.business_description))
        cols = st.columns(4)
        cols[0].metric("Revenue", f"${profile.revenue:,.0f}" if profile.revenue else "n/a")
        cols[1].metric("Growth", f"{profile.revenue_growth_rate * 100:.1f}%" if profile.revenue_growth_rate else "n/a")
        cols[2].metric("Op. margin", f"{profile.operating_margin * 100:.1f}%" if profile.operating_margin else "n/a")
        cols[3].metric("Employees", f"{profile.employee_count:,}" if profile.employee_count else "n/a")
        _evidence_lines(profile.evidence)

    if record.strategic_rationale:
        st.subheader("Strategic Rationale")
        st.markdown(_md(record.strategic_rationale.summary))
        _evidence_lines(record.strategic_rationale.supporting_points)

    st.divider()
    st.subheader("Approve assumptions")
    st.write(
        "Confirm the transaction assumptions below before the agents run financial scenario "
        "analysis. Financial estimates in the war room will use these figures and the documents "
        "ingested above."
    )
    st.json(record.transaction.model_dump())
    approved = st.checkbox("I approve these assumptions for scenario analysis", value=record.assumptions_approved)
    if approved != record.assumptions_approved:
        record.assumptions_approved = approved
        save_analysis(record)
        st.session_state.record = record

# ---------------------------------------------------------------- Page 3
elif page == "3. Agent War Room":
    _require_record()
    record = st.session_state.record
    st.header("Agent War Room")
    st.caption("Strategy, Financial, and Red-Team agents assess the deal independently, then Red-Team challenges the other two.")

    if not record.assumptions_approved:
        st.warning("Approve assumptions on the Evidence page before running the war room.")
        st.stop()

    if not record.agent_assessments and st.session_state.vector_store_id:
        if st.button("Run war room (Strategy → Financial → Red-Team)", type="primary"):
            with st.spinner("Agents assessing the deal..."):
                record, tool_call_log = orchestrator.run_war_room_stage(record, st.session_state.vector_store_id)
            st.session_state.tool_call_log = tool_call_log
            st.session_state.record = record
            save_analysis(record)

    for assessment in record.agent_assessments:
        with st.chat_message("assistant"):
            st.markdown(f"**{ROLE_LABEL.get(assessment.role, assessment.role.value)}:** {_md(assessment.position)}")
            if assessment.key_findings:
                with st.expander("Key findings"):
                    _evidence_lines(assessment.key_findings)
            if assessment.opportunities:
                with st.expander(f"Opportunities ({len(assessment.opportunities)})"):
                    for o in assessment.opportunities:
                        st.markdown(f"- **{_md(o.title)}** — base \\${o.estimated_value.base:,.0f} ({_md(o.estimated_value.as_range_string())})")
                        st.caption(_md(f"Assumptions: {'; '.join(o.assumptions)}"))
            if assessment.challenges:
                for c in assessment.challenges:
                    st.markdown(
                        f"> ⚔️ challenging **{ROLE_LABEL.get(c.target_agent, c.target_agent.value)}** "
                        f"on *“{_md(c.target_claim)}”* [{c.severity.value}]: {_md(c.critique)}"
                    )

    if st.session_state.tool_call_log:
        with st.expander("Tool call log (transparency)"):
            for call in st.session_state.tool_call_log:
                st.code(f"{call['name']}({call['arguments']}) -> {call['result']}")

# ---------------------------------------------------------------- Page 4
elif page == "4. 100-Day Plan":
    _require_record()
    record = st.session_state.record
    st.header("100-Day Integration Plan")

    if not record.opportunities:
        st.warning("Run the Agent War Room first to generate opportunities.")
        st.stop()

    if not record.integration_plan and st.session_state.vector_store_id:
        if st.button("Generate risk register, integration plan, and review", type="primary"):
            with st.spinner("Planning integration and identifying risks..."):
                record = orchestrator.run_integration_stage(record, st.session_state.vector_store_id)
            with st.spinner("Running reviewer checks..."):
                record = orchestrator.run_review_stage(
                    record, st.session_state.tool_call_log, st.session_state.document_names
                )
            with st.spinner("Writing executive summary..."):
                record = orchestrator.generate_executive_summary(record, st.session_state.vector_store_id)
            st.session_state.record = record
            save_analysis(record)

    if record.risks:
        st.subheader("Risk Register")
        st.table(
            [
                {"Risk": r.title, "Category": r.category, "Severity": r.severity.value, "Mitigation": r.mitigation}
                for r in record.risks
            ]
        )

    if record.integration_plan:
        st.subheader("Plan")
        for phase in ("0-30 days", "31-60 days", "61-100 days"):
            actions = [a for a in record.integration_plan.actions if a.phase == phase]
            if not actions:
                continue
            st.markdown(f"**{phase}**")
            for a in actions:
                st.markdown(f"- **{_md(a.title)}** ({a.owner_role}) — {_md(a.description)}")

    if record.review:
        st.subheader("Reviewer Notes")
        st.write("Status: " + ("✅ PASSED" if record.review.passed else "⚠️ ISSUES FOUND"))
        if record.review.citation_coverage_pct is not None:
            st.metric("Citation coverage", f"{record.review.citation_coverage_pct:.1f}%")
        for issue in record.review.issues:
            st.markdown(f"- **[{issue.severity.value}] {issue.stage} / {_md(issue.item_title)}** — {_md(issue.problem)}")

    if record.executive_summary:
        st.subheader("Executive Summary")
        st.markdown(_md(record.executive_summary))

    if record.executive_summary or record.integration_plan:
        report_md = generate_report(record)
        st.download_button("Download full report (Markdown)", report_md, file_name="deallens_report.md")
