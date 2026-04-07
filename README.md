# Xpectral

![Spectral decomposition](assets/xpectral_banner.gif)

A quantitative research library that extends **Polars** and **Pandas** DataFrames with charting and quant analytics.

## Modules

- **`xpectral.charts`** — Fluent Bokeh visualization via `df.bokeh.line(...)`, `df.bokeh.scatter(...)`, etc.
- **`xpectral.quant`** — Financial metrics (returns, volatility, beta) via `pl.col(...).quant.returns()`
- **`xpectral.data`** — Market data from the Polygon/Massive API with caching and rate limiting

## `xpectral.charts`

```python
import xpectral  # registers the accessors
from xpectral import PandasDataFrame
from xpectral import PolarsDataFrame

df: PolarsDataFrame = pl.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
fig = df.bokeh(title="Example", width=600, height=400)
fig.line(x="x", y="y")

pd_df: PandasDataFrame = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
pd_fig = pd_df.bokeh(title="Example", width=600, height=400)
pd_fig.line(x="x", y="y")
```

Annotate sample DataFrames with `PolarsDataFrame` or `PandasDataFrame` when you want the editor (pyright) to resolve the `df.bokeh(...)` parameters and chained accessor methods. Annotation is neccessary for type. hinting as accessors are not discovered dinamically.

## Install

```bash
pip install xpectral
```

```bash
uv add xpectral
```

For development:

```bash
uv sync
```
