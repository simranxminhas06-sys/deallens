"""Assembles the final Markdown report (executive summary + full analysis) with citations."""

from __future__ import annotations

from schemas.analysis_models import AnalysisRecord, EvidenceItem


def _fmt_evidence(evidence: list[EvidenceItem]) -> str:
    if not evidence:
        return ""
    lines = []
    for e in evidence:
        cites = "; ".join(f"{c.source_document} ({c.location})" for c in e.citations) or "no citation"
        lines.append(f"  - *[{e.claim_type.value}]* {e.claim} — {cites}")
    return "\n".join(lines)


def generate_report(record: AnalysisRecord) -> str:
    t = record.transaction
    lines: list[str] = []
    lines.append(f"# DealLens Analysis: {t.acquirer_name} / {t.target_name}\n")
    lines.append(f"_Generated {record.created_at:%Y-%m-%d %H:%M UTC}_\n")

    lines.append("## Executive Summary\n")
    lines.append(record.executive_summary or "_Not yet generated._")
    lines.append("")

    lines.append("## Company Profiles\n")
    for label, profile in (("Acquirer", record.acquirer_profile), ("Target", record.target_profile)):
        if not profile:
            continue
        lines.append(f"### {label}: {profile.company_name}\n")
        lines.append(profile.business_description)
        stats = []
        if profile.revenue is not None:
            stats.append(f"Revenue: ${profile.revenue:,.0f}")
        if profile.revenue_growth_rate is not None:
            stats.append(f"Growth: {profile.revenue_growth_rate * 100:.1f}%")
        if profile.operating_margin is not None:
            stats.append(f"Operating margin: {profile.operating_margin * 100:.1f}%")
        if stats:
            lines.append("\n" + " | ".join(stats))
        if profile.evidence:
            lines.append("\nEvidence:\n" + _fmt_evidence(profile.evidence))
        lines.append("")

    if record.strategic_rationale:
        lines.append("## Strategic Rationale\n")
        lines.append(record.strategic_rationale.summary)
        if record.strategic_rationale.supporting_points:
            lines.append("\nSupporting evidence:\n" + _fmt_evidence(record.strategic_rationale.supporting_points))
        lines.append("")

    if record.financial_baselines:
        lines.append("## Financial Baseline\n")
        lines.append("| Metric | Value | Method |")
        lines.append("|---|---|---|")
        for b in record.financial_baselines:
            lines.append(f"| {b.metric} | {b.value:,.2f} {b.unit} | {b.method} |")
        lines.append("")

    revenue_opps = [o for o in record.opportunities if o.category.value == "revenue_synergy"]
    cost_opps = [o for o in record.opportunities if o.category.value == "cost_synergy"]

    for title, opps in (("Revenue Opportunities", revenue_opps), ("Cost-Saving Opportunities", cost_opps)):
        if not opps:
            continue
        lines.append(f"## {title}\n")
        lines.append("| Opportunity | Estimated Value (Low / Base / High) | Difficulty | Horizon |")
        lines.append("|---|---|---|---|")
        for o in opps:
            v = o.estimated_value
            lines.append(
                f"| {o.title} | ${v.low:,.0f} / ${v.base:,.0f} / ${v.high:,.0f} "
                f"| {o.implementation_difficulty.value} | {o.time_horizon} |"
            )
        lines.append("")
        for o in opps:
            lines.append(f"**{o.title}**\n")
            lines.append(o.rationale)
            if o.assumptions:
                lines.append("\nAssumptions: " + "; ".join(o.assumptions))
            if o.key_risks:
                lines.append("\nKey risks: " + "; ".join(o.key_risks))
            if o.evidence:
                lines.append("\nEvidence:\n" + _fmt_evidence(o.evidence))
            lines.append("")

    if record.risks:
        lines.append("## Risk Register\n")
        lines.append("| Risk | Category | Severity | Mitigation |")
        lines.append("|---|---|---|---|")
        for r in record.risks:
            lines.append(f"| {r.title} | {r.category} | {r.severity.value} | {r.mitigation} |")
        lines.append("")

    if record.integration_plan:
        lines.append("## 100-Day Integration Plan\n")
        if record.integration_plan.guiding_principles:
            lines.append("Guiding principles: " + "; ".join(record.integration_plan.guiding_principles) + "\n")
        for phase in ("0-30 days", "31-60 days", "61-100 days"):
            actions = [a for a in record.integration_plan.actions if a.phase == phase]
            if not actions:
                continue
            lines.append(f"### {phase}\n")
            for a in actions:
                lines.append(f"- **{a.title}** ({a.owner_role}) — {a.description}")
                if a.success_metric:
                    lines.append(f"  - Success metric: {a.success_metric}")
                if a.risks:
                    lines.append(f"  - Risks: {'; '.join(a.risks)}")
            lines.append("")
        lines.append(f"Governance: {record.integration_plan.governance}\n")

    if record.review:
        lines.append("## Reviewer Notes\n")
        lines.append(f"Status: {'PASSED' if record.review.passed else 'ISSUES FOUND'}")
        if record.review.citation_coverage_pct is not None:
            lines.append(f"\nCitation coverage: {record.review.citation_coverage_pct:.1f}%")
        if record.review.issues:
            lines.append("\n| Severity | Stage | Item | Problem | Recommendation |")
            lines.append("|---|---|---|---|---|")
            for i in record.review.issues:
                lines.append(f"| {i.severity.value} | {i.stage} | {i.item_title} | {i.problem} | {i.recommendation} |")
        lines.append("")

    return "\n".join(lines)


def save_report(record: AnalysisRecord, path: str) -> str:
    content = generate_report(record)
    with open(path, "w") as f:
        f.write(content)
    return path
