"""Plan data structures and the single route simulator shared by every method."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TOL = 1e-6


@dataclass
class StopVisit:
    """One stop on a route (node 0 = depot at the start and end)."""

    node: int
    stop_id: int
    order: int
    arrival: float
    wait: float
    start: float
    departure: float
    load_after: float  # cumulative demand served so far on this route
    late: bool


@dataclass
class RoutePlan:
    """A single vehicle route with its simulated schedule."""

    vehicle_id: int
    visits: list[StopVisit]
    distance: float
    duration: float          # time of return to the depot
    load: float
    capacity: float
    tw_violations: int
    over_capacity: bool

    @property
    def customer_nodes(self) -> list[int]:
        return [v.node for v in self.visits[1:-1]]

    @property
    def utilization(self) -> float:
        return self.load / self.capacity if self.capacity else 0.0

    @property
    def total_wait(self) -> float:
        return sum(v.wait for v in self.visits)


@dataclass
class Solution:
    """A full plan from one method (RouteIQ or the baseline)."""

    method: str
    routes: list[RoutePlan]
    unserved: list[int]          # node indices that no route serves
    runtime: float
    status: str
    vehicles_available: int
    capacity: float
    extra: dict = field(default_factory=dict)

    @property
    def served_nodes(self) -> set[int]:
        return {n for r in self.routes for n in r.customer_nodes}


def simulate_route(
    nodes: list[int],
    vehicle_id: int,
    df: pd.DataFrame,
    dist: np.ndarray,
    capacity: float,
) -> RoutePlan:
    """Simulate a route [0, c1, ..., ck, 0] in exact floating point.

    Vehicles leave the depot at its ready time and wait for ready times. Service must
    *start* by a customer's due time; the return to the depot must be by the depot due time.
    """
    ready = df["ready_time"].to_numpy(float)
    due = df["due_time"].to_numpy(float)
    service = df["service_time"].to_numpy(float)
    demand = df["demand"].to_numpy(float)
    ids = df["stop_id"].to_numpy(int)

    visits: list[StopVisit] = []
    t_depart = 0.0
    load = 0.0
    total_dist = 0.0
    violations = 0
    for order, node in enumerate(nodes):
        is_end = order == len(nodes) - 1 and order > 0
        if order == 0:
            arrival = 0.0
        else:
            d = float(dist[nodes[order - 1], node])
            total_dist += d
            arrival = t_depart + d
        start = max(arrival, ready[node]) if not is_end else arrival
        late = start > due[node] + TOL
        violations += int(late)
        if 0 < order < len(nodes) - 1:
            load += demand[node]
        depart = start + (service[node] if not is_end else 0.0)
        visits.append(StopVisit(
            node=node, stop_id=int(ids[node]), order=order, arrival=arrival,
            wait=0.0 if order == 0 or is_end else start - arrival, start=start,
            departure=depart, load_after=load, late=late,
        ))
        t_depart = depart
    return RoutePlan(
        vehicle_id=vehicle_id, visits=visits, distance=total_dist,
        duration=visits[-1].arrival, load=load, capacity=float(capacity),
        tw_violations=violations, over_capacity=load > capacity + TOL,
    )
