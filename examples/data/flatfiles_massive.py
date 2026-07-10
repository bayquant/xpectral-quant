# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
import os
import tempfile
import time
from pathlib import Path

# Other imports
from xpectral.data import MassiveFlatFiles

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

# Smallest dataset (one row per ticker per day, whole US market), over two
# trading days, so the example downloads only a few hundred KB.
_DATASET = "day_aggs"
_FROM = "2024-01-02"
_TO = "2024-01-03"

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


def main() -> None:
    """Fetch Massive flat files into Polars, then prove the on-disk cache.

    Credentials are read from the environment, never hardcoded. Set them first::

        export MASSIVE_S3_ACCESS_KEY=...
        export MASSIVE_S3_SECRET_KEY=...

    Both the parsed-frame cache and the raw downloads go to a throwaway temp
    directory so nothing touches ``~/.cache`` or the repo.
    """
    if not (os.getenv("MASSIVE_S3_ACCESS_KEY") and os.getenv("MASSIVE_S3_SECRET_KEY")):
        raise SystemExit(
            "set MASSIVE_S3_ACCESS_KEY and MASSIVE_S3_SECRET_KEY (from the "
            "Massive Dashboard) before running this example"
        )

    tmp = Path(tempfile.mkdtemp(prefix="massive-flatfiles-example-"))
    os.environ["XPECTRAL_CACHE_DIR"] = str(tmp / "cache")

    # access_key/secret default to the MASSIVE_S3_* env vars checked above.
    flat_files = MassiveFlatFiles(download_dir=tmp / "downloads")

    # First call: downloads the .csv.gz files and parses them (a cache miss).
    print(f"fetching {_DATASET} {_FROM}..{_TO} ...")
    t0 = time.perf_counter()
    frame = flat_files.get_flat_files(_DATASET, _FROM, _TO).collect()
    miss = time.perf_counter() - t0

    print(f"\nfetch+parse took {miss:.2f}s")
    print("shape:", frame.shape)
    print("schema:", frame.schema)
    print("\nfirst rows:")
    print(frame.sort("ticker", "timestamp").head(4))

    # Second identical call: files already local and the parsed frame is cached,
    # so nothing is re-downloaded or re-parsed.
    t1 = time.perf_counter()
    again = flat_files.get_flat_files(_DATASET, _FROM, _TO).collect()
    hit = time.perf_counter() - t1
    print(f"\nsecond call took {hit:.4f}s (cache hit); equal={again.equals(frame)}")

    print("\ndownloaded files:")
    for path in sorted((tmp / "downloads").rglob("*.csv.gz")):
        print(f"  {path.relative_to(tmp)}  ({path.stat().st_size:,} bytes)")


# -----------------------------------------------------------------------------
# Private API
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    main()
