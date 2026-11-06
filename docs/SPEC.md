# RouteIQ — revised build specification (as implemented)

Changes from the first draft prompt, and why:

| Issue in draft | Resolution |
|---|---|
| OR-Tools needs integers; Solomon distances are floats | Scale ×100; travel/service/ready rounded **up**, due rounded **down**, so scaled-feasible ⇒ exactly feasible. Reporting uses float distances. |
| Example CSV rows were C101-like, not R101 | Removed. All values are parsed from `data/raw/R101.txt` only (depot at (35,35), due 230, capacity 200). |
| Folium can't draw abstract x-y as lat/lon | `folium.Map(crs="Simple", tiles=None)` with [y, x] plane coordinates. |
| "Visit every customer" vs "remove a vehicle, warn if infeasible" | Customers are optional with a large drop penalty; unserved customers are reported, never a blank screen. |
| Time-window violations would be 0 vs 0 | Documented: both planners treat windows as hard constraints. A separate audit re-verifies every route. Meaningful comparisons are vehicles, distance, unassigned. |
| Objective ignored fleet size | Fixed cost per vehicle used (1000 distance units): vehicles first, distance second — the Solomon convention. |
| Baseline fairness | Same fleet limit, capacity, windows, service times; feasibility includes return to the depot by its due time. |
| Improvement % when baseline is incomplete | Shown only if both plans serve the same customers. |
| Urgent delivery non-deterministic | Seeded; window of 30 units, always reachable from the depot. |
| `architecture.png` can't be generated | Mermaid diagram in the README. |
| No external reference | `scripts/validate.py` adds best-known columns and a gap-to-best-known metric. |

Behaviour notes: the optimizer runs automatically once on first load (so judges see results immediately),
then only on **Optimize Routes** or a scenario button. **Remove one vehicle** reduces the fleet to one fewer
than the vehicles currently used. `load_after_stop` is cumulative demand served on the route.
