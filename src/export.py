"""CSV export of the optimized route plan for drivers."""
from __future__ import annotations

import pandas as pd

from .models import Solution

EXPORT_COLUMNS = [
    "vehicle_id", "stop_order", "stop_id", "customer_name", "x", "y", "demand",
    "arrival_time", "service_start_time", "departure_time", "waiting_time",
    "load_after_stop", "route_distance", "route_duration",
]


def solution_to_dataframe(sol: Solution, df: pd.DataFrame) -> pd.DataFrame:
    """One row per stop, including the depot at the start and end of each route.

    ``load_after_stop`` is the cumulative demand served so far on the route.
    ``route_duration`` is the time the vehicle is back at the depot.
    """
    rows = []
    for r in sol.routes:
        for v in r.visits:
            c = df.iloc[v.node]
            rows.append({
                "vehicle_id": r.vehicle_id, "stop_order": v.order, "stop_id": v.stop_id,
                "customer_name": c["customer_name"], "x": c["x"], "y": c["y"], "demand": c["demand"],
                "arrival_time": v.arrival, "service_start_time": v.start,
                "departure_time": v.departure, "waiting_time": v.wait,
                "load_after_stop": v.load_after, "route_distance": r.distance,
                "route_duration": r.duration,
            })
    out = pd.DataFrame(rows, columns=EXPORT_COLUMNS)
    return out.round(2)


def to_csv_bytes(frame: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to UTF-8 CSV bytes for st.download_button."""
    return frame.to_csv(index=False).encode("utf-8")
