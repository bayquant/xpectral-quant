# `xpectral.data`

Market data access and synthetic price-path simulation.

See the [project README](../../README.md#modules) for an overview and [`examples/data`](../../examples/data) for runnable notebooks.

## Modules

- **`massive.py`** — `Massive(api_key=None, rate_limiter=None)` wraps a `massive.RESTClient`; its `get_aggregate_bars(tickers, multiplier, timespan, from_, to, ...)` method fetches OHLCV aggregate bars from the Polygon/Massive API, cached per instance, returning a wide-format `pl.LazyFrame` indexed by `timestamp`/`ticker`. Reads `MASSIVE_API_KEY` from the environment when `api_key` is omitted. Rate limiting is opt-in: pass a `RateLimiter` to apply one per ticker request, otherwise none is applied.
- **`simulations.py`** — `BrownianMotion(n_steps, n_paths, dt, seed)` generates `standard()` (arithmetic) and `geometric()` (lognormal) Brownian motion paths as a `pl.DataFrame` with `step` and `path_0 … path_N` columns.
