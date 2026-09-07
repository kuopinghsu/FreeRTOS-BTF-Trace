"""Hardened ZIP-container reader — one safe path for every archive BTFViewer opens.

The semantic layer on top of this is the ``.btfw`` package reader
(:mod:`btf_viewer_pkg.workspace`), which covers both portable workspaces and
shareable demo tours. Lockstep with ``web/src/utils/zipContainer.js``.

Guarantees for any archive opened through here:

* member names are plain relative POSIX paths — no ``..``, no absolute / drive /
  UNC roots, no backslashes or NUL (unsafe names are skipped with a warning);
* the entry count is capped (``CONTAINER_MAX_ENTRIES``);
* the total decompressed size is capped (``CONTAINER_MAX_UNCOMPRESSED_BYTES``);
* entries whose decompressed / stored ratio is implausible are refused as
  compression bombs;
* CRCs are verified;
* nothing in the archive is executed and nothing is fetched.
"""
from __future__ import annotations

import io
import os
import zipfile
from typing import Dict, List, Union

# Shared limits. A ``.btfw`` package is small; these leave generous headroom.
CONTAINER_MAX_ENTRIES = 4096
CONTAINER_MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
CONTAINER_MAX_COMPRESSION_RATIO = 250
CONTAINER_BOMB_MIN_SIZE = 64 * 1024

_Source = Union[str, bytes, bytearray]


def is_safe_member(name: str) -> bool:
    """True if *name* is a plain relative POSIX path with no traversal / root.

    Container members always use ``/`` separators; anything else is rejected.
    """
    n = str(name or "")
    if not n or n != n.strip():
        return False
    if "\\" in n or "\x00" in n:
        return False
    if n.startswith("/") or n.startswith("~"):
        return False
    # Windows drive / UNC (``C:\\...``).
    if len(n) >= 2 and n[1] == ":":
        return False
    parts = n.split("/")
    for i, p in enumerate(parts):
        if p in (".", ".."):
            return False
        if p == "" and i != len(parts) - 1:
            return False  # empty segment except a single trailing "" (dir entry)
    return True


def _is_zip_source(source: _Source) -> bool:
    if isinstance(source, (bytes, bytearray)):
        return zipfile.is_zipfile(io.BytesIO(bytes(source)))
    return zipfile.is_zipfile(source)


def _as_zipfile(source: _Source) -> zipfile.ZipFile:
    if isinstance(source, (bytes, bytearray)):
        return zipfile.ZipFile(io.BytesIO(bytes(source)), "r")
    return zipfile.ZipFile(source, "r")


def validate_zip_container(
    zf: zipfile.ZipFile,
    *,
    max_entries: int = CONTAINER_MAX_ENTRIES,
    max_uncompressed: int = CONTAINER_MAX_UNCOMPRESSED_BYTES,
    max_ratio: int = CONTAINER_MAX_COMPRESSION_RATIO,
    bomb_min_size: int = CONTAINER_BOMB_MIN_SIZE,
) -> List[str]:
    """Enforce the container limits. Returns warnings for skipped unsafe names."""
    warnings: List[str] = []
    infos = zf.infolist()
    if len(infos) > max_entries:
        raise ValueError(
            f"archive has too many entries ({len(infos)} > {max_entries})")
    total = 0
    for zi in infos:
        if zi.is_dir():
            continue
        total += zi.file_size
        if total > max_uncompressed:
            raise ValueError("archive decompressed size exceeds the limit")
        if (zi.file_size > bomb_min_size and zi.compress_size > 0
                and zi.file_size / zi.compress_size > max_ratio):
            raise ValueError(
                f"archive entry {zi.filename!r} looks like a compression bomb")
        if not is_safe_member(zi.filename):
            warnings.append(f"skipped unsafe member name: {zi.filename!r}")
    bad = zf.testzip()
    if bad is not None:
        raise ValueError(f"archive entry {bad!r} is corrupt")
    return warnings


def read_zip_container(
    source: _Source,
    *,
    container_desc: str = "ZIP",
    max_entries: int = CONTAINER_MAX_ENTRIES,
    max_uncompressed: int = CONTAINER_MAX_UNCOMPRESSED_BYTES,
    max_ratio: int = CONTAINER_MAX_COMPRESSION_RATIO,
    bomb_min_size: int = CONTAINER_BOMB_MIN_SIZE,
) -> Dict[str, object]:
    """Open *source* (a path or raw bytes) as a hardened ZIP container.

    Returns ``{"members": {name: bytes}, "warnings": [...]}`` holding only the
    safe-named, non-directory members. Raises ``ValueError`` for a non-ZIP input
    or any limit breach.
    """
    if not _is_zip_source(source):
        raise ValueError(f"not a {container_desc} container")
    members: Dict[str, bytes] = {}
    with _as_zipfile(source) as zf:
        warnings = validate_zip_container(
            zf, max_entries=max_entries, max_uncompressed=max_uncompressed,
            max_ratio=max_ratio, bomb_min_size=bomb_min_size)
        for zi in zf.infolist():
            if zi.is_dir() or not is_safe_member(zi.filename):
                continue
            members[zi.filename] = zf.read(zi)
    return {"members": members, "warnings": warnings}


def safe_extract_all(
    source: _Source,
    dest_dir: str,
    *,
    container_desc: str = "ZIP",
    max_entries: int = CONTAINER_MAX_ENTRIES,
    max_uncompressed: int = CONTAINER_MAX_UNCOMPRESSED_BYTES,
) -> List[str]:
    """Extract every safe member of *source* under *dest_dir*. Returns the paths.

    The resolved target of each member is re-checked to stay under *dest_dir*
    (defence in depth on top of :func:`is_safe_member`).
    """
    container = read_zip_container(
        source, container_desc=container_desc,
        max_entries=max_entries, max_uncompressed=max_uncompressed)
    dest_root = os.path.realpath(dest_dir)
    os.makedirs(dest_root, exist_ok=True)
    written: List[str] = []
    for name, data in container["members"].items():
        target = os.path.realpath(os.path.join(dest_root, name))
        if target != dest_root and not target.startswith(dest_root + os.sep):
            raise ValueError(
                f"refusing to extract outside destination: {name!r}")
        os.makedirs(os.path.dirname(target) or dest_root, exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(data)
        written.append(target)
    return written
