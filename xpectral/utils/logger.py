#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

# Standard library imports
import sys
from dataclasses import dataclass
from typing import Callable
from typing import Dict

#-----------------------------------------------------------------------------
# Globals and constants
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# General API
#-----------------------------------------------------------------------------

@dataclass(frozen=True)
class LogLevel:
    name: str
    color: str  # ANSI color code


class ColorLogger:
    _LEVELS: Dict[str, LogLevel] = {
        "DEBUG": LogLevel("DEBUG", "\033[94m"),
        "INFO": LogLevel("INFO", "\033[92m"),
        "WARNING": LogLevel("WARNING", "\033[93m"),
        "ERROR": LogLevel("ERROR", "\033[91m"),
        "CRITICAL": LogLevel("CRITICAL", "\033[95m"),
    }
    _RESET = "\033[0m"

    def __init__(self, name: str):
        self.name = name
        for level in self._LEVELS:
            setattr(self, level.lower(), self._build_logger(level))

    def _build_logger(self, level_name: str) -> Callable[..., None]:
        def log(message: str, *args) -> None:
            level = self._LEVELS[level_name]
            formatted = message.format(*args)
            output = f"{level.color}[{level.name}] {self.name}: {formatted}{self._RESET}"
            print(output, file=sys.stderr if level_name in {"ERROR", "CRITICAL"} else sys.stdout)

        return log


def get_logger(name: str) -> ColorLogger:
    return ColorLogger(name)

#-----------------------------------------------------------------------------
# Private API
#-----------------------------------------------------------------------------
