import pandas as pd
import pytest

from src.data_loader import (MAX_CUSTOMERS, REQUIRED_COLUMNS, DataValidationError, add_urgent_customer,
                             load_csv, subset_customers, validate_deliveries)
from tests.conftest import ROOT


def good_df():
    return pd.DataFrame([
        [0, "Depot", 0, 0, 0, 0, 100, 0, 1],
        [1, "A", 5, 5, 3, 10, 50, 2, 0],
        [2, "B", 9, 1, 4, 20, 60, 2, 0],
    ], columns=REQUIRED_COLUMNS)


def test_parse_r101_matches_benchmark(r101):
    full, capacity = r101
    assert capacity == 200 and full.shape == (101, 9)
    depot = full.iloc[0]
    assert (depot.x, depot.y, depot.demand, depot.ready_time, depot.due_time) == (35, 35, 0, 0, 230)
    assert list(full.columns) == REQUIRED_COLUMNS


def test_subset_keeps_ids_0_to_25_in_order(r101):
    sub = subset_customers(r101[0], 25)
    assert sub["stop_id"].tolist() == list(range(26))


@pytest.mark.parametrize("name,n", [("r101_25", 26), ("r101_100", 101)])
def test_processed_csvs_load_and_match_raw(r101, name, n):
    df = load_csv(ROOT / f"data/processed/{name}.csv")
    assert len(df) == n
    raw = r101[0].iloc[:n].reset_index(drop=True)
    pd.testing.assert_frame_equal(df[["x", "y", "demand", "ready_time", "due_time"]].astype(float),
                                  raw[["x", "y", "demand", "ready_time", "due_time"]].astype(float))


def test_valid_frame_puts_depot_first():
    shuffled = good_df().iloc[[2, 0, 1]].reset_index(drop=True)
    assert validate_deliveries(shuffled).iloc[0]["is_depot"] == 1


def _msgs(df):
    with pytest.raises(DataValidationError) as e:
        validate_deliveries(df)
    return " ".join(e.value.messages)


def test_missing_columns():
    assert "Missing required column" in _msgs(good_df().drop(columns=["demand"]))


def test_negative_demand():
    d = good_df(); d.loc[1, "demand"] = -1
    assert "Negative demand" in _msgs(d)


def test_invalid_coordinates():
    d = good_df(); d["x"] = d["x"].astype(object); d.loc[1, "x"] = "abc"
    assert "Invalid coordinates" in _msgs(d)


def test_ready_after_due():
    d = good_df(); d.loc[1, "ready_time"] = 99
    assert "ready_time is greater than due_time" in _msgs(d)


def test_missing_depot():
    d = good_df(); d.loc[0, "is_depot"] = 0
    assert "Missing depot" in _msgs(d)


def test_too_many_stops():
    rows = [[0, "Depot", 0, 0, 0, 0, 100, 0, 1]]
    rows += [[i, f"C{i}", i % 10, i % 7, 1, 0, 50, 1, 0] for i in range(1, MAX_CUSTOMERS + 2)]
    assert "limit is 100" in _msgs(pd.DataFrame(rows, columns=REQUIRED_COLUMNS))


def test_urgent_customer_is_deterministic_and_reachable(r101):
    df = validate_deliveries(subset_customers(r101[0], 25))
    a, new_id = add_urgent_customer(df, 0)
    b, _ = add_urgent_customer(df, 0)
    pd.testing.assert_frame_equal(a, b)
    row = a.iloc[-1]
    travel = ((row.x - df.iloc[0].x) ** 2 + (row.y - df.iloc[0].y) ** 2) ** 0.5
    assert new_id == 26 and row.due_time - row.ready_time <= 30
    assert travel <= row.due_time and row.due_time + row.service_time + travel <= df.iloc[0].due_time
