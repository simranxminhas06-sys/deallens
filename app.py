"""DealLens / DealRoom AI Streamlit app.

Two ways to run each page: "Demo (no API key)" loads a deterministic,
hand-authored Amazon/Whole Foods fixture (agent/demo_fixtures.py) — no
OpenAI calls, safe to click through with no cost. "Live (OpenAI)" runs the
real Responses API pipeline stage by stage.
"""

from __future__ import annotations

import html
import os
import tempfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from agent import orchestrator
from agent.demo_fixtures import DOCUMENT_NAMES as DEMO_DOCUMENT_NAMES
from agent.demo_fixtures import run_demo_pipeline
from agent.reviewer import review_analysis
from agent.sensitivity import compute_scenario_total, compute_tornado_rows
from agent.verdict import compute_verdict
from db.database import list_analyses, load_analysis, save_analysis
from schemas.analysis_models import AgentRole, EstimatedValue, TransactionAssumptions, VerdictLevel
from tools.financial_calculator import TOOL_FUNCTIONS, calculate_deal_economics, calculate_ramp_adjusted_value
from tools.pdf_generator import generate_pdf
from tools.pptx_generator import generate_pptx
from tools.report_generator import generate_report

st.set_page_config(page_title="DealLens", layout="wide", page_icon="📊")

