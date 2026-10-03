# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Third-party imports
import numpy as np
import pytest

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
_N = 20
_TAU = _T / _N
_SIGMA = 0.02
_ETA = 2.5e-6
_GAMMA = 2.5e-7
_ETA_TILDE = _ETA - 0.5 * _GAMMA * _TAU

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


def test_lambda_zero_is_a_straight_line():
    kappa = decay_parameter(0.0, _SIGMA, _ETA, _GAMMA, _TAU)
    assert kappa == 0.0

    x = optimal_holdings(_X, _T, _N, kappa)

    assert not np.isnan(x).any()
    np.testing.assert_allclose(x, _X * (1.0 - np.arange(_N + 1) / _N))


def test_kappa_solves_the_cosh_relation():
    lam = 0.5
    kappa = decay_parameter(lam, _SIGMA, _ETA, _GAMMA, _TAU)
    kappa_tilde_sq = lam * _SIGMA**2 / _ETA_TILDE

    np.testing.assert_allclose(
        2 / _TAU**2 * (np.cosh(kappa * _TAU) - 1), kappa_tilde_sq
    )
    assert kappa < np.sqrt(kappa_tilde_sq)


def test_decay_parameter_rejects_non_convex_cost():
    with pytest.raises(ValueError):
        decay_parameter(1.0, _SIGMA, _ETA, gamma=2 * _ETA / _TAU, tau=_TAU)


def test_holdings_satisfy_the_optimality_recurrence():
    lam = 0.5
    kappa = decay_parameter(lam, _SIGMA, _ETA, _GAMMA, _TAU)
    x = optimal_holdings(_X, _T, _N, kappa)

    second_difference = (x[2:] - 2 * x[1:-1] + x[:-2]) / _TAU**2
    np.testing.assert_allclose(
        second_difference, lam * _SIGMA**2 / _ETA_TILDE * x[1:-1], rtol=1e-8
    )


def test_risk_seeking_holdings_satisfy_the_recurrence_and_back_load():
    lam = -0.005
    kappa = decay_parameter(lam, _SIGMA, _ETA, _GAMMA, _TAU)
    x = optimal_holdings(_X, _T, _N, kappa)

    second_difference = (x[2:] - 2 * x[1:-1] + x[:-2]) / _TAU**2
    np.testing.assert_allclose(
        second_difference, lam * _SIGMA**2 / _ETA_TILDE * x[1:-1], rtol=1e-8
    )
    assert np.all(x[1:-1] > _X * (1.0 - np.arange(1, _N) / _N))
    assert np.all(np.diff(x) <= 0)


def test_holdings_reject_schedules_that_buy():
    kappa = decay_parameter(-1.0, _SIGMA, _ETA, _GAMMA, _TAU)

    with pytest.raises(ValueError):
        optimal_holdings(_X, _T, _N, kappa)


def test_general_endpoints_satisfy_boundaries_and_recurrence():
    lam = 0.01
    x_end = 0.25 * _X
    kappa = decay_parameter(lam, _SIGMA, _ETA, _GAMMA, _TAU)
    x = optimal_holdings(_X, _T, _N, kappa, X_T=x_end)

    np.testing.assert_allclose([x[0], x[-1]], [_X, x_end])
    second_difference = (x[2:] - 2 * x[1:-1] + x[:-2]) / _TAU**2
    np.testing.assert_allclose(
        second_difference, lam * _SIGMA**2 / _ETA_TILDE * x[1:-1], rtol=1e-8
    )


def test_general_endpoints_are_a_straight_line_at_lambda_zero():
    x = optimal_holdings(_X, _T, _N, 0.0, X_T=0.25 * _X)

    np.testing.assert_allclose(x, np.linspace(_X, 0.25 * _X, _N + 1))


def test_holdings_reject_paths_that_overshoot_the_end_value():
    kappa = decay_parameter(100.0, _SIGMA, _ETA, _GAMMA, _TAU)

    with pytest.raises(ValueError):
        optimal_holdings(_X, _T, _N, kappa, X_T=0.9 * _X)


def test_replanning_with_the_same_lambda_continues_the_schedule():
    kappa = decay_parameter(0.5, _SIGMA, _ETA, _GAMMA, _TAU)
    x = optimal_holdings(_X, _T, _N, kappa)

    k = 7
    x_replanned = optimal_holdings(x[k], _T - k * _TAU, _N - k, kappa)

    np.testing.assert_allclose(x_replanned, x[k:], atol=1e-6)


