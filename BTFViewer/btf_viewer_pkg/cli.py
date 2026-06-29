"""BTF Viewer — cli module (source). Do not edit btf_viewer.py; run make bundle."""
from __future__ import annotations

from ._imports import *  # noqa: F403,F401
from .config import *  # noqa: F403,F401
from .parser import *  # noqa: F403,F401
from .timeline_util import *  # noqa: F403,F401
from .graphics_items import *  # noqa: F403,F401
from .scene import *  # noqa: F403,F401
from .view import *  # noqa: F403,F401
from .stats import *  # noqa: F403,F401
from .mainwindow import *  # noqa: F403,F401
from .platform import *  # noqa: F403,F401

def _cli_validate_range_pair(lo: Optional[int], hi: Optional[int], label: str) -> Optional[str]:
    if (lo is None) ^ (hi is None):
        return f"error: {label} requires both endpoints (e.g. --{label}-lo and --{label}-hi)"
    if lo is not None and hi is not None and hi <= lo:
        return f"error: {label} end must be greater than start"
    return None

def _cli_load_trace(path: str) -> Tuple[Optional["BtfTrace"], Optional[str]]:
    trace_path = os.path.abspath(path)
    if not os.path.isfile(trace_path):
        return None, f"error: trace file not found: {trace_path}"
    try:
        return _parse_btf(trace_path), None
    except Exception as exc:
        return None, f"error: failed to parse {trace_path}: {exc}"

def _cli_dual_ranges(args: argparse.Namespace) -> Tuple[Optional[int], Optional[int],
                                                        Optional[int], Optional[int],
                                                        Optional[str]]:
    """Resolve compare scope: shared --lo/--hi or per-trace --lo-a/--hi-a/--lo-b/--hi-b."""
    shared = args.lo is not None or args.hi is not None
    per_a = args.lo_a is not None or args.hi_a is not None
    per_b = args.lo_b is not None or args.hi_b is not None
    if shared and (per_a or per_b):
        return None, None, None, None, (
            "error: use either --lo/--hi (both traces) or --lo-a/--hi-a / --lo-b/--hi-b")
    if shared:
        err = _cli_validate_range_pair(args.lo, args.hi, "range")
        if err:
            return None, None, None, None, err
        return args.lo, args.hi, args.lo, args.hi, None
    err = _cli_validate_range_pair(args.lo_a, args.hi_a, "lo-a/hi-a")
    if err:
        return None, None, None, None, err
    err = _cli_validate_range_pair(args.lo_b, args.hi_b, "lo-b/hi-b")
    if err:
        return None, None, None, None, err
    return args.lo_a, args.hi_a, args.lo_b, args.hi_b, None

def _trace_info_payload(trace: "BtfTrace", path: str,
                        lo: Optional[int], hi: Optional[int]) -> dict:
    snap = _trace_summary_snapshot(trace, lo, hi)
    tick = _tick_health_report(trace, lo, hi)
    scale = trace.time_scale
    span_ns = snap["span_ns"]
    return {
        "file": path,
        "meta": dict(trace.meta),
        "time_scale": scale,
        "time_min": trace.time_min,
        "time_max": trace.time_max,
        "span_ns": span_ns,
        "span": _format_time(span_ns, scale),
        "cores": list(trace.core_names),
        "multi_core": _trace_is_multi_core(trace),
        "scope": {"lo": lo, "hi": hi} if lo is not None and hi is not None else None,
        "summary": {
            "tasks": snap["tasks"],
            "segments": snap["segments"],
            "sti_events": snap["sti_events"],
            "context_switches": snap["context_switches"],
            "core_gap_avg": _format_time(snap["gap_avg_ns"], scale),
            "core_gap_max": _format_time(snap["gap_max_ns"], scale),
            "migrations": snap["migrations"],
            "migrated_tasks": snap["migrated_tasks"],
        },
        "instrumentation": {
            "priority": trace.has_priority_instrumentation,
            "sync_objects": trace.has_sync_object_instrumentation,
            "intervals": bool(trace.interval_ids),
            "tags": bool(trace.tag_channels),
        },
        "tick_health": tick,
    }

