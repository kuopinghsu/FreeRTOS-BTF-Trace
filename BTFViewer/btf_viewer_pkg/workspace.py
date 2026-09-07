"""Portable Workspace (``.btfw``) — versioned, ZIP-compatible container.

Lockstep with ``web/src/utils/workspace.js``.

A ``.btfw`` saves the complete investigation state — the trace, the view
state, the deterministic analysis (health + findings), the investigation
notebook, and optionally a rendered report — in one file that stays
inspectable with any ZIP tool and does not depend on an installed BTFViewer
or any online service.

Layout::

    manifest.json
    trace/source.btf              (only when the trace is embedded)
    state/view.json               (portable session: cursors, marks, viewport…)
    analysis/health.json          (Trace Health Check result)
    analysis/findings.json        (Investigation Findings)
    investigation/bookmarks.json  (Investigation notebook)
    reports/report.html           (optional)
    attachments/<name>            (optional)

Security: extraction rejects absolute paths and ``..`` segments, caps entry
count and decompressed size, guards against compression bombs, never executes
workspace content, and never fetches remote resources. Unknown manifest and
member fields are preserved for forward compatibility; older schemas are
migrated, newer ones open read-only.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from .investigation_notebook import load_investigation
from .zip_container import (
    CONTAINER_MAX_COMPRESSION_RATIO,
    CONTAINER_MAX_ENTRIES,
    CONTAINER_MAX_UNCOMPRESSED_BYTES,
    is_safe_member,
    read_zip_container,
    safe_extract_all,
)

WORKSPACE_SCHEMA_PREFIX = "btf-viewer-workspace/"
WORKSPACE_VERSION = 1
WORKSPACE_SCHEMA = f"{WORKSPACE_SCHEMA_PREFIX}{WORKSPACE_VERSION}"
WORKSPACE_EXT = ".btfw"

MANIFEST = "manifest.json"
TRACE_MEMBER = "trace/source.btf"
STATE_VIEW = "state/view.json"
ANALYSIS_HEALTH = "analysis/health.json"
ANALYSIS_FINDINGS = "analysis/findings.json"
INVESTIGATION_BOOKMARKS = "investigation/bookmarks.json"
INVESTIGATION_AI_CASE = "investigation/ai_case.json"
REPORT_HTML = "reports/report.html"
ATTACHMENTS_PREFIX = "attachments/"

_KNOWN_MEMBERS = (
    MANIFEST, TRACE_MEMBER, STATE_VIEW, ANALYSIS_HEALTH,
    ANALYSIS_FINDINGS, INVESTIGATION_BOOKMARKS, INVESTIGATION_AI_CASE, REPORT_HTML,
)

# Extraction limits — the archive-level caps come from the shared reader
# (:mod:`btf_viewer_pkg.zip_container`); only the manifest cap is workspace-only.
MAX_ENTRIES = CONTAINER_MAX_ENTRIES
MAX_UNCOMPRESSED_BYTES = CONTAINER_MAX_UNCOMPRESSED_BYTES
MAX_COMPRESSION_RATIO = CONTAINER_MAX_COMPRESSION_RATIO
MANIFEST_MAX_BYTES = 1 * 1024 * 1024

_CONTAINER_DESC = ".btfw / ZIP"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def workspace_sha256(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def now_iso(when: Optional[datetime.datetime] = None) -> str:
    dt = when or datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


def _dumps(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sanitize_attachment_name(name: str) -> str:
    base = str(name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    base = base.lstrip(".") or "attachment"
    return "".join(c for c in base if c.isalnum() or c in "-._ ()").strip() or "attachment"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def build_manifest(
    *,
    btfviewer_version: str = "",
    trace_name: str = "",
    trace_size: int = 0,
    trace_sha256: str = "",
    trace_embedded: bool = True,
    trace_ref: str = "",
    analysis_settings: Optional[Dict[str, Any]] = None,
    rule_set_version: str = "",
    locale: str = "",
    report: Optional[Dict[str, Any]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    contents: Optional[List[str]] = None,
    created: Optional[str] = None,
    modified: Optional[str] = None,
) -> Dict[str, Any]:
    stamp = now_iso()
    return {
        "schema": WORKSPACE_SCHEMA,
        "btfviewer_version": str(btfviewer_version or ""),
        "created": str(created or stamp),
        "modified": str(modified or stamp),
        "trace": {
            "name": str(trace_name or ""),
            "size": int(trace_size or 0),
            "sha256": str(trace_sha256 or ""),
            "embedded": bool(trace_embedded),
            "ref": "" if trace_embedded else str(trace_ref or ""),
        },
        "analysis": {
            "settings": dict(analysis_settings or {}),
            "rule_set_version": str(rule_set_version or ""),
        },
        "locale": str(locale or ""),
        "report": dict(report) if isinstance(report, dict) else None,
        "attachments": list(attachments or []),
        "contents": sorted(set(contents or [])),
    }


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------
def _schema_version(schema: str) -> Optional[int]:
    s = str(schema or "")
    if not s.startswith(WORKSPACE_SCHEMA_PREFIX):
        return None
    try:
        return int(s[len(WORKSPACE_SCHEMA_PREFIX):])
    except ValueError:
        return None


# {from_version: fn(manifest) -> manifest}. Each step bumps by one.
_MIGRATIONS: Dict[int, Any] = {}


def migrate_manifest(manifest: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Return ``(manifest, changed)`` migrated up to ``WORKSPACE_VERSION``.

    Unknown/newer schemas are returned untouched (callers open them read-only).
    """
    out = dict(manifest or {})
    ver = _schema_version(out.get("schema"))
    if ver is None or ver >= WORKSPACE_VERSION:
        return out, False
    changed = False
    while ver < WORKSPACE_VERSION and ver in _MIGRATIONS:
        out = _MIGRATIONS[ver](dict(out))
        ver += 1
        out["schema"] = f"{WORKSPACE_SCHEMA_PREFIX}{ver}"
        changed = True
    if ver < WORKSPACE_VERSION:
        # No migration path; stamp current and let the caller validate.
        out["schema"] = WORKSPACE_SCHEMA
        changed = True
    return out, changed


