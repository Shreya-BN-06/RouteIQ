"""Folium route map for abstract x-y benchmark coordinates (no lat/lon, no tiles)."""
from __future__ import annotations

import folium
import pandas as pd

from .models import Solution

PALETTE = [
    "#1f77b4", "#d95f02", "#1b9e77", "#7570b3", "#e7298a", "#66a61e",
    "#a6761d", "#e6ab02", "#17becf", "#b2182b", "#4d4d4d", "#386cb0",
]
UNSERVED_COLOR = "#9e9e9e"


def route_color(vehicle_id: int) -> str:
    """Stable color per vehicle (cycles through the palette)."""
    return PALETTE[(vehicle_id - 1) % len(PALETTE)]


def _badge(label: str, color: str, size: int = 24, square: bool = False, ring: str = "#ffffff") -> folium.DivIcon:
    radius = "4px" if square else "50%"
    html = (
        f'<div style="width:{size}px;height:{size}px;border-radius:{radius};background:{color};'
        f'border:2px solid {ring};color:#fff;font:600 11px/{size - 4}px sans-serif;text-align:center;'
        f'box-shadow:0 0 2px rgba(0,0,0,.5)">{label}</div>'
    )
    return folium.DivIcon(html=html, icon_size=(size, size), icon_anchor=(size // 2, size // 2))


def build_map(df: pd.DataFrame, sol: Solution | None) -> folium.Map:
    """Depot, numbered customers, one polyline per vehicle, and a legend.

    Leaflet's Simple CRS treats [y, x] as plain plane coordinates.
    """
    m = folium.Map(location=[float(df["y"].mean()), float(df["x"].mean())], zoom_start=3,
                   crs="Simple", tiles=None, zoom_snap=0.25, min_zoom=-2, max_zoom=8)
    m.get_root().header.add_child(folium.Element(
        "<style>.leaflet-container{background:#f6f7f9}</style>"))

    info: dict[int, dict] = {}
    if sol is not None:
        for r in sol.routes:
            for v in r.visits[1:-1]:
                info[v.node] = {"vehicle": r.vehicle_id, "arrival": v.arrival, "wait": v.wait}

    for i, row in df.iterrows():
        loc = [float(row["y"]), float(row["x"])]
        if i == 0:
            folium.Marker(loc, icon=_badge("D", "#111827", 28, square=True),
                          tooltip=f"Depot · window [{row['ready_time']:.0f}, {row['due_time']:.0f}]").add_to(m)
            continue
        base = (f"<b>{row['customer_name']}</b> (ID {int(row['stop_id'])})<br>"
                f"Demand {row['demand']:.0f} · window [{row['ready_time']:.0f}, {row['due_time']:.0f}]")
        if i in info:
            d = info[i]
            tip = base + f"<br>Vehicle {d['vehicle']} · arrives {d['arrival']:.1f} · waits {d['wait']:.1f}"
            icon = _badge(str(int(row["stop_id"])), route_color(d["vehicle"]))
        else:
            tip = base + "<br><b>Not served</b>" if sol is not None else base
            icon = _badge(str(int(row["stop_id"])), UNSERVED_COLOR if sol is not None else "#2563eb",
                          ring="#dc2626" if sol is not None else "#ffffff")
        folium.Marker(loc, icon=icon, tooltip=folium.Tooltip(tip)).add_to(m)

    if sol is not None:
        for r in sol.routes:
            pts = [[float(df.iloc[v.node]["y"]), float(df.iloc[v.node]["x"])] for v in r.visits]
            folium.PolyLine(pts, color=route_color(r.vehicle_id), weight=3, opacity=0.85,
                            tooltip=f"Vehicle {r.vehicle_id} · {len(r.customer_nodes)} stops · {r.distance:.1f}").add_to(m)
        _add_legend(m, sol)

    m.fit_bounds([[float(df["y"].min()) - 3, float(df["x"].min()) - 3],
                  [float(df["y"].max()) + 3, float(df["x"].max()) + 3]])
    return m


def _add_legend(m: folium.Map, sol: Solution) -> None:
    """Legend listing vehicle id, stops served, load and distance."""
    rows = "".join(
        f'<div style="white-space:nowrap"><span style="display:inline-block;width:12px;height:12px;'
        f'background:{route_color(r.vehicle_id)};margin-right:6px;border-radius:2px"></span>'
        f"V{r.vehicle_id}: {len(r.customer_nodes)} stops · load {r.load:.0f}/{r.capacity:.0f} · {r.distance:.1f}</div>"
        for r in sol.routes
    )
    html = (
        '<div style="position:fixed;bottom:12px;left:12px;z-index:9999;background:rgba(255,255,255,.94);'
        'padding:8px 10px;border:1px solid #cbd5e1;border-radius:6px;font:12px sans-serif;color:#111;'
        f'max-height:200px;overflow:auto"><b>Vehicles</b>{rows}</div>'
    )
    m.get_root().html.add_child(folium.Element(html))
