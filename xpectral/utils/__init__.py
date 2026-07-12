# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Other imports
from .logger import setup_logging

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

# Importing ``logger`` (above) registers the package's NullHandler on import,
# keeping the library silent until an app opts in. Because importing any
# ``xpectral.utils.*`` submodule runs this ``__init__`` first, that registration
# happens automatically for every logging module -- no per-module wiring needed.
# ``setup_logging`` is re-exported for convenience:
# ``from xpectral.utils import setup_logging``.
__all__ = ["setup_logging"]