# Targeted CSS on top of .streamlit/config.toml's theme colors. Only verified-stable
# data-testid/class selectors are used here (checked against the running app's DOM) —
# Streamlit's internal "st-emotion-cache-*" hash classes are deliberately avoided since
# they change across versions and would silently stop working on an upgrade.
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] h1 {
        font-size: 1.5rem;
        font-weight: 800;
        letter-spacing: -0.01em;
        background: linear-gradient(90deg, #3B7AFF, #7FB0FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.25rem;
    }
    h1 { letter-spacing: -0.015em; }
    h2, h3 { letter-spacing: -0.01em; }
    [data-testid="stMetric"] {
        background: rgba(59, 122, 255, 0.08);
        border: 1px solid rgba(59, 122, 255, 0.28);
        border-radius: 10px;
        padding: 0.75rem 1rem;
    }
    [data-testid="stMetricValue"] {
        font-weight: 700;
        white-space: normal;
        overflow-wrap: break-word;
        word-break: break-word;
        font-size: 1.5rem;
    }
    [data-testid="stMetricValue"] div { white-space: normal; }
    [data-testid="stMetricLabel"] {
        text-transform: uppercase;
        letter-spacing: 0.04em;
        font-size: 0.72rem;
        opacity: 0.75;
        white-space: normal;
        overflow-wrap: break-word;
    }
    [data-testid="stMetricLabel"] p { white-space: normal; }
    button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-secondary"] {
        border-radius: 8px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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
    [
        "1. Create Analysis", "2. Evidence", "3. Independent Assessments", "4. Sensitivity",
        "5. Risk Register", "6. Recommendation", "7. 100-Day Plan", "8. Executive Summary",
        "9. Evidence Trail", "10. Tables",
    ],
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
        cite_strs = [
            f"[{_md(c.source_document)}]({c.source_url})" if c.source_url else f"{_md(c.source_document)} ({c.location})"
            for c in e.citations
        ]
        cites = "; ".join(cite_strs) or "no citation"
        st.markdown(f"- **[{e.claim_type.value}]** {_md(e.claim)}  \n  _{cites}_")


CLAIM_TYPE_COLOR = {
    "documented_fact": "#1B7A3D",
    "calculated_result": "#1565C0",
    "assumption": "#B5670A",
    "hypothesis": "#6B6B6B",
}


def _render_evidence_trail(evidence) -> None:
    """Renders each EvidenceItem as a claim -> citation card, color-coded by claim_type.
    Evidence text ultimately comes from uploaded documents or web search — untrusted content
    — so it's HTML-escaped before going into unsafe_allow_html, not just '$'-escaped.
    """
    if not evidence:
        st.caption("No evidence recorded for this item.")
        return
    for e in evidence:
        color = CLAIM_TYPE_COLOR.get(e.claim_type.value, "#6B6B6B")
        cite_html = "; ".join(
            f'<a href="{html.escape(c.source_url)}">{html.escape(c.source_document)}</a>'
            if c.source_url
            else f"{html.escape(c.source_document)} ({html.escape(c.location)})"
            for c in e.citations
        ) or "no citation"
        notes_html = f'<div style="margin-top:4px;color:#888;font-size:0.85em;">Note: {html.escape(e.notes)}</div>' if e.notes else ""
        st.markdown(
            f'<div style="border-left:4px solid {color};padding:8px 0 8px 12px;margin-bottom:10px;">'
            f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;'
            f'font-size:0.72em;font-weight:600;text-transform:uppercase;letter-spacing:0.03em;">'
            f"{html.escape(e.claim_type.value.replace('_', ' '))}</span>"
            f'<div style="margin-top:6px;">{html.escape(e.claim)}</div>'
            f'<div style="margin-top:4px;color:#888;font-size:0.85em;">→ {cite_html}</div>'
            f"{notes_html}"
            f"</div>",
            unsafe_allow_html=True,
        )


def _pretty_param_label(param: str) -> str:
    return param.replace("_pct", "").replace("_", " ").strip().capitalize()


def _render_scenario_controls(o, key_prefix: str) -> None:
    """Lets the viewer drag the exact assumptions fed into `o.calculation_method` and see the
    low/base/high estimate recompute live via the real financial_calculator function — no LLM
    call, so this works in Demo mode with no API key.

    Widget keys carry a "generation" suffix that only changes on Reset. Streamlit widgets don't
    reliably drop a value just because a session_state key was popped after the widget already
    rendered once with it; bumping the generation forces genuinely fresh widgets instead.
    """
    fn = TOOL_FUNCTIONS.get(o.calculation_method)
    if not fn or not o.calculation_inputs:
        return

    orig_key = f"{key_prefix}_orig"
    if orig_key not in st.session_state:
        st.session_state[orig_key] = dict(o.calculation_inputs)
    gen_key = f"{key_prefix}_gen"
    gen = st.session_state.setdefault(gen_key, 0)

    if not st.toggle("Adjust scenario assumptions", value=True, key=f"{key_prefix}_toggle"):
        return

    st.caption(
        "Drag an assumption to see the estimate recompute instantly via the real "
        f"`{o.calculation_method}` function — the same one the Financial Agent called."
    )
    updated = {}
    for param, value in o.calculation_inputs.items():
        widget_key = f"{key_prefix}_{param}_{gen}"
        if "pct" in param:
            updated[param] = st.slider(
                _pretty_param_label(param), 0.0, 100.0, float(value) * 100, step=0.5,
                key=widget_key, format="%.1f%%",
            ) / 100
        else:
            updated[param] = st.number_input(
                f"{_pretty_param_label(param)} ($M)", value=float(value) / 1_000_000, step=10.0, key=widget_key,
            ) * 1_000_000

    if updated != o.calculation_inputs:
        try:
            result = fn(**updated)
        except ValueError as exc:
            st.warning(f"Can't recalculate with these inputs: {exc}")
            return
        o.calculation_inputs = updated
        o.estimated_value = EstimatedValue(low=result["low"], base=result["base"], high=result["high"])
        st.session_state.tool_call_log.append({"name": o.calculation_method, "arguments": updated, "result": result})
        save_analysis(st.session_state.record)

    st.markdown(f"Recalculated estimate: **{_md(o.estimated_value.as_range_string())}**")
    if st.button("Reset to original assumptions", key=f"{key_prefix}_reset_{gen}"):
        original = st.session_state[orig_key]
        result = fn(**original)
        o.calculation_inputs = dict(original)
        o.estimated_value = EstimatedValue(low=result["low"], base=result["base"], high=result["high"])
        st.session_state[gen_key] = gen + 1
        save_analysis(st.session_state.record)
        st.rerun()


def _short_title(title: str, max_len: int = 24) -> str:
    return title if len(title) <= max_len else title[: max_len - 1].rstrip() + "…"


def _render_tornado_chart(rows: list[dict], total_base: float, max_rows: int = 8) -> None:
    top_rows = rows[:max_rows]
    df = pd.DataFrame(top_rows)
    df["label"] = [
        f"{_short_title(r['opportunity'])} — {_pretty_param_label(r['parameter'])}" for r in top_rows
    ]
    order = df["label"].tolist()
    bars = (
        alt.Chart(df)
        .mark_bar(size=18, color="#E4572E")
        .encode(
            y=alt.Y("label:N", sort=order, title=None, axis=alt.Axis(labelLimit=240)),
            x=alt.X("total_low:Q", title="Total value creation ($)", axis=alt.Axis(format="$,.2s")),
            x2="total_high:Q",
            tooltip=[
                alt.Tooltip("label:N", title="Assumption"),
                alt.Tooltip("total_low:Q", title="If swung low", format="$,.0f"),
                alt.Tooltip("total_high:Q", title="If swung high", format="$,.0f"),
                alt.Tooltip("swing:Q", title="Swing", format="$,.0f"),
            ],
        )
    )
    base_rule = (
        alt.Chart(pd.DataFrame({"base": [total_base]}))
        .mark_rule(color="#888888", strokeDash=[4, 4])
        .encode(x="base:Q")
    )
    st.altair_chart((bars + base_rule).properties(height=32 * len(top_rows) + 20), use_container_width=True)


ROLE_LABEL = {AgentRole.STRATEGY: "Strategy Agent", AgentRole.FINANCIAL: "Financial Agent", AgentRole.RED_TEAM: "Red-Team Agent"}
VERDICT_LABEL = {
    VerdictLevel.PROCEED: "Proceed",
    VerdictLevel.PROCEED_WITH_CONDITIONS: "Proceed with conditions",
    VerdictLevel.FURTHER_DILIGENCE: "Further diligence required",
    VerdictLevel.DO_NOT_PROCEED: "Do not proceed",
}
VERDICT_COLOR = {
    VerdictLevel.PROCEED: "#1FA971",
    VerdictLevel.PROCEED_WITH_CONDITIONS: "#F5A623",
    VerdictLevel.FURTHER_DILIGENCE: "#8B6BF2",
    VerdictLevel.DO_NOT_PROCEED: "#E5484D",
}


def _render_verdict_banner(level: VerdictLevel) -> None:
    color = VERDICT_COLOR[level]
    st.markdown(
        f'<div style="background:{color};color:#0B1220;padding:1rem 1.25rem;border-radius:10px;'
        f'font-size:1.15rem;font-weight:700;margin-bottom:0.5rem;">{html.escape(VERDICT_LABEL[level])}</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------- Page 1
if page == "1. Create Analysis":
    st.header("Create Analysis")

    if is_demo:
        st.info(
            "Demo mode runs the full pipeline — company profiles, the Strategy/Financial/Red-Team "
            "independent assessments, risk register, 100-day plan, and reviewer — against a hand-authored "
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
            st.success("Demo analysis loaded. Continue on Evidence, Independent Assessments, or Sensitivity.")
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

        st.subheader("Upload documents (optional if web search is enabled below)")
        default_dir = Path("sample_data")
        use_sample = st.checkbox("Use bundled Amazon / Whole Foods sample documents", value=True)
        uploaded_files = st.file_uploader(
            "Annual reports, investor presentations, financial statements (PDF or text)",
            accept_multiple_files=True,
        )
        enable_web_search = st.checkbox(
            "Also use live web search for public company background",
            value=False,
            help="Lets the Researcher pull public facts (business description, filings, segment "
            "detail) straight from the web, so you don't have to re-upload the same background "
            "documents for every analysis. Deal-specific evidence (financials used in scenario "
            "math) still requires uploaded documents — Independent Assessments and the 100-Day "
            "Plan need an uploaded document set to run.",
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

            if not file_paths and not enable_web_search:
                st.error("Upload at least one document, keep the sample documents enabled, or enable web search.")
            else:
                vector_store_id, summary = None, None
                if file_paths:
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
                    record = orchestrator.run_research_stage(record, vector_store_id, enable_web_search)
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
        "analysis. Financial estimates in the independent assessments below will use these figures "
        "and the documents ingested above."
    )
    st.json(record.transaction.model_dump())
    approved = st.checkbox("I approve these assumptions for scenario analysis", value=record.assumptions_approved)
    if approved != record.assumptions_approved:
        record.assumptions_approved = approved
        save_analysis(record)
        st.session_state.record = record

# ---------------------------------------------------------------- Page 3
elif page == "3. Independent Assessments":
    _require_record()
    record = st.session_state.record
    st.header("Independent Assessments")
    st.caption("Strategy, Financial, and Red-Team agents assess the deal independently, then Red-Team challenges the other two.")

    if not record.assumptions_approved:
        st.warning("Approve assumptions on the Evidence page before running the assessments.")
        st.stop()

    if not record.agent_assessments and st.session_state.vector_store_id:
        if st.button("Run independent assessments (Strategy → Financial → Red-Team)", type="primary"):
            with st.spinner("Agents assessing the deal..."):
                record, tool_call_log = orchestrator.run_assessment_stage(record, st.session_state.vector_store_id)
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
                with st.expander(f"Opportunities ({len(assessment.opportunities)})", expanded=True):
                    for i, o in enumerate(assessment.opportunities):
                        with st.container(border=True):
                            st.markdown(f"**{_md(o.title)}** — base \\${o.estimated_value.base:,.0f} ({_md(o.estimated_value.as_range_string())})")
                            st.caption(_md(f"Assumptions: {'; '.join(o.assumptions)}"))
                            ramp = calculate_ramp_adjusted_value(
                                o.estimated_value.base, o.year_1_pct, o.year_2_pct, o.year_3_pct, o.cost_to_achieve
                            )
                            st.caption(
                                _md(
                                    f"3-year ramp: Y1 ${ramp['year_1']:,.0f} → Y2 ${ramp['year_2']:,.0f} → "
                                    f"Y3 ${ramp['year_3']:,.0f}  |  Cost to achieve: ${o.cost_to_achieve:,.0f}  |  "
                                    f"Net 3-yr value: ${ramp['net_3yr_value']:,.0f}"
                                )
                            )
                            _render_scenario_controls(o, key_prefix=f"scn_{assessment.role.value}_{i}")
            if assessment.challenges:
                for c in assessment.challenges:
                    st.markdown(
                        f"> **Challenge to {ROLE_LABEL.get(c.target_agent, c.target_agent.value)}** "
                        f"on *“{_md(c.target_claim)}”* [{c.severity.value}]: {_md(c.critique)}"
                    )

    if st.session_state.tool_call_log:
        with st.expander("Tool call log (transparency)"):
            for call in st.session_state.tool_call_log:
                st.code(f"{call['name']}({call['arguments']}) -> {call['result']}")

# ---------------------------------------------------------------- Page 4
elif page == "4. Sensitivity":
    _require_record()
    record = st.session_state.record
    st.header("Sensitivity")
    st.caption(
        "Which single assumption moves total value creation the most? Each bar swings just "
        "one assumption to its low/high bound, holding every other assumption at its current "
        "value, recomputed live via the same financial_calculator functions the Financial "
        "Agent used — no LLM call, so this is free to explore."
    )

    if not record.opportunities:
        st.warning("Run Independent Assessments first to generate opportunities.")
        st.stop()

    total_base = sum(o.estimated_value.base for o in record.opportunities)
    downside = compute_scenario_total(record.opportunities, "low")
    upside = compute_scenario_total(record.opportunities, "high")
    cols = st.columns(3)
    cols[0].metric("Downside case", f"${downside:,.0f}", help="Every assumption at its pessimistic bound, simultaneously.")
    cols[1].metric("Base case", f"${total_base:,.0f}")
    cols[2].metric("Upside case", f"${upside:,.0f}", help="Every assumption at its optimistic bound, simultaneously.")
    st.caption(
        "The tornado chart below isolates one assumption at a time. Downside/upside stress-test "
        "every assumption at once — the combined worst and best case."
    )

    if record.transaction.deal_value:
        econ = calculate_deal_economics(total_base, record.transaction.deal_value)
        st.metric(
            "Value creation vs. deal value",
            f"{econ['value_creation_pct_of_deal']:.2f}%",
            help=f"${total_base:,.0f} identified value creation against a ${record.transaction.deal_value:,.0f} purchase price.",
        )
    else:
        st.caption("Set a deal value on Create Analysis to compare value creation against the purchase price.")

    rows = compute_tornado_rows(record.opportunities)
    if not rows:
        st.info("No opportunity has recorded calculation inputs to analyze yet.")
    else:
        _render_tornado_chart(rows, total_base)
        with st.expander("How this is computed"):
            st.write(
                "For each assumption, this swaps only that one value to its low and high "
                "bound and recomputes that opportunity's base estimate, holding every other "
                "assumption fixed. A `_base` percentage (e.g. a synergy reduction rate) uses "
                "the opportunity's own stated low/high; a cost or revenue base or a margin "
                "with no stated range gets a default ±20% swing. The bar shows the resulting "
                "swing in total value creation across every opportunity. The dashed line marks "
                "the current base case."
            )
        st.caption(
            "Changed an assumption on Independent Assessments? This chart reads the same "
            "live record, so it updates too."
        )

# ---------------------------------------------------------------- Page 5
elif page == "5. Risk Register":
    _require_record()
    record = st.session_state.record
    st.header("Risk Register")

    if not record.opportunities:
        st.warning("Run Independent Assessments first to generate opportunities.")
        st.stop()

    if not record.risks and st.session_state.vector_store_id:
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

    if not record.risks:
        st.info("Click the button above to identify risks (this also builds the 100-Day Plan and executive summary).")
        st.stop()

    st.caption("Sorted by risk score (likelihood × impact, 1-9), highest first.")
    ranked_risks = sorted(record.risks, key=lambda r: r.score, reverse=True)
    st.table(
        [
            {
                "Risk": r.title,
                "Category": r.category,
                "Likelihood": r.likelihood.value,
                "Impact": r.severity.value,
                "Score": r.score,
                "Mitigation": r.mitigation,
            }
            for r in ranked_risks
        ]
    )

    for r in ranked_risks:
        if r.evidence:
            with st.expander(f"Evidence: {r.title}"):
                _evidence_lines(r.evidence)

# ---------------------------------------------------------------- Page 6
elif page == "6. Recommendation":
    _require_record()
    record = st.session_state.record
    st.header("Recommendation")
    st.caption(
        "A rule-based verdict, not a model's opinion — every reason below traces to a specific "
        "reviewer finding or Red-Team challenge already in this analysis. Recomputed live from "
        "the current record, so it reflects any assumption you've adjusted on Independent "
        "Assessments even if the Risk Register/Tables reviewer snapshot is stale."
    )

    if not record.agent_assessments:
        st.warning("Run Independent Assessments first — the verdict needs the agents' positions and challenges.")
        st.stop()

    fresh_review = review_analysis(record, st.session_state.tool_call_log, st.session_state.document_names)
    total_value = sum(o.estimated_value.base for o in record.opportunities)
    verdict = compute_verdict(fresh_review, record.agent_assessments, total_value, record.transaction)

    _render_verdict_banner(verdict.level)

    st.subheader("Why")
    for reason in verdict.reasons:
        st.markdown(f"- {_md(reason)}")

    if verdict.conditions:
        st.subheader("Conditions to resolve before proceeding")
        for condition in verdict.conditions:
            st.markdown(f"- {_md(condition)}")

    with st.expander("Reviewer detail behind this verdict"):
        st.write("Status: " + ("PASSED" if fresh_review.passed else "ISSUES FOUND"))
        if fresh_review.citation_coverage_pct is not None:
            st.metric("Citation coverage", f"{fresh_review.citation_coverage_pct:.1f}%")
        for issue in fresh_review.issues:
            st.markdown(f"- **[{issue.severity.value}] {issue.stage} / {_md(issue.item_title)}** — {_md(issue.problem)}")

    st.caption(
        "Rules: 2+ high-severity reviewer issues combined with a high-severity Red-Team "
        "challenge → do not proceed. Any unresolved high-severity reviewer issue, or citation "
        "coverage under 70%, → further diligence. A clean review with a high-severity Red-Team "
        "challenge → proceed with conditions. Otherwise → proceed. See agent/verdict.py."
    )

# ---------------------------------------------------------------- Page 7
elif page == "7. 100-Day Plan":
    _require_record()
    record = st.session_state.record
    st.header("100-Day Integration Plan")

    if not record.integration_plan:
        st.warning("Run the generation step on Risk Register first to build the integration plan.")
        st.stop()

    st.subheader("Plan")
    for phase in ("0-30 days", "31-60 days", "61-100 days"):
        actions = [a for a in record.integration_plan.actions if a.phase == phase]
        if not actions:
            continue
        st.markdown(f"**{phase}**")
        for a in actions:
            st.markdown(f"- **{_md(a.title)}** ({a.owner_role}) — {_md(a.description)}")
    if record.integration_plan.guiding_principles:
        st.markdown("**Guiding principles**")
        for principle in record.integration_plan.guiding_principles:
            st.markdown(f"- {_md(principle)}")
    st.caption(f"Governance: {_md(record.integration_plan.governance)}")

# ---------------------------------------------------------------- Page 8
elif page == "8. Executive Summary":
    _require_record()
    record = st.session_state.record
    st.header("Executive Summary")

    if not record.executive_summary and not record.integration_plan:
        st.warning("Run the generation step on Risk Register first to write the executive summary.")
        st.stop()

    if record.executive_summary:
        st.markdown(_md(record.executive_summary))
    else:
        st.info("Executive summary not yet generated.")

    st.divider()
    dl_cols = st.columns(3)
    report_md = generate_report(record)
    dl_cols[0].download_button("Download full report (Markdown)", report_md, file_name="deallens_report.md")
    report_pdf = generate_pdf(record)
    dl_cols[1].download_button(
        "Download full report (PDF)", report_pdf, file_name="deallens_report.pdf", mime="application/pdf"
    )
    report_pptx = generate_pptx(record)
    dl_cols[2].download_button(
        "Download IC deck (PowerPoint)",
        report_pptx,
        file_name="deallens_deck.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

# ---------------------------------------------------------------- Page 9
elif page == "9. Evidence Trail":
    _require_record()
    record = st.session_state.record
    st.header("Evidence Trail")
    st.caption(
        "Every claim traced to its source. Pick an item below to see each underlying claim, "
        "color-coded by type, with the citation it rests on — or a note that it has none."
    )

    sources: dict = {}
    if record.acquirer_profile:
        sources[f"Acquirer profile: {record.acquirer_profile.company_name}"] = record.acquirer_profile.evidence
    if record.target_profile:
        sources[f"Target profile: {record.target_profile.company_name}"] = record.target_profile.evidence
    if record.strategic_rationale:
        sources["Strategic rationale"] = record.strategic_rationale.supporting_points
    for o in record.opportunities:
        sources[f"Opportunity: {o.title}"] = o.evidence
    for r in record.risks:
        sources[f"Risk: {r.title}"] = r.evidence
    for a in record.agent_assessments:
        if a.key_findings:
            sources[f"{ROLE_LABEL.get(a.role, a.role.value)}: key findings"] = a.key_findings

    if not sources:
        st.warning("No evidence recorded yet — start on Create Analysis and Evidence.")
        st.stop()

    selected = st.selectbox("Trace an item", list(sources.keys()))
    _render_evidence_trail(sources[selected])

    with st.expander("Claim type legend"):
        legend = [
            ("documented_fact", "directly supported by a citation"),
            ("calculated_result", "produced by a financial_calculator tool call"),
            ("assumption", "explicitly stated, not sourced from a document"),
            ("hypothesis", "requires further diligence — no citation or calculation yet"),
        ]
        for claim_type, description in legend:
            color = CLAIM_TYPE_COLOR[claim_type]
            st.markdown(
                f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;'
                f'font-size:0.72em;font-weight:600;text-transform:uppercase;">{claim_type.replace("_", " ")}</span>'
                f" — {description}",
                unsafe_allow_html=True,
            )

# ---------------------------------------------------------------- Page 10
elif page == "10. Tables":
    _require_record()
    record = st.session_state.record
    st.header("Tables")
    st.caption("Every structured table in this analysis, in one place, for quick scanning.")

    if record.acquirer_profile or record.target_profile:
        st.subheader("Company Profiles")
        rows = []
        for metric, key, fmt in (
            ("Revenue", "revenue", lambda v: f"${v:,.0f}"),
            ("Growth", "revenue_growth_rate", lambda v: f"{v * 100:.1f}%"),
            ("Operating margin", "operating_margin", lambda v: f"{v * 100:.1f}%"),
            ("Employees", "employee_count", lambda v: f"{v:,}"),
        ):
            row = {"Metric": metric}
            for label, profile in (("Acquirer", record.acquirer_profile), ("Target", record.target_profile)):
                value = getattr(profile, key, None) if profile else None
                row[label] = fmt(value) if value is not None else "n/a"
            rows.append(row)
        st.table(rows)

    if record.financial_baselines:
        st.subheader("Financial Baseline")
        st.table(
            [{"Metric": b.metric, "Value": f"{b.value:,.2f} {b.unit}", "Method": b.method} for b in record.financial_baselines]
        )

    if record.opportunities:
        st.subheader("Opportunities")
        opp_rows = []
        for o in record.opportunities:
            ramp = calculate_ramp_adjusted_value(o.estimated_value.base, o.year_1_pct, o.year_2_pct, o.year_3_pct, o.cost_to_achieve)
            opp_rows.append({
                "Opportunity": o.title,
                "Category": o.category.value,
                "Low": f"${o.estimated_value.low:,.0f}",
                "Base": f"${o.estimated_value.base:,.0f}",
                "High": f"${o.estimated_value.high:,.0f}",
                "Difficulty": o.implementation_difficulty.value,
                "Horizon": o.time_horizon,
                "Cost to achieve": f"${o.cost_to_achieve:,.0f}",
                "Net 3-yr value": f"${ramp['net_3yr_value']:,.0f}",
            })
        st.table(opp_rows)

    if record.integration_plan and record.integration_plan.actions:
        st.subheader("Integration Actions")
        st.table(
            [
                {
                    "Phase": a.phase,
                    "Action": a.title,
                    "Owner": a.owner_role,
                    "Description": a.description,
                    "Success metric": a.success_metric or "n/a",
                }
                for a in record.integration_plan.actions
            ]
        )

    if record.review:
        st.subheader("Reviewer Issues")
        st.write("Status: " + ("PASSED" if record.review.passed else "ISSUES FOUND"))
        if record.review.citation_coverage_pct is not None:
            st.metric("Citation coverage", f"{record.review.citation_coverage_pct:.1f}%")
        if record.review.issues:
            st.table(
                [
                    {
                        "Severity": i.severity.value,
                        "Stage": i.stage,
                        "Item": i.item_title,
                        "Problem": i.problem,
                        "Recommendation": i.recommendation,
                    }
                    for i in record.review.issues
                ]
            )
        else:
            st.caption("No issues flagged.")
        st.caption(
            "This reflects the reviewer snapshot from the last time Risk Register generated it — "
            "see Recommendation for a live-recomputed check against your current assumptions."
        )

# ---------------------------------------------------------------- Sidebar: live deal scorecard
# Placed at the end of the script (not with the rest of the sidebar near the top) so it
# reflects any scenario-assumption edit made by the page body above, in this same run —
# Streamlit lets you append to st.sidebar from anywhere in the script.
if st.session_state.record and st.session_state.record.opportunities:
    _record = st.session_state.record
    _current_total = sum(o.estimated_value.base for o in _record.opportunities)

    _original_totals = st.session_state.setdefault("original_totals_by_id", {})
    if _record.id not in _original_totals:
        _original_totals[_record.id] = _current_total
    _original_total = _original_totals[_record.id]

    st.sidebar.divider()
    st.sidebar.caption("Live deal scorecard")
    _delta = _current_total - _original_total
    _delta_str = None
    if abs(_delta) > 0.01:
        _delta_pct = (_delta / _original_total * 100) if _original_total else 0.0
        _delta_str = f"{_delta:+,.0f} ({_delta_pct:+.1f}%) vs. original"
    st.sidebar.metric(
        "Total value creation",
        f"${_current_total:,.0f}",
        delta=_delta_str,
        help="Base case: sum of every opportunity's estimated_value.base.",
    )

    if _record.transaction.deal_value:
        _econ = calculate_deal_economics(_current_total, _record.transaction.deal_value)
        st.sidebar.metric("% of deal value", f"{_econ['value_creation_pct_of_deal']:.2f}%")
