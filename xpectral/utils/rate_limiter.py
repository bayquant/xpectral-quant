#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

# Standard library imports
import time
from collections import deque
from typing import Deque

# Other imports
from .logger import get_logger

#-----------------------------------------------------------------------------
# Globals and constants
#-----------------------------------------------------------------------------

log = get_logger(name="rate_limiter")

#-----------------------------------------------------------------------------
# General API
#-----------------------------------------------------------------------------

class RateLimiter:
    """Simple token bucket style limiter"""

    def __init__(self, calls: int, per_seconds: float):
        if calls <= 0 or per_seconds <= 0:
            raise ValueError("calls and per_seconds must be positive")
        self.calls = calls
        self.per_seconds = per_seconds
        self._hits: Deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        window_start = now - self.per_seconds

        while self._hits and self._hits[0] <= window_start:
            self._hits.popleft()

        if len(self._hits) >= self.calls:
            sleep_for = self.per_seconds - (now - self._hits[0])
            if sleep_for > 0:
                log.info("sleeping for {:.0f} seconds", sleep_for)
                time.sleep(sleep_for)
            self.acquire()
            return

        self._hits.append(time.monotonic())

#-----------------------------------------------------------------------------
# Private API
#-----------------------------------------------------------------------------
