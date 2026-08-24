"""User-facing error formatting (Step 3).

Lockstep with ``web/src/utils/errorFormat.py``.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

_PARSE_HINTS = (
    (re.compile(r"invalid timestamp", re.I), "Check for malformed timestamps near the reported line."),
    (
        re.compile(r"unexpected token|parse error|syntax", re.I),
        "Verify the file is a valid BTF/XML trace.",
    ),
    (re.compile(r"encoding|utf-8|unicode", re.I), "Save the trace as UTF-8 and try again."),
    (re.compile(r"empty|no events", re.I), "The file appears to contain no trace events."),
)


def format_error(
    *,
    operation: str,
    subject: str = "",
    reason: str = "",
    suggestion: str = "",
    detail: str = "",
) -> Dict[str, str]:
    op = str(operation or "Operation").strip()
    title = f"{op}: {subject}" if subject else op
    parts = []
    if reason:
        parts.append(str(reason).strip())
    if suggestion:
        parts.append(str(suggestion).strip())
    return {
        "title": title,
        "message": " ".join(parts) if parts else f"{op} failed.",
        "suggestion": suggestion or "",
        "detail": detail or "",
    }


def format_error_toast(err: Any) -> str:
    if not err:
        return "An error occurred."
    if isinstance(err, str):
        return err
    if isinstance(err, dict):
        title = str(err.get("title") or "")
        msg = str(err.get("message") or "")
        if title and msg and not msg.startswith(title):
            return f"{title}\n{msg}"
        return msg or title or "An error occurred."
    return str(err)


def _guess_parse_suggestion(text: str) -> str:
    blob = str(text or "")
    for pattern, hint in _PARSE_HINTS:
        if pattern.search(blob):
            return hint
    return "Check that the file is a valid .btf/.xml trace and try again."


def _err_raw(err: Any) -> tuple[str, str]:
    if isinstance(err, BaseException):
        raw = str(err)
        detail = getattr(err, "__traceback__", None) and str(err) or raw
        return raw, detail
    raw = str(err)
    return raw, raw


def format_parse_error(err: Any, file_name: str = "") -> Dict[str, str]:
    raw, detail = _err_raw(err)
    subject = file_name or "trace file"
    reason = re.sub(r"^Error:\s*", "", raw, flags=re.I).strip() or "The trace could not be parsed."
    return format_error(
        operation="Could not open trace",
        subject=subject,
        reason=reason,
        suggestion=_guess_parse_suggestion(raw),
        detail=detail,
    )


def format_io_error(err: Any, file_name: str = "") -> Dict[str, str]:
    raw, detail = _err_raw(err)
    subject = file_name or "file"
    suggestion = "Check that the file exists and is readable."
    if re.search(r"permission|denied", raw, re.I):
        suggestion = "Check file permissions and try again."
    elif re.search(r"not found|enoent", raw, re.I):
        suggestion = "Verify the path and try opening the file again."
    reason = re.sub(r"^Error:\s*", "", raw, flags=re.I).strip() or "The file could not be read."
    return format_error(
        operation="Could not read file",
        subject=subject,
        reason=reason,
        suggestion=suggestion,
        detail=detail,
    )


def format_ai_error(err: Any, provider: str = "") -> Dict[str, str]:
    raw, detail = _err_raw(err)
    subject = f"AI provider ({provider})" if provider else "AI provider"
    suggestion = "Check Settings → AI for provider URL, model, and authentication."
    if re.search(r"timeout|timed out", raw, re.I):
        suggestion = "The provider did not respond in time — check network connectivity."
    elif re.search(r"401|403|unauthorized|forbidden", raw, re.I):
        suggestion = "Verify API key or authentication settings."
    reason = re.sub(r"^Error:\s*", "", raw, flags=re.I).strip()
    return format_error(
        operation="AI request failed",
        subject=subject,
        reason=reason,
        suggestion=suggestion,
        detail=detail,
    )


def format_export_error(err: Any, kind: str = "export") -> Dict[str, str]:
    raw, detail = _err_raw(err)
    labels = {
        "export": "Could not export",
        "report": "Could not generate report",
        "session": "Could not save session",
    }
    reason = re.sub(r"^Error:\s*", "", raw, flags=re.I).strip()
    return format_error(
        operation=labels.get(kind, labels["export"]),
        reason=reason,
        suggestion="Try again or choose a different destination.",
        detail=detail,
    )
