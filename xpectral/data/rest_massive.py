# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
import os
from datetime import date
from datetime import datetime
from typing import Literal

import polars as pl

# Other imports
from massive import RESTClient
from massive.rest.models import Order
from massive.rest.models import Sort

from ..utils.rate_limiter import RateLimiter

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

__all__ = ["MassiveREST"]

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


class MassiveREST:
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
        start: str | int | datetime | date,
        end: str | int | datetime | date,
        adjusted: bool = True,
        sort: str | Sort | None = None,
        limit: int | None = None,
        params: dict | None = None,
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
            start: Start of the range, inclusive.
            end: End of the range, inclusive.
            adjusted: Whether results are adjusted for splits.
            sort: Sort direction of the raw API response; irrelevant to the
                returned frame since no row order is guaranteed here -- sort
                the collected DataFrame yourself if order matters.
            limit: Maximum number of base aggregates queried per request;
                pagination fetches the remainder of the range.
            params: Additional raw query params forwarded to the API.
            tz: Time zone the returned ``timestamp`` column is expressed in.

        Returns:
            LazyFrame with ``timestamp``/``ticker`` index columns followed by
            one column per aggregate metric.
        """
        # Every remaining local is a valid ``list_aggs`` filter kwarg by name,
        # except ``tz`` (consumed below, not part of the API call) and
        # ``start``/``end`` (the API's underlying SDK requires ``from_``/``to``,
        # which collides with the ``from`` keyword -- translate below).
        filters = {
            k: v
            for k, v in locals().items()
            if k not in ("self", "tickers", "tz", "start", "end")
        }
        filters["from_"] = start
        filters["to"] = end

        rows = []
        for ticker in tickers:
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()
            for agg in self._client.list_aggs(ticker=ticker, **filters):
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

    def get_dividends(
        self,
        tickers: list[str],
        ex_dividend_date: str | date | None = None,
        ex_dividend_date_lt: str | date | None = None,
        ex_dividend_date_lte: str | date | None = None,
        ex_dividend_date_gt: str | date | None = None,
        ex_dividend_date_gte: str | date | None = None,
        record_date: str | date | None = None,
        record_date_lt: str | date | None = None,
        record_date_lte: str | date | None = None,
        record_date_gt: str | date | None = None,
        record_date_gte: str | date | None = None,
        declaration_date: str | date | None = None,
        declaration_date_lt: str | date | None = None,
        declaration_date_lte: str | date | None = None,
        declaration_date_gt: str | date | None = None,
        declaration_date_gte: str | date | None = None,
        pay_date: str | date | None = None,
        pay_date_lt: str | date | None = None,
        pay_date_lte: str | date | None = None,
        pay_date_gt: str | date | None = None,
        pay_date_gte: str | date | None = None,
        frequency: int | None = None,
        cash_amount: float | None = None,
        cash_amount_lt: float | None = None,
        cash_amount_lte: float | None = None,
        cash_amount_gt: float | None = None,
        cash_amount_gte: float | None = None,
        dividend_type: str | None = None,
        limit: int | None = None,
        params: dict | None = None,
    ) -> pl.LazyFrame:
        """Fetch cash dividends for ``tickers`` as a semi-wide LazyFrame.

        Mirrors the filters ``massive.RESTClient.list_dividends`` accepts,
        minus ``ticker``/``ticker_lt``/etc. (superseded by ``tickers``, which
        drives one call per symbol -- an alphabetical ticker-range filter
        doesn't compose with that) and ``sort``/``order``/``raw``/``options``
        (API-side response shaping that doesn't survive into the returned
        DataFrame, which has no guaranteed row order; sort the collected
        frame yourself if order matters).

        Args:
            tickers: Symbols to fetch.
            ex_dividend_date: Exact ex-dividend date match.
            ex_dividend_date_lt: Ex-dividend date strictly before this date.
            ex_dividend_date_lte: Ex-dividend date on or before this date.
            ex_dividend_date_gt: Ex-dividend date strictly after this date.
            ex_dividend_date_gte: Ex-dividend date on or after this date.
            record_date: Exact record date match.
            record_date_lt: Record date strictly before this date.
            record_date_lte: Record date on or before this date.
            record_date_gt: Record date strictly after this date.
            record_date_gte: Record date on or after this date.
            declaration_date: Exact declaration date match.
            declaration_date_lt: Declaration date strictly before this date.
            declaration_date_lte: Declaration date on or before this date.
            declaration_date_gt: Declaration date strictly after this date.
            declaration_date_gte: Declaration date on or after this date.
            pay_date: Exact pay date match.
            pay_date_lt: Pay date strictly before this date.
            pay_date_lte: Pay date on or before this date.
            pay_date_gt: Pay date strictly after this date.
            pay_date_gte: Pay date on or after this date.
            frequency: Payouts per year (0 one-time, 1 annual, 2 bi-annual,
                4 quarterly, 12 monthly).
            cash_amount: Exact cash amount match.
            cash_amount_lt: Cash amount strictly less than this value.
            cash_amount_lte: Cash amount less than or equal to this value.
            cash_amount_gt: Cash amount strictly greater than this value.
            cash_amount_gte: Cash amount greater than or equal to this value.
            dividend_type: ``"CD"`` (regular cash) or ``"SC"`` (special cash).
            limit: Maximum number of dividends queried per request per
                ticker; pagination fetches the remainder.
            params: Additional raw query params forwarded to the API.

        Returns:
            LazyFrame with ``ex_dividend_date``/``ticker`` index columns,
            followed by declaration/record/pay dates, frequency, cash
            amount, currency, and dividend type.
        """
        filters = {k: v for k, v in locals().items() if k not in ("self", "tickers")}

        rows = []
        for ticker in tickers:
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()
            for div in self._client.list_dividends(ticker=ticker, **filters):
                rows.append(div.__dict__ | {"ticker": ticker})

        df = pl.DataFrame(rows)

        # Dividend dates are plain YYYY-MM-DD strings with no time component,
        # unlike aggregate bar timestamps -- no timezone conversion applies.
        date_cols = ["ex_dividend_date", "declaration_date", "record_date", "pay_date"]
        df = df.with_columns(
            [pl.col(c).str.to_date() for c in date_cols if c in df.columns]
        )

        # Order the index columns first, leaving the metric columns as returned.
        index = ["ex_dividend_date", "ticker"]
        df = df.select(index + [col for col in df.columns if col not in index])

        return df.lazy()

    def get_splits(
        self,
        tickers: list[str],
        execution_date: str | date | None = None,
        execution_date_lt: str | date | None = None,
        execution_date_lte: str | date | None = None,
        execution_date_gt: str | date | None = None,
        execution_date_gte: str | date | None = None,
        reverse_split: bool | None = None,
        limit: int | None = None,
        params: dict | None = None,
    ) -> pl.LazyFrame:
        """Fetch stock splits for ``tickers`` as a semi-wide LazyFrame.

        Mirrors the filters ``massive.RESTClient.list_splits`` accepts, minus
        ``ticker``/``ticker_lt``/etc. (superseded by ``tickers``, which
        drives one call per symbol -- an alphabetical ticker-range filter
        doesn't compose with that) and ``sort``/``order``/``raw``/``options``
        (API-side response shaping that doesn't survive into the returned
        DataFrame, which has no guaranteed row order; sort the collected
        frame yourself if order matters).

        Args:
            tickers: Symbols to fetch.
            execution_date: Exact execution date match.
            execution_date_lt: Execution date strictly before this date.
            execution_date_lte: Execution date on or before this date.
            execution_date_gt: Execution date strictly after this date.
            execution_date_gte: Execution date on or after this date.
            reverse_split: When ``True``/``False``, restrict to reverse
                splits (``split_from`` > ``split_to``) or forward splits,
                respectively. ``None`` returns both.
            limit: Maximum number of splits queried per request per ticker;
                pagination fetches the remainder.
            params: Additional raw query params forwarded to the API.

        Returns:
            LazyFrame with ``execution_date``/``ticker`` index columns,
            followed by ``split_from``/``split_to`` (the split ratio
            components; a reverse split has ``split_from`` > ``split_to``).
        """
        filters = {k: v for k, v in locals().items() if k not in ("self", "tickers")}

        rows = []
        for ticker in tickers:
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()
            for split in self._client.list_splits(ticker=ticker, **filters):
                rows.append(split.__dict__ | {"ticker": ticker})

        df = pl.DataFrame(rows)

        # Execution dates are plain YYYY-MM-DD strings with no time component.
        df = df.with_columns(pl.col("execution_date").str.to_date())

        # Order the index columns first, leaving the metric columns as returned.
        index = ["execution_date", "ticker"]
        df = df.select(index + [col for col in df.columns if col not in index])

        return df.lazy()

    def get_tickers(
        self,
        ticker: str | None = None,
        ticker_lt: str | None = None,
        ticker_lte: str | None = None,
        ticker_gt: str | None = None,
        ticker_gte: str | None = None,
        type: str | None = None,
        market: str | None = None,
        exchange: str | None = None,
        cusip: int | None = None,
        cik: int | None = None,
        date: str | date | None = None,
        active: bool | None = None,
        search: str | None = None,
        limit: int | None = 10,
        sort: str | Sort | None = "ticker",
        order: str | Order | None = "asc",
        params: dict | None = None,
    ) -> pl.LazyFrame:
        """Fetch the reference ticker universe (or a filtered slice) as a LazyFrame.

        Unlike ``get_aggregate_bars``/``get_dividends``/``get_splits``, this
        wraps a single paginated call rather than looping per ticker -- so
        ``ticker``/``ticker_lt``/etc. are genuine filters here (there's no
        per-ticker loop for a ticker-range filter to conflict with), and
        ``sort``/``order`` genuinely determine the returned row order since
        there's no per-ticker concatenation to scramble it. No rate limiting
        is applied since this issues one request (paginated internally), not
        one per ticker.

        Mirrors ``massive.RESTClient.list_tickers``, minus ``raw``/``options``
        (API-side response/transport shaping that doesn't survive into the
        returned DataFrame).

        Args:
            ticker: Exact ticker symbol match.
            ticker_lt: Ticker symbol strictly less than this value.
            ticker_lte: Ticker symbol less than or equal to this value.
            ticker_gt: Ticker symbol strictly greater than this value.
            ticker_gte: Ticker symbol greater than or equal to this value.
            type: Ticker type code (see ``client.get_ticker_types()``).
            market: Market type, e.g. ``"stocks"``, ``"crypto"``, ``"fx"``.
            exchange: Primary exchange MIC (ISO 10383).
            cusip: CUSIP code to search for.
            cik: CIK code to search for.
            date: Point in time to retrieve tickers as of. Defaults to the
                most recent available date.
            active: Restrict to actively (or inactively) traded tickers as
                of ``date``. Defaults to actively traded only.
            search: Free-text search across ticker and company name.
            limit: Maximum number of tickers queried per request; pagination
                fetches the remainder.
            sort: Field to sort results on. Ignored by the API if ``search``
                is set.
            order: Sort direction, ``"asc"`` or ``"desc"``.
            params: Additional raw query params forwarded to the API.

        Returns:
            LazyFrame with ``ticker`` first, followed by ``name``,
            ``composite_figi``, ``share_class_figi``, and the remaining
            reference columns (market, exchange, currency, CIK, active/
            delisted status, ...).
        """
        filters = {k: v for k, v in locals().items() if k != "self"}

        rows = [t.__dict__ for t in self._client.list_tickers(**filters)]
        df = pl.DataFrame(rows)

        # Order the ticker key first, leaving the reference columns as returned.
        index = ["ticker"]
        df = df.select(index + [col for col in df.columns if col not in index])

        return df.lazy()

    # -------------------------------------------------------------------------
    # Private API
    # -------------------------------------------------------------------------
