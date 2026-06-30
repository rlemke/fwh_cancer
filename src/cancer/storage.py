"""Backend-aware paths for the cancer domain's cache + outputs.

On the fleet (``FW_STORAGE=s3`` / ``FW_DATA_ROOT=s3://afl-cache``) cached
expression matrices, evidence tables and rendered HTML land in the shared MinIO
object store under ``$FW_DATA_ROOT/cache/cancer/...``; locally they fall back to
a host path. A thin wrapper over ``facetwork.runtime.storage`` (the shape
census-us / health use), so terminal use and fleet runs share one layout.
"""
from __future__ import annotations

import io
import os
import tempfile

from facetwork.config import get_output_base
from facetwork.runtime import storage as _fws


def is_remote(path: str) -> bool:
    return "://" in (path or "")


def data_root() -> str:
    return os.environ.get("FW_DATA_ROOT") or get_output_base()


def join(*parts: str) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return ""
    base = parts[0].rstrip("/")
    rest = [p.strip("/") for p in parts[1:]]
    return "/".join([base, *[p for p in rest if p]])


def cache_root() -> str:
    """Cached intermediates (expression matrices, evidence tables) live here."""
    r = data_root()
    return join(r, "cache", "cancer") if is_remote(r) else join(r, "cancer-cache")


def maps_root() -> str:
    """Rendered evidence-table HTML bundles: <root>/cache/cancer/maps/<name>."""
    r = data_root()
    return join(r, "cache", "cancer", "maps") if is_remote(r) else join(r, "cancer-maps")


def exists(path: str) -> bool:
    return _fws.get_storage_backend(path).exists(path)


def read_bytes(path: str) -> bytes:
    if not is_remote(path):
        with open(path, "rb") as f:
            return f.read()
    local = _fws.localize(path)
    with open(local, "rb") as f:
        return f.read()


def write_bytes(path: str, data: bytes) -> None:
    if not is_remote(path):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return
    fd, tmp = tempfile.mkstemp(suffix="_" + os.path.basename(path))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        with open(tmp, "rb") as src, _fws.get_storage_backend(path).open(path, "wb") as dst:
            dst.write(src.read())
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def write_text(path: str, text: str) -> None:
    write_bytes(path, text.encode("utf-8"))


def read_parquet(path: str):
    import pandas as pd
    return pd.read_parquet(io.BytesIO(read_bytes(path)))


def write_parquet(path: str, df) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=True)
    write_bytes(path, buf.getvalue())
