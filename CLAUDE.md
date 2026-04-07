# CLAUDE.md

## Architecture

Xpectral is a quantitative research library that extends **Pandas** and **Polars** DataFrames with domain-specific functionality via Python's accessor registration pattern.

## Code Style

- All .py files (even if sections are empty) should contain the following blocks:

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------
Separate imports with comments # Standard library imports and # Other imports. Should import one item per line. Sort by absolute and relative style and then alphabetically.

#-----------------------------------------------------------------------------
# Globals and constants
#-----------------------------------------------------------------------------
Module-level __all__ and other constants. Only add constants that are used substantially across the code.

#-----------------------------------------------------------------------------
# General API
#-----------------------------------------------------------------------------
The public surface — classes and functions documented, and exported via __all__.              

#-----------------------------------------------------------------------------
# Private API
#-----------------------------------------------------------------------------
Implementation details prefixed with _. Not intended for external use.

- Use `#` for all comments, including multi-line blocks (PEP 8). Reserve `"""` for docstrings on modules, classes, and functions (PEP 257).

- TODO: add note on how to write my doctrings.

### Naming conventions

- Use `args` and `kwargs` for positional and keyword argument collections. Use `arg` and `kwarg` when iterating over them.

## External library context
