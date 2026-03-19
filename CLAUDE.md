# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Spectral is a quantitative research library that extends **Polars** DataFrames with domain-specific functionality via Python's accessor registration pattern.

### Three main modules

**`spectral/charts/`** — Bokeh visualization via `df.bokeh.*`
- `polars_accessors.py`: Registers `BokehAccessor` on Polars DataFrames via `@pl.api.register_dataframe_namespace("bokeh")`. The accessor holds a `ColumnDataSource` built from the DataFrame and exposes 30+ glyph methods.
- `_decorators.py`: `glyph_method` decorator dynamically generates glyph methods from Bokeh glyph classes. It maps positional args to kwargs, auto-injects an index column when x/y are missing, and builds docstrings from the Bokeh class.
- `_figure.py`: Custom `Figure` class extending Bokeh's `Plot`. Handles axes, scales, tools, and grids during initialization.
- `theme_manager.py`: Wraps Bokeh's built-in themes plus a custom "ocean" theme.

**`spectral/quant/`** — Financial metrics via `pl.col(...).quant.*`
- `polars_accessors.py`: Registers `QuantAccessor` on Polars Expressions via `@pl.api.register_expr_namespace("quant")`. Methods: `returns()`, `compound()`, `rolling_vol()`, `rolling_beta()`.
- `portfolio.py`: `Portfolio` class for return decomposition into systematic and idiosyncratic components.
- `polars_expressions.py`: Custom Polars expression utilities (e.g., `ffill_inside`).

**`spectral/data/`** — Market data from Polygon/Massive API
- `massive.py`: `get_aggregate_bars()` with `@lru_cache` and rate limiting (5 calls/60s). Returns Polars DataFrame pivoted from long to semi-wide format with UTC→America/New_York timezone conversion.

### Key patterns

- **Accessor registration**: All public APIs attach to Polars objects rather than standalone functions. Import `spectral` to register the accessors automatically.
- **Glyph method generation**: Adding a new chart type means passing a Bokeh glyph class to `glyph_method` — no manual method writing needed.
- **Environment**: `spectral/__init__.py` loads `spectral/.env` on import (API keys for Polygon/Massive go there).

## Commands

```bash
# Run all tests
python -m unittest discover

# Run a single test file
python -m unittest tests/test_polars_charts_accessor.py

# Run a single test case
python -m unittest tests.test_polars_charts_accessor.TestPolarsBokehAccessor.test_name

# Install dependencies
uv sync

# Format code
black spectral/
```