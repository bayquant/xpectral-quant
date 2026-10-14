"""
Almgren-Chriss optimal execution: trajectory, expected cost, and variance.

Everything is in discrete time: the horizon T is split into N steps of
length tau = T / N, x_k is the number of shares held after step k
(x_0 = X_0, x_N = X_T, with X_T = 0 for a full liquidation), and
n_k = x_(k-1) - x_k is the number traded in step k.

Reference: Almgren, R., & Chriss, N. (2000). Optimal execution of portfolio
transactions. Journal of Risk, 3, 39-60.
"""

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


def decay_parameter(
    lam: float | np.ndarray, sigma: float, eta: float, gamma: float, tau: float
) -> float | complex | np.ndarray:
    """
    Decay rate kappa of the discrete optimal schedule.

    kappa solves (2 / tau^2) * (cosh(kappa * tau) - 1) = kappa_tilde^2, with
    kappa_tilde^2 = lambda * sigma^2 / eta_tilde and
    eta_tilde = eta - gamma * tau / 2. Since cosh(2a) - 1 = 2 sinh(a)^2, this
    is evaluated as kappa = (2 / tau) * arcsinh(kappa_tilde * tau / 2), which
    stays accurate when kappa_tilde * tau is small.

    For a risk-seeking trader (lambda < 0), kappa_tilde^2 < 0 and kappa is
    purely imaginary, kappa = i * omega, which `optimal_holdings` turns into
    the back-loaded schedule sin(omega(T - t)) / sin(omega * T).

    Parameters
    ----------
    lam : float | np.ndarray
        Risk aversion. Larger values front-load the liquidation schedule;
        negative values (risk seeking) back-load it.
    sigma : float
        Volatility, in dollars per share per sqrt(time).
    eta : float
        Temporary impact coefficient.
    gamma : float
        Permanent impact coefficient.
    tau : float
        Length of one trading step, T / N.

    Returns
    -------
    float | complex | np.ndarray
        kappa, the decay rate of the optimal holdings, same shape as `lam`.
        Complex if any `lam` is negative.

    Raises
    ------
    ValueError
        If eta_tilde <= 0, where the cost is no longer strictly convex.
    """
    eta_tilde = eta - 0.5 * gamma * tau
    if eta_tilde <= 0:
        raise ValueError(f"eta - gamma * tau / 2 must be positive, got {eta_tilde:.3g}")

    # emath.sqrt returns an imaginary root for negative lambda instead of nan
    kappa_tilde = np.emath.sqrt(lam * sigma**2 / eta_tilde)
    return 2.0 / tau * np.arcsinh(kappa_tilde * tau / 2.0)


def optimal_holdings(
    X_0: float, T: float, N: int, kappa: float | complex, X_T: float = 0.0
) -> np.ndarray:
    """
    Optimal shares held after each step, x_j for j = 0, ..., N.

    x_j = (X_0 * sinh(kappa(T - t_j)) + X_T * sinh(kappa * t_j))
    / sinh(kappa * T) with t_j = j * T / N: a hyperbolic interpolation between
    the holdings X_0 at t = 0 and X_T at t = T. As kappa -> 0 (i.e.
    lambda == 0), where the sinh ratios would otherwise be 0/0, this falls
    back to the straight line x_j = X_0 * (1 - j/N) + X_T * j/N. An imaginary
    kappa = i * omega (lambda < 0) turns each sinh into a sin.

    Parameters
    ----------
    X_0 : float
        Shares held at t = 0.
    T : float
        Trading horizon.
    N : int
        Number of trading steps.
    kappa : float | complex
        Decay rate, from `decay_parameter`.
    X_T : float
        Shares held at t = T. Defaults to 0, a full liquidation.

    Returns
    -------
    np.ndarray
        Holdings x_0, ..., x_N, of length N + 1, with x_0 = X_0 and x_N = X_T.

    Raises
    ------
    ValueError
        If the trades n_j = x_(j-1) - x_j change sign. The model assumes a
        pure sell (or pure buy) program, so such a schedule is outside it.
        This happens for lambda too negative, or for X_T of the same sign as
        X_0 with kappa * T large enough that the path overshoots X_T and
        comes back.
    """
    steps_elapsed = np.arange(N + 1, dtype=float)

    if abs(kappa * T) < _KAPPA_T_TOL:
        holdings = X_0 + (X_T - X_0) * steps_elapsed / N
    else:
        tau = T / N
        holdings = np.real(
            (
                X_0 * np.sinh(kappa * tau * (N - steps_elapsed))
                + X_T * np.sinh(kappa * tau * steps_elapsed)
            )
            / np.sinh(kappa * T)
        )

    trades = -np.diff(holdings)
    if np.any(trades > 0) and np.any(trades < 0):
        raise ValueError("the schedule would buy as well as sell")

    return holdings


