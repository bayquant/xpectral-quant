# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
from pathlib import Path

# Other imports
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

# Load `xpectral/.env` (one level up) before importing `massive`, so the
# Polygon/Massive API credentials it reads are available. The `xpectral`
# namespace package has no top-level __init__.py to do this, so it lives here —
# the entry point for anything that touches market data.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# -----------------------------------------------------------------------------
# Imports (post-env)
# -----------------------------------------------------------------------------

from . import massive
from . import simulations
from .massive import Massive
from .simulations import BrownianMotion

__all__ = [
    "BrownianMotion",
    "Massive",
    "massive",
    "simulations",
]
