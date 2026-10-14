# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Local imports
from .logger import setup_logging

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

# Importing ``logger`` (above) registers the package's NullHandler on import,
# keeping the library silent until an app opts in. Because importing any
# ``xpectral_quant.utils.*`` submodule runs this ``__init__`` first, that registration
# happens automatically for every logging module -- no per-module wiring needed.
# ``setup_logging`` is re-exported for convenience:
# ``from xpectral_quant.utils import setup_logging``.
__all__ = ["setup_logging"]
