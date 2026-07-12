# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------

# Standard library imports
from pathlib import Path
import logging
import os

# Other imports
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

# -----------------------------------------------------------------------------
# Globals and constants
# -----------------------------------------------------------------------------

__all__ = ["S3Downloader"]

_logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# General API
# -----------------------------------------------------------------------------


class S3Downloader:
    """Download objects from an S3-compatible bucket to local disk.

    A thin read-only wrapper over a boto3 S3 client: it lists object keys under
    a prefix and downloads them to a local root, preserving each key's path,
    skipping files already on disk, and tolerating missing objects. It knows
    nothing about the data it moves -- object-key layout, parsing, and caching
    belong to the caller.

    Args:
        bucket: Name of the S3 bucket to read from.
        dest_dir: Default local directory downloaded objects are written under,
            preserving each key's path. Overridable per :meth:`download` call.
        endpoint_url: S3-compatible endpoint. ``None`` uses the AWS default.
        access_key: Access key id. ``None`` falls back to boto3's own
            credential resolution.
        secret_key: Secret access key. ``None`` falls back to boto3's own
            credential resolution.
        offline: When True, never contact the network: :meth:`download` returns
            only keys already present under ``dest_dir`` and skips the rest.
    """

    def __init__(
        self,
        bucket: str,
        dest_dir: str | os.PathLike,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        offline: bool = False,
    ):
        # boto3 resolves credentials lazily -- building the session and client
        # requires none; they are only needed on an actual API call. An offline
        # client never makes one, so it works with no credentials or account.
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self._client = session.client(
            "s3",
            endpoint_url=endpoint_url,
            config=Config(signature_version="s3v4"),
        )
        self._bucket = bucket
        self._dest_dir = Path(dest_dir)
        self._offline = offline

    def list_keys(self, prefix: str) -> list[str]:
        """List every object key under ``prefix`` in the bucket."""
        keys = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys

    def download(
        self,
        keys: list[str],
        dest_dir: str | os.PathLike | None = None,
        overwrite: bool = False,
    ) -> list[Path]:
        """Download ``keys`` to ``dest_dir`` and return the local paths present.

        Files already on disk are reused rather than re-downloaded, and keys with
        no object (a 404/403) are logged and omitted from the result. When the
        client is ``offline``, no network call is made: only keys already present
        locally are returned and ``overwrite`` is ignored.

        Args:
            keys: Object keys to download.
            dest_dir: Destination directory; the key path is preserved beneath
                it. Defaults to the instance ``dest_dir``.
            overwrite: When ``True``, re-download and replace files that already
                exist locally instead of reusing them (ignored when offline).

        Returns:
            Local paths, one per key that exists locally after the call.
        """
        root = Path(dest_dir) if dest_dir is not None else self._dest_dir
        paths = []
        for key in keys:
            path = root / key
            if path.exists() and (self._offline or not overwrite):
                paths.append(path)
                continue
            if self._offline:
                _logger.warning("offline, not cached; skipping: %s", key)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._client.download_file(self._bucket, key, str(path))
            except ClientError as error:
                if _is_missing(error):
                    _logger.warning("no object for key, skipping: %s", key)
                    continue
                raise
            _logger.info("downloaded %s", key)
            paths.append(path)
        return paths


# -----------------------------------------------------------------------------
# Private API
# -----------------------------------------------------------------------------


def _is_missing(error: ClientError) -> bool:
    """Return whether a ClientError means the object is absent.

    S3-compatible buckets that withhold ``s3:ListBucket`` from download-only
    credentials hide object existence: a missing key comes back as ``403`` /
    ``AccessDenied`` rather than ``404`` / ``NoSuchKey``. Treat both as "not
    there" so gaps (weekends, holidays, unpublished days) are skipped. Trade-off:
    genuinely bad credentials also land here, surfacing downstream as an empty
    result instead of a raised auth error.
    """
    code = error.response.get("Error", {}).get("Code")
    return code in {"404", "NoSuchKey", "403", "AccessDenied"}
