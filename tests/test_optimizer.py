from src.baseline import nearest_neighbor
from src.data_loader import add_urgent_customer
from src.distance_matrix import euclidean_matrix
from src.export import EXPORT_COLUMNS, solution_to_dataframe
from src.metrics import audit_solution, comparison_table, comparison_valid, compute_kpis
from src.optimizer import solve_vrptw
from tests.conftest import independent_check


def test_routeiq_plan_is_feasible_and_complete(r101_25):
    df, d, cap = r101_25
    sol = solve_vrptw(df, d, cap, 12, time_limit=3)
    assert sol.unserved == []
    assert independent_check(sol, df, cap) == []
    assert audit_solution(sol, df, d, cap) == []
    assert len(sol.routes) <= 10


def test_baseline_plan_is_feasible_with_same_constraints(r101_25):
    df, d, cap = r101_25
    base = nearest_neighbor(df, d, cap, 25)
    assert base.unserved == []
    assert independent_check(base, df, cap) == []


def test_routeiq_beats_baseline_on_vehicles_and_distance(r101_25):
    df, d, cap = r101_25
    sol, base = solve_vrptw(df, d, cap, 25, time_limit=3), nearest_neighbor(df, d, cap, 25)
    valid, _ = comparison_valid(sol, base)
    k1, k2 = compute_kpis(sol), compute_kpis(base)
    assert valid and k1["vehicles"] < k2["vehicles"] and k1["distance"] < k2["distance"]
    assert comparison_table(sol, base)["Improvement"].str.contains("%").any()


def test_small_fleet_returns_partial_plan_instead_of_failing(r101_25):
    df, d, cap = r101_25
    sol = solve_vrptw(df, d, cap, 3, time_limit=3)
    assert sol.routes and len(sol.routes) <= 3 and sol.unserved
    assert independent_check(sol, df, cap) == []


def test_improvement_hidden_when_baseline_leaves_customers_unassigned(r101_25):
    df, d, cap = r101_25
    sol, base = solve_vrptw(df, d, cap, 25, time_limit=3), nearest_neighbor(df, d, cap, 5)
    assert base.unserved and not comparison_valid(sol, base)[0]
    assert set(comparison_table(sol, base)["Improvement"]) == {"n/a"}


def test_customer_above_capacity_is_reported_unserved(r101_25):
    df, d, cap = r101_25
    big = df.copy(); big.loc[5, "demand"] = cap + 1
    sol = solve_vrptw(big, d, cap, 12, time_limit=3)
    assert 5 in sol.unserved and independent_check(sol, big, cap) == []


def test_urgent_customer_is_served_and_plan_feasible(r101_25):
    df, _, cap = r101_25
    df2, _ = add_urgent_customer(df, 0)
    d2 = euclidean_matrix(df2["x"], df2["y"])
    sol = solve_vrptw(df2, d2, cap, 25, time_limit=3)
    assert sol.unserved == [] and independent_check(sol, df2, cap) == []


def test_export_schema_and_route_boundaries(r101_25):
    df, d, cap = r101_25
    sol = solve_vrptw(df, d, cap, 12, time_limit=3)
    out = solution_to_dataframe(sol, df)
    assert list(out.columns) == EXPORT_COLUMNS
    for _, g in out.groupby("vehicle_id"):
        assert g.iloc[0]["stop_id"] == 0 and g.iloc[-1]["stop_id"] == 0
        assert g["stop_order"].tolist() == list(range(len(g)))
