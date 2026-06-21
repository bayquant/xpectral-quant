# `xpectral.quant`

Financial metrics as Polars expressions via `pl.col(...).quant.*`, plus portfolio-level return decomposition.

See the [project README](../../README.md#modules) for an overview and [`examples/quant`](../../examples/quant) for runnable notebooks.

## Modules

- **`polars_accessors.py`** — `QuantAccessor`, registered on `pl.Expr` as the `quant` namespace: `returns`, `compound`, `rolling_vol`, `rolling_beta`. Each accepts an optional `over` column for grouped (e.g. per-ticker) computation.
- **`polars_expressions.py`** — Standalone Polars expression helpers, e.g. `ffill_inside` (forward-fill nulls only between existing values, leaving leading/trailing nulls untouched).
- **`portfolio.py`** — `Portfolio`, which combines asset returns/betas with a weights dict and a benchmark ticker to compute portfolio-level total, systematic, and idiosyncratic returns via `compute_returns()`.
