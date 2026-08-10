"""Export a cursor-range slice of a BTF text stream (Desktop + CLI)."""
from __future__ import annotations

import gzip
import os
from typing import Iterable, List, Tuple

from .parser import BtfTrace, _open_btf_text, _task_display_name


def filter_btf_text_to_range(text: str, lo: int, hi: int) -> Tuple[str, int]:
    """Keep ``#`` meta, ``C`` (set_frequency) lines, and events in ``[lo, hi]``."""
    if hi < lo:
        lo, hi = hi, lo
    lines, n = _filter_btf_lines(str(text or "").splitlines(), lo, hi)
    return "\n".join(lines) + ("\n" if lines else ""), n


def filter_btf_file_to_range(filepath: str, lo: int, hi: int) -> Tuple[str, int]:
    """Re-read *filepath* and keep events whose timestamp is in ``[lo, hi]``."""
    if hi < lo:
        lo, hi = hi, lo
    with _open_btf_text(filepath) as fh:
        lines, n = _filter_btf_lines(fh, lo, hi)
    return "\n".join(lines) + ("\n" if lines else ""), n


def write_btf_text(text: str, dest_path: str) -> None:
    """Write UTF-8 BTF; ``.gz`` destinations are gzip-compressed."""
    dest = os.path.abspath(dest_path)
    data = str(text or "").encode("utf-8")
    parent = os.path.dirname(dest)
    if parent:
        os.makedirs(parent, exist_ok=True)
    low = dest.lower()
    if low.endswith(".gz"):
        with gzip.open(dest, "wb") as fh:
            fh.write(data)
        return
    with open(dest, "wb") as fh:
        fh.write(data)


def reconstruct_btf_slice(trace: BtfTrace, lo: int, hi: int) -> Tuple[str, int]:
    """Build a best-effort BTF when the original source text is unavailable."""
    if hi < lo:
        lo, hi = hi, lo
    lines: List[str] = []
    for key, val in dict(getattr(trace, "meta", None) or {}).items():
        lines.append(f"#{key} {val}")
    scale = getattr(trace, "time_scale", "") or ""
    if scale and "timeScale" not in (getattr(trace, "meta", None) or {}):
        lines.append(f"#timeScale {scale}")
    lines.append(f"#sliced {lo}-{hi}")
    events: List[Tuple[int, str]] = []
    repr_map = getattr(trace, "task_repr", None) or {}
    for seg in getattr(trace, "segments", None) or []:
        start = int(seg.start)
        end = int(seg.end)
        if end < lo or start > hi:
            continue
        a = max(start, lo)
        b = min(end, hi)
        if a >= b:
            continue
        core = str(seg.core or "Core_0")
        raw = repr_map.get(seg.task, seg.task)
        name = _task_display_name(raw) if raw else str(seg.task)
        name = str(name or seg.task).replace(",", " ")
        events.append((a, f"{a},{core},0,T,{name},0,resume,"))
        events.append((b, f"{b},{core},0,T,{name},0,preempt,"))
    for ev in getattr(trace, "sti_events", None) or []:
        t = int(ev.time)
        if t < lo or t > hi:
            continue
        note = str(ev.note or "").replace("\n", " ")
        events.append((
            t,
            f"{t},{ev.core or 'Core_0'},0,STI,{ev.target},0,{ev.event},{note}",
        ))
    for t in getattr(trace, "tick_sti_times", None) or []:
        ts = int(t)
        if lo <= ts <= hi:
            events.append((ts, f"{ts},Core_0,0,STI,TICK,0,trigger,"))
    events.sort(key=lambda row: (row[0], row[1]))
    for _t, line in events:
        lines.append(line)
    return "\n".join(lines) + ("\n" if lines else ""), len(events)


def _filter_btf_lines(src: Iterable[str], lo: int, hi: int) -> Tuple[List[str], int]:
    out: List[str] = [f"#sliced {lo}-{hi}"]
    kept = 0
    for raw in src:
        line = str(raw).rstrip("\r\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] == "#":
            out.append(stripped)
            continue
        parts = stripped.split(",", 8)
        if len(parts) < 4:
            continue
        ev_type = parts[3].strip()
        if ev_type == "C":
            out.append(stripped)
            continue
        try:
            t = int(parts[0].strip())
        except ValueError:
            continue
        if lo <= t <= hi:
            out.append(stripped)
            kept += 1
    return out, kept
