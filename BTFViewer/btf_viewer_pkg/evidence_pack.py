"""Bundle Analysis Findings + portable session into a downloadable zip.

Mirrors ``web/src/utils/evidencePack.js`` exactly (same member names,
README text, and ``<base>-evidence-<UTC timestamp>.zip`` filename pattern)
so a Desktop-built evidence pack and a Web-built one are interchangeable.

Distinct from ``ai_evidence_package.py``, which builds the unrelated,
question-driven AI evidence JSON used by the Investigation Notebook's
"Evidence package…" action.
"""
from __future__ import annotations

import datetime
import io
import re
import zipfile

_README_TEXT = (
    "BTFViewer evidence pack\n"
    "----------------------\n"
    "analysis-findings.txt — Analysis Findings snapshot\n"
    "session.json — portable session (marks, cursors, layout)\n"
    "statistics-report.html — optional HTML stats export\n"
    "Open the matching .btf in BTFViewer to verify events.\n"
)

_BASENAME_SANITIZE_RE = re.compile(r"[^\w.-]+", re.ASCII)


def build_evidence_pack_zip(
    *,
    base_name: str = "",
    findings_text: str = "",
    session_json: str = "",
    stats_html: str = "",
    notes: str = "",
) -> tuple[bytes, str]:
    """Return ``(zip_bytes, filename)`` for an evidence pack.

    Same member set, naming, and timestamp format as ``buildEvidencePackZip()``
    in ``web/src/utils/evidencePack.js``.
    """
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    base = _BASENAME_SANITIZE_RE.sub("_", base_name or "btf-evidence") or "btf-evidence"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        if findings_text:
            zf.writestr("analysis-findings.txt", findings_text)
        if session_json:
            zf.writestr("session.json", session_json)
        if stats_html:
            zf.writestr("statistics-report.html", stats_html)
        if notes:
            zf.writestr("notes.txt", notes)
        zf.writestr("README.txt", _README_TEXT)
    return buf.getvalue(), f"{base}-evidence-{stamp}.zip"
