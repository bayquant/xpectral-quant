# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
import gzip
from datetime import date
from datetime import datetime
from pathlib import Path

# Third-party imports
import polars as pl
import pytest
from botocore.exceptions import ClientError

# First-party imports
from xpectral.data import flatfiles_massive
from xpectral.data.flatfiles_massive import MassiveFlatFiles

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

# One synthetic ``day_aggs`` row per day, keyed by trade date. ``window_start``
# is epoch nanoseconds in UTC (2024-01-02 14:30:00Z and 2024-01-03 14:30:00Z).
_DAY_AGGS_HEADER = "close,high,low,open,ticker,transactions,volume,window_start"
_ROWS = {
    date(2024, 1, 2): "187.0,188.0,183.0,184.0,AAPL,100,5000,1704205800000000000",
    date(2024, 1, 3): "185.0,186.0,182.0,184.0,AAPL,120,6000,1704292200000000000",
}

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


class _FakeS3:
    """In-memory stand-in for a boto3 S3 client, counting download calls."""

    def __init__(self, store: dict[str, bytes]):
        self._store = store
        self.download_calls = []

    def download_file(self, Bucket, Key, Filename):
        self.download_calls.append(Key)
        if Key not in self._store:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        Path(Filename).write_bytes(self._store[Key])

    def get_paginator(self, _name):
        return _FakePaginator(self._store)


class _FakePaginator:
    def __init__(self, store: dict[str, bytes]):
        self._store = store

    def paginate(self, Bucket, Prefix):
        contents = [{"Key": key} for key in self._store if key.startswith(Prefix)]
        yield {"Contents": contents}


def _gz(header: str, row: str) -> bytes:
    return gzip.compress(f"{header}\n{row}\n".encode())


def _day_aggs_store() -> dict[str, bytes]:
    return {
        f"us_stocks_sip/day_aggs_v1/{day:%Y/%m}/{day.isoformat()}.csv.gz": _gz(
            _DAY_AGGS_HEADER, row
        )
        for day, row in _ROWS.items()
    }


def _make(tmp_path: Path, store: dict[str, bytes]) -> MassiveFlatFiles:
    ff = MassiveFlatFiles(download_dir=tmp_path / "downloads")
    ff._s3._client = _FakeS3(store)
    return ff


# --- object-key / cache-path resolution ---------------------------------------


def test_parquet_path_is_hive_partitioned():
    path = flatfiles_massive._parquet_path(
        Path("/cache"), "us_stocks_sip", "trades_v1", date(2024, 1, 2)
    )
    assert path == Path(
        "/cache/us_stocks_sip/trades_v1/year=2024/month=01/2024-01-02.parquet"
    )


# --- high-level pipeline -----------------------------------------------------


def test_get_flat_files_concats_and_reuses_downloads(tmp_path):
    store = _day_aggs_store()
    ff = _make(tmp_path, store)

    lf = ff.get_flat_files("day_aggs", "2024-01-02", "2024-01-03")
    assert isinstance(lf, pl.LazyFrame)
    df = lf.collect()

    assert df.height == 2  # concatenated across two days
    assert df.columns[0] == "ticker"
    assert df.get_column("window_start").dt.day().to_list() == [2, 3]
    assert len(ff._s3._client.download_calls) == 2

    # Default reuses the local parquet cache; no re-download.
    df2 = ff.get_flat_files("day_aggs", "2024-01-02", "2024-01-03").collect()
    assert df2.equals(df)
    assert len(ff._s3._client.download_calls) == 2


def test_get_flat_files_caches_as_parquet_only(tmp_path):
    store = _day_aggs_store()
    ff = _make(tmp_path, store)

    ff.get_flat_files("day_aggs", "2024-01-02", "2024-01-02")

    files = list((tmp_path / "downloads").rglob("*"))
    suffixes = {f.suffix for f in files if f.is_file()}
    assert suffixes == {".parquet"}  # no .csv.gz left on disk

    cached = tmp_path / "downloads" / "us_stocks_sip" / "day_aggs_v1"
    assert (cached / "year=2024" / "month=01" / "2024-01-02.parquet").exists()


