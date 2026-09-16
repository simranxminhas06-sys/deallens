"""Stage 7: Reviewer.

Deterministic, independently testable quality gate — no LLM call required.
It re-derives what it can (citation presence, duplicate titles, calculation
consistency, false precision) rather than asking a model to grade itself.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from schemas.analysis_models import (
    AnalysisRecord,
    ClaimType,
    EvidenceItem,
    ReviewIssue,
    ReviewResult,
    RiskSeverity,
    ValueOpportunity,
)
from tools.financial_calculator import TOOL_FUNCTIONS, calculate_precision_flag

HEDGE_WORDS = {"assume", "assumes", "assuming", "could", "might", "likely", "projected", "probably", "presumably"}
DUPLICATE_TITLE_THRESHOLD = 0.82


def _collect_evidence(record: AnalysisRecord) -> list[tuple[str, EvidenceItem]]:
    items: list[tuple[str, EvidenceItem]] = []
    for profile, label in ((record.acquirer_profile, "acquirer_profile"), (record.target_profile, "target_profile")):
        if profile:
            items += [(f"{label}:{profile.company_name}", e) for e in profile.evidence]
    if record.strategic_rationale:
        items += [("strategic_rationale", e) for e in record.strategic_rationale.supporting_points]
    for o in record.opportunities:
        items += [(f"opportunity:{o.title}", e) for e in o.evidence]
    for r in record.risks:
        items += [(f"risk:{r.title}", e) for e in r.evidence]
    return items


def _check_citations(record: AnalysisRecord) -> tuple[list[ReviewIssue], float]:
    issues = []
    evidence = _collect_evidence(record)
    factual = [e for e in evidence if e[1].claim_type in (ClaimType.DOCUMENTED_FACT, ClaimType.CALCULATED_RESULT)]
    cited = [e for e in factual if e[1].citations]
    for stage, item in factual:
        if not item.citations:
            issues.append(
                ReviewIssue(
                    severity=RiskSeverity.HIGH,
                    stage=stage,
                    item_title=item.claim[:80],
                    problem=f"Claim classified as {item.claim_type.value} has no citation.",
                    recommendation="Add a source document + location, or reclassify as an assumption/hypothesis.",
                )
            )
    coverage_pct = 100.0 * len(cited) / len(factual) if factual else 100.0
    return issues, coverage_pct


def _check_assumptions_as_facts(record: AnalysisRecord) -> list[ReviewIssue]:
    issues = []
    for stage, item in _collect_evidence(record):
        if item.claim_type != ClaimType.DOCUMENTED_FACT:
            continue
        words = set(re.findall(r"[a-z]+", item.claim.lower()))
        if words & HEDGE_WORDS:
            issues.append(
                ReviewIssue(
                    severity=RiskSeverity.MEDIUM,
                    stage=stage,
                    item_title=item.claim[:80],
                    problem="Claim uses hedging language but is classified as a documented fact.",
                    recommendation="Reclassify as an assumption or hypothesis, or remove the hedging language if the source is unambiguous.",
                )
            )
    return issues


def _check_duplicates(opportunities: list[ValueOpportunity]) -> list[ReviewIssue]:
    issues = []
    for i in range(len(opportunities)):
        for j in range(i + 1, len(opportunities)):
            a, b = opportunities[i], opportunities[j]
            similarity = SequenceMatcher(None, a.title.lower(), b.title.lower()).ratio()
            if similarity >= DUPLICATE_TITLE_THRESHOLD:
                issues.append(
                    ReviewIssue(
                        severity=RiskSeverity.MEDIUM,
                        stage="value_creation",
                        item_title=f"{a.title} / {b.title}",
                        problem=f"Opportunities appear to be duplicates (title similarity {similarity:.2f}).",
                        recommendation="Merge into a single opportunity or differentiate the underlying lever.",
                    )
                )
    return issues


def _check_precision(opportunities: list[ValueOpportunity]) -> list[ReviewIssue]:
    issues = []
    for o in opportunities:
        for label, value in (("low", o.estimated_value.low), ("base", o.estimated_value.base), ("high", o.estimated_value.high)):
            flag = calculate_precision_flag(value)
            if flag["flagged"]:
                issues.append(
                    ReviewIssue(
                        severity=RiskSeverity.LOW,
                        stage="value_creation",
                        item_title=o.title,
                        problem=f"{label} estimate (${value:,.0f}) states more precision than diligence-stage analysis supports.",
                        recommendation="Round to 2-3 significant figures.",
                    )
                )
    return issues


def _check_calculation_consistency(opportunities: list[ValueOpportunity], tool_call_log: list[dict]) -> list[ReviewIssue]:
    issues = []
    calc_calls = [c for c in tool_call_log if c["name"] in TOOL_FUNCTIONS]
    for o in opportunities:
        if not o.calculation_method:
            issues.append(
                ReviewIssue(
                    severity=RiskSeverity.MEDIUM,
                    stage="value_creation",
                    item_title=o.title,
                    problem="Opportunity has no recorded calculation_method.",
                    recommendation="Recompute using a financial_calculator function and record the method.",
                )
            )
            continue
        match = any(
            c["name"] == o.calculation_method
            and abs(c["result"].get("base", -1) - o.estimated_value.base) < max(1.0, 0.01 * abs(o.estimated_value.base))
            for c in calc_calls
        )
        if not match:
            issues.append(
                ReviewIssue(
                    severity=RiskSeverity.HIGH,
                    stage="value_creation",
                    item_title=o.title,
                    problem="Reported base estimate does not match any logged calculator call for this opportunity.",
                    recommendation="Recompute with the calculator tool and verify the reported value matches the tool output.",
                )
            )
    return issues


def _check_document_grounding(record: AnalysisRecord, valid_document_names: set[str]) -> list[ReviewIssue]:
    issues = []
    if not valid_document_names:
        return issues
    for o in record.opportunities:
        cited_docs = {c.source_document for e in o.evidence for c in e.citations}
        if not cited_docs & valid_document_names:
            issues.append(
                ReviewIssue(
                    severity=RiskSeverity.HIGH,
                    stage="value_creation",
                    item_title=o.title,
                    problem="No citation to any uploaded document; recommendation may be unrelated to supplied evidence.",
                    recommendation="Ground the opportunity in a specific uploaded document or remove it.",
                )
            )
    return issues


def review_analysis(
    record: AnalysisRecord,
    tool_call_log: list[dict] | None = None,
    valid_document_names: set[str] | None = None,
) -> ReviewResult:
    tool_call_log = tool_call_log or []
    issues: list[ReviewIssue] = []

    citation_issues, coverage_pct = _check_citations(record)
    issues += citation_issues
    issues += _check_assumptions_as_facts(record)
    issues += _check_duplicates(record.opportunities)
    issues += _check_precision(record.opportunities)
    issues += _check_calculation_consistency(record.opportunities, tool_call_log)
    issues += _check_document_grounding(record, valid_document_names or set())

    claim_type_coverage: dict[str, int] = {}
    for _, item in _collect_evidence(record):
        claim_type_coverage[item.claim_type.value] = claim_type_coverage.get(item.claim_type.value, 0) + 1

    passed = not any(i.severity == RiskSeverity.HIGH for i in issues)
    return ReviewResult(
        passed=passed,
        issues=issues,
        claim_type_coverage=claim_type_coverage,
        citation_coverage_pct=round(coverage_pct, 1),
    )
