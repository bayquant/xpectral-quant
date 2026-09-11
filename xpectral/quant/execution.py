# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Third-party imports
import numpy as np

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

__all__ = [
    "decay_parameter",
    "optimal_holdings",
    "permanent_impact_cost",
    "temporary_impact_cost",
    "expected_cost",
    "cost_variance",
    "efficient_frontier",
]

# Below this, kappa * T is small enough that sinh(z) ~= z to within float64
# precision, so the ratio sinh(kappa(T-t))/sinh(kappa*T) is evaluated via its
# closed-form limit instead of risking a 0/0 (or numerically unstable) divide.
_KAPPA_T_TOL = 1e-8

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


def decay_parameter(lam: float, sigma: float, eta: float) -> float:
    """
    Almgren-Chriss decay parameter kappa = sqrt(lambda * sigma^2 / eta).

    Parameters
    ----------
    lam : float
        Risk aversion. Larger values front-load the liquidation schedule.
    sigma : float
        Volatility, in dollars per share per sqrt(time).
    eta : float
        Temporary impact coefficient.

    Returns
    -------
    float
        kappa, the exponential decay rate of the optimal holdings curve.
    """
    return np.sqrt(lam * sigma**2 / eta)


def optimal_holdings(
    t: float | np.ndarray, X: float, T: float, kappa: float
) -> float | np.ndarray:
    """
    Optimal shares-held trajectory x(t) for the Almgren-Chriss schedule.

    x(t) = X * sinh(kappa(T - t)) / sinh(kappa*T), falling back to the
    closed-form risk-neutral limit x(t) = X * (1 - t/T) as kappa -> 0
    (i.e. lambda == 0), where the sinh ratio would otherwise be 0/0.

    Parameters
    ----------
    t : float | np.ndarray
        Time(s) since the start of the liquidation window, 0 <= t <= T.
        May be a scalar or an array (e.g. a full time grid).
    X : float
        Initial shares held (position size at t=0).
    T : float
        Liquidation horizon.
    kappa : float
        Decay parameter, from `decay_parameter`.

    Returns
    -------
    float | np.ndarray
        Shares still held at time(s) `t`, same shape as `t`.
    """
    is_scalar = np.isscalar(t)
    t_arr = np.asarray(t, dtype=float)

    if abs(kappa * T) < _KAPPA_T_TOL:
        x = X * (1.0 - t_arr / T)
    else:
        x = X * np.sinh(kappa * (T - t_arr)) / np.sinh(kappa * T)

    return float(x) if is_scalar else x


def permanent_impact_cost(X: float, gamma: float) -> float:
    """
    Permanent-impact component of expected liquidation cost: (1/2) * gamma * X^2.

    Schedule-independent, so it is the same for any trajectory that
    liquidates X shares.

    Parameters
    ----------
    X : float
        Initial shares held.
    gamma : float
        Permanent impact coefficient.

    Returns
    -------
    float
        Permanent-impact cost in dollars.
    """
    return 0.5 * gamma * X**2


def temporary_impact_cost(X: float, eta: float, T: float, kappa: float) -> float:
    """
    Temporary-impact component of expected liquidation cost under the
    optimal trajectory for a given kappa.

    Continuous-time form: eta * integral(x'(t)^2, 0, T), evaluated in
    closed form from the optimal x(t), falling back to the risk-neutral
    limit X^2 / T as kappa * T -> 0 (i.e. lambda == 0), where the
    closed-form expression would otherwise be 0/0.

    Parameters
    ----------
    X : float
        Initial shares held.
    eta : float
        Temporary impact coefficient.
    T : float
        Liquidation horizon.
    kappa : float
        Decay parameter for the trajectory being costed, from
        `decay_parameter`.

    Returns
    -------
    float
        Temporary-impact cost in dollars.
    """
    if abs(kappa * T) < _KAPPA_T_TOL:
        trading_integral = X**2 / T
    else:
        trading_integral = (
            X**2
            * kappa
            / np.sinh(kappa * T) ** 2
            * (kappa * T / 2 + np.sinh(2 * kappa * T) / 4)
        )

    return eta * trading_integral


def expected_cost(X: float, gamma: float, eta: float, T: float, kappa: float) -> float:
    """
    Expected liquidation cost under the optimal trajectory for a given kappa.

    Sum of the permanent-impact cost (`permanent_impact_cost`) and the
    temporary-impact cost (`temporary_impact_cost`).

    Parameters
    ----------
    X : float
        Initial shares held.
    gamma : float
        Permanent impact coefficient.
    eta : float
        Temporary impact coefficient.
    T : float
        Liquidation horizon.
    kappa : float
        Decay parameter for the trajectory being costed, from
        `decay_parameter`.

    Returns
    -------
    float
        Expected cost in dollars.
    """
    return permanent_impact_cost(X, gamma) + temporary_impact_cost(X, eta, T, kappa)


def cost_variance(X: float, sigma: float, T: float, kappa: float) -> float:
    """
    Variance of liquidation cost under the optimal trajectory for a given kappa.

    Continuous-time form: sigma^2 * integral(x(t)^2, 0, T), evaluated in
    closed form from the optimal x(t).

    Parameters
    ----------
    X : float
        Initial shares held.
    sigma : float
        Volatility, in dollars per share per sqrt(time).
    T : float
        Liquidation horizon.
    kappa : float
        Decay parameter for the trajectory being costed, from
        `decay_parameter`.

    Returns
    -------
    float
        Variance of cost, in dollars squared.
    """
    if abs(kappa * T) < _KAPPA_T_TOL:
        holdings_integral = X**2 * T / 3
    else:
        holdings_integral = (
            X**2
            / np.sinh(kappa * T) ** 2
            * (np.sinh(2 * kappa * T) / (4 * kappa) - T / 2)
        )

    return sigma**2 * holdings_integral


def efficient_frontier(
    lambdas: np.ndarray, X: float, T: float, sigma: float, eta: float, gamma: float
) -> dict[str, np.ndarray]:
    """
    Sweep risk aversion lambda and trace the (variance, expected cost) frontier.

    For each lambda, the corresponding optimal trajectory is derived (via
    `decay_parameter`) and its expected cost and cost variance are computed
    in closed form — no numerical optimizer is involved.

    Parameters
    ----------
    lambdas : np.ndarray
        Risk-aversion values to sweep, in increasing order of risk aversion.
    X : float
        Initial shares held.
    T : float
        Liquidation horizon.
    sigma : float
        Volatility, in dollars per share per sqrt(time).
    eta : float
        Temporary impact coefficient.
    gamma : float
        Permanent impact coefficient.

    Returns
    -------
    dict[str, np.ndarray]
        Keys "lambda", "kappa", "expected_cost", "variance", each an array
        aligned with `lambdas`. "expected_cost" vs "variance" is the
        efficient frontier.
    """
    lambdas = np.asarray(lambdas, dtype=float)
    kappas = decay_parameter(lambdas, sigma, eta)
    expected_costs = np.array(
        [expected_cost(X, gamma, eta, T, kappa) for kappa in kappas]
    )
    variances = np.array([cost_variance(X, sigma, T, kappa) for kappa in kappas])

    return {
        "lambda": lambdas,
        "kappa": kappas,
        "expected_cost": expected_costs,
        "variance": variances,
    }


# -----------------------------------------------------------------------------
# Private API
# -----------------------------------------------------------------------------
