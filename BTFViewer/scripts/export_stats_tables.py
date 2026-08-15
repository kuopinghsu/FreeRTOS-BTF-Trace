#!/usr/bin/env python3
"""Export compact SVG tables for Statistics pages that have no plot dialog.

Usage (from BTFViewer/):
  PYTHONPATH=. python3 scripts/export_stats_tables.py \\
      ../tracedata/example-8cores.btf.gz ../images/stats
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from btf_viewer_pkg import _bootstrap  # noqa: E402

_bootstrap.install()

from btf_viewer_pkg.parser import _parse_btf  # noqa: E402
from btf_viewer_pkg.timeline_util import _format_time  # noqa: E402
from btf_viewer_pkg.ux_explore import (  # noqa: E402
    KIND_LABEL,
    analyze_response_times,
    core_util_over_time,
    critical_path_rows,
    detect_timeline_anomalies,
    harvest_mutex_holds,
    harvest_ux_events,
    mutex_blocking_table,
    pair_mutex_waits,
    preemption_pairs,
    preemptor_ranking,
    recurring_patterns,
    unified_jitter,
)

BG = "#1e1e1e"
FG = "#d4d4d4"
HEAD = "#9cdcfe"
GRID = "#3c3c3c"
TITLE = "#cccccc"
ROW_H = 22
HEAD_H = 26
PAD_X = 10
CHAR_W = 7.2


def _esc(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _col_width(header: str, cells) -> int:
    widest = max([len(header)] + [len(str(c)) for c in cells], default=len(header))
    return max(72, int(widest * CHAR_W) + 2 * PAD_X)


def write_table_svg(path: Path, title: str, headers, rows, *, max_rows: int = 8) -> None:
    body = list(rows)[:max_rows]
    widths = [
        _col_width(h, [r[i] if i < len(r) else "" for r in body])
        for i, h in enumerate(headers)
    ]
    width = sum(widths)
    height = 36 + HEAD_H + ROW_H * max(1, len(body)) + 12
    x_off = []
    acc = 0
    for w in widths:
        x_off.append(acc)
        acc += w
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f"<title>{_esc(title)}</title>",
        f'<rect width="{width}" height="{height}" fill="{BG}"/>',
        f'<text x="{PAD_X}" y="22" fill="{TITLE}" font-family="ui-sans-serif, system-ui, sans-serif" '
        f'font-size="13">{_esc(title)}</text>',
    ]
    y0 = 36
    parts.append(
        f'<rect x="0" y="{y0}" width="{width}" height="{HEAD_H}" fill="#252526"/>'
    )
    for i, header in enumerate(headers):
        parts.append(
            f'<text x="{x_off[i] + PAD_X}" y="{y0 + 18}" fill="{HEAD}" '
            f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="11">'
            f"{_esc(header)}</text>"
        )
    if not body:
        parts.append(
            f'<text x="{PAD_X}" y="{y0 + HEAD_H + 16}" fill="{FG}" '
            f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="11">'
            "No rows in this trace</text>"
        )
    for r, row in enumerate(body):
        y = y0 + HEAD_H + r * ROW_H
        if r % 2:
            parts.append(
                f'<rect x="0" y="{y}" width="{width}" height="{ROW_H}" fill="#252526"/>'
            )
        parts.append(
            f'<line x1="0" y1="{y + ROW_H}" x2="{width}" y2="{y + ROW_H}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        for i, cell in enumerate(row):
            parts.append(
                f'<text x="{x_off[i] + PAD_X}" y="{y + 16}" fill="{FG}" '
                f'font-family="ui-sans-serif, system-ui, sans-serif" font-size="11">'
                f"{_esc(cell)}</text>"
            )
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: export_stats_tables.py TRACE.btf[.gz] OUT_DIR", file=sys.stderr)
        return 2
    trace_path = Path(argv[1])
    out_dir = Path(argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    trace = _parse_btf(str(trace_path))
    scale = trace.time_scale
    evs = harvest_ux_events(trace)

    def t(ns) -> str:
        return _format_time(int(ns or 0), scale)

    crit = critical_path_rows(evs, 8)
    write_table_svg(
        out_dir / "stats-crit-path.svg",
        "Critical Path — example-8cores",
        ["Task", "Duration", "Exec", "Preempt", "Wait", "Mig"],
        [
            [
                r.get("task") or "",
                t(r.get("duration")),
                t(r.get("exec_ns")),
                t(r.get("preempt_ns")),
                t(r.get("wait_ns")),
                t(r.get("migration_ns")),
            ]
            for r in crit
        ],
    )

    patterns = recurring_patterns(detect_timeline_anomalies(evs, 12), 2)
    write_table_svg(
        out_dir / "stats-patterns.svg",
        "Recurring Patterns — example-8cores",
        ["Task", "Kind", "Count", "Worst", "Why"],
        [
            [
                r.get("task") or "",
                KIND_LABEL.get(str(r.get("kind") or ""), str(r.get("kind") or "")),
                r.get("count") or 0,
                t(r.get("duration")),
                r.get("reason") or "",
            ]
            for r in patterns
        ],
    )

    jitter = unified_jitter(evs)
    write_table_svg(
        out_dir / "stats-jitter.svg",
        "Unified Jitter — example-8cores",
        ["Task", "Exec", "Exec CV", "Block", "Block CV", "Inter", "Inter CV",
         "Response", "Resp CV"],
        [
            [
                r.get("task") or "",
                t(r.get("exec_jitter_ns")),
                f"{float(r.get('exec_cv') or 0) * 100:.1f}%",
                t(r.get("block_jitter_ns")),
                f"{float(r.get('block_cv') or 0) * 100:.1f}%",
                t(r.get("inter_jitter_ns")),
                f"{float(r.get('inter_cv') or 0) * 100:.1f}%",
                t(r.get("response_jitter_ns")),
                f"{float(r.get('response_cv') or 0) * 100:.1f}%",
            ]
            for r in jitter
        ],
    )

    ranks = preemptor_ranking(preemption_pairs(evs), 8)
    write_table_svg(
        out_dir / "stats-preempt-matrix.svg",
        "Preemption Matrix — example-8cores",
        ["Victim", "Count", "Total", "Max", "Top preemptors"],
        [
            [
                r.get("task") or "",
                r.get("count") or 0,
                t(r.get("total_ns")),
                t(r.get("max_ns")),
                r.get("top_label") or "",
            ]
            for r in ranks
        ],
    )

    mutex_rows = mutex_blocking_table(pair_mutex_waits(harvest_mutex_holds(trace)))
    write_table_svg(
        out_dir / "stats-mutex-block.svg",
        "Mutex Blocking — example-8cores",
        ["Task", "Object", "Owner", "Count", "Total", "Max"],
        [
            [
                r.get("task") or "",
                r.get("object") or "",
                r.get("owner") or "",
                r.get("count") or 0,
                t(r.get("total_ns")),
                t(r.get("max_ns")),
            ]
            for r in mutex_rows
        ],
    )

    grid = core_util_over_time(evs, list(trace.core_names or []))
    cores = list(grid.get("cores") or [])
    bins = list(grid.get("bins") or [])
    write_table_svg(
        out_dir / "stats-core-time.svg",
        "Core Utilization Over Time — example-8cores",
        ["Time"] + cores,
        [
            [t(row.get("start"))]
            + [
                f"{float((row.get('cells') or {}).get(core, {}).get('pct') or 0):.1f}%"
                for core in cores
            ]
            for row in bins
        ],
        max_rows=16,
    )

    # Also emit a compact Response Time table (plot snapshot is separate).
    resp = analyze_response_times(evs).get("rows") or []
    write_table_svg(
        out_dir / "stats-response.svg",
        "Response Time — example-8cores",
        ["Task", "N", "Avg", "p50", "p99", "Max", "CV"],
        [
            [
                r.get("task") or "",
                r.get("n") or 0,
                t(r.get("avg_ns")),
                t(r.get("p50_ns")),
                t(r.get("p99_ns")),
                t(r.get("max_ns")),
                f"{float(r.get('cv') or 0) * 100:.1f}%",
            ]
            for r in resp
        ],
    )
    print(f"Updated table SVGs in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