def _build_migrations_csv(trace: "BtfTrace",
                          lo: Optional[int] = None,
                          hi: Optional[int] = None) -> str:
    header = ("Task,Migrations,Migr rate,Avg dwell,Core count,Primary core,"
              "Primary %,Ping-pong,STI near,Avg gap after,Avg gap other")
    lines = [header]
    for row in _migration_rows(trace, lo, hi):
        (_mk, name, n_mig, n_cores, _cores, primary, pct, ping, sti,
         ga, go, migr_rate, _rps, avg_dwell, _adtu) = row
        lines.append(",".join(_compare_csv_cell(c) for c in (
            name, n_mig, migr_rate, avg_dwell, n_cores, primary,
            f"{pct:.1f}", ping, sti, ga, go,
        )))
    return "\n".join(lines) + "\n"

_CLI_HELP = """\
Headless analysis commands (desktop only — no GUI, no Qt window):

  info         Quick trace summary on stdout (--json for scripts).
  report       Full statistics export (Statistics panel → Export CSV/HTML).
  compare      Two-trace diff (Trace Compare dialog → Export).
  migrations   Core Migrations table only (CSV).

Time range (--lo / --hi):
  Values are raw trace timestamps in the file's time units (see # timeScale
  in the .btf header: ns, us, ms, …). Both endpoints are required together;
  hi must be greater than lo. Omit for the full trace span.

Output format (--format, report and compare only):
  html   Styled report (default when -o has no extension or ends in .html)
  csv    Tabular export (default when -o ends in .csv)
  both   Write PATH.html and PATH.csv (or stem.html + stem.csv)
"""

_CLI_EPILOG_GUI = """\
GUI examples:
  %(prog)s                                    restore previous session (btf_viewer.rc)
  %(prog)s tracedata/example.btf              open one trace in the interactive viewer
  %(prog)s run1.btf run2.btf                   open multiple traces (first tab active)

CLI examples:
  %(prog)s info tracedata/example-4cores.btf
  %(prog)s info tracedata/example-4cores.btf --json
  %(prog)s report tracedata/example-4cores.btf -o /tmp/stats.html
  %(prog)s report tracedata/example-4cores.btf -o /tmp/stats --format both
  %(prog)s compare run1.btf run2.btf -o /tmp/compare.html --name-a baseline --name-b tuned
  %(prog)s migrations tracedata/example-4cores.btf -o /tmp/migrations.csv

Run "%(prog)s <command> -h" for command-specific help.
"""

_CLI_EPILOG_INFO = """\
Prints span, core list, task/segment counts, context switches, migration
totals, instrumentation flags, and TICK health (when STI TICK events exist).

examples:
  %(prog)s trace.btf
  %(prog)s trace.btf --json
  %(prog)s trace.btf --lo 200000 --hi 400000
"""

_CLI_EPILOG_REPORT = """\
Same content as Statistics → Export in the GUI:

  HTML — summary KPIs, CPU bars, and detail tables (priority episodes,
         mutex/semaphore holds, interval instances).
  CSV  — all statistics sections as worksheets in one file.

examples:
  %(prog)s trace.btf -o statistics.html
  %(prog)s trace.btf -o statistics.csv --format csv
  %(prog)s trace.btf -o report --format both
  %(prog)s trace.btf -o scoped.html --lo 1000000 --hi 5000000
"""