def test_boundary_conditions_hold():
    for lam in (0.0, 1e-8, 1.0, 100.0):
        kappa = decay_parameter(lam, _SIGMA, _ETA, _GAMMA, _TAU)
        x = optimal_holdings(_X, _T, _N, kappa)

        assert x.shape == (_N + 1,)
        np.testing.assert_allclose(x[0], _X, rtol=1e-6)
        assert x[-1] == 0.0


def test_holdings_decay_monotonically():
    kappa = decay_parameter(5.0, _SIGMA, _ETA, _GAMMA, _TAU)
    x = optimal_holdings(_X, _T, _N, kappa)

    assert np.all(np.diff(x) <= 0)


def test_trades_match_closed_form_trade_list():
    kappa = decay_parameter(0.5, _SIGMA, _ETA, _GAMMA, _TAU)
    trades = -np.diff(optimal_holdings(_X, _T, _N, kappa))

    t_mid = (np.arange(1, _N + 1) - 0.5) * _TAU
    expected_trades = (
        2
        * np.sinh(0.5 * kappa * _TAU)
        / np.sinh(kappa * _T)
        * np.cosh(kappa * (_T - t_mid))
        * _X
    )
    np.testing.assert_allclose(trades, expected_trades)


def test_cost_and_variance_match_closed_form():
    kappa = decay_parameter(0.5, _SIGMA, _ETA, _GAMMA, _TAU)
    x = optimal_holdings(_X, _T, _N, kappa)

    # Almgren-Chriss (2000), equation (20), with epsilon = 0
    closed_form_cost = 0.5 * _GAMMA * _X**2 + _ETA_TILDE * _X**2 * np.tanh(
        0.5 * kappa * _TAU
    ) * (_TAU * np.sinh(2 * kappa * _T) + 2 * _T * np.sinh(kappa * _TAU)) / (
        2 * _TAU**2 * np.sinh(kappa * _T) ** 2
    )
    closed_form_variance = (
        0.5
        * _SIGMA**2
        * _X**2
        * (
            _TAU * np.sinh(kappa * _T) * np.cosh(kappa * (_T - _TAU))
            - _T * np.sinh(kappa * _TAU)
        )
        / (np.sinh(kappa * _T) ** 2 * np.sinh(kappa * _TAU))
    )

    np.testing.assert_allclose(expected_cost(x, _TAU, _GAMMA, _ETA), closed_form_cost)
    np.testing.assert_allclose(cost_variance(x, _TAU, _SIGMA), closed_form_variance)


def test_efficient_frontier_trades_off_cost_and_risk():
    lambdas = np.array([0.0, 1e-6, 1e-4, 1e-2, 1.0])
    frontier = efficient_frontier(lambdas, _X, _T, _N, _SIGMA, _ETA, _GAMMA)

    assert np.all(np.diff(frontier["expected_cost"]) >= 0)
    assert np.all(np.diff(frontier["variance"]) <= 0)


def test_permanent_impact_cost_matches_summation_by_parts():
    kappa = decay_parameter(0.5, _SIGMA, _ETA, _GAMMA, _TAU)
    x = optimal_holdings(_X, _T, _N, kappa)
    trades = -np.diff(x)

    np.testing.assert_allclose(
        permanent_impact_cost(x, _GAMMA),
        0.5 * _GAMMA * _X**2 - 0.5 * _GAMMA * np.sum(trades**2),
    )


def test_expected_cost_is_sum_of_permanent_and_temporary_components():
    kappa = decay_parameter(0.5, _SIGMA, _ETA, _GAMMA, _TAU)
    x = optimal_holdings(_X, _T, _N, kappa)

    np.testing.assert_allclose(
        expected_cost(x, _TAU, _GAMMA, _ETA),
        permanent_impact_cost(x, _GAMMA) + temporary_impact_cost(x, _TAU, _ETA),
    )


def test_temporary_impact_cost_matches_risk_neutral_limit_at_kappa_zero():
    x = optimal_holdings(_X, _T, _N, 0.0)

    np.testing.assert_allclose(temporary_impact_cost(x, _TAU, _ETA), _ETA * _X**2 / _T)


def test_frontier_point_matches_direct_cost_and_variance_calls():
    lam = 0.5
    kappa = decay_parameter(lam, _SIGMA, _ETA, _GAMMA, _TAU)
    x = optimal_holdings(_X, _T, _N, kappa)

    frontier = efficient_frontier(np.array([lam]), _X, _T, _N, _SIGMA, _ETA, _GAMMA)

    assert frontier["kappa"][0] == kappa
    np.testing.assert_allclose(
        frontier["expected_cost"][0], expected_cost(x, _TAU, _GAMMA, _ETA)
    )
    np.testing.assert_allclose(frontier["variance"][0], cost_variance(x, _TAU, _SIGMA))
