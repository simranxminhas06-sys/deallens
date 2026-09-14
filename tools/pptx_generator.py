"""Assembles a slide-deck version of the same analysis generate_report() renders as
Markdown — an actual IC/partner deck (title, verdict, economics, opportunities, risks,
100-day plan) rather than a linear document, since that's the artifact a deal team
hands upward. Pure python-pptx, no PowerPoint installation required, so this deploys
the same way everywhere the rest of the app does.
"""

from __future__ import annotations

import io

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from agent.verdict import compute_verdict
from schemas.analysis_models import AnalysisRecord
from tools.financial_calculator import calculate_deal_economics

NAVY = RGBColor(0x1B, 0x2A, 0x4A)
DARK_BG = RGBColor(0x0B, 0x12, 0x20)
ACCENT = RGBColor(0x3B, 0x7A, 0xFF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT_GRAY = RGBColor(0xE7, 0xEC, 0xF5)
MUTED = RGBColor(0x9A, 0xA5, 0xB8)

VERDICT_COLOR = {
    "proceed": RGBColor(0x1F, 0xA9, 0x71),
    "proceed_with_conditions": RGBColor(0xF5, 0xA6, 0x23),
    "further_diligence": RGBColor(0x8B, 0x6B, 0xF2),
    "do_not_proceed": RGBColor(0xE5, 0x48, 0x4D),
}

VERDICT_LABEL = {
    "proceed": "Proceed",
    "proceed_with_conditions": "Proceed with conditions",
    "further_diligence": "Further diligence required",
    "do_not_proceed": "Do not proceed",
}

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.5)
CONTENT_W = SLIDE_W - 2 * MARGIN


