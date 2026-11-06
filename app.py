"""RouteIQ — Intelligent Last-Mile Delivery Route Optimization (Streamlit app)."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from src.baseline import nearest_neighbor
from src.data_loader import (MAX_CUSTOMERS, DataValidationError, add_urgent_customer,
                             load_csv)
from src.distance_matrix import euclidean_matrix
from src.export import solution_to_dataframe, to_csv_bytes
from src.maps import build_map
from src.metrics import (IMPROVABLE, Assumptions, audit_solution, comparison_table,
                         comparison_valid, compute_kpis, improvement_pct)
from src.optimizer import solve_vrptw

log = logging.getLogger("routeiq")
ROOT = Path(__file__).parent
SAMPLE_25 = "Solomon R101 · 25 customers (demo)"
SAMPLE_100 = "Solomon R101 · 100 customers (benchmark)"
UPLOAD = "Upload your own CSV"
SAMPLES = {SAMPLE_25: ROOT / "data/processed/r101_25.csv", SAMPLE_100: ROOT / "data/processed/r101_100.csv"}
BENCH_CAPACITY, MAX_VEHICLES, DEFAULT_TIME_LIMIT = 200, 25, 8

st.set_page_config(page_title="RouteIQ", page_icon="🚚", layout="wide")


# ---------- cached computation ----------
@st.cache_data(show_spinner=False)
def cached_csv(path: str) -> pd.DataFrame:
    """Load and validate a bundled CSV."""
    return load_csv(path)


@st.cache_data(show_spinner=False)
def cached_matrix(x: tuple, y: tuple):
    """Euclidean distance matrix (also the travel-time matrix for Solomon data)."""
    return euclidean_matrix(x, y)


@st.cache_data(show_spinner=False, max_entries=32)
def cached_solve(df: pd.DataFrame, vehicles: int, capacity: float, time_limit: int):
    """RouteIQ solve; identical inputs return the stored result instantly."""
    return solve_vrptw(df, cached_matrix(tuple(df["x"]), tuple(df["y"])), capacity, vehicles, time_limit)


@st.cache_data(show_spinner=False, max_entries=32)
def cached_baseline(df: pd.DataFrame, vehicles: int, capacity: float):
    """Nearest-neighbour baseline under the same constraints."""
    return nearest_neighbor(df, cached_matrix(tuple(df["x"]), tuple(df["y"])), capacity, vehicles)


# ---------- state ----------
def load_sample(name: str) -> None:
    """Switch to a bundled dataset and reset everything derived from it."""
    ss = st.session_state
    ss.df, ss.dataset_name = cached_csv(str(SAMPLES[name])), name
    ss.capacity, ss.n_vehicles = BENCH_CAPACITY, MAX_VEHICLES
    ss.solution = ss.baseline = ss.scenario = None
    ss.urgent_count, ss.upload_sig, ss.run = 0, None, True


def init_state() -> None:
    ss = st.session_state
    if "df" not in ss:
        ss.dataset = SAMPLE_25
        ss.time_limit = DEFAULT_TIME_LIMIT
        ss.fuel, ss.co2, ss.upload_errors, ss.flash = 0.18, 0.12, [], []
        load_sample(SAMPLE_25)


def snapshot(label: str) -> None:
    if st.session_state.solution is not None:
        st.session_state.scenario = {"label": label, "before": compute_kpis(st.session_state.solution)}


def on_dataset() -> None:
    ss = st.session_state
    ss.upload_errors = []
    if ss.dataset in SAMPLES:
        load_sample(ss.dataset)


def on_optimize() -> None:
    st.session_state.scenario, st.session_state.run = None, True


def on_urgent() -> None:
    ss = st.session_state
    if len(ss.df) - 1 >= MAX_CUSTOMERS:
        ss.flash.append(("error", f"The dataset already has {MAX_CUSTOMERS} delivery stops (the limit)."))
        return
    snapshot("Added urgent delivery")
    ss.df, new_id = add_urgent_customer(ss.df, ss.urgent_count)
    ss.urgent_count += 1
    ss.flash.append(("info", f"Added urgent customer {new_id} with a tight 30-unit time window."))
    ss.run = True


def on_remove_vehicle() -> None:
    ss = st.session_state
    used = len(ss.solution.routes) if ss.solution else ss.n_vehicles
    new = max(1, min(ss.n_vehicles, used) - 1)
    if new == ss.n_vehicles:
        ss.flash.append(("info", "Already down to a single vehicle."))
        return
    snapshot(f"Removed one vehicle ({ss.n_vehicles} → {new} available)")
    ss.n_vehicles, ss.run = new, True


def on_reset() -> None:
    ss = st.session_state
    ss.dataset = ss.dataset if ss.dataset in SAMPLES else SAMPLE_25
    ss.upload_errors = []
    load_sample(ss.dataset)


# ---------- sidebar ----------
init_state()
ss = st.session_state
with st.sidebar:
    st.header("Plan settings")
    st.selectbox("Dataset", [SAMPLE_25, SAMPLE_100, UPLOAD], key="dataset", on_change=on_dataset)
    upload = None
    if ss.dataset == UPLOAD:
        upload = st.file_uploader("CSV file", type="csv", help="Columns: stop_id, customer_name, x, y, demand, "
                                  "ready_time, due_time, service_time, is_depot")
        for msg in ss.upload_errors:
            st.error(msg)
    st.slider("Number of vehicles", 1, MAX_VEHICLES, key="n_vehicles",
              help="Vehicles available. The solver uses as few as it can.")
    st.number_input("Vehicle capacity", min_value=1, step=10, key="capacity")
    st.selectbox("Solver time limit (seconds)", [3, 5, 8, 10], key="time_limit")
    st.button("Optimize Routes", type="primary", on_click=on_optimize, width="stretch")
    st.subheader("Scenarios")
    st.button("Add urgent delivery", on_click=on_urgent, width="stretch")
    st.button("Remove one vehicle", on_click=on_remove_vehicle, width="stretch",
              help="Reduces the fleet to one fewer than the vehicles currently used, then re-optimizes.")
    st.button("Reset to sample dataset", on_click=on_reset, width="stretch")
    with st.expander("Impact assumptions"):
        st.caption("Illustrative factors per distance unit — configurable, not measured.")
        st.number_input("Fuel cost per distance unit", min_value=0.0, step=0.01, key="fuel")
        st.number_input("CO2 (kg) per distance unit", min_value=0.0, step=0.01, key="co2")

# Uploaded CSV: parse once per file; on errors keep the previous dataset.
if ss.dataset == UPLOAD and upload is not None:
    sig = (upload.name, upload.size)
    if sig != ss.upload_sig:
        ss.upload_sig = sig
        try:
            ss.df, ss.dataset_name = load_csv(upload), f"Uploaded · {upload.name}"
            ss.upload_errors, ss.solution, ss.baseline, ss.scenario, ss.run = [], None, None, None, True
        except DataValidationError as exc:
            ss.upload_errors = exc.messages
            st.rerun()

assump = Assumptions(ss.fuel, ss.co2)
df = ss.df

# ---------- optimize (only on first load, button click or scenario change) ----------
if ss.run:
    ss.run = False
    try:
        with st.spinner(f"Optimizing routes (up to {ss.time_limit}s)…"):
            ss.solution = cached_solve(df, ss.n_vehicles, float(ss.capacity), int(ss.time_limit))
            ss.baseline = cached_baseline(df, ss.n_vehicles, float(ss.capacity))
    except Exception:  # noqa: BLE001 - never show a stack trace
        log.exception("optimization failed")
        ss.solution = ss.baseline = None
        st.error("Optimization failed. Check the dataset and settings, then try again.")

# ---------- header ----------
st.title("RouteIQ — Intelligent Last-Mile Delivery Route Optimization")
st.caption("Turning delivery data into cost-saving, reliable, lower-emission routes")
for level, text in ss.flash:
    getattr(st, level)(text)
ss.flash = []

sol, base = ss.solution, ss.baseline
n_cust = len(df) - 1
st.markdown(f"**{ss.dataset_name}** · {n_cust} customers · capacity {ss.capacity:g} · "
            f"up to {ss.n_vehicles} vehicles · Euclidean distance, travel time = distance")
if (df["demand"] > ss.capacity).any():
    st.warning("Some customers have demand above the vehicle capacity and can never be served.")
if sol is None:
    st.info("Press **Optimize Routes** in the sidebar to build a plan.")
    st.stop()

dist = cached_matrix(tuple(df["x"]), tuple(df["y"]))
problems = audit_solution(sol, df, dist, float(ss.capacity))
if problems:
    st.error("The solver returned a plan that failed verification: " + "; ".join(problems))
if sol.unserved:
    ids = ", ".join(str(int(df.iloc[i]["stop_id"])) for i in sol.unserved)
    st.warning(f"With {ss.n_vehicles} vehicle(s) the plan cannot serve every customer within capacity and "
               f"time windows. **{len(sol.unserved)} unserved:** {ids}. Add vehicles or capacity.")

# ---------- KPIs ----------
k, kb = compute_kpis(sol, assump), compute_kpis(base, assump)
valid, reason = comparison_valid(sol, base)


def card(col, label: str, key: str, fmt: str, help_: str = "") -> None:
    delta = None
    if valid and key in IMPROVABLE:
        p = improvement_pct(k[key], kb[key])
        delta = None if p is None else f"{p:+.1f}% vs baseline"
    col.metric(label, fmt.format(k[key]), delta, help=help_ or None)


c = st.columns(5)
card(c[0], "Total distance", "distance", "{:.1f}")
card(c[1], "Travel time", "travel_time", "{:.1f}", "Solomon convention: travel time equals distance.")
card(c[2], "Vehicles used", "vehicles", "{:.0f}")
card(c[3], "Est. fuel cost", "fuel_cost", "{:.2f}", "Illustrative: distance × fuel cost per unit.")
card(c[4], "Est. CO2 (kg)", "co2_kg", "{:.1f}", "Illustrative: distance × CO2 factor.")
c = st.columns(4)
card(c[0], "Avg vehicle utilization", "avg_util", "{:.0%}")
card(c[1], "Max vehicle utilization", "max_util", "{:.0%}")
card(c[2], "Time-window violations", "tw_violations", "{:.0f}",
     "Both planners treat windows as hard constraints, so 0 is expected; a separate audit re-checks every route.")
card(c[3], "Unassigned customers", "unassigned", "{:.0f}")
if valid:
    st.caption("Improvement is measured against a nearest-neighbour baseline with the same fleet, capacity "
               "and time windows. Fuel and CO2 use the illustrative factors in the sidebar.")
else:
    st.info(f"Improvement % is hidden because the comparison is not like-for-like: {reason}.")

# ---------- scenario before/after ----------
if ss.scenario:
    b, a = ss.scenario["before"], k
    st.subheader(f"Scenario: {ss.scenario['label']}")
    rows = [("Customers unserved", "unassigned", "{:.0f}"), ("Vehicles used", "vehicles", "{:.0f}"),
            ("Total distance", "distance", "{:.1f}"), ("Est. CO2 (kg)", "co2_kg", "{:.1f}")]
    st.dataframe(pd.DataFrame([{"Metric": n, "Before": f.format(b[key]), "After": f.format(a[key]),
                                "Change": f"{a[key] - b[key]:+.1f}"} for n, key, f in rows]),
                 hide_index=True, width="stretch")

# ---------- map ----------
st.subheader("Route map")
st_folium(build_map(df, sol), height=560, use_container_width=True, returned_objects=[])
st.caption("Abstract benchmark coordinates (not latitude/longitude). Hover a stop for its time window, "
           "arrival and waiting time. Grey markers with a red ring are unserved.")

# ---------- route details ----------
st.subheader("Route details")
detail = pd.DataFrame([{
    "Vehicle": f"V{r.vehicle_id}", "Stops": len(r.customer_nodes),
    "Sequence": " → ".join(str(v.stop_id) for v in r.visits),
    "Load": f"{r.load:.0f}/{r.capacity:.0f}", "Utilization": f"{r.utilization:.0%}",
    "Distance": round(r.distance, 1), "Duration": round(r.duration, 1),
    "Waiting": round(r.total_wait, 1), "TW violations": r.tw_violations} for r in sol.routes])
st.dataframe(detail, hide_index=True, width="stretch", height=int(min(40 + 35 * len(detail), 800)))
plan = solution_to_dataframe(sol, df)
with st.expander("Stop-level schedule (what drivers receive)"):
    st.dataframe(plan, hide_index=True, width="stretch")

# ---------- baseline comparison ----------
st.subheader("RouteIQ vs nearest-neighbour baseline")
left, right = st.columns([3, 2])
# Distance/CO2 bars only make sense when both plans serve the same customers.
chart_metrics = ((("Distance", "distance"), ("Vehicles used", "vehicles"), ("Avg utilization (%)", "avg_util"),
                  ("CO2 (kg)", "co2_kg")) if valid else
                 (("Vehicles used", "vehicles"), ("Unassigned customers", "unassigned"),
                  ("Avg utilization (%)", "avg_util")))
chart = pd.DataFrame([
    {"Metric": m, "Method": name, "Value": kk[key] * (100 if key == "avg_util" else 1)}
    for name, kk in (("RouteIQ", k), ("Baseline", kb))
    for m, key in chart_metrics])
fig = px.bar(chart, x="Method", y="Value", color="Method", facet_col="Metric", text_auto=".4~g",
             color_discrete_map={"RouteIQ": "#0f766e", "Baseline": "#94a3b8"})
fig.update_yaxes(matches=None, showticklabels=False, title=None)
fig.update_xaxes(title=None)
fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
fig.update_layout(showlegend=False, height=330, margin=dict(t=30, b=10, l=10, r=10))
left.plotly_chart(fig, width="stretch")
if not valid:
    left.caption("Distance and CO2 bars are hidden: the baseline serves fewer customers, so a shorter "
                 "distance would not mean a better plan.")
right.dataframe(comparison_table(sol, base, assump), hide_index=True, width="stretch")
st.caption(f"RouteIQ solver: {sol.status}, {sol.runtime:.1f}s · Baseline: {base.runtime * 1000:.0f} ms. "
           "Solver results are cached per input set.")

st.download_button("Download optimized route plan (CSV)", to_csv_bytes(plan),
                   file_name="routeiq_route_plan.csv", mime="text/csv", type="primary")
st.caption("Data: Solomon R101 VRPTW benchmark (M. Solomon, 1987). Decision support only — dispatchers "
           "should review plans before execution.")