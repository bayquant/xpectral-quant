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
import boto3
import polars as pl
from botocore.config import Config
from botocore.exceptions import ClientError

from ..utils.cache import disk_cache
from ..utils.logger import get_logger

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

__all__ = ["MassiveFlatFiles"]

# S3-compatible endpoint and bucket that serve the Massive flat files. Both are
# fixed by the product; the endpoint is overridable per instance.
_DEFAULT_ENDPOINT_URL = "https://files.massive.com"
_BUCKET = "flatfiles"

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

# Local download root, mirroring the cache.py env/default convention: explicit
# arg, else this env var, else a ``flatfiles`` subdir of the shared cache root.
_DOWNLOAD_DIR_ENV = "XPECTRAL_FLATFILES_DIR"
_DEFAULT_DOWNLOAD_DIR = Path.home() / ".cache" / "xpectral" / "flatfiles"

_logger = get_logger("MassiveFlatFiles")

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


class MassiveFlatFiles:
    """Fetch Massive (formerly Polygon.io) S3 flat files into Polars.

    Two layers over the ``flatfiles`` bucket:

    * a low-level S3 client (:meth:`list_objects`, :meth:`download`) that lists
      and downloads raw ``.csv.gz`` objects, skipping files already on disk;
    * a high-level pipeline (:meth:`get_flat_files`) that resolves the per-day
      object keys for a dataset and date range, downloads them, and parses the
      gzipped CSVs into a semi-wide ``pl.LazyFrame`` indexed by
      ``timestamp``/``ticker`` -- mirroring :class:`~xpectral.data.rest_massive.MassiveREST`.

    The flat-files S3 credentials are issued in the Massive Dashboard and are
    separate from ``MASSIVE_API_KEY``.

    Args:
        access_key: S3 access key. Defaults to ``MASSIVE_S3_ACCESS_KEY``.
        secret_key: S3 secret key. Defaults to ``MASSIVE_S3_SECRET_KEY``.
        endpoint_url: S3-compatible endpoint. Defaults to
            ``https://files.massive.com``.
        download_dir: Root for downloaded ``.csv.gz`` files. Defaults to the
            ``XPECTRAL_FLATFILES_DIR`` environment variable, else
            ``~/.cache/xpectral/flatfiles``.
        cache_expire: Time-to-live in seconds for the parsed-frame cache.
            ``None`` (the default) caches indefinitely, which suits the
            immutable historical flat files.
    """

    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
        endpoint_url: str | None = None,
        download_dir: str | os.PathLike | None = None,
        cache_expire: float | None = None,
    ):
        session = boto3.Session(
            aws_access_key_id=access_key or os.getenv("MASSIVE_S3_ACCESS_KEY", ""),
            aws_secret_access_key=secret_key or os.getenv("MASSIVE_S3_SECRET_KEY", ""),
        )
        self._client = session.client(
            "s3",
            endpoint_url=endpoint_url or _DEFAULT_ENDPOINT_URL,
            config=Config(signature_version="s3v4"),
        )
        self._download_dir = _resolve_download_dir(download_dir)

        # Cache the parsed frames via a module-level, ``self``-free helper so the
        # boto3 client never leaks into the cache key. Wrapping here (rather than
        # decorating at module scope) keeps ``cache_expire`` overridable per
        # instance while sharing one on-disk store across instances.
        self._parse = disk_cache(
            "MassiveFlatFiles._parse_flat_files",
            expire=cache_expire,
        )(_parse_flat_files)

    def list_objects(self, prefix: str) -> list[str]:
        """List every object key under ``prefix`` in the flat-files bucket."""
        keys = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=_BUCKET, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

    def download(
        self,
        keys: list[str],
        dest_dir: str | os.PathLike | None = None,
    ) -> list[Path]:
        """Download ``keys`` to ``dest_dir`` and return the local paths present.

        Files already on disk are skipped rather than re-downloaded, and keys
        with no object (e.g. weekends/holidays for a daily dataset) are logged
        and omitted from the result.

        Args:
            keys: Object keys to download.
            dest_dir: Destination root; the key path is preserved beneath it.
                Defaults to the instance ``download_dir``.

        Returns:
            Local paths, one per key that exists locally after the call.
        """
        root = Path(dest_dir) if dest_dir is not None else self._download_dir
        paths = []
        for key in keys:
            path = root / key
            if path.exists():
                paths.append(path)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._client.download_file(_BUCKET, key, str(path))
            except ClientError as error:
                if _is_missing(error):
                    _logger.warning("no object for key, skipping: {}", key)
                    continue
                raise
            _logger.info("downloaded {}", key)
            paths.append(path)
        return paths

    def get_flat_files(
        self,
        dataset: str,
        from_: str | date | datetime,
        to: str | date | datetime,
        prefix: str = _DEFAULT_PREFIX,
        tz: str = "America/New_York",
    ) -> pl.LazyFrame:
        """Download and parse a dataset over a date range into a LazyFrame.

        Resolves one object key per calendar day in the inclusive
        ``from_``..``to`` range, downloads the missing ones, parses each
        gzipped CSV, and concatenates across days. The dataset's epoch-nanosecond
        timestamp column is promoted to a tz-aware ``timestamp`` index column.

        Args:
            dataset: One of ``trades``, ``quotes``, ``minute_aggs``,
                ``day_aggs``.
            from_: Start of the range, inclusive.
            to: End of the range, inclusive.
            prefix: Asset-class prefix. Defaults to ``us_stocks_sip``.
            tz: Time zone the returned ``timestamp`` column is expressed in.

        Returns:
            LazyFrame with ``timestamp``/``ticker`` index columns followed by
            the dataset's remaining columns.
        """
        if dataset not in _DATASETS:
            raise ValueError(
                f"unknown dataset {dataset!r}; expected one of {sorted(_DATASETS)}"
            )
        folder, timestamp_col = _DATASETS[dataset]

        keys = _resolve_keys(prefix, folder, from_, to)
        paths = self.download(keys)
        if not paths:
            raise ValueError(
                f"no flat files found for {prefix}/{folder} in {from_}..{to}"
            )

        # Key the cache on the concrete local paths (which encode the dates)
        # plus the parse parameters -- never on ``self``.
        df = self._parse(tuple(sorted(str(p) for p in paths)), timestamp_col, tz)
        return df.lazy()


