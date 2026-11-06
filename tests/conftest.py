"""Shared fixtures and an independent route checker (does not use src.models)."""
import math
from pathlib import Path

import pytest

from src.data_loader import parse_solomon, subset_customers, validate_deliveries
from src.distance_matrix import euclidean_matrix

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def r101():
    full, capacity = parse_solomon(ROOT / "data/raw/R101.txt")
    return full, capacity


@pytest.fixture(scope="session")
def r101_25(r101):
    full, capacity = r101
    df = validate_deliveries(subset_customers(full, 25))
    return df, euclidean_matrix(df["x"], df["y"]), capacity


def independent_check(solution, df, capacity):
    """Re-derive every constraint with plain Python math; returns a list of problems."""
    rows = df.to_dict("records")
    problems, seen = [], []
    for r in solution.routes:
        seq = [v.node for v in r.visits]
        if seq[0] != 0 or seq[-1] != 0:
            problems.append("route does not start/end at depot")
        t, load = rows[0]["ready_time"], 0.0
        t += rows[0]["service_time"]
        for prev, cur in zip(seq, seq[1:]):
            a, b = rows[prev], rows[cur]
            t += math.hypot(a["x"] - b["x"], a["y"] - b["y"])
            if cur == 0:
                if t > rows[0]["due_time"] + 1e-6:
                    problems.append(f"depot return {t:.2f} after due {rows[0]['due_time']}")
                continue
            t = max(t, b["ready_time"])
            if t > b["due_time"] + 1e-6:
                problems.append(f"customer {b['stop_id']} served at {t:.2f} after due {b['due_time']}")
            load += b["demand"]
            t += b["service_time"]
            seen.append(cur)
        if load > capacity + 1e-6:
            problems.append(f"load {load} > capacity {capacity}")
    if len(seen) != len(set(seen)):
        problems.append("a customer is visited more than once")
    if sorted(seen + solution.unserved) != list(range(1, len(df))):
        problems.append("served + unserved does not cover every customer exactly once")
    return problems
