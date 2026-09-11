# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Third-party imports
import numpy as np

# First-party imports
from xpectral.quant.execution import cost_variance
from xpectral.quant.execution import decay_parameter
from xpectral.quant.execution import efficient_frontier
from xpectral.quant.execution import expected_cost
from xpectral.quant.execution import optimal_holdings
from xpectral.quant.execution import permanent_impact_cost
from xpectral.quant.execution import temporary_impact_cost

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

_X = 1_000_000.0
_T = 1.0
_SIGMA = 0.02
_ETA = 2.5e-6
_GAMMA = 2.5e-7

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


def test_lambda_zero_is_a_straight_line():
    kappa = decay_parameter(0.0, _SIGMA, _ETA)
    assert kappa == 0.0

    t = np.linspace(0.0, _T, 11)
    x = optimal_holdings(t, _X, _T, kappa)

    assert not np.isnan(x).any()
    np.testing.assert_allclose(x, _X * (1.0 - t / _T))


def test_boundary_conditions_hold_for_scalar_and_array_kappa():
    for lam in (0.0, 1e-8, 1.0, 100.0):
        kappa = decay_parameter(lam, _SIGMA, _ETA)

        x_start = optimal_holdings(0.0, _X, _T, kappa)
        x_end = optimal_holdings(_T, _X, _T, kappa)

        assert isinstance(x_start, float)
        np.testing.assert_allclose(x_start, _X, rtol=1e-6)
        np.testing.assert_allclose(x_end, 0.0, atol=1e-6)


def test_holdings_decay_monotonically():
    kappa = decay_parameter(5.0, _SIGMA, _ETA)
    t = np.linspace(0.0, _T, 50)
    x = optimal_holdings(t, _X, _T, kappa)

    assert np.all(np.diff(x) <= 0)


def test_efficient_frontier_trades_off_cost_and_risk():
    lambdas = np.array([0.0, 1e-6, 1e-4, 1e-2, 1.0])
    frontier = efficient_frontier(lambdas, _X, _T, _SIGMA, _ETA, _GAMMA)

    assert np.all(np.diff(frontier["expected_cost"]) >= 0)
    assert np.all(np.diff(frontier["variance"]) <= 0)


def test_permanent_impact_cost_matches_closed_form():
    np.testing.assert_allclose(
        permanent_impact_cost(_X, _GAMMA), 0.5 * _GAMMA * _X**2
    )


def test_expected_cost_is_sum_of_permanent_and_temporary_components():
    kappa = decay_parameter(0.5, _SIGMA, _ETA)

    np.testing.assert_allclose(
        expected_cost(_X, _GAMMA, _ETA, _T, kappa),
        permanent_impact_cost(_X, _GAMMA)
        + temporary_impact_cost(_X, _ETA, _T, kappa),
    )


def test_temporary_impact_cost_matches_risk_neutral_limit_at_kappa_zero():
    np.testing.assert_allclose(
        temporary_impact_cost(_X, _ETA, _T, 0.0), _ETA * _X**2 / _T
    )


def test_frontier_point_matches_direct_cost_and_variance_calls():
    lam = 0.5
    kappa = decay_parameter(lam, _SIGMA, _ETA)

    frontier = efficient_frontier(np.array([lam]), _X, _T, _SIGMA, _ETA, _GAMMA)

    assert frontier["kappa"][0] == kappa
    np.testing.assert_allclose(
        frontier["expected_cost"][0],
        expected_cost(_X, _GAMMA, _ETA, _T, kappa),
    )
    np.testing.assert_allclose(
        frontier["variance"][0], cost_variance(_X, _SIGMA, _T, kappa)
    )
