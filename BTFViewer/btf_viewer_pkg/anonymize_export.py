"""Stable ``Task-N`` aliasing for the Export dialog's *Anonymize* option.

Lockstep with ``web/src/utils/anonymizeExport.js``.

One alias map is built per export from the trace's task set — ``sorted`` so web
and desktop agree on the numbering — then applied to every artifact the export
writes:

* the embedded / sliced raw BTF text (``anonymize_btf_text``);
* Perfetto ``thread_name`` / slice ``name`` fields, the bundled Trace Health,
  Investigation Findings and notebook JSON (``anonymize_json_strings``).

Only whole-token task-name occurrences are replaced (``ControlTask`` does not
match inside ``ControlTaskHelper``), so the alias is reversible by eye.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable

ANON_PREFIX = "Task-"


def build_task_alias_map(names: Iterable[str]) -> Dict[str, str]:
    """``{real_name: "Task-N"}`` for the unique, sorted, non-empty *names*."""
    uniq = sorted({str(n).strip() for n in (names or [])
                   if n is not None and str(n).strip()})
    return {n: f"{ANON_PREFIX}{i}" for i, n in enumerate(uniq, 1)}


def _alias_regex(names: Iterable[str]):
    # Longest first so a longer name wins over a prefix of it.
    ordered = sorted((re.escape(str(n)) for n in names if str(n)), key=len,
                     reverse=True)
    if not ordered:
        return None
    # No word char / hyphen / dot on either side → whole-identifier match only.
    return re.compile(r"(?<![\w.\-])(?:" + "|".join(ordered) + r")(?![\w.\-])")


def anonymize_with_map(text: str, alias_map: Dict[str, str]) -> str:
    """Replace every whole-token task name in *text* with its ``Task-N`` alias."""
    if not text or not alias_map:
        return text if text is not None else ""
    rx = _alias_regex(alias_map.keys())
    if rx is None:
        return text
    return rx.sub(lambda m: alias_map.get(m.group(0), m.group(0)), str(text))


# Raw BTF text and Perfetto/JSON strings use the same whole-token substitution.
anonymize_btf_text = anonymize_with_map


def anonymize_json_strings(obj: Any, alias_map: Dict[str, str]) -> Any:
    """Recursively rewrite every string value in a JSON-able structure."""
    if isinstance(obj, str):
        return anonymize_with_map(obj, alias_map)
    if isinstance(obj, list):
        return [anonymize_json_strings(v, alias_map) for v in obj]
    if isinstance(obj, tuple):
        return tuple(anonymize_json_strings(v, alias_map) for v in obj)
    if isinstance(obj, dict):
        return {k: anonymize_json_strings(v, alias_map) for k, v in obj.items()}
    return obj
