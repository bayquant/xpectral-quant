# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
from datetime import date
from datetime import datetime
from pathlib import Path
import gzip

# Other imports
import polars as pl
import pytest
from botocore.exceptions import ClientError

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


def _make(tmp_path: Path, store: dict[str, bytes], monkeypatch) -> MassiveFlatFiles:
    # Keep the parsed-frame cache off the real ~/.cache during tests.
    monkeypatch.setenv("XPECTRAL_CACHE_DIR", str(tmp_path / "cache"))
    ff = MassiveFlatFiles(download_dir=tmp_path / "downloads")
    ff._client = _FakeS3(store)
    return ff


# --- object-key resolution ---------------------------------------------------


def test_resolve_keys_padding_and_inclusive_range():
    keys = flatfiles_massive._resolve_keys(
        "us_stocks_sip", "trades_v1", "2024-01-02", "2024-01-04"
    )
    assert keys == [
        "us_stocks_sip/trades_v1/2024/01/2024-01-02.csv.gz",
        "us_stocks_sip/trades_v1/2024/01/2024-01-03.csv.gz",
        "us_stocks_sip/trades_v1/2024/01/2024-01-04.csv.gz",
    ]


def test_resolve_keys_accepts_date_and_datetime_and_crosses_month():
    keys = flatfiles_massive._resolve_keys(
        "global_crypto",
        "minute_aggs_v1",
        date(2024, 1, 31),
        datetime(2024, 2, 1, 16, 0),
    )
    assert keys == [
        "global_crypto/minute_aggs_v1/2024/01/2024-01-31.csv.gz",
        "global_crypto/minute_aggs_v1/2024/02/2024-02-01.csv.gz",
    ]


def test_resolve_keys_rejects_reversed_range():
    with pytest.raises(ValueError):
        flatfiles_massive._resolve_keys(
            "us_stocks_sip", "trades_v1", "2024-01-04", "2024-01-02"
        )


# --- CSV.gz parsing ----------------------------------------------------------


def test_parse_flat_files_dtypes_tz_and_column_order(tmp_path):
    path = tmp_path / "2024-01-02.csv.gz"
    path.write_bytes(_gz(_DAY_AGGS_HEADER, _ROWS[date(2024, 1, 2)]))

    df = flatfiles_massive._parse_flat_files(
        (str(path),), "window_start", "America/New_York"
    )

    # Index columns first, raw timestamp column dropped.
    assert df.columns[:2] == ["timestamp", "ticker"]
    assert "window_start" not in df.columns
    # tz-aware nanosecond timestamp, converted from 14:30:00Z to 09:30 New York.
    assert df.schema["timestamp"] == pl.Datetime("ns", "America/New_York")
    ts = df.get_column("timestamp")[0]
    assert (ts.hour, ts.minute) == (9, 30)
    assert str(ts.tzinfo) == "America/New_York"


# --- download layer ----------------------------------------------------------


def test_download_skips_existing_and_missing(tmp_path, monkeypatch):
    store = _day_aggs_store()
    ff = _make(tmp_path, store, monkeypatch)
    keys = list(store)

    # Pre-place the first file so only the second is fetched.
    first = tmp_path / "downloads" / keys[0]
    first.parent.mkdir(parents=True)
    first.write_bytes(store[keys[0]])

    missing_key = "us_stocks_sip/day_aggs_v1/2024/01/2024-01-06.csv.gz"  # weekend
    paths = ff.download(keys + [missing_key])

    assert ff._client.download_calls == [keys[1], missing_key]  # not keys[0]
    assert {p.name for p in paths} == {"2024-01-02.csv.gz", "2024-01-03.csv.gz"}


def test_list_objects(tmp_path, monkeypatch):
    store = _day_aggs_store()
    ff = _make(tmp_path, store, monkeypatch)
    keys = ff.list_objects("us_stocks_sip/day_aggs_v1/2024/01")
    assert sorted(keys) == sorted(store)


# --- high-level pipeline + caching ------------------------------------------


def test_get_flat_files_concats_and_caches(tmp_path, monkeypatch):
    store = _day_aggs_store()

    # Count real parse executions to prove the cache short-circuits the second call.
    parse_calls = []
    real_parse = flatfiles_massive._parse_flat_files

    def counting_parse(*args):
        parse_calls.append(1)
        return real_parse(*args)

    monkeypatch.setattr(flatfiles_massive, "_parse_flat_files", counting_parse)

    ff = _make(tmp_path, store, monkeypatch)

    lf = ff.get_flat_files("day_aggs", "2024-01-02", "2024-01-03")
    assert isinstance(lf, pl.LazyFrame)
    df = lf.collect()

    assert df.height == 2  # concatenated across two days
    assert df.columns[:2] == ["timestamp", "ticker"]
    assert df.get_column("timestamp").dt.day().to_list() == [2, 3]
    assert len(ff._client.download_calls) == 2
    assert len(parse_calls) == 1

    # Second call: files already local and parse result cached -> no new work.
    df2 = ff.get_flat_files("day_aggs", "2024-01-02", "2024-01-03").collect()
    assert df2.equals(df)
    assert len(ff._client.download_calls) == 2  # nothing re-downloaded
    assert len(parse_calls) == 1  # parse not re-executed


def test_get_flat_files_rejects_unknown_dataset(tmp_path, monkeypatch):
    ff = _make(tmp_path, {}, monkeypatch)
    with pytest.raises(ValueError):
        ff.get_flat_files("ticks", "2024-01-02", "2024-01-03")


def test_get_flat_files_raises_when_nothing_found(tmp_path, monkeypatch):
    ff = _make(tmp_path, {}, monkeypatch)  # empty store -> all keys 404
    with pytest.raises(ValueError):
        ff.get_flat_files("day_aggs", "2024-01-06", "2024-01-07")
