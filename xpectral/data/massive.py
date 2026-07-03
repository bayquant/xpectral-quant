# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
from datetime import date
from datetime import datetime
from functools import lru_cache
import os

# Other imports
from massive import RESTClient
from massive.rest.models import Sort
import polars as pl

from ..utils.rate_limiter import RateLimiter

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

__all__ = ["Massive"]

# Map an aggregate timespan onto the polars duration used to truncate its
# timestamp. Anything coarser than a minute is truncated to the day.
_FREQ_MAP = {
    "second": "1s",
    "minute": "1m",
}

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


class Massive:
    """Fetch aggregate bars from the Polygon/Massive API into Polars.

    Wraps a single :class:`massive.RESTClient` and returns OHLCV aggregate
    bars for a set of tickers as a semi-wide ``pl.LazyFrame`` indexed by
    ``timestamp``/``ticker``.

    Args:
        api_key: Massive API key. Defaults to the ``MASSIVE_API_KEY``
            environment variable.
        rate_limiter: Optional :class:`RateLimiter` applied once per ticker
            before its request. When omitted, no rate limiting is applied.
    """

    def __init__(
        self,
        api_key: str | None = None,
        rate_limiter: RateLimiter | None = None,
    ):
        self._client = RESTClient(
            api_key=api_key or os.getenv("MASSIVE_API_KEY", ""),
            pagination=True,
            trace=False,
        )
        self._rate_limiter = rate_limiter
        # Per-instance, bounded cache of fetched frames keyed by request args.
        # Binding the wrapper here keeps `self` out of the cache key and avoids
        # the cross-instance leak of decorating the method at class scope.
        self._get_aggregate_bars = lru_cache(maxsize=10)(self._get_aggregate_bars)

    def get_aggregate_bars(
        self,
        tickers: list[str],
        multiplier: int,
        timespan: str,
        from_: str | int | datetime | date,
        to: str | int | datetime | date,
        adjusted: bool = True,
        sort: str | Sort | None = None,
        limit: int | None = None,
    ) -> pl.LazyFrame:
        """Fetch aggregate bars for ``tickers`` as a semi-wide LazyFrame.

        Args:
            tickers: Symbols to fetch.
            multiplier: Size of the timespan multiplier (e.g. ``5`` minutes).
            timespan: Aggregate window (``"second"``, ``"minute"``, ``"day"``,
                ...).
            from_: Start of the range, inclusive.
            to: End of the range, inclusive.
            adjusted: Whether results are adjusted for splits.
            sort: Sort direction for the returned bars.
            limit: Maximum number of base aggregates queried per request.

        Returns:
            LazyFrame with ``timestamp``/``ticker`` index columns followed by
            one column per aggregate metric.
        """
        # Normalise tickers to a hashable tuple so the cached fetch can key on it.
        return self._get_aggregate_bars(
            tuple(tickers), multiplier, timespan, from_, to, adjusted, sort, limit
        )

    # -----------------------------------------------------------------------------
    # Private API
    # -----------------------------------------------------------------------------

    def _get_aggregate_bars(
        self,
        tickers: tuple[str, ...],
        multiplier: int,
        timespan: str,
        from_: str | int | datetime | date,
        to: str | int | datetime | date,
        adjusted: bool,
        sort: str | Sort | None,
        limit: int | None,
    ) -> pl.LazyFrame:
        rows = []
        for ticker in tickers:
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()
            for agg in self._client.list_aggs(
                ticker=ticker,
                multiplier=multiplier,
                timespan=timespan,
                from_=from_,
                to=to,
                adjusted=adjusted,
                sort=sort,
                limit=limit,
            ):
                # Each aggregate is already one wide row; tag it with its ticker.
                rows.append(agg.__dict__ | {"ticker": ticker})

        df = pl.DataFrame(rows)

        # Transform the unix timestamp to New York local time, truncated to the
        # aggregate's frequency.
        df = df.with_columns(
            pl.col("timestamp")
            .cast(pl.Datetime("ms"))
            .dt.replace_time_zone("UTC")
            .dt.convert_time_zone("America/New_York")
            .dt.truncate(_FREQ_MAP.get(timespan, "1d"))
        )

        # Order the index columns first, leaving the metric columns as returned.
        index = ["timestamp", "ticker"]
        df = df.select(index + [col for col in df.columns if col not in index])

        return df.lazy()
