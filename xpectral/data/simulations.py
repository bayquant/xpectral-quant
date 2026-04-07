# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
from typing import Optional
from typing import Union

# Other imports
import numpy as np
import polars as pl

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


class BrownianMotion:
    """Generates standard and geometric Brownian motion paths.

    Args:
        n_steps: Number of time steps per path.
        n_paths: Number of independent paths to simulate.
        dt: Length of each time step in years. Defaults to :math:`1/252`
            (one trading day).
        seed: Random seed for reproducibility.
    """

    def __init__(
        self,
        n_steps: int,
        n_paths: int = 1,
        dt: float = 1 / 252,
        seed: Optional[int] = None,
    ):
        self.n_steps = n_steps
        self.n_paths = n_paths
        self.dt = dt
        self._rng = np.random.default_rng(seed)

    def standard(self) -> pl.DataFrame:
        """Generate standard Brownian motion paths.

        Each path is constructed as cumulative Gaussian increments:

        .. math::

            W_t = \\sum_{i=1}^{t} \\epsilon_i \\sqrt{\\Delta t},
            \\quad \\epsilon_i \\sim \\mathcal{N}(0, 1)

        Returns:
            DataFrame with columns ``step`` and ``path_0 … path_N``.
            Each path starts at :math:`W_0 = 0`.
        """
        increments = self._rng.normal(
            loc=0.0, scale=np.sqrt(self.dt), size=(self.n_steps, self.n_paths)
        )
        paths = np.vstack([np.zeros((1, self.n_paths)), np.cumsum(increments, axis=0)])
        return self._to_frame(paths)

    def geometric(
        self, mu: float = 0.0, sigma: float = 1.0, s0: float = 1.0
    ) -> pl.DataFrame:
        """Generate geometric Brownian motion paths.

        Uses the exact closed-form solution:

        .. math::

            S_t = S_0 \\exp\\!\\left(
                \\left(\\mu - \\tfrac{1}{2}\\sigma^2\\right) t
                + \\sigma W_t
            \\right)

        Args:
            mu: Annualised drift :math:`\\mu`. Defaults to ``0.0``.
            sigma: Annualised volatility :math:`\\sigma`. Defaults to ``1.0``.
            s0: Initial asset price :math:`S_0`. Defaults to ``1.0``.

        Returns:
            DataFrame with columns ``step`` and ``path_0 … path_N``.
            Each path starts at :math:`S_0`.
        """
        increments = self._rng.normal(
            loc=0.0, scale=np.sqrt(self.dt), size=(self.n_steps, self.n_paths)
        )
        log_returns = (mu - 0.5 * sigma**2) * self.dt + sigma * increments
        paths = s0 * np.exp(
            np.vstack([np.zeros((1, self.n_paths)), np.cumsum(log_returns, axis=0)])
        )
        return self._to_frame(paths)

    # -----------------------------------------------------------------------------
    # Private API
    # -----------------------------------------------------------------------------

    def _to_frame(self, paths: np.ndarray) -> pl.DataFrame:
        # paths shape: (n_steps + 1, n_paths)
        data = {"step": list(range(paths.shape[0]))}
        for i in range(self.n_paths):
            data[f"path_{i}"] = paths[:, i].tolist()
        return pl.DataFrame(data)