_CLI_EPILOG_COMPARE = """\
Same tables as Trace Compare → Export:

  Summary        span, tasks, segments, STI, context switches, core gaps,
                 migration totals (with Δ column).
  Top Tasks      CPU%% per display name (union of both traces).
  Core Migrations  per-task migr count, rate, dwell, ping-pong (A vs B + Δ).

Scope:
  Omit range flags for the full trace on each side.
  --lo/--hi        apply the same window to both traces.
  --lo-a/--hi-a    window for trace A only (like C1–Cn on tab A).
  --lo-b/--hi-b    window for trace B only (like C1–Cn on tab B).
  Do not mix shared --lo/--hi with per-trace --lo-a/--hi-a/--lo-b/--hi-b.

examples:
  %(prog)s before.btf after.btf -o compare.html
  %(prog)s a.btf b.btf -o diff.csv --format csv
  %(prog)s a.btf b.btf -o cmp --format both
  %(prog)s a.btf b.btf -o cmp.html --lo-a 0 --hi-a 100000 --lo-b 0 --hi-b 100000
"""

_CLI_EPILOG_MIGRATIONS = """\
Columns: Task, Migrations, Migr rate (/s and /tick), Avg dwell, Core count,
Primary core, Primary %%, Ping-pong, STI±, Avg gap after, Avg gap other.

examples:
  %(prog)s trace.btf                    # write CSV to stdout
  %(prog)s trace.btf -o migrations.csv
  %(prog)s trace.btf -o -               # explicit stdout
  %(prog)s trace.btf -o out.csv --lo T --hi T
"""

_CLI_LO_HELP = (
    "range start (trace time units; must be used with --hi; "
    "see # timeScale in the .btf file)"
)
_CLI_HI_HELP = (
    "range end (trace time units; must be greater than --lo)"
)

