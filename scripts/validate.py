"""Reproducible validation: RouteIQ vs nearest-neighbour vs published best-known on Solomon R101.

Usage: python scripts/validate.py [--time-limit 8] [--time-limit-100 30]
Writes results/validation_results.csv.
"""
import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.baseline import nearest_neighbor  # noqa: E402
from src.data_loader import load_csv, parse_solomon  # noqa: E402
from src.distance_matrix import euclidean_matrix  # noqa: E402
from src.metrics import audit_solution, comparison_valid, compute_kpis, improvement_pct  # noqa: E402
from src.optimizer import solve_vrptw  # noqa: E402

# Reference values (vehicles, distance, distance convention).
# R101-100: SINTEF Solomon table, double precision (hierarchical objective).
# R101-25: exact-method literature value, which truncates distances to one decimal; SINTEF notes such
# results are not directly comparable with double precision, so the gap is computed in the SAME convention.
BEST_KNOWN = {25: (8, 617.1, "truncated"), 100: (19, 1650.8, "double")}
MAX_VEHICLES = 25


def truncated_distance(sol, d) -> float:
    """Total distance with every leg truncated to one decimal (exact-method convention)."""
    return sum(math.floor(d[a.node, b.node] * 10 + 1e-9) / 10
               for r in sol.routes for a, b in zip(r.visits, r.visits[1:]))


def run(n: int, time_limit: int) -> list[dict]:
    """Run both methods on the n-customer instance and return result rows."""
    df = load_csv(ROOT / f"data/processed/r101_{n}.csv")
    _, capacity = parse_solomon(ROOT / "data/raw/R101.txt")
    d = euclidean_matrix(df["x"], df["y"])
    sol = solve_vrptw(df, d, capacity, MAX_VEHICLES, time_limit)
    base = nearest_neighbor(df, d, capacity, MAX_VEHICLES)
    valid, _ = comparison_valid(sol, base)
    bk_v, bk_d, bk_conv = BEST_KNOWN[n]
    rows = []
    for name, s in (("RouteIQ (OR-Tools)", sol), ("Nearest-neighbour", base)):
        k = compute_kpis(s)
        bad = audit_solution(s, df, d, capacity)
        row = {
            "instance": f"R101-{n}", "method": name, "vehicles": k["vehicles"],
            "distance": round(k["distance"], 1),
            "distance_truncated_1dp": round(truncated_distance(s, d), 2), "solver_runtime_s": round(s.runtime, 2),
            "time_limit_s": time_limit if s is sol else "", "tw_violations": k["tw_violations"],
            "unassigned": k["unassigned"], "audit_ok": not bad,
            "improvement_distance_pct": "", "improvement_vehicles_pct": "",
            "best_known_vehicles": bk_v, "best_known_distance": bk_d, "best_known_convention": bk_conv,
            "gap_vs_best_known_pct": "",
        }
        if s is sol and valid:
            base_k = compute_kpis(base)
            row["improvement_distance_pct"] = round(improvement_pct(k["distance"], base_k["distance"]), 1)
            row["improvement_vehicles_pct"] = round(improvement_pct(k["vehicles"], base_k["vehicles"]), 1)
        if k["vehicles"] == bk_v and k["unassigned"] == 0:
            mine = truncated_distance(s, d) if bk_conv == "truncated" else k["distance"]
            row["gap_vs_best_known_pct"] = round((mine - bk_d) / bk_d * 100, 2)
        rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-limit", type=int, default=8, help="seconds for the 25-customer run")
    ap.add_argument("--time-limit-100", type=int, default=30, help="seconds for the 100-customer run")
    args = ap.parse_args()
    rows = run(25, args.time_limit) + run(100, args.time_limit_100)
    out = pd.DataFrame(rows)
    (ROOT / "results").mkdir(exist_ok=True)
    out.to_csv(ROOT / "results/validation_results.csv", index=False)
    pd.set_option("display.width", 220, "display.max_columns", 20)
    print(out.to_string(index=False))
    print(f"\nSaved {ROOT / 'results/validation_results.csv'}")


if __name__ == "__main__":
    main()