def permanent_impact_cost(holdings: np.ndarray, gamma: float) -> float:
    """
    Permanent-impact component of expected cost: gamma * sum_k n_k * x_k.

    For a full liquidation this equals (1/2) * gamma * X^2 minus
    (1/2) * gamma * sum_k n_k^2, so it depends (weakly) on the schedule.
    Passing only the first k + 1 holdings gives the cost accrued through
    step k.

    Parameters
    ----------
    holdings : np.ndarray
        Holdings x_0, ..., x_N, e.g. from `optimal_holdings`.
    gamma : float
        Permanent impact coefficient.

    Returns
    -------
    float
        Permanent-impact cost in dollars.
    """
    trades = -np.diff(holdings)
    return gamma * np.sum(trades * holdings[1:])


def temporary_impact_cost(holdings: np.ndarray, tau: float, eta: float) -> float:
    """
    Temporary-impact component of expected cost: (eta / tau) * sum_k n_k^2.

    Passing only the first k + 1 holdings gives the cost accrued through
    step k.

    Parameters
    ----------
    holdings : np.ndarray
        Holdings x_0, ..., x_N, e.g. from `optimal_holdings`.
    tau : float
        Length of one trading step, T / N.
    eta : float
        Temporary impact coefficient.

    Returns
    -------
    float
        Temporary-impact cost in dollars.
    """
    trades = -np.diff(holdings)
    return eta / tau * np.sum(trades**2)


def expected_cost(holdings: np.ndarray, tau: float, gamma: float, eta: float) -> float:
    """
    Expected cost of a trading schedule.

    Sum of the permanent-impact cost (`permanent_impact_cost`) and the
    temporary-impact cost (`temporary_impact_cost`). For a full liquidation
    this is (1/2) * gamma * X^2 + (eta_tilde / tau) * sum_k n_k^2.

    Parameters
    ----------
    holdings : np.ndarray
        Holdings x_0, ..., x_N, e.g. from `optimal_holdings`.
    tau : float
        Length of one trading step, T / N.
    gamma : float
        Permanent impact coefficient.
    eta : float
        Temporary impact coefficient.

    Returns
    -------
    float
        Expected cost in dollars.
    """
    return permanent_impact_cost(holdings, gamma) + temporary_impact_cost(
        holdings, tau, eta
    )


def cost_variance(holdings: np.ndarray, tau: float, sigma: float) -> float:
    """
    Variance of the cost of a trading schedule: sigma^2 * tau * sum_k x_k^2.

    Parameters
    ----------
    holdings : np.ndarray
        Holdings x_0, ..., x_N, e.g. from `optimal_holdings`.
    tau : float
        Length of one trading step, T / N.
    sigma : float
        Volatility, in dollars per share per sqrt(time).

    Returns
    -------
    float
        Variance of cost, in dollars squared.
    """
    return sigma**2 * tau * np.sum(holdings[1:] ** 2)


def efficient_frontier(
    lambdas: np.ndarray,
    X: float,
    T: float,
    N: int,
    sigma: float,
    eta: float,
    gamma: float,
) -> dict[str, np.ndarray]:
    """
    Sweep risk aversion lambda and trace the (variance, expected cost) frontier.

    For each lambda, the corresponding optimal trajectory is built (via
    `decay_parameter` and `optimal_holdings`) and its expected cost and cost
    variance are computed exactly: no numerical optimizer is involved.

    Parameters
    ----------
    lambdas : np.ndarray
        Risk-aversion values to sweep, in increasing order of risk aversion.
    X : float
        Initial shares held.
    T : float
        Liquidation horizon.
    N : int
        Number of trading steps.
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
        efficient frontier for lambda >= 0; negative lambdas trace the
        inefficient risk-seeking branch, and make "kappa" complex.
    """
    tau = T / N
    lambdas = np.asarray(lambdas, dtype=float)
    kappas = decay_parameter(lambdas, sigma, eta, gamma, tau)
    holdings = [optimal_holdings(X, T, N, kappa) for kappa in kappas]
    expected_costs = np.array([expected_cost(x, tau, gamma, eta) for x in holdings])
    variances = np.array([cost_variance(x, tau, sigma) for x in holdings])

    return {
        "lambda": lambdas,
        "kappa": kappas,
        "expected_cost": expected_costs,
        "variance": variances,
    }


# -----------------------------------------------------------------------------
# Private API
# -----------------------------------------------------------------------------
