"""CVRPTW model solved with Google OR-Tools.

Design choices (all documented in the README):
* Integer scaling with conservative rounding (see distance_matrix.py).
* A fixed cost per vehicle used, so fleet size is minimised first and distance second,
  which is how Solomon benchmark results are normally ranked.
* Customers are *optional* with a large drop penalty. Normally every customer is served,
  but if the fleet is too small the solver returns the best partial plan and reports
  which customers are unserved, instead of failing with no solution.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .distance_matrix import SCALE, solver_inputs
from .models import RoutePlan, Solution, simulate_route

DEFAULT_TIME_LIMIT = 8
DEFAULT_VEHICLE_FIXED_COST = 1000.0  # distance units charged per vehicle used


def _status_name(code: int) -> str:
    """Human-readable routing status (robust across OR-Tools versions)."""
    try:
        return routing_enums_pb2.RoutingSearchStatus.Value.Name(int(code)).removeprefix("ROUTING_").lower()
    except Exception:  # noqa: BLE001
        return f"code {code}"


def solve_vrptw(
    df: pd.DataFrame,
    dist: np.ndarray,
    capacity: float,
    num_vehicles: int,
    time_limit: int = DEFAULT_TIME_LIMIT,
    vehicle_fixed_cost: float = DEFAULT_VEHICLE_FIXED_COST,
    allow_unserved: bool = True,
) -> Solution:
    """Solve the capacitated VRP with time windows and return a Solution.

    ``df`` must have the depot as row 0 (see data_loader.validate_deliveries).
    First solution: PARALLEL_CHEAPEST_INSERTION; metaheuristic: GUIDED_LOCAL_SEARCH.
    """
    t0 = time.perf_counter()
    n = len(df)
    inp = solver_inputs(df, dist)
    horizon = inp.due[0]
    cap_int = int(capacity)

    manager = pywrapcp.RoutingIndexManager(n, num_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)
    node = manager.IndexToNode

    arc = routing.RegisterTransitCallback(lambda i, j: inp.dist[node(i)][node(j)])
    routing.SetArcCostEvaluatorOfAllVehicles(arc)
    routing.SetFixedCostOfAllVehicles(int(vehicle_fixed_cost * SCALE))

    # Time dimension: travel + service at the departure node; waiting is allowed (slack).
    tcb = routing.RegisterTransitCallback(
        lambda i, j: inp.travel[node(i)][node(j)] + inp.service[node(i)]
    )
    routing.AddDimension(tcb, horizon, horizon, True, "Time")
    time_dim = routing.GetDimensionOrDie("Time")

    force_drop = []
    for c in range(1, n):
        idx = manager.NodeToIndex(c)
        lo, hi = inp.ready[c], min(inp.due[c], horizon)
        if lo > hi:
            force_drop.append(idx)  # window can never be met
        else:
            time_dim.CumulVar(idx).SetRange(lo, hi)
    for v in range(num_vehicles):
        for var in (time_dim.CumulVar(routing.Start(v)), time_dim.CumulVar(routing.End(v))):
            var.SetRange(inp.ready[0], inp.due[0])

    # Capacity dimension.
    dcb = routing.RegisterUnaryTransitCallback(lambda i: inp.demand[node(i)])
    routing.AddDimensionWithVehicleCapacity(dcb, 0, [cap_int] * num_vehicles, True, "Capacity")

    # Optional customers with a penalty far above any vehicle + detour cost.
    if allow_unserved:
        penalty = int(vehicle_fixed_cost * SCALE * 10)
        for c in range(1, n):
            routing.AddDisjunction([manager.NodeToIndex(c)], penalty)
    for idx in force_drop:
        routing.solver().Add(routing.ActiveVar(idx) == 0)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(int(time_limit))

    sol = routing.SolveWithParameters(params)
    runtime = time.perf_counter() - t0
    status = _status_name(routing.status())
    if sol is None:
        return Solution("RouteIQ", [], list(range(1, n)), runtime, f"no solution ({status})",
                        num_vehicles, capacity)

    routes: list[RoutePlan] = []
    served: set[int] = set()
    for v in range(num_vehicles):
        idx = routing.Start(v)
        seq = [0]
        idx = sol.Value(routing.NextVar(idx))
        while not routing.IsEnd(idx):
            seq.append(node(idx))
            idx = sol.Value(routing.NextVar(idx))
        if len(seq) > 1:
            seq.append(0)
            served.update(seq[1:-1])
            routes.append(simulate_route(seq, len(routes) + 1, df, dist, capacity))
    unserved = [c for c in range(1, n) if c not in served]
    return Solution(
        "RouteIQ", routes, unserved, runtime, f"feasible ({status})", num_vehicles, capacity,
        extra={"objective_scaled": sol.ObjectiveValue()},
    )
