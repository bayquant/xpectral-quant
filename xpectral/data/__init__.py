# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
from pathlib import Path

# Third-party imports
from dotenv import load_dotenv

# Local imports
from . import simulations
from . import xml_treasury
from .simulations import BrownianMotion
from .xml_treasury import USTreasuryRates

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

# Load `xpectral/.env` (one level up) before importing `massive`, so the
# Polygon/Massive API credentials it reads are available. The `xpectral`
# namespace package has no top-level __init__.py to do this, so it lives here —
# the entry point for anything that touches market data.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# Local imports deferred until after load_dotenv() — these read Massive/Polygon
# credentials at import time.
from . import flatfiles_massive  # noqa: E402
from . import rest_massive  # noqa: E402
from .flatfiles_massive import MassiveFlatFiles  # noqa: E402
from .rest_massive import MassiveREST  # noqa: E402

__all__ = [
    "BrownianMotion",
    "MassiveFlatFiles",
    "MassiveREST",
    "USTreasuryRates",
    "flatfiles_massive",
    "rest_massive",
    "simulations",
    "xml_treasury",
]