# -----------------------------------------------------------------------------
# Private API
# -----------------------------------------------------------------------------


def _parse_flat_files(
    paths: tuple[str, ...],
    timestamp_col: str,
    tz: str,
) -> pl.DataFrame:
    """Read gzipped CSV flat files into one tz-indexed DataFrame.

    Returns a materialized ``pl.DataFrame`` (not a ``LazyFrame``) so it is a
    stable, picklable value for the disk cache; callers ``.lazy()`` at the
    boundary.
    """
    # Polars decompresses ``.csv.gz`` transparently when given the path.
    frames = [pl.read_csv(path) for path in paths]
    df = pl.concat(frames)

    # Flat-file timestamps are epoch nanoseconds in UTC; express them in ``tz``.
    df = df.with_columns(
        pl.col(timestamp_col)
        .cast(pl.Datetime("ns"))
        .dt.replace_time_zone("UTC")
        .dt.convert_time_zone(tz)
        .alias("timestamp")
    )

    # Index columns first; drop the now-redundant raw timestamp column.
    index = ["timestamp", "ticker"]
    rest = [col for col in df.columns if col not in index and col != timestamp_col]
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

    keys = []
    day = start
    while day <= end:
        # e.g. us_stocks_sip/trades_v1/2024/01/2024-01-02.csv.gz
        keys.append(
            f"{prefix}/{folder}/{day.year:04d}/{day.month:02d}/{day.isoformat()}.csv.gz"
        )
        day += timedelta(days=1)
    return keys


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


def _resolve_download_dir(download_dir: str | os.PathLike | None) -> Path:
    """Resolve the download root: explicit arg, else env var, else default."""
    if download_dir is not None:
        return Path(download_dir)
    env = os.getenv(_DOWNLOAD_DIR_ENV)
    return Path(env) if env else _DEFAULT_DOWNLOAD_DIR


def _is_missing(error: ClientError) -> bool:
    """Return whether a ClientError is a missing-object (404) error."""
    code = error.response.get("Error", {}).get("Code")
    return code in {"404", "NoSuchKey"}