def _blank_slide(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = DARK_BG
    bg.line.fill.background()
    bg.shadow.inherit = False
    slide.shapes._spTree.remove(bg._element)
    slide.shapes._spTree.insert(2, bg._element)
    return slide


def _title(slide, text: str, subtitle: str | None = None):
    box = slide.shapes.add_textbox(MARGIN, Inches(0.35), CONTENT_W, Inches(0.9))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = WHITE
    if subtitle:
        p2 = tf.add_paragraph()
        p2.text = subtitle
        p2.font.size = Pt(13)
        p2.font.color.rgb = MUTED
    return box


def _body_textbox(slide, top, height=None):
    height = height or (SLIDE_H - top - Inches(0.4))
    box = slide.shapes.add_textbox(MARGIN, top, CONTENT_W, height)
    box.text_frame.word_wrap = True
    return box


def _bullets(slide, lines: list[str], top=Inches(1.4), font_size=14, height=None):
    box = _body_textbox(slide, top, height)
    tf = box.text_frame
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = f"• {line}"
        p.font.size = Pt(font_size)
        p.font.color.rgb = LIGHT_GRAY
        p.space_after = Pt(6)
    return box


def _table(slide, header: list[str], rows: list[list[str]], top, col_widths=None, font_size=10):
    n_rows, n_cols = len(rows) + 1, len(header)
    height = min(Inches(0.35) * n_rows, SLIDE_H - top - Inches(0.3))
    shape = slide.shapes.add_table(n_rows, n_cols, MARGIN, top, CONTENT_W, height)
    table = shape.table
    if col_widths:
        total = sum(col_widths)
        for i, w in enumerate(col_widths):
            table.columns[i].width = int(CONTENT_W * (w / total))

    for c, h in enumerate(header):
        cell = table.cell(0, c)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        p = cell.text_frame.paragraphs[0]
        p.font.bold = True
        p.font.size = Pt(font_size)
        p.font.color.rgb = WHITE

    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            cell = table.cell(r, c)
            cell.text = str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(0x14, 0x1B, 0x2E)
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(font_size)
            p.font.color.rgb = LIGHT_GRAY
    return shape


def _truncate_rows(rows: list[list[str]], limit: int) -> list[list[str]]:
    if len(rows) <= limit:
        return rows
    return rows[: limit - 1] + [[f"+ {len(rows) - limit + 1} more"] + [""] * (len(rows[0]) - 1)]


def generate_pptx(record: AnalysisRecord) -> bytes:
    t = record.transaction
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    total_value_creation = sum(o.estimated_value.base for o in record.opportunities)

    # --- Title slide
    slide = _blank_slide(prs)
    box = slide.shapes.add_textbox(MARGIN, Inches(2.6), CONTENT_W, Inches(2))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "DealLens Analysis"
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = ACCENT
    p.alignment = PP_ALIGN.CENTER
    p2 = tf.add_paragraph()
    p2.text = f"{t.acquirer_name} / {t.target_name}"
    p2.font.size = Pt(24)
    p2.font.color.rgb = WHITE
    p2.alignment = PP_ALIGN.CENTER
    p3 = tf.add_paragraph()
    p3.text = f"Generated {record.created_at:%Y-%m-%d %H:%M UTC}"
    p3.font.size = Pt(12)
    p3.font.color.rgb = MUTED
    p3.alignment = PP_ALIGN.CENTER

    # --- Executive summary
    slide = _blank_slide(prs)
    _title(slide, "Executive Summary")
    box = _body_textbox(slide, Inches(1.4))
    p = box.text_frame.paragraphs[0]
    p.text = record.executive_summary or "Not yet generated."
    p.font.size = Pt(15)
    p.font.color.rgb = LIGHT_GRAY

    # --- Recommendation / verdict
    if record.review is not None:
        verdict = compute_verdict(record.review, record.agent_assessments, total_value_creation, t)
        slide = _blank_slide(prs)
        _title(
            slide,
            "Recommendation",
            "A rule-based verdict, not a model's opinion — every reason traces to a specific reviewer finding or Red-Team challenge.",
        )
        banner = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGIN, Inches(1.5), CONTENT_W, Inches(0.7))
        banner.fill.solid()
        banner.fill.fore_color.rgb = VERDICT_COLOR[verdict.level.value]
        banner.line.fill.background()
        banner.shadow.inherit = False
        bp = banner.text_frame.paragraphs[0]
        bp.text = VERDICT_LABEL[verdict.level.value]
        bp.font.size = Pt(20)
        bp.font.bold = True
        bp.font.color.rgb = DARK_BG
        bp.alignment = PP_ALIGN.CENTER
        banner.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE

        reason_lines = list(verdict.reasons)
        if verdict.conditions:
            reason_lines.append("Conditions to resolve before proceeding:")
            reason_lines += [f"  – {c}" for c in verdict.conditions]
        _bullets(slide, reason_lines, top=Inches(2.4), font_size=13)

    # --- Deal economics
    if t.deal_value and record.opportunities:
        econ = calculate_deal_economics(total_value_creation, t.deal_value)
        slide = _blank_slide(prs)
        _title(slide, "Deal Economics")
        _bullets(
            slide,
            [
                f"Identified value creation: ${total_value_creation:,.0f}",
                f"Deal value: ${t.deal_value:,.0f}",
                f"Value creation as % of deal value: {econ['value_creation_pct_of_deal']:.2f}%",
            ],
            top=Inches(1.6),
            font_size=18,
        )

    # --- Company profiles
    slide = _blank_slide(prs)
    _title(slide, "Company Profiles")
    col_w = (CONTENT_W - Inches(0.4)) / 2
    left_positions = [MARGIN, MARGIN + col_w + Inches(0.4)]
    for pos, (label, profile) in zip(
        left_positions, (("Acquirer", record.acquirer_profile), ("Target", record.target_profile))
    ):
        if not profile:
            continue
        box = slide.shapes.add_textbox(pos, Inches(1.4), col_w, Inches(5.5))
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = f"{label}: {profile.company_name}"
        p.font.size = Pt(16)
        p.font.bold = True
        p.font.color.rgb = ACCENT

        p2 = tf.add_paragraph()
        p2.text = profile.business_description
        p2.font.size = Pt(12)
        p2.font.color.rgb = LIGHT_GRAY
        p2.space_before = Pt(8)

        stats = []
        if profile.revenue is not None:
            stats.append(f"Revenue: ${profile.revenue:,.0f}")
        if profile.revenue_growth_rate is not None:
            stats.append(f"Growth: {profile.revenue_growth_rate * 100:.1f}%")
        if profile.operating_margin is not None:
            stats.append(f"Operating margin: {profile.operating_margin * 100:.1f}%")
        for s in stats:
            ps = tf.add_paragraph()
            ps.text = s
            ps.font.size = Pt(11)
            ps.font.color.rgb = MUTED
            ps.space_before = Pt(4)

    # --- Strategic rationale
    if record.strategic_rationale:
        slide = _blank_slide(prs)
        _title(slide, "Strategic Rationale")
        box = _body_textbox(slide, Inches(1.4))
        p = box.text_frame.paragraphs[0]
        p.text = record.strategic_rationale.summary
        p.font.size = Pt(15)
        p.font.color.rgb = LIGHT_GRAY

    # --- Financial baseline
    if record.financial_baselines:
        slide = _blank_slide(prs)
        _title(slide, "Financial Baseline")
        rows = [[b.metric, f"{b.value:,.2f} {b.unit}", b.method] for b in record.financial_baselines]
        _table(slide, ["Metric", "Value", "Method"], _truncate_rows(rows, 10), top=Inches(1.5), col_widths=[2, 2, 4])

    # --- Opportunities
    revenue_opps = [o for o in record.opportunities if o.category.value == "revenue_synergy"]
    cost_opps = [o for o in record.opportunities if o.category.value == "cost_synergy"]
    for section_title, opps in (("Revenue Opportunities", revenue_opps), ("Cost-Saving Opportunities", cost_opps)):
        if not opps:
            continue
        slide = _blank_slide(prs)
        _title(slide, section_title)
        rows = [
            [
                o.title,
                f"${o.estimated_value.low:,.0f} / ${o.estimated_value.base:,.0f} / ${o.estimated_value.high:,.0f}",
                o.implementation_difficulty.value,
                o.time_horizon,
            ]
            for o in opps
        ]
        _table(
            slide,
            ["Opportunity", "Low / Base / High", "Difficulty", "Horizon"],
            _truncate_rows(rows, 8),
            top=Inches(1.5),
            col_widths=[3, 3, 1.5, 1.5],
        )

    # --- Risk register
    if record.risks:
        slide = _blank_slide(prs)
        _title(slide, "Risk Register", "Sorted by risk score (likelihood x impact, 1-9), highest first.")
        rows = [
            [r.title, r.category, r.likelihood.value, r.severity.value, str(r.score)]
            for r in sorted(record.risks, key=lambda r: r.score, reverse=True)
        ]
        _table(
            slide,
            ["Risk", "Category", "Likelihood", "Impact", "Score"],
            _truncate_rows(rows, 10),
            top=Inches(1.7),
            col_widths=[3, 2, 1.5, 1.5, 1],
        )

    # --- 100-day plan
    if record.integration_plan:
        slide = _blank_slide(prs)
        _title(slide, "100-Day Integration Plan")
        lines = []
        for phase in ("0-30 days", "31-60 days", "61-100 days"):
            actions = [a for a in record.integration_plan.actions if a.phase == phase]
            if not actions:
                continue
            lines.append(f"{phase}:")
            lines += [f"  {a.title} ({a.owner_role})" for a in actions]
        _bullets(slide, lines, top=Inches(1.4), font_size=13)

    # --- Reviewer notes
    if record.review:
        slide = _blank_slide(prs)
        _title(slide, "Reviewer Notes")
        lines = [f"Status: {'PASSED' if record.review.passed else 'ISSUES FOUND'}"]
        if record.review.citation_coverage_pct is not None:
            lines.append(f"Citation coverage: {record.review.citation_coverage_pct:.1f}%")
        _bullets(slide, lines, top=Inches(1.5), font_size=16, height=Inches(1.2))
        if record.review.issues:
            rows = [[i.severity.value, i.stage, i.item_title, i.problem] for i in record.review.issues]
            _table(
                slide,
                ["Severity", "Stage", "Item", "Problem"],
                _truncate_rows(rows, 8),
                top=Inches(2.8),
                col_widths=[1.2, 2, 2.5, 4],
            )

    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()
