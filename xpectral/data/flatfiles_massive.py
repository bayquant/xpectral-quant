# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
import os
import tempfile
from datetime import date
from datetime import timedelta
from pathlib import Path

# Third-party imports
import polars as pl

# Local imports
from ..utils.s3 import S3Downloader

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

__all__ = ["MassiveFlatFiles"]

# Default asset-class prefix. Other classes (``us_options_opra``, ``us_indices``,
# ``global_forex``, ``global_crypto``) are reached by passing ``prefix``.
_DEFAULT_PREFIX = "us_stocks_sip"

# Concrete stock datasets: logical name -> object-key folder. The folders are
# shared across asset classes, so this registry doubles as the generic key
# spec for any prefix that exposes the same datasets.
_DATASETS = {
    "trades": "trades_v1",
    "quotes": "quotes_v1",
    "minute_aggs": "minute_aggs_v1",
    "day_aggs": "day_aggs_v1",
}

# Every column, across the datasets above, that holds an epoch-nanosecond
# timestamp -- all of them are converted to tz-aware datetimes on load.
# trades/quotes carry three independent clocks side by side:
#   participant_timestamp: when the originating exchange or broker-dealer
#       generated/executed the trade.
#   sip_timestamp: when the Securities Information Processor (SIP) received
#       the trade for inclusion in the consolidated tape.
#   trf_timestamp: when a Trade Reporting Facility (TRF) received the trade
#       report, only for off-exchange/OTC trades.
# aggs carry only their window start.
_TIMESTAMP_COLUMNS = {
    "participant_timestamp",
    "sip_timestamp",
    "trf_timestamp",
    "window_start",
}

# Documented dtype for every column across trades/quotes/minute_aggs/day_aggs
# (https://massive.com/docs/flat-files/stocks/{trades,quotes,minute-aggregates,
# day-aggregates}). Every day's CSV is cast to this schema before being
# written to parquet, so a column can never drift dtype (e.g. an
# all-integer ``volume`` one day, fractional the next) across cached files --
# without this, files scanned together would need per-file schema
# reconciliation, which is slower than a single multi-file scan.
_COLUMN_DTYPES = {
    "ticker": pl.String,
    "id": pl.String,
    "conditions": pl.Int64,
    "correction": pl.Int64,
    "exchange": pl.Int64,
    "sequence_number": pl.Int64,
    "tape": pl.Int64,
    "trf_id": pl.Int64,
    "ask_exchange": pl.Int64,
    "bid_exchange": pl.Int64,
    "indicators": pl.Int64,
    "transactions": pl.Int64,
    "participant_timestamp": pl.Int64,
    "sip_timestamp": pl.Int64,
    "trf_timestamp": pl.Int64,
    "window_start": pl.Int64,
    "price": pl.Float64,
    "size": pl.Float64,
    "ask_price": pl.Float64,
    "ask_size": pl.Float64,
    "bid_price": pl.Float64,
    "bid_size": pl.Float64,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
}

# Default local cache root: a ``massive`` subdir of the shared cache root.
_DEFAULT_DOWNLOAD_DIR = Path.home() / ".cache" / "xpectral" / "massive"

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


