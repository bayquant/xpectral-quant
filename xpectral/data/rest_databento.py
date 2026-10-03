# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
from datetime import date
from datetime import datetime

# Third-party imports
import databento as db
import polars as pl

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

__all__ = ["DatabentoREST"]

# OPRA consolidates quotes and trades from every US options exchange.
_OPRA_DATASET = "OPRA.PILLAR"

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


class DatabentoREST:
    """Fetch US equity option quotes from the Databento historical API into Polars.

    Requests are billed per byte of data returned, so check a request with
    :meth:`get_option_quotes_cost` before running it over a long range.

    Args:
        api_key: Databento API key. Defaults to the ``DATABENTO_API_KEY``
            environment variable.
    """

    def __init__(self, api_key: str | None = None):
        self._client = db.Historical(key=api_key)

    def get_option_quotes(
        self,
        tickers: list[str],
        start: str | datetime | date,
        end: str | datetime | date,
        schema: str = "cbbo-1m",
        tz: str = "America/New_York",
    ) -> pl.LazyFrame:
        """Fetch consolidated best bid and offer for every option on ``tickers``.

        Each ticker is requested as its parent symbol (``AAPL`` becomes
        ``AAPL.OPT``), which returns every listed expiry and strike, including
        options with adjusted roots after a corporate action.

        Args:
            tickers: Underlying symbols whose option chains to fetch.
            start: Start of the range, inclusive.
            end: End of the range, exclusive.
            schema: Databento quote schema: ``"cbbo-1m"`` or ``"cbbo-1s"``
                (top of book sampled each minute or second), or ``"tcbbo"``
                (top of book at each trade).
            tz: Time zone the returned timestamp columns are expressed in.

        Returns:
            LazyFrame with ``ts_recv``/``ticker``/``symbol`` index columns,
            then the contract terms parsed from the OCC symbol (``root``,
            ``expiration``, ``option_type``, ``strike``), then the quote
            columns as Databento returns them (``bid_px_00``, ``ask_px_00``,
            ``bid_sz_00``, ``ask_sz_00``, ...).
        """
        frames = []
        for ticker in tickers:
            store = self._client.timeseries.get_range(
                dataset=_OPRA_DATASET,
                schema=schema,
                symbols=[f"{ticker}.OPT"],
                stype_in="parent",
                start=start,
                end=end,
            )
            df = pl.from_pandas(store.to_df(tz=tz).reset_index())
            frames.append(df.with_columns(pl.lit(ticker).alias("ticker")))

        df = pl.concat(frames, how="diagonal_relaxed")

        # OCC symbols pad the root to six characters, then encode expiry,
        # type, and strike in thousandths of a dollar, e.g.
        # "AAPL  240119C00190000" -> AAPL, 2024-01-19, call, 190.0.
        contract = pl.col("symbol").str.extract_groups(
            r"^(?<root>\S+)\s*(?<expiration>\d{6})(?<option_type>[CP])(?<strike>\d{8})$"
        )
        df = df.with_columns(contract.alias("contract")).unnest("contract")
        df = df.with_columns(
            pl.col("expiration").str.to_date("%y%m%d"),
            pl.col("strike").cast(pl.Int64) / 1000,
        )

        # Order the index and contract columns first, leaving the quote
        # columns as returned.
        index = [
            "ts_recv",
            "ticker",
            "symbol",
            "root",
            "expiration",
            "option_type",
            "strike",
        ]
        df = df.select(index + [col for col in df.columns if col not in index])

        return df.lazy()

    def get_option_quotes_cost(
        self,
        tickers: list[str],
        start: str | datetime | date,
        end: str | datetime | date,
        schema: str = "cbbo-1m",
    ) -> float:
        """Return the cost in US dollars of the matching :meth:`get_option_quotes` call.

        Args:
            tickers: Underlying symbols whose option chains to price.
            start: Start of the range, inclusive.
            end: End of the range, exclusive.
            schema: Databento quote schema, as in :meth:`get_option_quotes`.

        Returns:
            Total cost across all tickers, in US dollars.
        """
        return self._client.metadata.get_cost(
            dataset=_OPRA_DATASET,
            schema=schema,
            symbols=[f"{ticker}.OPT" for ticker in tickers],
            stype_in="parent",
            start=start,
            end=end,
        )