def test_get_flat_files_column_dtypes_and_tz_conversion(tmp_path):
    store = _day_aggs_store()
    ff = _make(tmp_path, store)

    df = ff.get_flat_files("day_aggs", "2024-01-02", "2024-01-02").collect()

    # tz-aware nanosecond timestamp, converted from 14:30:00Z to 09:30 New York.
    assert df.schema["window_start"] == pl.Datetime("ns", "America/New_York")
    ts = df.get_column("window_start")[0]
    assert (ts.hour, ts.minute) == (9, 30)
    assert str(ts.tzinfo) == "America/New_York"

    # Documented dtypes applied: transactions is integer, volume/OHLC are float.
    assert df.schema["transactions"] == pl.Int64
    assert df.schema["volume"] == pl.Float64
    assert df.schema["close"] == pl.Float64


def test_get_flat_files_reconciles_dtype_drift_across_days(tmp_path):
    # ``volume`` is an integer on one day and fractional the next; each day is
    # cast to the documented (float) dtype at write time, so the two cached
    # parquet files never disagree and can be scanned together in one pass.
    store = {
        "us_stocks_sip/day_aggs_v1/2024/01/2024-01-02.csv.gz": _gz(
            _DAY_AGGS_HEADER,
            "187.0,188.0,183.0,184.0,AAPL,100,5000,1704205800000000000",
        ),
        "us_stocks_sip/day_aggs_v1/2024/01/2024-01-03.csv.gz": _gz(
            _DAY_AGGS_HEADER,
            "185.0,186.0,182.0,184.0,AAPL,120,6000.5,1704292200000000000",
        ),
    }
    ff = _make(tmp_path, store)

    df = ff.get_flat_files("day_aggs", "2024-01-02", "2024-01-03").collect()
    assert df.height == 2
    assert df.schema["volume"] == pl.Float64
    assert df.get_column("volume").to_list() == [5000.0, 6000.5]


def test_get_flat_files_overwrite_refetches(tmp_path):
    store = _day_aggs_store()
    ff = _make(tmp_path, store)

    ff.get_flat_files("day_aggs", "2024-01-02", "2024-01-03")
    assert len(ff._s3._client.download_calls) == 2

    # overwrite=True forces a fresh download of the same days.
    ff.get_flat_files("day_aggs", "2024-01-02", "2024-01-03", overwrite=True)
    assert len(ff._s3._client.download_calls) == 4


def test_get_flat_files_offline_uses_cache(tmp_path):
    store = _day_aggs_store()

    # Online client populates the local cache.
    online = _make(tmp_path, store)
    online.get_flat_files("day_aggs", "2024-01-02", "2024-01-03")
    assert len(online._s3._client.download_calls) == 2

    # Offline client over the same download_dir reuses those files, no network.
    offline = MassiveFlatFiles(download_dir=tmp_path / "downloads", offline=True)
    offline._s3._client = _FakeS3(store)
    df = offline.get_flat_files("day_aggs", "2024-01-02", "2024-01-03").collect()
    assert df.height == 2
    assert offline._s3._client.download_calls == []


def test_get_flat_files_rejects_unknown_dataset(tmp_path):
    ff = _make(tmp_path, {})
    with pytest.raises(ValueError):
        ff.get_flat_files("ticks", "2024-01-02", "2024-01-03")


def test_get_flat_files_raises_when_nothing_found(tmp_path):
    ff = _make(tmp_path, {})  # empty store -> all keys 404
    with pytest.raises(ValueError):
        ff.get_flat_files("day_aggs", "2024-01-06", "2024-01-07")


def test_get_flat_files_rejects_datetime(tmp_path):
    # ``datetime`` is a ``date`` subclass, so it can't be told apart from a
    # calendar date by type alone; a bare datetime's ``str()`` includes a time
    # component, which ``date.fromisoformat`` rejects.
    ff = _make(tmp_path, {})
    with pytest.raises(ValueError):
        ff.get_flat_files("day_aggs", datetime(2024, 1, 2), datetime(2024, 1, 3))