# ---------------------------------------------------------------------------
# Save (atomic)
# ---------------------------------------------------------------------------
def save_workspace(
    path: str,
    *,
    trace_bytes: Optional[bytes] = None,
    trace_ref: str = "",
    trace_name: str = "",
    trace_sha256: str = "",
    trace_size: Optional[int] = None,
    embed_trace: bool = True,
    view_state: Optional[Dict[str, Any]] = None,
    health: Optional[Dict[str, Any]] = None,
    findings: Optional[List[Dict[str, Any]]] = None,
    investigation: Optional[Dict[str, Any]] = None,
    ai_case: Optional[Dict[str, Any]] = None,
    report_html: Optional[str] = None,
    attachments: Optional[Dict[str, bytes]] = None,
    analysis_settings: Optional[Dict[str, Any]] = None,
    rule_set_version: str = "",
    locale: str = "",
    btfviewer_version: str = "",
    created: Optional[str] = None,
    modified: Optional[str] = None,
) -> Dict[str, Any]:
    """Write a ``.btfw`` to *path* atomically. Returns the manifest written.

    Pass ``created`` (from an earlier manifest) to preserve the original
    creation time across re-saves.
    """
    embedded = bool(embed_trace and trace_bytes is not None)
    if embedded:
        trace_size = len(trace_bytes)
        if not trace_sha256:
            trace_sha256 = workspace_sha256(trace_bytes)
    else:
        trace_size = int(trace_size or 0)

    att_items: List[Tuple[str, bytes]] = []
    att_manifest: List[Dict[str, Any]] = []
    seen_att: set = set()
    for raw_name, blob in (attachments or {}).items():
        nm = _sanitize_attachment_name(raw_name)
        while nm in seen_att:
            nm = "_" + nm
        seen_att.add(nm)
        data = blob if isinstance(blob, (bytes, bytearray)) else str(blob).encode("utf-8")
        att_items.append((ATTACHMENTS_PREFIX + nm, bytes(data)))
        att_manifest.append({"name": nm, "size": len(data),
                             "sha256": workspace_sha256(bytes(data))})

    contents = [STATE_VIEW] if view_state is not None else []
    if health is not None:
        contents.append(ANALYSIS_HEALTH)
    if findings is not None:
        contents.append(ANALYSIS_FINDINGS)
    if investigation is not None:
        contents.append(INVESTIGATION_BOOKMARKS)
    if ai_case is not None:
        contents.append(INVESTIGATION_AI_CASE)
    if report_html is not None:
        contents.append(REPORT_HTML)
    if embedded:
        contents.append(TRACE_MEMBER)
    contents.extend(nm for nm, _ in att_items)

    report_meta = None
    if report_html is not None:
        rb = report_html.encode("utf-8")
        report_meta = {"path": REPORT_HTML, "size": len(rb),
                       "sha256": workspace_sha256(rb)}

    manifest = build_manifest(
        btfviewer_version=btfviewer_version,
        trace_name=trace_name or (os.path.basename(trace_ref) if trace_ref else ""),
        trace_size=trace_size,
        trace_sha256=trace_sha256,
        trace_embedded=embedded,
        trace_ref=trace_ref,
        analysis_settings=analysis_settings,
        rule_set_version=rule_set_version,
        locale=locale,
        report=report_meta,
        attachments=att_manifest,
        contents=contents,
        created=created,
        modified=modified,
    )

    members: List[Tuple[str, bytes]] = [(MANIFEST, _dumps(manifest))]
    if embedded:
        members.append((TRACE_MEMBER, bytes(trace_bytes)))
    if view_state is not None:
        members.append((STATE_VIEW, _dumps(view_state)))
    if health is not None:
        members.append((ANALYSIS_HEALTH, _dumps(health)))
    if findings is not None:
        members.append((ANALYSIS_FINDINGS, _dumps(list(findings))))
    if investigation is not None:
        members.append((INVESTIGATION_BOOKMARKS, _dumps(load_investigation(investigation))))
    if ai_case is not None:
        members.append((INVESTIGATION_AI_CASE, _dumps(ai_case)))
    if report_html is not None:
        members.append((REPORT_HTML, report_html.encode("utf-8")))
    members.extend(att_items)

    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Fixed timestamp keeps saves reproducible.
            for name, data in members:
                zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                zf.writestr(zi, data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return manifest


# ---------------------------------------------------------------------------
# Open (hardened, read-only, in-memory)
# ---------------------------------------------------------------------------
def _read_json_member(members: Dict[str, bytes], name: str) -> Any:
    blob = members.get(name)
    if blob is None:
        return None
    try:
        return json.loads(blob.decode("utf-8"))
    except (ValueError, KeyError):
        return None


def read_manifest(path: str) -> Dict[str, Any]:
    """Read + migrate just the manifest (fast inspection)."""
    if not zipfile.is_zipfile(path):
        raise ValueError("not a .btfw / ZIP container")
    with zipfile.ZipFile(path, "r") as zf:
        if MANIFEST not in zf.namelist():
            raise ValueError("workspace has no manifest.json")
        info = zf.getinfo(MANIFEST)
        if info.file_size > MANIFEST_MAX_BYTES:
            raise ValueError("manifest.json is implausibly large")
        raw = json.loads(zf.read(MANIFEST).decode("utf-8"))
    manifest, _ = migrate_manifest(raw)
    return manifest


def open_workspace(
    path: str,
    *,
    max_entries: int = MAX_ENTRIES,
    max_uncompressed: int = MAX_UNCOMPRESSED_BYTES,
    load_report: bool = True,
) -> Dict[str, Any]:
    """Open a ``.btfw`` safely. Reads members into memory; never writes or execs.

    The archive is read through the shared hardened container reader
    (:func:`btf_viewer_pkg.zip_container.read_zip_container`); everything below is
    ``.btfw`` interpretation on top of the safe member map it returns.
    """
    container = read_zip_container(
        path, container_desc=_CONTAINER_DESC,
        max_entries=max_entries, max_uncompressed=max_uncompressed)
    members: Dict[str, bytes] = container["members"]
    warnings: List[str] = list(container["warnings"])

    if MANIFEST not in members:
        raise ValueError("workspace has no manifest.json")
    if len(members[MANIFEST]) > MANIFEST_MAX_BYTES:
        raise ValueError("manifest.json is implausibly large")
    raw_manifest = json.loads(members[MANIFEST].decode("utf-8"))

    raw_ver = _schema_version(raw_manifest.get("schema"))
    read_only = raw_ver is not None and raw_ver > WORKSPACE_VERSION
    manifest, migrated = migrate_manifest(raw_manifest)

    trace_bytes = None
    trace_meta = manifest.get("trace") or {}
    if bool(trace_meta.get("embedded")) and TRACE_MEMBER in members:
        trace_bytes = members[TRACE_MEMBER]
        if trace_meta.get("sha256") and workspace_sha256(trace_bytes) != trace_meta["sha256"]:
            warnings.append("embedded trace hash does not match the manifest")

    view_state = _read_json_member(members, STATE_VIEW)
    health = _read_json_member(members, ANALYSIS_HEALTH)
    findings = _read_json_member(members, ANALYSIS_FINDINGS)
    raw_inv = _read_json_member(members, INVESTIGATION_BOOKMARKS)
    investigation = load_investigation(raw_inv) if raw_inv is not None else None
    ai_case = _read_json_member(members, INVESTIGATION_AI_CASE)

    report_html = None
    if load_report and REPORT_HTML in members:
        report_html = members[REPORT_HTML].decode("utf-8", "replace")

    attachments: Dict[str, bytes] = {}
    for n in sorted(members):
        if n.startswith(ATTACHMENTS_PREFIX) and not n.endswith("/"):
            attachments[n[len(ATTACHMENTS_PREFIX):]] = members[n]

    extra_members = sorted(
        n for n in members
        if n not in _KNOWN_MEMBERS and not n.startswith(ATTACHMENTS_PREFIX)
    )

    return {
        "manifest": manifest,
        "schema": manifest.get("schema"),
        "read_only": read_only,
        "migrated": migrated,
        "trace_bytes": trace_bytes,
        "trace_embedded": bool(trace_meta.get("embedded")),
        "trace_ref": str(trace_meta.get("ref") or ""),
        "view_state": view_state,
        "health": health,
        "findings": findings,
        "investigation": investigation,
        "ai_case": ai_case,
        "report_html": report_html,
        "attachments": attachments,
        "extra_members": extra_members,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Trace freshness
# ---------------------------------------------------------------------------
def workspace_trace_status(
    manifest: Dict[str, Any],
    *,
    current_sha256: str = "",
    current_size: Optional[int] = None,
) -> Dict[str, Any]:
    """Whether the workspace's cached analysis can still be trusted for a trace.

    ``matches`` is ``True``/``False`` when it can be decided, ``None`` when
    there is nothing to compare against (no stored hash, or no current trace).
    """
    trace = (manifest or {}).get("trace") or {}
    stored_hash = str(trace.get("sha256") or "")
    embedded = bool(trace.get("embedded"))
    ref = str(trace.get("ref") or "")

    if not current_sha256 and current_size is None:
        return {"embedded": embedded, "referenced": ref, "matches": None,
                "reason": "no current trace to compare"}
    if not stored_hash:
        return {"embedded": embedded, "referenced": ref, "matches": None,
                "reason": "workspace stored no trace hash"}
    if current_sha256:
        if current_sha256 == stored_hash:
            return {"embedded": embedded, "referenced": ref, "matches": True,
                    "reason": "trace hash matches"}
        return {"embedded": embedded, "referenced": ref, "matches": False,
                "reason": "trace content changed since the workspace was saved"}
    if current_size is not None and int(current_size) != int(trace.get("size") or -1):
        return {"embedded": embedded, "referenced": ref, "matches": False,
                "reason": "trace size changed since the workspace was saved"}
    return {"embedded": embedded, "referenced": ref, "matches": None,
            "reason": "size matches but content not verified"}


# ---------------------------------------------------------------------------
# Safe extraction to disk (opt-in helper; the GUI/CLI can offer this)
# ---------------------------------------------------------------------------
def extract_workspace(path: str, dest_dir: str, *, max_entries: int = MAX_ENTRIES,
                      max_uncompressed: int = MAX_UNCOMPRESSED_BYTES) -> List[str]:
    """Extract every safe member under *dest_dir*. Returns the written paths.

    Thin wrapper over the shared :func:`btf_viewer_pkg.zip_container.safe_extract_all`.
    """
    return safe_extract_all(
        path, dest_dir, container_desc=_CONTAINER_DESC,
        max_entries=max_entries, max_uncompressed=max_uncompressed)
