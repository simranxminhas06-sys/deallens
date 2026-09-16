"""Optional stage: sensitivity / tornado analysis.

Pure, deterministic, no LLM: reuses tools/financial_calculator.py to show which single
assumption moves total value creation the most, holding every other assumption fixed at
its current value. This is the standard "tornado chart" a deal team builds around a
synergy case, not a model-generated narrative.
"""

from __future__ import annotations

from schemas.analysis_models import ValueOpportunity
from tools.financial_calculator import TOOL_FUNCTIONS

DEFAULT_SWING_PCT = 0.20  # +/-20% swing for a parameter with no stated low/high sibling


def _param_bounds(param: str, inputs: dict) -> tuple[float, float] | None:
    """(low, high) to swing one parameter across, holding the rest of `inputs` fixed.

    A `_base` parameter that has `_low`/`_high` siblings (e.g. reduction_pct_base next to
    reduction_pct_low/high) uses those already-stated bounds. A `_low`/`_high` parameter
    itself is skipped — its sibling `_base` entry already covers that swing. Anything else
    (a cost or revenue base, a margin) gets a default +/-20% swing, clamped to [0, 1] for
    fraction-like ("pct") parameters and to a non-negative floor otherwise.
    """
    value = inputs.get(param)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if param.endswith("_low") or param.endswith("_high"):
        return None
    if param.endswith("_base"):
        low_key = param[: -len("_base")] + "_low"
        high_key = param[: -len("_base")] + "_high"
        if low_key in inputs and high_key in inputs:
            return float(inputs[low_key]), float(inputs[high_key])
    low = value * (1 - DEFAULT_SWING_PCT)
    high = value * (1 + DEFAULT_SWING_PCT)
    if "pct" in param:
        low, high = max(0.0, low), min(1.0, high)
    else:
        low = max(0.0, low)
    return float(low), float(high)


def compute_tornado_rows(opportunities: list[ValueOpportunity]) -> list[dict]:
    """One row per (opportunity, assumption), ranked by how much swinging that single
    assumption to its low/high bound moves total value creation across all opportunities,
    everything else held at its current value.
    """
    total_base = sum(o.estimated_value.base for o in opportunities)
    rows: list[dict] = []
    for o in opportunities:
        fn = TOOL_FUNCTIONS.get(o.calculation_method)
        if not fn or not o.calculation_inputs:
            continue
        for param in o.calculation_inputs:
            bounds = _param_bounds(param, o.calculation_inputs)
            if bounds is None:
                continue
            low_bound, high_bound = bounds
            try:
                low_result = fn(**{**o.calculation_inputs, param: low_bound})
                high_result = fn(**{**o.calculation_inputs, param: high_bound})
            except ValueError:
                continue
            opp_low = min(low_result["base"], high_result["base"])
            opp_high = max(low_result["base"], high_result["base"])
            total_low = total_base - o.estimated_value.base + opp_low
            total_high = total_base - o.estimated_value.base + opp_high
            rows.append(
                {
                    "opportunity": o.title,
                    "parameter": param,
                    "total_low": round(total_low, 2),
                    "total_high": round(total_high, 2),
                    "swing": round(abs(total_high - total_low), 2),
                }
            )
    rows.sort(key=lambda r: r["swing"], reverse=True)
    return rows


def compute_scenario_total(opportunities: list[ValueOpportunity], direction: str) -> float:
    """Total value creation if every swingable assumption, across every opportunity, moves to
    its pessimistic ("low"/downside) or optimistic ("high"/upside) bound simultaneously — the
    combined-stress-test companion to the tornado chart's one-assumption-at-a-time view.

    Every calculation here is monotonic in each of its inputs (all multiplicative, no offsetting
    terms) — but not always in the same DIRECTION: more uplift_pct or reduction_pct is better
    (a benefit), while more attrition_pct (calculate_dis_synergy_scenario) is worse (a cost). So
    rather than assuming the parameter named "_low" always produces the worse output, each bound
    is evaluated and whichever one actually produces the lower/higher result is used — the same
    min/max approach compute_tornado_rows already takes, just applied while building the combined
    scenario instead of a single-parameter swing.
    """
    if direction not in ("low", "high"):
        raise ValueError("direction must be 'low' or 'high'")
    total = 0.0
    for o in opportunities:
        fn = TOOL_FUNCTIONS.get(o.calculation_method)
        if not fn or not o.calculation_inputs:
            total += o.estimated_value.base
            continue
        swung_inputs = dict(o.calculation_inputs)
        for param in o.calculation_inputs:
            bounds = _param_bounds(param, o.calculation_inputs)
            if bounds is None:
                continue
            low_bound, high_bound = bounds
            try:
                low_result = fn(**{**swung_inputs, param: low_bound})["base"]
                high_result = fn(**{**swung_inputs, param: high_bound})["base"]
            except ValueError:
                continue
            worse_bound = low_bound if low_result <= high_result else high_bound
            better_bound = high_bound if worse_bound == low_bound else low_bound
            swung_inputs[param] = worse_bound if direction == "low" else better_bound
        try:
            result = fn(**swung_inputs)
            total += result["base"]
        except ValueError:
            total += o.estimated_value.base
    return round(total, 2)
