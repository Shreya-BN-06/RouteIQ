"""Loading, parsing and validating delivery datasets (Solomon format and CSV)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = [
    "stop_id", "customer_name", "x", "y", "demand",
    "ready_time", "due_time", "service_time", "is_depot",
]
NUMERIC_COLUMNS = ["x", "y", "demand", "ready_time", "due_time", "service_time"]
MAX_CUSTOMERS = 100


class DataValidationError(ValueError):
    """Raised when a dataset fails validation; ``messages`` lists every problem."""

    def __init__(self, messages: list[str]):
        super().__init__("; ".join(messages))
        self.messages = messages


def parse_solomon(path: str | Path) -> tuple[pd.DataFrame, int]:
    """Parse a Solomon VRPTW text file.

    Returns the full instance (depot first) and the benchmark vehicle capacity.
    """
    lines = Path(path).read_text().splitlines()
    capacity = None
    rows: list[list[float]] = []
    for i, line in enumerate(lines):
        parts = line.split()
        if capacity is None and "CAPACITY" in line.upper() and i + 1 < len(lines):
            nums = lines[i + 1].split()
            if len(nums) >= 2:
                capacity = int(float(nums[1]))
            continue
        if len(parts) == 7:
            try:
                rows.append([float(p) for p in parts])
            except ValueError:
                continue
    if not rows or capacity is None:
        raise DataValidationError(["Not a valid Solomon instance file."])
    df = pd.DataFrame(
        rows,
        columns=["stop_id", "x", "y", "demand", "ready_time", "due_time", "service_time"],
    )
    df["stop_id"] = df["stop_id"].astype(int)
    df["customer_name"] = np.where(df["stop_id"] == 0, "Depot", "Customer " + df["stop_id"].astype(str))
    df["is_depot"] = (df["stop_id"] == 0).astype(int)
    return df[REQUIRED_COLUMNS], capacity


def subset_customers(full: pd.DataFrame, n_customers: int) -> pd.DataFrame:
    """Keep the depot and customers 1..n (standard Solomon convention, no sampling)."""
    return full[full["stop_id"] <= n_customers].reset_index(drop=True)


def validate_deliveries(df: pd.DataFrame) -> pd.DataFrame:
    """Validate a delivery table and return a cleaned copy with the depot as row 0.

    Raises DataValidationError listing *all* problems found.
    """
    errors: list[str] = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataValidationError([f"Missing required column(s): {', '.join(missing)}."])

    out = df[REQUIRED_COLUMNS].copy()
    for col in NUMERIC_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    flag = out["is_depot"].astype(str).str.strip().str.lower()
    out["is_depot"] = flag.isin(["1", "1.0", "true", "yes"]).astype(int)

    bad_coord = out[["x", "y"]].isna().any(axis=1) | ~np.isfinite(out[["x", "y"]].fillna(0)).all(axis=1)
    if bad_coord.any():
        errors.append(f"Invalid coordinates (non-numeric or missing) in rows: {_rows(out, bad_coord)}.")
    other_nan = out[["demand", "ready_time", "due_time", "service_time"]].isna().any(axis=1)
    if other_nan.any():
        errors.append(f"Non-numeric or missing demand/time values in rows: {_rows(out, other_nan)}.")
    neg_demand = out["demand"] < 0
    if neg_demand.any():
        errors.append(f"Negative demand in rows: {_rows(out, neg_demand)}.")
    neg_service = out["service_time"] < 0
    if neg_service.any():
        errors.append(f"Negative service time in rows: {_rows(out, neg_service)}.")
    bad_tw = out["ready_time"] > out["due_time"]
    if bad_tw.any():
        errors.append(f"ready_time is greater than due_time in rows: {_rows(out, bad_tw)}.")
    if out["stop_id"].duplicated().any():
        errors.append("stop_id values must be unique.")

    n_depot = int(out["is_depot"].sum())
    if n_depot == 0:
        errors.append("Missing depot row (exactly one row needs is_depot = 1).")
    elif n_depot > 1:
        errors.append("More than one depot row found (exactly one row needs is_depot = 1).")
    n_customers = len(out) - n_depot
    if n_customers > MAX_CUSTOMERS:
        errors.append(f"{n_customers} delivery stops found; the limit is {MAX_CUSTOMERS}.")
    if n_customers < 1 and n_depot == 1:
        errors.append("At least one delivery stop is required.")

    if errors:
        raise DataValidationError(errors)

    out = pd.concat([out[out["is_depot"] == 1], out[out["is_depot"] == 0]]).reset_index(drop=True)
    out["stop_id"] = out["stop_id"].astype(int)
    return out


def _rows(df: pd.DataFrame, mask: pd.Series) -> str:
    """Format the (1-based) CSV row numbers where mask is True, truncated."""
    idx = [str(i + 1) for i in df.index[mask]]
    return ", ".join(idx[:8]) + (" …" if len(idx) > 8 else "")


def load_csv(source) -> pd.DataFrame:
    """Read a CSV path or file-like object and validate it."""
    try:
        df = pd.read_csv(source)
    except Exception as exc:  # noqa: BLE001 - surface a friendly message only
        raise DataValidationError(["The file could not be read as a CSV."]) from exc
    return validate_deliveries(df)


def add_urgent_customer(df: pd.DataFrame, seed_offset: int = 0) -> tuple[pd.DataFrame, int]:
    """Append one deterministic urgent customer inside the current coordinate range.

    The time window is tight (30 units) but always reachable straight from the depot,
    so the new customer is feasible for a fresh vehicle. Returns (new_df, new_stop_id).
    """
    depot = df.iloc[0]
    cust = df.iloc[1:]
    rng = np.random.default_rng(2026 + seed_offset)
    x = float(rng.integers(int(cust["x"].min()), int(cust["x"].max()) + 1))
    y = float(rng.integers(int(cust["y"].min()), int(cust["y"].max()) + 1))
    travel = float(np.hypot(x - depot["x"], y - depot["y"]))
    service = float(cust["service_time"].median())
    horizon = float(depot["due_time"])
    ready = float(np.ceil(travel)) + 20.0
    due = min(ready + 30.0, horizon - service - travel)
    ready = min(ready, due)
    demand = float(max(1, round(cust["demand"].median())))
    new_id = int(df["stop_id"].max()) + 1
    row = {
        "stop_id": new_id, "customer_name": f"Urgent {new_id}", "x": x, "y": y,
        "demand": demand, "ready_time": ready, "due_time": due,
        "service_time": service, "is_depot": 0,
    }
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True), new_id
