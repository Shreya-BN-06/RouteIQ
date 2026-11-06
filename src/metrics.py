"""KPIs, baseline comparison and an independent-of-solver feasibility audit."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .models import Solution, TOL, simulate_route


@dataclass(frozen=True)
class Assumptions:
    """Illustrative, configurable conversion factors (NOT measured real-world values)."""

    fuel_cost_per_unit: float = 0.18   # currency units per distance unit
    co2_kg_per_unit: float = 0.12      # kg CO2 per distance unit


# (key, label, lower_is_better_for_improvement)
IMPROVABLE = ["distance", "travel_time", "vehicles", "fuel_cost", "co2_kg"]


def compute_kpis(sol: Solution, a: Assumptions = Assumptions()) -> dict:
    """Aggregate KPIs for one solution."""
    dist = sum(r.distance for r in sol.routes)
    utils = [r.utilization for r in sol.routes]
    return {
        "distance": dist,
        "travel_time": dist,  # Solomon convention: travel time == distance
        "duration": sum(r.duration for r in sol.routes),
        "vehicles": len(sol.routes),
        "avg_util": float(np.mean(utils)) if utils else 0.0,
        "max_util": float(max(utils)) if utils else 0.0,
        "tw_violations": sum(r.tw_violations for r in sol.routes),
        "unassigned": len(sol.unserved),
        "fuel_cost": dist * a.fuel_cost_per_unit,
        "co2_kg": dist * a.co2_kg_per_unit,
    }


def comparison_valid(sol: Solution, base: Solution) -> tuple[bool, str]:
    """Distance/cost comparisons are only fair if both plans serve the same customers."""
    if not sol.routes or not base.routes:
        return False, "one of the plans has no routes"
    if sol.served_nodes != base.served_nodes:
        return False, (
            f"the plans serve different customers (RouteIQ leaves {len(sol.unserved)} unserved, "
            f"baseline leaves {len(base.unserved)} unassigned)"
        )
    return True, ""


def improvement_pct(ours: float, base: float) -> float | None:
    """Percentage reduction versus the baseline (positive = better); None if undefined."""
    if base is None or base <= 0:
        return None
    return (base - ours) / base * 100.0


def comparison_table(sol: Solution, base: Solution, a: Assumptions = Assumptions()) -> pd.DataFrame:
    """Side-by-side KPI table with improvement % where the comparison is valid."""
    k1, k2 = compute_kpis(sol, a), compute_kpis(base, a)
    valid, _ = comparison_valid(sol, base)
    rows = [
        ("Total distance", "distance", "{:.1f}"),
        ("Total travel time", "travel_time", "{:.1f}"),
        ("Vehicles used", "vehicles", "{:.0f}"),
        ("Avg vehicle utilization", "avg_util", "{:.0%}"),
        ("Max vehicle utilization", "max_util", "{:.0%}"),
        ("Time-window violations", "tw_violations", "{:.0f}"),
        ("Unassigned customers", "unassigned", "{:.0f}"),
        ("Est. fuel cost", "fuel_cost", "{:.2f}"),
        ("Est. CO2 (kg)", "co2_kg", "{:.1f}"),
    ]
    out = []
    for label, key, fmt in rows:
        imp = "n/a"
        if valid and key in IMPROVABLE:
            p = improvement_pct(k1[key], k2[key])
            imp = "—" if p is None else f"{p:+.1f}%"
        out.append({"Metric": label, "RouteIQ": fmt.format(k1[key]),
                    "Baseline": fmt.format(k2[key]), "Improvement": imp})
    return pd.DataFrame(out)


def audit_solution(sol: Solution, df: pd.DataFrame, dist: np.ndarray, capacity: float) -> list[str]:
    """Re-check a plan from scratch; returns a list of problems (empty = valid).

    Checks depot start/end, no duplicate visits, capacity, time windows and depot due time.
    """
    problems: list[str] = []
    seen: set[int] = set()
    for r in sol.routes:
        nodes = [v.node for v in r.visits]
        if nodes[0] != 0 or nodes[-1] != 0:
            problems.append(f"V{r.vehicle_id}: route must start and end at the depot")
        dup = seen.intersection(nodes[1:-1])
        if dup:
            problems.append(f"V{r.vehicle_id}: customers visited twice: {sorted(dup)}")
        seen.update(nodes[1:-1])
        check = simulate_route(nodes, r.vehicle_id, df, dist, capacity)
        if check.over_capacity:
            problems.append(f"V{r.vehicle_id}: load {check.load:.0f} exceeds capacity {capacity:.0f}")
        if check.tw_violations:
            problems.append(f"V{r.vehicle_id}: {check.tw_violations} time-window violation(s)")
    if len(sol.routes) > sol.vehicles_available:
        problems.append("more routes than available vehicles")
    return problems
