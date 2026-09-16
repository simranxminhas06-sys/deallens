"""Assembles a formatted PDF version of the same analysis generate_report() renders as
Markdown — a document someone can actually open and hand to a partner, not a text dump.
Pure Python (reportlab has no system-binary dependency), so this deploys the same way
everywhere the rest of the app does.
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape as _esc

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from agent.verdict import compute_verdict
from schemas.analysis_models import AnalysisRecord, EvidenceItem
from tools.financial_calculator import calculate_accretion_dilution, calculate_deal_economics, calculate_ramp_adjusted_value

NAVY = colors.HexColor("#1B2A4A")
ACCENT = colors.HexColor("#3D5AFE")
LIGHT_GRAY = colors.HexColor("#F2F4F7")
VERDICT_TEXT = colors.HexColor("#0B1220")

VERDICT_COLOR = {
    "proceed": colors.HexColor("#00D084"),
    "proceed_with_conditions": colors.HexColor("#FFB800"),
    "further_diligence": colors.HexColor("#8C5CFF"),
    "do_not_proceed": colors.HexColor("#FF3B3B"),
}

VERDICT_LABEL = {
    "proceed": "Proceed",
    "proceed_with_conditions": "Proceed with conditions",
    "further_diligence": "Further diligence required",
    "do_not_proceed": "Do not proceed",
}

_styles = getSampleStyleSheet()
_styles.add(ParagraphStyle("DLTitle", parent=_styles["Title"], textColor=NAVY, spaceAfter=4))
_styles.add(ParagraphStyle("DLMeta", parent=_styles["Normal"], textColor=colors.gray, spaceAfter=16))
_styles.add(ParagraphStyle("DLH1", parent=_styles["Heading1"], textColor=NAVY, spaceBefore=16, spaceAfter=8))
_styles.add(ParagraphStyle("DLH2", parent=_styles["Heading2"], textColor=ACCENT, spaceBefore=10, spaceAfter=4, fontSize=12))
_styles.add(ParagraphStyle("DLBody", parent=_styles["Normal"], alignment=TA_LEFT, spaceAfter=6, leading=14))
_styles.add(ParagraphStyle("DLCaption", parent=_styles["Normal"], textColor=colors.gray, fontSize=8.5, leading=11, spaceAfter=6))
_styles.add(ParagraphStyle("DLVerdict", parent=_styles["Heading2"], textColor=VERDICT_TEXT, fontSize=13, leading=16))

_TABLE_HEADER_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
)


def _p(text: str, style: str = "DLBody") -> Paragraph:
    return Paragraph(_esc(text), _styles[style])


def _fmt_evidence(evidence: list[EvidenceItem]):
    flowables = []
    for e in evidence:
        cites = "; ".join(f"{c.source_document} ({c.location})" for c in e.citations) or "no citation"
        flowables.append(_p(f"[{e.claim_type.value}] {e.claim}", "DLBody"))
        flowables.append(_p(cites, "DLCaption"))
    return flowables


def _table(header: list[str], rows: list[list[str]], col_widths=None) -> Table:
    data = [[Paragraph(f"<b>{_esc(h)}</b>", _styles["DLCaption"]) for h in header]]
    for row in rows:
        data.append([Paragraph(_esc(str(cell)), _styles["DLCaption"]) for cell in row])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(_TABLE_HEADER_STYLE)
    return t


def generate_pdf(record: AnalysisRecord) -> bytes:
    t = record.transaction
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.75 * inch, bottomMargin=0.75 * inch,
    )
    story = []

    story.append(Paragraph(_esc(f"DealLens Analysis: {t.acquirer_name} / {t.target_name}"), _styles["DLTitle"]))
    story.append(Paragraph(_esc(f"Generated {record.created_at:%Y-%m-%d %H:%M UTC}"), _styles["DLMeta"]))

    story.append(Paragraph("Executive Summary", _styles["DLH1"]))
    story.append(_p(record.executive_summary or "Not yet generated."))

    total_value_creation = sum(o.estimated_value.base for o in record.opportunities)
    if record.review is not None:
        verdict = compute_verdict(record.review, record.agent_assessments, total_value_creation, t)
        story.append(Paragraph("Recommendation", _styles["DLH1"]))
        verdict_table = Table(
            [[Paragraph(_esc(VERDICT_LABEL[verdict.level.value]), _styles["DLVerdict"])]],
            colWidths=[6.5 * inch],
        )
        verdict_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), VERDICT_COLOR[verdict.level.value]),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(verdict_table)
        story.append(Spacer(1, 6))
        for reason in verdict.reasons:
            story.append(_p(f"• {reason}", "DLCaption"))
        if verdict.conditions:
            story.append(_p("Conditions to resolve before proceeding:", "DLBody"))
            for condition in verdict.conditions:
                story.append(_p(f"• {condition}", "DLCaption"))

    if t.deal_value and record.opportunities:
        econ = calculate_deal_economics(total_value_creation, t.deal_value)
        story.append(Paragraph("Deal Economics", _styles["DLH1"]))
        story.append(_p(
            f"Identified value creation of ${total_value_creation:,.0f} against a "
            f"${t.deal_value:,.0f} deal value — {econ['value_creation_pct_of_deal']:.2f}% of the purchase price."
        ))

    if t.deal_value and t.financing:
        f = t.financing
        ad = calculate_accretion_dilution(
            deal_value=t.deal_value,
            cash_pct=f.cash_pct,
            stock_pct=f.stock_pct,
            debt_pct=f.debt_pct,
            new_debt_interest_rate=f.new_debt_interest_rate,
            foregone_interest_rate=f.foregone_interest_rate,
            acquirer_tax_rate=f.acquirer_tax_rate,
            acquirer_share_price=f.acquirer_share_price,
            acquirer_shares_outstanding=f.acquirer_shares_outstanding,
            acquirer_net_income=f.acquirer_net_income,
            target_net_income=f.target_net_income or 0.0,
            synergies_after_tax_run_rate=total_value_creation * (1 - f.acquirer_tax_rate),
        )
        story.append(Paragraph("Financing &amp; Accretion/Dilution", _styles["DLH1"]))
        if f.note:
            story.append(_p(f.note, "DLCaption"))
        story.append(_p(
            f"Financed with {f.cash_pct:.0%} cash / {f.stock_pct:.0%} stock / {f.debt_pct:.0%} debt. "
            f"Standalone EPS ${ad['standalone_eps']:.2f}; pro forma EPS ${ad['pro_forma_eps_day1']:.2f} "
            f"({ad['accretion_dilution_pct_day1']:+.1f}%) on Day 1, ${ad['pro_forma_eps_run_rate']:.2f} "
            f"({ad['accretion_dilution_pct_run_rate']:+.1f}%) once synergies reach full run-rate."
        ))

    story.append(Paragraph("Company Profiles", _styles["DLH1"]))
    for label, profile in (("Acquirer", record.acquirer_profile), ("Target", record.target_profile)):
        if not profile:
            continue
        story.append(Paragraph(f"{label}: {_esc(profile.company_name)}", _styles["DLH2"]))
        story.append(_p(profile.business_description))
        stats = []
        if profile.revenue is not None:
            stats.append(f"Revenue: ${profile.revenue:,.0f}")
        if profile.revenue_growth_rate is not None:
            stats.append(f"Growth: {profile.revenue_growth_rate * 100:.1f}%")
        if profile.operating_margin is not None:
            stats.append(f"Operating margin: {profile.operating_margin * 100:.1f}%")
        if stats:
            story.append(_p(" | ".join(stats), "DLCaption"))
        story += _fmt_evidence(profile.evidence)

    if record.strategic_rationale:
        story.append(Paragraph("Strategic Rationale", _styles["DLH1"]))
        story.append(_p(record.strategic_rationale.summary))
        story += _fmt_evidence(record.strategic_rationale.supporting_points)

    if record.financial_baselines:
        story.append(Paragraph("Financial Baseline", _styles["DLH1"]))
        story.append(_table(
            ["Metric", "Value", "Method"],
            [[b.metric, f"{b.value:,.2f} {b.unit}", b.method] for b in record.financial_baselines],
            col_widths=[1.8 * inch, 1.5 * inch, 3.2 * inch],
        ))

    revenue_opps = [o for o in record.opportunities if o.category.value == "revenue_synergy"]
    cost_opps = [o for o in record.opportunities if o.category.value == "cost_synergy"]
    dis_synergy_opps = [o for o in record.opportunities if o.category.value == "dis_synergy"]
    for section_title, opps in (
        ("Revenue Opportunities", revenue_opps),
        ("Cost-Saving Opportunities", cost_opps),
        ("Dis-Synergies", dis_synergy_opps),
    ):
        if not opps:
            continue
        story.append(Paragraph(section_title, _styles["DLH1"]))
        story.append(_table(
            ["Opportunity", "Low / Base / High", "Difficulty", "Horizon"],
            [
                [o.title, f"${o.estimated_value.low:,.0f} / ${o.estimated_value.base:,.0f} / ${o.estimated_value.high:,.0f}",
                 o.implementation_difficulty.value, o.time_horizon]
                for o in opps
            ],
            col_widths=[2.3 * inch, 2.4 * inch, 0.9 * inch, 0.9 * inch],
        ))
        story.append(Spacer(1, 8))
        for o in opps:
            story.append(Paragraph(o.title, _styles["DLH2"]))
            story.append(_p(o.rationale))
            if o.assumptions:
                story.append(_p("Assumptions: " + "; ".join(o.assumptions), "DLCaption"))
            if o.key_risks:
                story.append(_p("Key risks: " + "; ".join(o.key_risks), "DLCaption"))
            ramp = calculate_ramp_adjusted_value(o.estimated_value.base, o.year_1_pct, o.year_2_pct, o.year_3_pct, o.cost_to_achieve)
            story.append(_p(
                f"3-year ramp: Y1 ${ramp['year_1']:,.0f}, Y2 ${ramp['year_2']:,.0f}, Y3 ${ramp['year_3']:,.0f}. "
                f"Cost to achieve: ${o.cost_to_achieve:,.0f}. Net 3-year value: ${ramp['net_3yr_value']:,.0f}.",
                "DLCaption",
            ))
            story += _fmt_evidence(o.evidence)
            story.append(Spacer(1, 4))

    if record.risks:
        story.append(Paragraph("Risk Register", _styles["DLH1"]))
        story.append(_p("Sorted by risk score (likelihood x impact, 1-9), highest first.", "DLCaption"))
        ranked_risks = sorted(record.risks, key=lambda r: r.score, reverse=True)
        story.append(_table(
            ["Risk", "Category", "Likelihood", "Impact", "Score", "Owner"],
            [
                [r.title, r.category, r.likelihood.value, r.severity.value, str(r.score), r.owner_role or "n/a"]
                for r in ranked_risks
            ],
            col_widths=[1.3 * inch, 0.8 * inch, 0.7 * inch, 0.6 * inch, 0.5 * inch, 2.6 * inch],
        ))
        story.append(Spacer(1, 6))
        for r in ranked_risks:
            story.append(Paragraph(_esc(r.title), _styles["DLH2"]))
            story.append(_p(r.description))
            story.append(_p(f"Mitigation: {r.mitigation}", "DLCaption"))
            if r.contingency:
                story.append(_p(f"Contingency: {r.contingency}", "DLCaption"))
            if r.early_warning_indicator:
                story.append(_p(f"Early warning indicator: {r.early_warning_indicator}", "DLCaption"))

    if record.integration_plan:
        story.append(Paragraph("100-Day Integration Plan", _styles["DLH1"]))
        if record.integration_plan.guiding_principles:
            story.append(_p("Guiding principles: " + "; ".join(record.integration_plan.guiding_principles), "DLCaption"))
        for phase in ("0-30 days", "31-60 days", "61-100 days"):
            actions = [a for a in record.integration_plan.actions if a.phase == phase]
            if not actions:
                continue
            story.append(Paragraph(phase, _styles["DLH2"]))
            for a in actions:
                story.append(_p(f"{a.title} ({a.owner_role}) — {a.description}"))
                if a.success_metric:
                    story.append(_p(f"Success metric: {a.success_metric}", "DLCaption"))
                if a.risks:
                    story.append(_p("Risks: " + "; ".join(a.risks), "DLCaption"))
        story.append(_p(f"Governance: {record.integration_plan.governance}", "DLCaption"))

    if record.review:
        story.append(Paragraph("Reviewer Notes", _styles["DLH1"]))
        story.append(_p("Status: " + ("PASSED" if record.review.passed else "ISSUES FOUND")))
        if record.review.citation_coverage_pct is not None:
            story.append(_p(f"Citation coverage: {record.review.citation_coverage_pct:.1f}%", "DLCaption"))
        if record.review.issues:
            story.append(_table(
                ["Severity", "Stage", "Item", "Problem", "Recommendation"],
                [[i.severity.value, i.stage, i.item_title, i.problem, i.recommendation] for i in record.review.issues],
                col_widths=[0.7 * inch, 1.0 * inch, 1.3 * inch, 1.8 * inch, 1.7 * inch],
            ))

    doc.build(story)
    return buffer.getvalue()
