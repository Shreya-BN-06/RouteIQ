import numpy as np

from src.distance_matrix import SCALE, euclidean_matrix, solver_inputs


def test_3_4_5_triangle():
    d = euclidean_matrix(np.array([0, 3]), np.array([0, 4]))
    assert d[0, 1] == 5.0 and d[1, 0] == 5.0 and d[0, 0] == 0.0


def test_symmetric_zero_diagonal(r101_25):
    _, d, _ = r101_25
    assert np.allclose(d, d.T) and np.allclose(np.diag(d), 0)


def test_integer_scaling_is_conservative(r101_25):
    df, d, _ = r101_25
    inp = solver_inputs(df, d)
    travel = np.array(inp.travel)
    assert (travel >= d * SCALE - 1e-6).all()          # never underestimates travel time
    assert (travel <= d * SCALE + 1.0).all()           # by less than one scaled unit
    assert (np.array(inp.due) <= df["due_time"].to_numpy() * SCALE).all()
    assert (np.array(inp.ready) >= df["ready_time"].to_numpy() * SCALE).all()
