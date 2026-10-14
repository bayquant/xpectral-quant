# Xpectral Quant

![Spectral decomposition](https://raw.githubusercontent.com/bayquant/xpectral-quant/main/assets/xpectral_banner.gif)

Quant analytics and market data that extend **Polars** DataFrames via the
accessor pattern.

Part of the Xpectral project, alongside [`xpectral-chart`](https://github.com/bayquant/xpectral-chart)
(fluent Bokeh charting). Each installs its own top-level package
(`xpectral_quant` and `xpectral_chart`) and they can be used together.

## Modules

- **`xpectral_quant.quant`**: Financial metrics (returns, volatility, beta) via
  `pl.col(...).quant.returns()`, plus a `Portfolio` builder.
- **`xpectral_quant.data`**: Market data from the Polygon/Massive API with caching
  and rate limiting, plus simulations (`BrownianMotion`).

## Usage

```python
import xpectral_quant.quant  # registers the .quant accessor
import polars as pl

df = pl.DataFrame({"close": [100.0, 101.0, 99.5, 102.0]})
df.with_columns(pl.col("close").quant.returns())
```

Importing `xpectral_quant.quant` / `xpectral_quant.data` is what registers the accessors and
loads market-data credentials.

### Market data credentials

`xpectral_quant.data` reads Polygon/Massive API credentials from an `xpectral_quant/.env`
file (loaded automatically on `import xpectral_quant.data`). Create it with your keys;
it is git-ignored and never committed.

## Install

```bash
pip install xpectral-quant
```

```bash
uv add xpectral-quant
```

For development:

```bash
uv sync
```
