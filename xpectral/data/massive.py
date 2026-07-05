# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
from datetime import date
from datetime import datetime
from typing import Literal
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

    def get_aggregate_bars(
        self,
        tickers: list[str],
        multiplier: int,
        timespan: Literal[
            "second",
            "minute",
            "hour",
            "day",
            "week",
            "month",
            "quarter",
            "year",
        ],
        from_: str | int | datetime | date,
        to: str | int | datetime | date,
        adjusted: bool = True,
        sort: str | Sort | None = None,
        limit: int | None = None,
        tz: str = "America/New_York",
    ) -> pl.LazyFrame:
        """Fetch aggregate bars for ``tickers`` as a semi-wide LazyFrame.

        The API returns each bar's timestamp as the start of its aggregate
        window, so the timestamp is only converted to ``tz`` -- no
        per-frequency alignment is applied, which works for any timespan.

        Args:
            tickers: Symbols to fetch.
            multiplier: Size of the timespan multiplier (e.g. ``5`` minutes).
            timespan: Aggregate window.
            from_: Start of the range, inclusive.
            to: End of the range, inclusive.
            adjusted: Whether results are adjusted for splits.
            sort: Sort direction for the returned bars.
            limit: Maximum number of base aggregates queried per request;
                pagination fetches the remainder of the range.
            tz: Time zone the returned ``timestamp`` column is expressed in.

        Returns:
            LazyFrame with ``timestamp``/``ticker`` index columns followed by
            one column per aggregate metric.
        """
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

        # The API returns the window-start timestamp as unix milliseconds in
        # UTC; express it in the requested time zone. No truncation is needed,
        # which keeps the same code correct for every timespan.
        df = df.with_columns(
            # e.g. 1704205805000 -> 2024-01-02 09:30:05-05:00 in New York:
            pl.col("timestamp")  # 1704205805000 (int, epoch-ms, UTC)
            .cast(pl.Datetime("ms"))  # 2024-01-02 14:30:05, naive datetime, no zone
            .dt.replace_time_zone(
                "UTC"
            )  # 2024-01-02 14:30:05+00:00, stamp zone, no shift
            .dt.convert_time_zone(
                tz
            )  # 2024-01-02 09:30:05-05:00, shift to tz wall clock
        )

        # Order the index columns first, leaving the metric columns as returned.
        index = ["timestamp", "ticker"]
        df = df.select(index + [col for col in df.columns if col not in index])

        return df.lazy()

    # -------------------------------------------------------------------------
    # Private API
    # -------------------------------------------------------------------------
