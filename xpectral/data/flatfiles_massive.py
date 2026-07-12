# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
from datetime import date
from datetime import datetime
from datetime import timedelta
from pathlib import Path
import os

# Other imports
import polars as pl

from ..utils.s3 import S3Downloader

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

__all__ = ["MassiveFlatFiles"]

# Default asset-class prefix. Other classes (``us_options_opra``, ``us_indices``,
# ``global_forex``, ``global_crypto``) are reached by passing ``prefix``.
_DEFAULT_PREFIX = "us_stocks_sip"

# Concrete stock datasets: logical name -> (object-key folder, the epoch-ns
# column promoted to the tz-aware ``timestamp`` index). The folders are shared
# across asset classes, so this registry doubles as the generic key/parse spec
# for any prefix that exposes the same datasets.
_DATASETS = {
    "trades": ("trades_v1", "sip_timestamp"),
    "quotes": ("quotes_v1", "sip_timestamp"),
    "minute_aggs": ("minute_aggs_v1", "window_start"),
    "day_aggs": ("day_aggs_v1", "window_start"),
}

# Default local download root: a ``flatfiles`` subdir of the shared cache root.
_DEFAULT_DOWNLOAD_DIR = Path.home() / ".cache" / "xpectral" / "flatfiles"

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


class MassiveFlatFiles:
    """Fetch Massive (formerly Polygon.io) S3 flat files into Polars.

    Resolves the per-day object keys for a dataset and date range, downloads the
    gzipped CSVs via a generic :class:`~xpectral.utils.s3.S3Downloader`, and
    parses them into a semi-wide ``pl.LazyFrame`` with the dataset's tz-aware
    timestamp column and ``ticker`` first -- mirroring
    :class:`~xpectral.data.rest_massive.MassiveREST`.

    The flat-files S3 credentials are issued in the Massive Dashboard and are
    separate from ``MASSIVE_API_KEY``.

    Args:
        access_key: S3 access key. Defaults to ``MASSIVE_S3_ACCESS_KEY``.
        secret_key: S3 secret key. Defaults to ``MASSIVE_S3_SECRET_KEY``.
        download_dir: Root for downloaded ``.csv.gz`` files. Defaults to
            ``~/.cache/xpectral/flatfiles``.
        offline: When True, use only flat files already under ``download_dir``
            and make no network calls -- for working against the local cache
            without an active subscription.
    """

    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
        download_dir: str | os.PathLike | None = None,
        offline: bool = False,
    ):
        dest_dir = (
            Path(download_dir) if download_dir is not None else _DEFAULT_DOWNLOAD_DIR
        )
        self._s3 = S3Downloader(
            bucket="flatfiles",
            dest_dir=dest_dir,
            endpoint_url="https://files.massive.com",
            access_key=access_key or os.getenv("MASSIVE_S3_ACCESS_KEY", ""),
            secret_key=secret_key or os.getenv("MASSIVE_S3_SECRET_KEY", ""),
            offline=offline,
        )

    def get_flat_files(
        self,
        dataset: str,
        from_: str | date | datetime,
        to: str | date | datetime,
        prefix: str = _DEFAULT_PREFIX,
        tz: str = "America/New_York",
        overwrite: bool = False,
    ) -> pl.LazyFrame:
        """Download and parse a dataset over a date range into a LazyFrame.

        Resolves one object key per calendar day in the inclusive
        ``from_``..``to`` range, downloads any not already on disk, parses each
        gzipped CSV, and concatenates across days. The dataset's epoch-nanosecond
        timestamp column is converted to a tz-aware datetime in place (keeping its
        source name) and placed first.

        Args:
            dataset: One of ``trades``, ``quotes``, ``minute_aggs``,
                ``day_aggs``.
            from_: Start of the range, inclusive.
            to: End of the range, inclusive.
            prefix: Asset-class prefix. Defaults to ``us_stocks_sip``.
            tz: Time zone the timestamp column is expressed in.
            overwrite: Re-download files that already exist locally. By default
                the downloaded ``.csv.gz`` files are reused as an on-disk cache
                (historical flat files are immutable); pass ``True`` to force a
                fresh fetch, e.g. for a recent day that may still be finalizing.
                No effect when the client is offline.

        Returns:
            LazyFrame with the dataset's timestamp column and ``ticker`` first,
            followed by its remaining columns.
        """
        if dataset not in _DATASETS:
            raise ValueError(
                f"unknown dataset {dataset!r}; expected one of {sorted(_DATASETS)}"
            )
        folder, timestamp_col = _DATASETS[dataset]

        keys = _resolve_keys(prefix, folder, from_, to)
        # Reuse already-downloaded files by default; they act as an on-disk cache.
        paths = self._s3.download(keys, overwrite=overwrite)
        if not paths:
            raise ValueError(
                f"no flat files found for {prefix}/{folder} in {from_}..{to}"
            )

        # Parse the downloaded files in a stable, sorted order.
        return _parse_flat_files(sorted(paths), timestamp_col, tz).lazy()


# -----------------------------------------------------------------------------
# Private API
# -----------------------------------------------------------------------------


def _parse_flat_files(
    paths: list[Path],
    timestamp_col: str,
    tz: str,
) -> pl.DataFrame:
    """Read gzipped CSV flat files into one tz-indexed DataFrame.

    Returns a materialized ``pl.DataFrame``; the caller applies ``.lazy()`` at
    the boundary so the public return type is a ``pl.LazyFrame``.
    """
    # Polars decompresses ``.csv.gz`` transparently when given the path.
    # ``vertical_relaxed`` reconciles a column whose inferred dtype differs across
    # days (e.g. Int64 one day, Float64 another) by casting to a common supertype.
    frames = [pl.read_csv(path) for path in paths]
    df = pl.concat(frames, how="vertical_relaxed")

    # Flat-file timestamps are epoch nanoseconds in UTC; express them in ``tz``
    # in place, keeping the source column name.
    df = df.with_columns(
        pl.col(timestamp_col)
        .cast(pl.Datetime("ns"))
        .dt.replace_time_zone("UTC")
        .dt.convert_time_zone(tz)
    )

    # Timestamp and ticker columns first.
    index = [timestamp_col, "ticker"]
    rest = [col for col in df.columns if col not in index]
    return df.select(index + rest)


def _resolve_keys(
    prefix: str,
    folder: str,
    from_: str | date | datetime,
    to: str | date | datetime,
) -> list[str]:
    """Resolve the per-day object keys for an inclusive date range."""
    start = _to_date(from_)
    end = _to_date(to)
    if end < start:
        raise ValueError(f"end date {end} precedes start date {start}")

    # e.g. us_stocks_sip/trades_v1/2024/01/2024-01-02.csv.gz
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    return [f"{prefix}/{folder}/{day:%Y/%m}/{day.isoformat()}.csv.gz" for day in days]


def _to_date(value: str | date | datetime) -> date:
    """Coerce a date-like value to a :class:`datetime.date`."""
    # ``datetime`` subclasses ``date``, so test it first.
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"unsupported date value: {value!r}")