class MassiveFlatFiles:
    """Fetch Massive (formerly Polygon.io) S3 flat files into Polars.

    Resolves the per-day object keys for a dataset and date range, downloads
    any gzipped CSVs not already cached (via a generic
    :class:`~xpectral.utils.s3.S3Downloader` into a scratch temp directory),
    and writes each day's raw rows to a local Hive-partitioned parquet cache
    (``download_dir/prefix/folder/year=YYYY/month=MM/YYYY-MM-DD.parquet``) --
    the temp CSV is discarded once its parquet file is written, so only
    parquet is kept on disk. Reads scan that cache and convert every
    recognized epoch-ns timestamp column to a tz-aware datetime, returning a
    semi-wide ``pl.LazyFrame`` with ``ticker`` first -- mirroring
    :class:`~xpectral.data.rest_massive.MassiveREST`.

    The flat-files S3 credentials are issued in the Massive Dashboard and are
    separate from ``MASSIVE_API_KEY``.

    Args:
        access_key: S3 access key. Defaults to ``MASSIVE_S3_ACCESS_KEY``.
        secret_key: S3 secret key. Defaults to ``MASSIVE_S3_SECRET_KEY``.
        download_dir: Root for the local Hive-partitioned parquet cache.
            Defaults to ``~/.cache/xpectral/massive``.
        offline: When True, use only parquet files already cached under
            ``download_dir`` and make no network calls -- for working against
            the local cache without an active subscription.
    """

    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
        download_dir: str | os.PathLike | None = None,
        offline: bool = False,
    ):
        self._download_dir = (
            Path(download_dir) if download_dir is not None else _DEFAULT_DOWNLOAD_DIR
        )
        self._offline = offline
        self._s3 = S3Downloader(
            bucket="flatfiles",
            dest_dir=self._download_dir,
            endpoint_url="https://files.massive.com",
            access_key=access_key or os.getenv("MASSIVE_S3_ACCESS_KEY", ""),
            secret_key=secret_key or os.getenv("MASSIVE_S3_SECRET_KEY", ""),
        )

    def get_flat_files(
        self,
        dataset: str,
        start: str | date,
        end: str | date,
        prefix: str = _DEFAULT_PREFIX,
        tz: str = "America/New_York",
        overwrite: bool = False,
    ) -> pl.LazyFrame:
        """Load a dataset over a date range into a LazyFrame, caching as parquet.

        Resolves one object key per calendar day in the inclusive
        ``start``..``end`` range. Days not already cached locally are
        downloaded and converted to parquet (see class docstring); the
        resulting cache is then scanned for the full range. Every recognized
        timestamp column present (``participant_timestamp``,
        ``sip_timestamp``, ``trf_timestamp``, ``window_start``) is converted
        from raw epoch nanoseconds to a tz-aware datetime, keeping its source
        name.

        Args:
            dataset: One of ``trades``, ``quotes``, ``minute_aggs``,
                ``day_aggs``.
            start: Start of the range, inclusive.
            end: End of the range, inclusive.
            prefix: Asset-class prefix. Defaults to ``us_stocks_sip``.
            tz: Time zone the timestamp columns are expressed in.
            overwrite: Rebuild the parquet cache for days that already have
                a cached file, re-fetching them from S3. By default cached
                days are reused (historical flat files are immutable); pass
                ``True`` to force a fresh fetch, e.g. for a recent day that
                may still be finalizing. No effect when the client is
                offline.

        Returns:
            LazyFrame with ``ticker`` first, followed by its remaining
            columns in their on-disk order.
        """
        if dataset not in _DATASETS:
            raise ValueError(
                f"unknown dataset {dataset!r}; expected one of {sorted(_DATASETS)}"
            )
        folder = _DATASETS[dataset]

        # ``date.fromisoformat`` only accepts ``YYYY-MM-DD``, so ``str(value)``
        # round-trips a ``date`` (or an ISO date string) but rejects a
        # ``datetime`` (whose ``str()`` includes a time component).
        start_date = date.fromisoformat(str(start))
        end_date = date.fromisoformat(str(end))
        if end_date < start_date:
            raise ValueError(f"end date {end_date} precedes start date {start_date}")
        days = [
            start_date + timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
        ]
        self._cache_days(prefix, folder, days, overwrite=overwrite)

        paths = [
            path
            for day in days
            if (path := _parquet_path(self._download_dir, prefix, folder, day)).exists()
        ]
        if not paths:
            raise ValueError(
                f"no flat files found for {prefix}/{folder} in {start}..{end}"
            )

        return _load_parquet_files(paths, tz)

    # -------------------------------------------------------------------------
    # Private API
    # -------------------------------------------------------------------------

    def _cache_days(
        self,
        prefix: str,
        folder: str,
        days: list[date],
        overwrite: bool,
    ) -> None:
        """Ensure each day's Hive parquet file is on disk, downloading gaps.

        Missing days are fetched as gzipped CSV into a scratch temp
        directory, parsed with their raw (unconverted) values, cast to the
        documented dtype for each recognized column, written to the local
        ``year=/month=/<date>.parquet`` cache, and the temp CSV is discarded
        -- only the parquet form is kept. When offline, no network is
        attempted at all -- ``get_flat_files`` falls back to whatever is
        already cached.
        """
        if self._offline:
            return

        pending = [
            day
            for day in days
            if overwrite
            or not _parquet_path(self._download_dir, prefix, folder, day).exists()
        ]
        if not pending:
            return

        # e.g. ``us_stocks_sip/trades_v1/2024/01/2024-01-02.csv.gz``.
        keys = [
            f"{prefix}/{folder}/{day:%Y/%m}/{day.isoformat()}.csv.gz" for day in pending
        ]
        key_to_day = dict(zip(keys, pending))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            csv_paths = self._s3.download(keys, dest_dir=tmp_dir)
            for csv_path in csv_paths:
                key = csv_path.relative_to(tmp_dir).as_posix()
                out_path = _parquet_path(
                    self._download_dir, prefix, folder, key_to_day[key]
                )
                out_path.parent.mkdir(parents=True, exist_ok=True)
                # ``schema_overrides`` applies only to columns actually present
                # in csv_path -- unmapped columns pass through with their
                # inferred dtype, and mapped ones never drift across cached
                # days.
                df = pl.read_csv(csv_path, schema_overrides=_COLUMN_DTYPES)
                df.write_parquet(out_path)


# -----------------------------------------------------------------------------
# Private API
# -----------------------------------------------------------------------------


def _load_parquet_files(paths: list[Path], tz: str) -> pl.LazyFrame:
    """Scan Hive-partitioned parquet files into one tz-aware LazyFrame.

    Raw flat-file timestamps are epoch nanoseconds in UTC; every recognized
    timestamp column present is converted to a tz-aware datetime in ``tz``,
    keeping its source name.
    """
    lf = pl.scan_parquet(sorted(paths), hive_partitioning=True)
    schema_names = lf.collect_schema().names()

    convert = [col for col in schema_names if col in _TIMESTAMP_COLUMNS]
    lf = lf.with_columns(
        pl.col(col)
        .cast(pl.Datetime("ns"))
        .dt.replace_time_zone("UTC")
        .dt.convert_time_zone(tz)
        for col in convert
    )

    # Ticker first; drop the Hive partition columns (``year``/``month``),
    # which are cache-layout artifacts, not source data.
    rest = [col for col in schema_names if col not in ("ticker", "year", "month")]
    return lf.select(["ticker"] + rest)


def _parquet_path(download_dir: Path, prefix: str, folder: str, day: date) -> Path:
    """Local Hive-partitioned cache path for one day of a dataset."""
    return (
        download_dir
        / prefix
        / folder
        / f"year={day.year}"
        / f"month={day.month:02d}"
        / f"{day.isoformat()}.parquet"
    )
