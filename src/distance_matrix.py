"""Euclidean distance matrices and the integer scaling OR-Tools requires.

OR-Tools routing works on integers, but Solomon distances are real numbers.
We scale by SCALE and round *conservatively* (travel and service times up, ready
times up, due times down) so that any plan feasible in scaled integers is also
feasible in exact floating point. Reported distances always use the float matrix.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SCALE = 100
_EPS = 1e-9


def euclidean_matrix(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """n x n matrix: distance(i, j) = sqrt((x_i - x_j)^2 + (y_i - y_j)^2)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    return np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])


@dataclass(frozen=True)
class SolverInputs:
    """Integer-scaled model data (all values multiplied by SCALE)."""

    dist: list[list[int]]      # arc cost, rounded to nearest
    travel: list[list[int]]    # travel time, rounded up (Solomon: time == distance)
    ready: list[int]
    due: list[int]
    service: list[int]
    demand: list[int]


def solver_inputs(df: pd.DataFrame, dist: np.ndarray) -> SolverInputs:
    """Convert a validated dataset + float distance matrix to scaled integers."""
    ceil = lambda a: np.ceil(np.asarray(a, dtype=float) * SCALE - _EPS).astype(int)  # noqa: E731
    return SolverInputs(
        dist=np.rint(dist * SCALE).astype(int).tolist(),
        travel=ceil(dist).tolist(),
        ready=ceil(df["ready_time"]).tolist(),
        due=np.floor(df["due_time"].to_numpy(float) * SCALE + _EPS).astype(int).tolist(),
        service=ceil(df["service_time"]).tolist(),
        demand=np.rint(df["demand"].to_numpy(float)).astype(int).tolist(),
    )