def _make_arg_parser() -> Tuple[argparse.ArgumentParser, Dict[str, argparse.ArgumentParser]]:
    """Return (top-level parser, subcommand parsers keyed by name)."""
    parser = argparse.ArgumentParser(
        prog="btf_viewer.py",
        description=(
            "RTOS BTF trace viewer (interactive GUI) and headless analysis (CLI).\n\n"
            + _CLI_HELP
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_CLI_EPILOG_GUI,
    )
    sub = parser.add_subparsers(
        dest="command",
        metavar="command",
        title="commands",
        description="headless analysis (run with -h for details)",
    )

    report = sub.add_parser(
        "report",
        help="export full statistics report (Statistics → Export CSV/HTML)",
        description=(
            "Export a complete statistics report for one trace.\n\n"
            "Matches Statistics → Export CSV / Export HTML in the GUI."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_CLI_EPILOG_REPORT,
    )
    report.add_argument(
        "trace", metavar="trace.btf",
        help="path to the .btf trace file to analyse",
    )
    report.add_argument(
        "-o", "--output", required=True, metavar="PATH",
        help=(
            "output path: .html or .csv file, or a stem when --format both "
            "(writes stem.html and stem.csv)"
        ),
    )
    report.add_argument(
        "--format", choices=("html", "csv", "both"), default=None,
        metavar="FMT",
        help=(
            "output format: html, csv, or both (default: infer from -o extension, "
            "else html)"
        ),
    )
    report.add_argument("--lo", type=int, default=None, metavar="T", help=_CLI_LO_HELP)
    report.add_argument("--hi", type=int, default=None, metavar="T", help=_CLI_HI_HELP)

    compare = sub.add_parser(
        "compare",
        help="compare two traces side-by-side (Trace Compare → Export)",
        description=(
            "Compare two .btf traces: summary metrics, top tasks by CPU%%, and "
            "core migration tables with A/B deltas.\n\n"
            "Matches Trace Compare → Export CSV / Export HTML in the GUI."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_CLI_EPILOG_COMPARE,
    )
    compare.add_argument(
        "trace_a", metavar="trace_a.btf",
        help="first trace (.btf); shown as Trace A in the report",
    )
    compare.add_argument(
        "trace_b", metavar="trace_b.btf",
        help="second trace (.btf); shown as Trace B in the report",
    )
    compare.add_argument(
        "-o", "--output", required=True, metavar="PATH",
        help="output path (.html / .csv) or stem when --format both",
    )
    compare.add_argument(
        "--format", choices=("html", "csv", "both"), default=None,
        metavar="FMT",
        help="output format (default: infer from -o extension, else html)",
    )
    compare.add_argument(
        "--name-a", default=None, metavar="LABEL",
        help="display label for trace A (default: basename of trace_a.btf)",
    )
    compare.add_argument(
        "--name-b", default=None, metavar="LABEL",
        help="display label for trace B (default: basename of trace_b.btf)",
    )
    compare.add_argument(
        "--lo", type=int, default=None, metavar="T",
        help="shared range start for both traces (alternative to --lo-a/--lo-b)",
    )
    compare.add_argument(
        "--hi", type=int, default=None, metavar="T",
        help="shared range end for both traces (alternative to --hi-a/--hi-b)",
    )
    compare.add_argument(
        "--lo-a", type=int, default=None, metavar="T",
        help="range start for trace A only",
    )
    compare.add_argument(
        "--hi-a", type=int, default=None, metavar="T",
        help="range end for trace A only",
    )
    compare.add_argument(
        "--lo-b", type=int, default=None, metavar="T",
        help="range start for trace B only",
    )
    compare.add_argument(
        "--hi-b", type=int, default=None, metavar="T",
        help="range end for trace B only",
    )

    info = sub.add_parser(
        "info",
        help="print trace summary on stdout",
        description=(
            "Print a concise summary for one trace: span, cores, counts, "
            "migrations, instrumentation, and TICK health."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_CLI_EPILOG_INFO,
    )
    info.add_argument(
        "trace", metavar="trace.btf",
        help="path to the .btf trace file to summarise",
    )
    info.add_argument(
        "--json", action="store_true",
        help="emit machine-readable JSON (file path, meta, summary, tick_health)",
    )
    info.add_argument("--lo", type=int, default=None, metavar="T", help=_CLI_LO_HELP)
    info.add_argument("--hi", type=int, default=None, metavar="T", help=_CLI_HI_HELP)

    migrations = sub.add_parser(
        "migrations",
        help="export Core Migrations statistics table as CSV",
        description=(
            "Export the Core Migrations table (Rate, Dwell, ping-pong, STI±, "
            "gaps, …) as CSV. Useful for scripting without the full statistics report."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_CLI_EPILOG_MIGRATIONS,
    )
    migrations.add_argument(
        "trace", metavar="trace.btf",
        help="path to the .btf trace file",
    )
    migrations.add_argument(
        "-o", "--output", default="-", metavar="PATH",
        help="output CSV path (default: '-' = stdout)",
    )
    migrations.add_argument("--lo", type=int, default=None, metavar="T", help=_CLI_LO_HELP)
    migrations.add_argument("--hi", type=int, default=None, metavar="T", help=_CLI_HI_HELP)

    return parser, {
        "report": report,
        "compare": compare,
        "info": info,
        "migrations": migrations,
    }

def _cli_export_output_paths(output: str, fmt: Optional[str]) -> Tuple[str, str, str]:
    """Return (format, html_path, csv_path) for the report subcommand."""
    low = output.lower()
    if fmt is None:
        if low.endswith(".csv"):
            fmt = "csv"
        elif low.endswith(".html") or low.endswith(".htm"):
            fmt = "html"
        else:
            fmt = "html"
    if fmt == "html":
        html_path = output if low.endswith((".html", ".htm")) else f"{output}.html"
        return fmt, html_path, ""
    if fmt == "csv":
        csv_path = output if low.endswith(".csv") else f"{output}.csv"
        return fmt, "", csv_path
    # both
    root, ext = os.path.splitext(output)
    if ext.lower() in (".html", ".htm", ".csv"):
        stem = root
    else:
        stem = output
    return fmt, f"{stem}.html", f"{stem}.csv"

def _cli_report_run(args: argparse.Namespace) -> int:
    trace_path = os.path.abspath(args.trace)
    if not os.path.isfile(trace_path):
        print(f"error: trace file not found: {trace_path}", file=sys.stderr)
        return 1
    if (args.lo is None) ^ (args.hi is None):
        print("error: --lo and --hi must be given together", file=sys.stderr)
        return 1
    if args.lo is not None and args.hi is not None and args.hi <= args.lo:
        print("error: --hi must be greater than --lo", file=sys.stderr)
        return 1

    fmt, html_path, csv_path = _cli_export_output_paths(args.output, args.format)

    try:
        trace = _parse_btf(trace_path)
    except Exception as exc:
        print(f"error: failed to parse trace: {exc}", file=sys.stderr)
        return 1

    panel = _StatsPanel.__new__(_StatsPanel)
    panel._trace = trace
    panel._export_scope_override = None
    panel._scope_to_cursors = False
    panel._cursor_times = []
    if args.lo is not None and args.hi is not None:
        panel._export_scope_override = (args.lo, args.hi)

    written: List[str] = []
    try:
        if fmt in ("html", "both"):
            panel.write_statistics_html_report(html_path)
            written.append(html_path)
        if fmt in ("csv", "both"):
            panel.write_statistics_csv_report(csv_path)
            written.append(csv_path)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for path in written:
        print(path)
    return 0

def _cli_report_main(argv: List[str]) -> int:
    _parsers = _make_arg_parser()[1]
    args = _parsers["report"].parse_args(argv)
    return _cli_report_run(args)

def _cli_compare_run(args: argparse.Namespace) -> int:
    lo_a, hi_a, lo_b, hi_b, err = _cli_dual_ranges(args)
    if err:
        print(err, file=sys.stderr)
        return 1

    path_a = os.path.abspath(args.trace_a)
    path_b = os.path.abspath(args.trace_b)
    trace_a, err_a = _cli_load_trace(path_a)
    if err_a:
        print(err_a, file=sys.stderr)
        return 1
    trace_b, err_b = _cli_load_trace(path_b)
    if err_b:
        print(err_b, file=sys.stderr)
        return 1

    name_a = args.name_a or os.path.basename(path_a)
    name_b = args.name_b or os.path.basename(path_b)
    scope_enabled = (lo_a is not None) or (lo_b is not None)
    summary, top, mig, blocking, preemption, sync = _build_trace_compare_rows(
        trace_a, trace_b, lo_a, hi_a, lo_b, hi_b)

    fmt, html_path, csv_path = _cli_export_output_paths(args.output, args.format)
    written: List[str] = []
    try:
        if fmt in ("html", "both"):
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(_build_compare_html(
                    name_a, name_b, scope_enabled, summary, top, mig,
                    blocking, preemption, sync))
            written.append(html_path)
        if fmt in ("csv", "both"):
            text = _build_compare_csv(
                name_a, name_b, scope_enabled, summary, top, mig,
                blocking, preemption, sync)
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
                fh.write(text)
            written.append(csv_path)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for path in written:
        print(path)
    return 0

def _cli_compare_main(argv: List[str]) -> int:
    args = _make_arg_parser()[1]["compare"].parse_args(argv)
    return _cli_compare_run(args)

def _cli_info_run(args: argparse.Namespace) -> int:
    path = os.path.abspath(args.trace)
    err = _cli_validate_range_pair(args.lo, args.hi, "range")
    if err:
        print(err, file=sys.stderr)
        return 1

    trace, err_load = _cli_load_trace(path)
    if err_load:
        print(err_load, file=sys.stderr)
        return 1

    payload = _trace_info_payload(trace, path, args.lo, args.hi)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    scope = payload["scope"]
    scope_line = ""
    if scope:
        scale = payload["time_scale"]
        scope_line = (
            f"Scope: {_format_time(scope['lo'], scale)} … "
            f"{_format_time(scope['hi'], scale)}  "
            f"({_format_time(scope['hi'] - scope['lo'], scale)})\n"
        )
    s = payload["summary"]
    inst = payload["instrumentation"]
    tick = payload["tick_health"]
    lines = [
        f"File: {payload['file']}",
        f"Span: {payload['span']}  ({payload['time_min']} … {payload['time_max']} {payload['time_scale']})",
        scope_line.rstrip(),
        f"Cores ({len(payload['cores'])}): {', '.join(payload['cores']) or '—'}",
        f"Tasks: {s['tasks']}  Segments: {s['segments']}  STI events: {s['sti_events']}",
        f"Context switches: {s['context_switches']}  "
        f"Core gap avg/max: {s['core_gap_avg']} / {s['core_gap_max']}",
        f"Migrations: {s['migrations']}  Migrated tasks: {s['migrated_tasks']}",
        f"Instrumentation: priority={inst['priority']}  "
        f"sync={inst['sync_objects']}  intervals={inst['intervals']}",
    ]
    if tick.get("tick_count"):
        lines.append(
            f"TICK health: {tick['health'].upper()}  "
            f"({'TICKLESS' if tick['is_tickless'] else 'TICK'})  "
            f"ticks={tick['tick_count']}  CV={tick['tick_cv'] * 100.0:.2f}%"
        )
    print("\n".join(line for line in lines if line))
    return 0

def _cli_info_main(argv: List[str]) -> int:
    args = _make_arg_parser()[1]["info"].parse_args(argv)
    return _cli_info_run(args)

def _cli_migrations_run(args: argparse.Namespace) -> int:
    err = _cli_validate_range_pair(args.lo, args.hi, "range")
    if err:
        print(err, file=sys.stderr)
        return 1

    path = os.path.abspath(args.trace)
    trace, err_load = _cli_load_trace(path)
    if err_load:
        print(err_load, file=sys.stderr)
        return 1

    text = _build_migrations_csv(trace, args.lo, args.hi)
    out = args.output
    if out in ("-", ""):
        sys.stdout.write(text)
        return 0
    try:
        with open(out, "w", newline="", encoding="utf-8-sig") as fh:
            fh.write(text)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(out)
    return 0

def _cli_migrations_main(argv: List[str]) -> int:
    args = _make_arg_parser()[1]["migrations"].parse_args(argv)
    return _cli_migrations_run(args)

_CLI_COMMANDS = {
    "report": _cli_report_main,
    "compare": _cli_compare_main,
    "info": _cli_info_main,
    "migrations": _cli_migrations_main,
}

def _cli_gui_trace_paths(argv: List[str]) -> List[str]:
    """Normalize existing .btf paths from GUI argv (preserves order, dedupes)."""
    seen: set = set()
    out: List[str] = []
    for arg in argv:
        if arg.startswith("-"):
            continue
        path = os.path.abspath(os.path.expanduser(arg))
        if not os.path.isfile(path):
            print(f"warning: trace file not found, skipping: {arg}", file=sys.stderr)
            continue
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out

def main() -> None:
    argv = sys.argv[1:]
    parser, _subs = _make_arg_parser()

    if argv in (["-h"], ["--help"]):
        parser.print_help()
        raise SystemExit(0)

    if argv and argv[0] in _CLI_COMMANDS:
        raise SystemExit(_CLI_COMMANDS[argv[0]](argv[1:]))

    if argv and argv[0].startswith("-"):
        parser.print_help()
        print(f"\nerror: unrecognized arguments: {' '.join(argv)}", file=sys.stderr)
        raise SystemExit(2)

    _platform_preflight()
    app = _bootstrap_qt_app(sys.argv)
    _install_macos_stderr_filter()
    app.setApplicationName("RTOS BTF Viewer")
    app.setApplicationDisplayName("RTOS BTF Viewer")
    app.setOrganizationName("btf_viewer")
    app.setWindowIcon(app_icon())

    win = MainWindow()
    win.show()
    _process_ui_events_safely()  # ensure the window is painted before any file open

    cli_paths = _cli_gui_trace_paths(argv)
    if cli_paths:
        win._session_restore_active_idx = 0
        win._session_restore_queue = cli_paths[1:]
        QTimer.singleShot(100, lambda: win._open_file(cli_paths[0]))
    elif argv:
        QTimer.singleShot(100, win._restore_session_tabs)
    else:
        QTimer.singleShot(100, win._restore_session_tabs)

    sys.exit(app.exec())
