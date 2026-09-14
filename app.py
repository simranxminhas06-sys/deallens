"""DealLens Streamlit app: four pages driving the pipeline one stage at a time."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import streamlit as st

from agent import orchestrator
from db.database import list_analyses, load_analysis, save_analysis
from schemas.analysis_models import TransactionAssumptions
from tools.report_generator import generate_report

st.set_page_config(page_title="DealLens", layout="wide")

if "record" not in st.session_state:
    st.session_state.record = None
if "vector_store_id" not in st.session_state:
    st.session_state.vector_store_id = None
if "document_names" not in st.session_state:
    st.session_state.document_names = set()
if "tool_call_log" not in st.session_state:
    st.session_state.tool_call_log = []

st.sidebar.title("DealLens")
if not os.environ.get("OPENAI_API_KEY"):
    st.sidebar.warning("OPENAI_API_KEY is not set. Set it in your environment before running a live analysis.")

page = st.sidebar.radio(
    "Workflow",
    ["1. Create Analysis", "2. Evidence", "3. Value Creation", "4. 100-Day Plan"],
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


# ---------------------------------------------------------------- Page 1
if page == "1. Create Analysis":
    st.header("Create Analysis")

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
        st.write(profile.business_description)
        cols = st.columns(4)
        cols[0].metric("Revenue", f"${profile.revenue:,.0f}" if profile.revenue else "n/a")
        cols[1].metric("Growth", f"{profile.revenue_growth_rate * 100:.1f}%" if profile.revenue_growth_rate else "n/a")
        cols[2].metric("Op. margin", f"{profile.operating_margin * 100:.1f}%" if profile.operating_margin else "n/a")
        cols[3].metric("Employees", f"{profile.employee_count:,}" if profile.employee_count else "n/a")
        for e in profile.evidence:
            cites = "; ".join(f"{c.source_document} ({c.location})" for c in e.citations) or "no citation"
            st.markdown(f"- **[{e.claim_type.value}]** {e.claim}  \n  _{cites}_")

    if record.strategic_rationale:
        st.subheader("Strategic Rationale")
        st.write(record.strategic_rationale.summary)
        for e in record.strategic_rationale.supporting_points:
            cites = "; ".join(f"{c.source_document} ({c.location})" for c in e.citations) or "no citation"
            st.markdown(f"- **[{e.claim_type.value}]** {e.claim}  \n  _{cites}_")

    st.divider()
    st.subheader("Approve assumptions")
    st.write(
        "Confirm the transaction assumptions below before the agent runs financial scenario "
        "analysis. Financial estimates in the next stage will use these figures and the "
        "documents ingested above."
    )
    st.json(record.transaction.model_dump())
    approved = st.checkbox("I approve these assumptions for scenario analysis", value=record.assumptions_approved)
    if approved != record.assumptions_approved:
        record.assumptions_approved = approved
        save_analysis(record)
        st.session_state.record = record

# ---------------------------------------------------------------- Page 3
elif page == "3. Value Creation":
    _require_record()
    record = st.session_state.record
    st.header("Value Creation")

    if not record.assumptions_approved:
        st.warning("Approve assumptions on the Evidence page before running scenario analysis.")
        st.stop()

    if st.button("Run financial baseline + opportunity generation", type="primary"):
        with st.spinner("Computing baseline metrics and generating opportunities..."):
            record, tool_call_log = orchestrator.run_value_creation_stage(record, st.session_state.vector_store_id)
        st.session_state.tool_call_log = tool_call_log
        st.session_state.record = record
        save_analysis(record)

    if record.financial_baselines:
        st.subheader("Financial Baseline")
        st.table(
            [
                {"Metric": b.metric, "Value": f"{b.value:,.2f} {b.unit}", "Method": b.method}
                for b in record.financial_baselines
            ]
        )

    if record.opportunities:
        for category, title in (("revenue_synergy", "Revenue Opportunities"), ("cost_synergy", "Cost-Saving Opportunities")):
            opps = [o for o in record.opportunities if o.category.value == category]
            if not opps:
                continue
            st.subheader(title)
            for o in opps:
                with st.expander(f"{o.title} — base ${o.estimated_value.base:,.0f}"):
                    st.write(o.rationale)
                    st.write(f"**Range:** {o.estimated_value.as_range_string()}")
                    st.write(f"**Assumptions:** {'; '.join(o.assumptions)}")
                    st.write(f"**Difficulty:** {o.implementation_difficulty.value} | **Horizon:** {o.time_horizon}")
                    st.write(f"**Key risks:** {'; '.join(o.key_risks)}")
                    for e in o.evidence:
                        cites = "; ".join(f"{c.source_document} ({c.location})" for c in e.citations) or "no citation"
                        st.markdown(f"- **[{e.claim_type.value}]** {e.claim}  \n  _{cites}_")

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
        st.warning("Generate value-creation opportunities first.")
        st.stop()

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
                st.markdown(f"- **{a.title}** ({a.owner_role}) — {a.description}")

    if record.review:
        st.subheader("Reviewer Notes")
        st.write("Status: " + ("✅ PASSED" if record.review.passed else "⚠️ ISSUES FOUND"))
        if record.review.citation_coverage_pct is not None:
            st.metric("Citation coverage", f"{record.review.citation_coverage_pct:.1f}%")
        for issue in record.review.issues:
            st.markdown(f"- **[{issue.severity.value}] {issue.stage} / {issue.item_title}** — {issue.problem}")

    if record.executive_summary:
        st.subheader("Executive Summary")
        st.write(record.executive_summary)

    if record.executive_summary or record.integration_plan:
        report_md = generate_report(record)
        st.download_button("Download full report (Markdown)", report_md, file_name="deallens_report.md")
