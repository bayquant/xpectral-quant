# Xpectral

![Spectral decomposition](assets/xpectral_banner.gif)

A quantitative research library that extends **Polars** DataFrames with charting and financial analytics.

## Modules

- **`xpectral.charts`** — Fluent Bokeh visualization via `df.bokeh.line(...)`, `df.bokeh.scatter(...)`, etc.
- **`xpectral.quant`** — Financial metrics (returns, volatility, beta) via `pl.col(...).quant.returns()`
- **`xpectral.data`** — Market data from the Polygon/Massive API with caching and rate limiting

## Usage

```python
import polars as pl
import xpectral  # registers .bokeh and .quant accessors

df = pl.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
fig = df.bokeh.line(x="x", y="y")
```

## Install

```bash
uv sync
```
