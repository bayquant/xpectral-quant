# CLAUDE.md

## Xpectral Quant

Quant analytics and market data that extend **Polars** DataFrames with
domain-specific functionality via Python's accessor registration pattern.

`xpectral` is a PEP 420 namespace package shared with the separate
[`xpectral-chart`](https://github.com/bayquant/xpectral-chart) project — there is
no top-level `xpectral/__init__.py`. Importing `xpectral.quant` / `xpectral.data`
registers the accessors; `xpectral.data` also loads `xpectral/.env` for
Polygon/Massive API credentials.

Each subpackage has its own README documenting its modules:

- [`xpectral/quant/README.md`](xpectral/quant/README.md)
- [`xpectral/data/README.md`](xpectral/data/README.md)
