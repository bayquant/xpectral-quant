# `xpectral.data`

Market data access and synthetic price-path simulation.

See the [project README](../../README.md#modules) for an overview and [`examples/data`](../../examples/data) for runnable notebooks.

## Modules

- **`massive.py`** — `get_aggregate_bars(tickers, multiplier, timespan, from_, to, ...)` fetches OHLCV aggregate bars from the Polygon/Massive API via `massive.RESTClient`, rate-limited and cached, returning a wide-format `pl.LazyFrame` indexed by `timestamp`/`ticker`. Requires a `MASSIVE_API_KEY` environment variable.
- **`simulations.py`** — `BrownianMotion(n_steps, n_paths, dt, seed)` generates `standard()` (arithmetic) and `geometric()` (lognormal) Brownian motion paths as a `pl.DataFrame` with `step` and `path_0 … path_N` columns.
