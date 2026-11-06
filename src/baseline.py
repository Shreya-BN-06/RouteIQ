"""Nearest-neighbour baseline that obeys exactly the same constraints as RouteIQ."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .models import RoutePlan, Solution, TOL, simulate_route


def nearest_neighbor(df: pd.DataFrame, dist: np.ndarray, capacity: float, num_vehicles: int) -> Solution:
    """Build routes one vehicle at a time, always going to the nearest feasible customer.

    A customer is feasible if, after adding it: capacity holds, service starts within its
    time window, and the vehicle can still return to the depot by the depot due time.
    Vehicles are limited to ``num_vehicles``; leftovers are reported as unassigned.
    """
    t0 = time.perf_counter()
    ready = df["ready_time"].to_numpy(float)
    due = df["due_time"].to_numpy(float)
    service = df["service_time"].to_numpy(float)
    demand = df["demand"].to_numpy(float)
    n = len(df)
    unvisited = set(range(1, n))
    routes: list[RoutePlan] = []

    for _ in range(num_vehicles):
        if not unvisited:
            break
        seq, cur, t_dep, load = [0], 0, max(0.0, ready[0]) + service[0], 0.0
        while True:
            best, best_d, best_depart = None, np.inf, 0.0
            for j in sorted(unvisited):
                if load + demand[j] > capacity + TOL:
                    continue
                start = max(t_dep + dist[cur, j], ready[j])
                if start > due[j] + TOL:
                    continue
                depart = start + service[j]
                if depart + dist[j, 0] > due[0] + TOL:
                    continue
                if dist[cur, j] < best_d - 1e-12:
                    best, best_d, best_depart = j, dist[cur, j], depart
            if best is None:
                break
            seq.append(best)
            unvisited.discard(best)
            load += demand[best]
            cur, t_dep = best, best_depart
        if len(seq) == 1:
            break  # a fresh vehicle cannot serve anything that remains
        seq.append(0)
        routes.append(simulate_route(seq, len(routes) + 1, df, dist, capacity))

    return Solution(
        "Nearest-neighbour baseline", routes, sorted(unvisited), time.perf_counter() - t0,
        "heuristic", num_vehicles, capacity,
    )
