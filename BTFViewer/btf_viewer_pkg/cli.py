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
from .perfetto_export import export_perfetto
from .platform import *  # noqa: F403,F401

def _cli_validate_range_pair(lo: Optional[int], hi: Optional[int], label: str) -> Optional[str]:
    if (lo is None) ^ (hi is None):
        return f"error: {label} requires both endpoints (e.g. --{label}-lo and --{label}-hi)"
    if lo is not None and hi is not None and hi <= lo:
        return f"error: {label} end must be greater than start"
    return None

def _cli_load_trace(path: str) -> Tuple[Optional["BtfTrace"], Optional[str]]:
    """Load a .btf path, including ``archive.zip::member.btf`` zip members."""
    load_path = _normalize_open_path(path)
    zip_path, _member = _split_zip_member_path(load_path)
    if not os.path.isfile(zip_path):
        return None, f"error: trace file not found: {zip_path}"
    try:
        return _parse_btf(load_path), None
    except Exception as exc:
        return None, f"error: failed to parse {load_path}: {exc}"


def _cli_compare_pair_members(members: List[str]) -> Optional[List[str]]:
    """Pick exactly two ``.btf`` zip members for Trace Compare.

    Prefers two top-level members when present (ignores nested duplicates);
    otherwise requires the archive to contain exactly two ``.btf`` files.
    """
    if len(members) == 2:
        return list(members)
    top = [n for n in members if "/" not in n and "\\" not in n]
    if len(top) == 2:
        return top
    return None


def _cli_resolve_compare_traces(
    traces: List[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve compare inputs to two load paths.

    Accepts either two ``.btf`` / ``zip::member`` paths, or one ``.zip`` that
    contains exactly two ``.btf`` members (or exactly two at the archive root).
    """
    if len(traces) == 2:
        return (
            _normalize_open_path(traces[0]),
            _normalize_open_path(traces[1]),
            None,
        )
    if len(traces) != 1:
        return None, None, (
            "error: compare expects two .btf paths, or one .zip with two .btf members"
        )

    path = _normalize_open_path(traces[0])
    zip_path, member = _split_zip_member_path(path)
    if member:
        return None, None, (
            "error: a single zip::member path is not enough; "
            "pass two members (a.zip::a.btf a.zip::b.btf) or the zip alone"
        )
    if not os.path.isfile(zip_path):
        return None, None, f"error: trace file not found: {zip_path}"

    if _sniff_compression(zip_path) != "zip":
        return None, None, (
            "error: compare needs two traces; pass a second .btf or a .zip "
            "with two .btf members"
        )

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            members = _list_zip_btf_members(names)
    except (OSError, zipfile.BadZipFile) as exc:
        return None, None, f"error: failed to read zip: {exc}"

    if not members:
        return None, None, f"error: {_zip_no_btf_message(names)}"

    picked = _cli_compare_pair_members(members)
    if picked is None:
        listing = ", ".join(members[:12])
        more = "…" if len(members) > 12 else ""
        return None, None, (
            f"error: zip has {len(members)} .btf members "
            f"(need exactly two, or exactly two at the archive root); "
            f"found: {listing}{more}. "
            f"Pass two paths as archive.zip::member.btf …"
        )
    return (
        f"{zip_path}{_ZIP_MEMBER_SEP}{picked[0]}",
        f"{zip_path}{_ZIP_MEMBER_SEP}{picked[1]}",
        None,
    )

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
  snapshot     Export a PNG/SVG image (timeline, migration heatmap, or a
               statistics metric plot) without opening the GUI.
  perfetto     Export Chrome Trace JSON for https://ui.perfetto.dev
               (same as File → Export Perfetto…).

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
  %(prog)s run1.btf run2.btf                  open multiple traces (first tab active)

CLI examples:
  %(prog)s info tracedata/example-4cores.btf
  %(prog)s info tracedata/example-4cores.btf --json
  %(prog)s report tracedata/example-4cores.btf -o /tmp/stats.html
  %(prog)s report tracedata/example-4cores.btf -o /tmp/stats --format both
  %(prog)s compare run1.btf run2.btf -o /tmp/compare.html --name-a baseline --name-b tuned
  %(prog)s compare tracedata/tickless-8cores.zip -o /tmp/tick-policy.html
  %(prog)s migrations tracedata/example-4cores.btf -o /tmp/migrations.csv
  %(prog)s snapshot tracedata/example-4cores.btf -o /tmp/timeline.png --view timeline
  %(prog)s snapshot tracedata/example-4cores.btf -o /tmp/task.png --view plot --metric exec --task "Producer[1]"
  %(prog)s perfetto tracedata/example-4cores.btf -o /tmp/example.json

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

Inputs:
  Two paths     Trace A then Trace B (.btf, .btf.gz, .btf.bz2, or zip::member).
  One .zip      Archive with exactly two .btf members (or exactly two at the
                archive root — nested duplicates are ignored). Members are
                ordered top-level first, then lexicographically → Trace A, B.

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
  %(prog)s pair.zip -o compare.html
  %(prog)s tracedata/tickless-8cores.zip -o tick-policy.html \\
      --name-a Tickful --name-b Tickless
  %(prog)s pair.zip::a.btf pair.zip::b.btf -o cmp.csv --format csv
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

_CLI_EPILOG_PERFETTO = """\
Writes Chrome Trace Event Format JSON (no protobuf). Tracks:

  Cores       one row per core; slices named by the running task
  Tasks       one row per task; on-CPU run slices (core in args)
  STI         instant events per software-trace channel (+ TICK);
              tag and mutex/sem/queue channels are omitted when promoted below
  Intervals   paired interval_start / interval_stop spans (when present)
  Tags        counter tracks (ph:C) for tag0_event … tag7_event samples
  Sync        take/give (or send/recv) hold slices per mutex/sem/queue object

Optional --lo / --hi clip the export to a time window (native trace units).

examples:
  %(prog)s trace.btf -o trace.json
  %(prog)s tracedata/example-4cores.btf -o /tmp/example.json
  %(prog)s trace.btf -o scoped.json --lo 100000 --hi 500000
"""

_CLI_LO_HELP = (
    "range start (trace time units; must be used with --hi; "
    "see # timeScale in the .btf file)"
)
_CLI_HI_HELP = (
    "range end (trace time units; must be greater than --lo)"
)

_CLI_EPILOG_SNAPSHOT = """\
Views (--view):
  timeline   Main task/timeline view (like File -> Save Image / Save SVG).
             --task centers and highlights that task's row; --lo/--hi zoom
             to a time range first.  --view-mode core|task selects Core View
             or Task View (default: task).  With --task, the task is
             lock-highlighted and other tasks remain visible but grayed out
             (no filter).  --cpu-load appends the synchronised CPU Load strip;
             with a locked --task it shows that task's usage on each core.
             Without --lo/--hi the timeline fits the full trace (Fit to Window).
  heatmap    Migration Heatmap (core-pair x time-bin grid). --task is not
             supported (the heatmap is inherently cross-task); --lo/--hi
             scope the grid to a time range. --drill-row/--drill-bin drill
             into the per-task grid for one core-pair row and time bin
             (matrix-mode heatmaps, >16 cores, are not drillable headlessly).
  chord      Migration Chord Diagram (directional core-to-core migration
             volume as a circular chord diagram). --task/--drill-row/
             --drill-bin are not supported; --lo/--hi scope the diagram to
             a time range. Requires a multi-core trace (2+ cores).
  plot       A statistics metric scatter+histogram popup, selected with
             --metric:
               tick       tick-interval distribution (trace-wide, no --task)
               exec       task execution-time distribution   (--task)
               block      task blocking-time distribution     (--task)
               inter      task inter-arrival-time distribution (--task)
               priority   task priority-boost episodes         (--task)
               preempt    victim vs. one preemptor duration     (--task + --preemptor)
               interval   interval-id duration distribution     (--interval-id)
               tag        tag-channel value distribution        (--channel)
               tag_interval  time between consecutive samples on a tag channel (--channel)
               mig_dwell  on-core dwell time per migrated run    (--task)
               mig_rate   time between consecutive migrations    (--task)
               mig_gap    post-migration blocking-gap distribution (--task)
               pair_gap   post-migration gap for a core pair     (--from-core + --to-core)
               pair_rate  time between migrations on a core pair (--from-core + --to-core)

Sizing (--width/--height): only used for --view timeline / --view plot; the
heatmap and chord diagram image sizes are derived from their data (grid /
default dialog size respectively).

examples:
  %(prog)s trace.btf -o timeline.png --view timeline
  %(prog)s trace.btf -o timeline.svg --view timeline --task "Producer[1]" --lo 0 --hi 500000
  %(prog)s trace.btf -o migrate.svg --view timeline --view-mode task --task "CS[22]" --lo 1805000 --hi 1865000
  %(prog)s trace.btf -o cpu-load.svg --view timeline --view-mode task --task "CS[22]" --cpu-load
  %(prog)s trace.btf -o heatmap.png --view heatmap
  %(prog)s trace.btf -o heatmap-tasks.svg --view heatmap --drill-row 0 --drill-bin 3
  %(prog)s trace.btf -o chord.png --view chord
  %(prog)s trace.btf -o chord.svg --view chord
  %(prog)s trace.btf -o tick.svg --view plot --metric tick
  %(prog)s trace.btf -o exec.png --view plot --metric exec --task "Producer[1]"
  %(prog)s trace.btf -o preempt.png --view plot --metric preempt --task "Producer[1]" --preemptor "Consumer[2]"
  %(prog)s trace.btf -o interval.png --view plot --metric interval --interval-id 0
  %(prog)s trace.btf -o tag.png --view plot --metric tag --channel tag0_event
  %(prog)s trace.btf -o tag-interval.png --view plot --metric tag_interval --channel tag0_event
  %(prog)s trace.btf -o mig-dwell.svg --view plot --metric mig_dwell --task "CS[22]"
  %(prog)s trace.btf -o mig-rate.svg --view plot --metric mig_rate --task "CS[22]"
  %(prog)s trace.btf -o mig-gap.svg --view plot --metric mig_gap --task "CS[22]"
  %(prog)s trace.btf -o pair-gap.svg --view plot --metric pair_gap --from-core Core_0 --to-core Core_1
  %(prog)s trace.btf -o pair-rate.svg --view plot --metric pair_rate --from-core Core_5 --to-core Core_7
"""

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
            "Pass two .btf paths, or one .zip / .btf.zip that contains two "
            ".btf members (same multi-BTF zip the GUI opens as two tabs).\n\n"
            "Matches Trace Compare → Export CSV / Export HTML in the GUI."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_CLI_EPILOG_COMPARE,
    )
    compare.add_argument(
        "traces", nargs="+", metavar="TRACE",
        help=(
            "two .btf paths (Trace A then Trace B), or one .zip containing "
            "exactly two .btf members"
        ),
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
        help="display label for trace A (default: basename of Trace A)",
    )
    compare.add_argument(
        "--name-b", default=None, metavar="LABEL",
        help="display label for trace B (default: basename of Trace B)",
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

    snapshot = sub.add_parser(
        "snapshot",
        help="export a PNG/SVG image (timeline, migration heatmap, or a metric plot)",
        description=(
            "Export a PNG/SVG image without opening the GUI: the main timeline view, "
            "the Migration Heatmap, or a statistics metric scatter+histogram plot."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_CLI_EPILOG_SNAPSHOT,
    )
    snapshot.add_argument(
        "trace", metavar="trace.btf",
        help="path to the .btf trace file to render",
    )
    snapshot.add_argument(
        "-o", "--output", required=True, metavar="PATH",
        help="output image path (.png or .svg)",
    )
    snapshot.add_argument(
        "--format", choices=("png", "svg"), default=None, metavar="FMT",
        help="image format (default: infer from -o extension, else png)",
    )
    snapshot.add_argument(
        "--view", choices=("timeline", "heatmap", "chord", "plot"), required=True,
        help="which view to render",
    )
    snapshot.add_argument(
        "--task", default=None, metavar="NAME",
        help=(
            "task display name (e.g. 'Producer[1]'), bare name, or merge key; "
            "required for most --metric values, optional for --view timeline "
            "(highlights + centers that task), unused for --view heatmap/chord"
        ),
    )
    snapshot.add_argument(
        "--view-mode", choices=("task", "core"), default="task",
        dest="view_mode",
        help=(
            "timeline layout: task (one row per task, default) or core "
            "(one expandable row per CPU core).  With --task, lock-highlights "
            "that task and grays out others (no filter) "
            "(--view timeline only)"
        ),
    )
    snapshot.add_argument(
        "--cpu-load", action="store_true", dest="cpu_load",
        help=(
            "include the synchronised CPU Load strip under the timeline "
            "(--view timeline only).  With a locked --task, shows that task's "
            "usage on each core (one sparkline per core)"
        ),
    )
    snapshot.add_argument(
        "--metric",
        choices=("tick", "exec", "block", "inter", "priority", "preempt", "interval", "tag",
                "tag_interval", "mig_dwell", "mig_rate", "mig_gap", "pair_gap", "pair_rate"),
        default=None,
        help="metric to plot; required when --view plot",
    )
    snapshot.add_argument(
        "--preemptor", default=None, metavar="NAME",
        help="preemptor task name; required when --metric preempt",
    )
    snapshot.add_argument(
        "--interval-id", default=None, metavar="ID", dest="interval_id",
        help="interval id (e.g. '0'); required when --metric interval",
    )
    snapshot.add_argument(
        "--channel", default=None, metavar="NAME",
        help=(
            "tag channel (e.g. 'tag0_event') or bare index (e.g. '0'); "
            "required when --metric tag or tag_interval"
        ),
    )
    snapshot.add_argument(
        "--from-core", default=None, metavar="CORE", dest="from_core",
        help="source core (e.g. 'Core_0' or '0'); required for --metric pair_gap/pair_rate",
    )
    snapshot.add_argument(
        "--to-core", default=None, metavar="CORE", dest="to_core",
        help="destination core; required for --metric pair_gap/pair_rate",
    )
    snapshot.add_argument("--lo", type=int, default=None, metavar="T", help=_CLI_LO_HELP)
    snapshot.add_argument("--hi", type=int, default=None, metavar="T", help=_CLI_HI_HELP)
    snapshot.add_argument(
        "--drill-row", type=int, default=None, metavar="N", dest="drill_row",
        help=(
            "core-pair row index (0-based, top row = 0) to drill into the "
            "per-task grid; requires --drill-bin (--view heatmap only, not chord)"
        ),
    )
    snapshot.add_argument(
        "--drill-bin", type=int, default=None, metavar="N", dest="drill_bin",
        help=(
            "time-bin column index (0-based, leftmost = 0) to drill into the "
            "per-task grid; requires --drill-row (--view heatmap only)"
        ),
    )
    snapshot.add_argument(
        "--width", type=int, default=None, metavar="PX",
        help="image width in pixels (--view timeline default 1600, --view plot default 820)",
    )
    snapshot.add_argument(
        "--height", type=int, default=None, metavar="PX",
        help="image height in pixels (--view timeline default 900, --view plot default 620)",
    )
    snapshot.add_argument(
        "--theme", choices=("dark", "light"), default="dark",
        help="colour theme for the rendered image (default: dark)",
    )

    perfetto = sub.add_parser(
        "perfetto",
        help="export Chrome Trace JSON for ui.perfetto.dev (File → Export Perfetto…)",
        description=(
            "Export a Perfetto-compatible Chrome Trace Event JSON file.\n\n"
            "Open the result in https://ui.perfetto.dev (Open trace file).\n"
            "Matches File → Export Perfetto… in the GUI."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_CLI_EPILOG_PERFETTO,
    )
    perfetto.add_argument(
        "trace", metavar="trace.btf",
        help="path to the .btf trace file to export",
    )
    perfetto.add_argument(
        "-o", "--output", required=True, metavar="PATH",
        help="output Chrome Trace JSON path (e.g. trace.json)",
    )
    perfetto.add_argument("--lo", type=int, default=None, metavar="T", help=_CLI_LO_HELP)
    perfetto.add_argument("--hi", type=int, default=None, metavar="T", help=_CLI_HI_HELP)

    return parser, {
        "report": report,
        "compare": compare,
        "info": info,
        "migrations": migrations,
        "snapshot": snapshot,
        "perfetto": perfetto,
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
    panel._cpu_budget_pct = 0.0
    panel._task_deadlines_ns = {}
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

    path_a, path_b, err_paths = _cli_resolve_compare_traces(list(args.traces))
    if err_paths:
        print(err_paths, file=sys.stderr)
        return 1
    assert path_a is not None and path_b is not None

    trace_a, err_a = _cli_load_trace(path_a)
    if err_a:
        print(err_a, file=sys.stderr)
        return 1
    trace_b, err_b = _cli_load_trace(path_b)
    if err_b:
        print(err_b, file=sys.stderr)
        return 1

    name_a = args.name_a or _trace_display_name(path_a)
    name_b = args.name_b or _trace_display_name(path_b)
    scope_enabled = (lo_a is not None) or (lo_b is not None)
    tables = _build_trace_compare_rows(
        trace_a, trace_b, lo_a, hi_a, lo_b, hi_b)

    fmt, html_path, csv_path = _cli_export_output_paths(args.output, args.format)
    written: List[str] = []
    try:
        if fmt in ("html", "both"):
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(_build_compare_html(
                    name_a, name_b, scope_enabled, tables))
            written.append(html_path)
        if fmt in ("csv", "both"):
            text = _build_compare_csv(
                name_a, name_b, scope_enabled, tables)
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

# ---------------------------------------------------------------------------
# snapshot: headless PNG/SVG image export (timeline / heatmap / metric plot)
# ---------------------------------------------------------------------------

_CLI_SNAPSHOT_TASK_METRICS = ("exec", "block", "inter", "priority", "preempt")

def _cli_resolve_task(trace: "BtfTrace", name: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a --task/--preemptor NAME to a merge key.

    Matches (case-insensitively) against the display name (e.g. 'Producer[1]'),
    the raw merge key, and the bare name without the '[id]' suffix. Returns
    (merge_key, None) on a unique match, or (None, error_message) otherwise.
    """
    needle = name.strip().lower()
    exact: List[str] = []
    bare: List[str] = []
    for mk in trace.tasks:
        raw = trace.task_repr.get(mk, mk)
        disp = _task_display_name(raw)
        if disp.lower() == needle or mk.lower() == needle or raw.lower() == needle:
            exact.append(mk)
            continue
        if disp.split("[", 1)[0].strip().lower() == needle:
            bare.append(mk)
    matches = exact or bare
    if not matches:
        sample = ", ".join(
            _task_display_name(trace.task_repr.get(mk, mk)) for mk in trace.tasks[:20])
        more = ", ..." if len(trace.tasks) > 20 else ""
        return None, f"error: no task matches --task {name!r}. Available: {sample}{more}"
    if len(matches) > 1:
        names = ", ".join(_task_display_name(trace.task_repr.get(mk, mk)) for mk in matches)
        return None, f"error: --task {name!r} is ambiguous, matches: {names}"
    return matches[0], None

def _cli_resolve_interval_id(trace: "BtfTrace", value: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a --interval-id value to a valid trace interval id (exact match)."""
    needle = value.strip()
    if needle in trace.interval_ids:
        return needle, None
    sample = ", ".join(trace.interval_ids[:20])
    more = ", ..." if len(trace.interval_ids) > 20 else ""
    return (None,
            f"error: no interval matches --interval-id {value!r}. "
            f"Available: {sample or '(none — trace has no interval markers)'}{more}")

def _cli_resolve_tag_channel(trace: "BtfTrace", value: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a --channel value to a valid tag channel.

    Matches the raw channel name (e.g. 'tag0_event') case-insensitively, or a
    bare index (e.g. '0') expanded to 'tag{N}_event'.
    """
    needle = value.strip().lower()
    for ch in trace.tag_channels:
        if ch.lower() == needle:
            return ch, None
    candidate = f"tag{needle}_event"
    if candidate in trace.tag_channels:
        return candidate, None
    sample = ", ".join(trace.tag_channels[:20])
    more = ", ..." if len(trace.tag_channels) > 20 else ""
    return (None,
            f"error: no tag channel matches --channel {value!r}. "
            f"Available: {sample or '(none — trace has no tag channels)'}{more}")

def _cli_resolve_core(trace: "BtfTrace", value: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a --from-core/--to-core value to a core name in the trace."""
    needle = value.strip()
    if needle in trace.core_names:
        return needle, None
    if needle.isdigit():
        candidate = f"Core_{needle}"
        if candidate in trace.core_names:
            return candidate, None
    low = needle.lower()
    matches = [c for c in trace.core_names if c.lower() == low]
    if len(matches) == 1:
        return matches[0], None
    sample = ", ".join(trace.core_names[:20])
    more = ", ..." if len(trace.core_names) > 20 else ""
    return (None,
            f"error: no core matches {value!r}. Available: {sample or '(none)'}{more}")

def _cli_snapshot_output_path(output: str, fmt: Optional[str]) -> Tuple[str, str]:
    """Return (format, path) for the snapshot subcommand (default: png)."""
    low = output.lower()
    if fmt is None:
        fmt = "svg" if low.endswith(".svg") else "png"
    ext = f".{fmt}"
    path = output if low.endswith(ext) else f"{output}{ext}"
    return fmt, path

def _cli_save_widget_png(widget: "QWidget", path: str) -> bool:
    """Grab *widget* as displayed and save it as a PNG (bypasses SnapshotEditorDialog)."""
    pixmap, dpr = _normalize_grab_pixmap(widget.grab())
    return _save_snapshot_png(pixmap, path, dpr)

def _cli_save_widget_svg(widget: "QWidget", path: str, title: str) -> None:
    """Render *widget* to an SVG file (bypasses QFileDialog)."""
    sz = widget.size()
    gen = QSvgGenerator()
    gen.setFileName(path)
    gen.setSize(sz)
    gen.setViewBox(QRectF(0, 0, sz.width(), sz.height()))
    gen.setTitle(title)
    gen.setDescription("Generated by RTOS BTF Viewer")
    with _svg_safe_app_style():
        painter = QPainter(gen)
        try:
            widget.render(painter, QPoint(0, 0))
        finally:
            painter.end()

def _cli_save_timeline_svg(view: "TimelineView", path: str,
                           cpu_graph: Optional["_CpuLoadGraph"] = None) -> None:
    """Standalone equivalent of MainWindow._on_save_svg (optional CPU-load strip)."""
    scene = view._scene
    vp_rect = view.viewport().rect()
    scene_rect = QRectF(
        view.mapToScene(vp_rect.topLeft()),
        view.mapToScene(vp_rect.bottomRight()),
    )
    w, h = vp_rect.width(), vp_rect.height()
    cpu_h = cpu_graph.height() if cpu_graph is not None else 0
    total_h = h + cpu_h
    # Opaque canvas fill so transparent scene gaps do not show as white on
    # light page backgrounds (GitHub README light mode, etc.).
    canvas = (QColor("#1E1E1E") if getattr(scene, "_is_dark_ui", True)
              else QColor("#FFFFFF"))
    gen = QSvgGenerator()
    gen.setFileName(path)
    gen.setSize(QSize(int(w), int(total_h)))
    gen.setViewBox(QRectF(0, 0, w, total_h))
    gen.setTitle("BTF Timeline")
    gen.setDescription("Generated by RTOS BTF Viewer")
    with _svg_safe_app_style():
        painter = QPainter(gen)
        try:
            painter.fillRect(QRectF(0, 0, w, total_h), canvas)
            scene.render(painter, QRectF(0, 0, w, h), scene_rect)
            if cpu_graph is not None and cpu_h > 0:
                painter.translate(0, h)
                cpu_graph.render(painter, QPoint(0, 0))
                painter.translate(0, -h)
        finally:
            painter.end()


def _cli_save_timeline_png(view: "TimelineView", path: str,
                           cpu_graph: Optional["_CpuLoadGraph"] = None) -> None:
    """Capture timeline viewport (+ optional CPU Load strip) as PNG."""
    tl_pm, dpr = view._capture_pixmap()
    if cpu_graph is None:
        if not _save_snapshot_png(tl_pm, path, dpr):
            raise OSError(f"QPixmap.save() failed for path: {path}")
        return
    cpu_pm, _ = _normalize_grab_pixmap(cpu_graph.grab())
    w = max(tl_pm.width(), cpu_pm.width())
    out = QPixmap(w, tl_pm.height() + cpu_pm.height())
    out.setDevicePixelRatio(tl_pm.devicePixelRatio())
    # Opaque dark/light fill under the composite (same as SVG canvas fill).
    scene = view._scene
    canvas = (QColor("#1E1E1E") if getattr(scene, "_is_dark_ui", True)
              else QColor("#FFFFFF"))
    out.fill(canvas)
    p = QPainter(out)
    try:
        p.drawPixmap(0, 0, tl_pm)
        p.drawPixmap(0, tl_pm.height(), cpu_pm)
    finally:
        p.end()
    if not _save_snapshot_png(out, path, dpr):
        raise OSError(f"QPixmap.save() failed for path: {path}")

def _cli_scroll_view_to_task(view: "TimelineView", task_mk: str) -> None:
    """Standalone equivalent of MainWindow._scroll_view_to_task."""
    sc = view._scene
    orth = sc.task_orth_scene_coord(task_mk)
    if orth is None:
        return
    half = (sc._row_height / 2 if sc._horizontal
            else max(sc._row_height + sc._row_gap, 26) / 2)
    row_lo, row_hi = orth - half, orth + half
    vp = view.viewport().rect()
    if sc._horizontal:
        vp_lo = view.mapToScene(vp.topLeft()).y()
        vp_hi = view.mapToScene(vp.bottomLeft()).y()
        if row_lo >= vp_lo and row_hi <= vp_hi:
            return
        cur = view.mapToScene(vp.center())
        view.centerOn(cur.x(), orth)
    else:
        vp_lo = view.mapToScene(vp.topLeft()).x()
        vp_hi = view.mapToScene(vp.topRight()).x()
        if row_lo >= vp_lo and row_hi <= vp_hi:
            return
        cur = view.mapToScene(vp.center())
        view.centerOn(orth, cur.y())

def _cli_apply_heatmap_scope(dlg: "_MigrationHeatmapDialog",
                             lo: Optional[int], hi: Optional[int]) -> None:
    """Rebuild the level-0 grid for an explicit [lo, hi] scope.

    Standalone equivalent of _MigrationHeatmapDialog.refresh_scope(), which
    normally derives lo/hi from cursor times on a QMainWindow parent (there
    is none in headless CLI use).
    """
    if lo is None or hi is None:
        return
    trace = dlg._trace
    dlg._scope_lo, dlg._scope_hi = lo, hi
    dlg._scope_suffix = (
        f"  ({_format_time(lo, trace.time_scale)} \u2026 {_format_time(hi, trace.time_scale)})")
    if dlg._apply_scope_cache(lo, hi):
        dlg._go_level0()
        return
    pairs, grid, time_bins = _migration_heatmap_data(trace, lo, hi, bounce_only=dlg._bounce_only)
    dlg._pairs = pairs
    dlg._grid0 = grid
    if dlg._uses_matrix:
        dlg._matrix_cores, dlg._matrix_grid = _migration_heatmap_matrix(
            trace, lo, hi, bounce_only=dlg._bounce_only)
    span = max(hi - lo, 1)
    dlg._cache_scope_grid(lo, hi, pairs, grid, time_bins, lo, hi, span)
    dlg._ov_t_min, dlg._ov_t_max = lo, hi
    dlg._ov_bin_w = span / time_bins
    dlg._ov_time_bins = time_bins
    dlg._go_level0()

def _cli_snapshot_timeline(trace: "BtfTrace",
                          args: argparse.Namespace
                          ) -> Tuple[Optional["TimelineView"], Optional[str],
                                     Optional["_CpuLoadGraph"]]:
    if args.metric is not None:
        print("warning: --metric is ignored for --view timeline", file=sys.stderr)
    view_mode = getattr(args, "view_mode", "task") or "task"
    if view_mode not in ("task", "core"):
        return None, f"error: invalid --view-mode {view_mode!r} (use task or core)", None
    want_cpu = bool(getattr(args, "cpu_load", False))
    mk = None
    if args.task:
        mk, err = _cli_resolve_task(trace, args.task)
        if err:
            return None, err, None

    view = TimelineView()
    # Core View with a filtered task needs vertical room for one sub-row per core.
    default_h = 1100 if view_mode == "core" else 900
    view.resize(args.width or 1600, args.height or default_h)
    if args.theme == "light":
        view._scene.set_theme(False, rebuild=False)
    view.load_trace(trace)
    # Keep fit_mode off before show() so the debounced resize-to-fit handler
    # (triggered by show) cannot discard an upcoming --lo/--hi zoom.
    if args.lo is not None and args.hi is not None:
        view._fit_mode = False

    sc = view._scene
    if view_mode == "core":
        sc.set_view_mode("core")
        # Keep all tasks visible; --task only lock-highlights (others gray out).
        sc.set_all_cores_expanded(True)

    if mk is not None:
        sc.set_highlighted_task(mk, locked=True)
    view.show()
    _process_ui_events_safely()
    # Zoom *after* show/layout.  Pre-show viewport is only ~640×480 even after
    # resize(1600,900), so zoom_to_range would compute a too-coarse timescale
    # and the exported image would show ~3× more time than --lo/--hi.
    if args.lo is not None and args.hi is not None:
        view._scene.zoom_to_range(args.lo, args.hi, view._time_axis_viewport_px())
        view._navigate_time_to_ns((args.lo + args.hi) // 2)
        _process_ui_events_safely()
    else:
        # Fit to Window (Ctrl+0) — full trace span in the viewport.
        view.zoom_fit()
        _process_ui_events_safely()
    if mk is not None:
        _cli_scroll_view_to_task(view, mk)
    _process_ui_events_safely()

    cpu_graph = None
    if want_cpu:
        cpu_graph = _CpuLoadGraph(view)
        cpu_graph.set_dark(args.theme != "light")
        cpu_graph.set_view_mode(view_mode)
        cpu_graph.set_trace(trace)
        if mk is not None:
            cpu_graph.set_task(mk, True)
        cpu_h = max(cpu_graph.preferred_pane_height(), CPU_LOAD_ROW_H + 22)
        cpu_graph.setFixedSize(view.width(), cpu_h)
        cpu_graph.show()
        _process_ui_events_safely()
        # Keep bars in sync with the fitted/zoomed viewport.
        cpu_graph.update()
        _process_ui_events_safely()

    return view, None, cpu_graph

def _cli_apply_theme_chrome(app: "QApplication", is_dark: bool) -> None:
    """Apply the dark/light palette + minimal QSS for headless snapshot dialogs.

    ``_MetricsPlotDialog`` and friends paint their scatter/histogram canvases
    directly (respecting ``is_dark``), but plain Qt chrome around them
    (QComboBox, QLabel, and the QWidget containers that hold them, e.g. the
    "Histogram scale" toolbar) relies on the app-wide palette/QSS that
    ``MainWindow._apply_theme`` normally installs. The CLI's headless
    bootstrap (``_bootstrap_qt_app``) never runs that path, so without this,
    that chrome renders with the native/light OS palette even when
    ``--theme dark`` (the default) was requested — a white bar over an
    otherwise dark plot.
    """
    # Fusion avoids macOS QMacStyle + QSvgGenerator failures
    # (Unsupported paint engine type 8 / nullptr graphics context).
    _force_fusion_style(app)
    c = MainWindow._theme_tokens(is_dark)
    palette = QPalette()
    palette.setColor(QPalette.Window,          QColor(c['win_bg']))
    palette.setColor(QPalette.WindowText,      QColor(c['text']))
    palette.setColor(QPalette.Base,            QColor(c['win_base']))
    palette.setColor(QPalette.AlternateBase,   QColor(c['mid']))
    palette.setColor(QPalette.Text,            QColor(c['text']))
    palette.setColor(QPalette.Button,          QColor(c['mid']))
    palette.setColor(QPalette.ButtonText,      QColor(c['text']))
    palette.setColor(QPalette.Highlight,       QColor(c['accent']))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)
    app.setStyleSheet(f"""
        QComboBox {{ background:{c['combo_bg']}; color:{c['text']};
                     border:1px solid {c['input_border']}; border-radius:3px;
                     padding:2px 6px; min-height:1.6em; }}
        QComboBox QAbstractItemView {{ background:{c['combo_view_bg']}; color:{c['text']};
                     selection-background-color:{c['accent']}; selection-color:#FFFFFF; }}
        QLabel {{ color:{c['text']}; }}
    """)


def _cli_snapshot_heatmap(trace: "BtfTrace",
                         args: argparse.Namespace) -> Tuple[Optional["_MigrationHeatmapDialog"], Optional[str]]:
    if args.metric is not None:
        print("warning: --metric is ignored for --view heatmap", file=sys.stderr)
    if args.task:
        return None, "error: --task is not supported for --view heatmap (cross-task view)"
    if (args.drill_row is None) != (args.drill_bin is None):
        return None, "error: --drill-row requires --drill-bin (and vice versa)"
    dlg = _MigrationHeatmapDialog(trace, parent=None)
    if args.lo is not None and args.hi is not None:
        _cli_apply_heatmap_scope(dlg, args.lo, args.hi)
    if args.drill_row is not None:
        if dlg._uses_matrix:
            return None, (
                "error: --drill-row/--drill-bin is not supported for matrix-mode "
                "heatmaps (>16 cores); drill interactively in the GUI instead")
        row, bi = args.drill_row, args.drill_bin
        if row < 0 or row >= len(dlg._pairs):
            return None, f"error: --drill-row {row} out of range (0..{len(dlg._pairs) - 1})"
        if bi < 0 or bi >= dlg._time_bins:
            return None, f"error: --drill-bin {bi} out of range (0..{dlg._time_bins - 1})"
        if not dlg._grid0 or dlg._grid0[row][bi] <= 0:
            return None, f"error: no migrations at --drill-row {row} --drill-bin {bi}"
        fc, tc, label = dlg._pairs[row]
        bin_lo, bin_hi = _heatmap_bin_range(
            dlg._t_min, dlg._bin_w, dlg._time_bins, dlg._t_max, bi)
        dlg._go_level1(fc, tc, label, bin_lo, bin_hi, bi)
    dlg.show()
    _process_ui_events_safely()
    return dlg, None

def _cli_snapshot_chord(trace: "BtfTrace",
                        args: argparse.Namespace) -> Tuple[Optional["_ChordDiagramDialog"], Optional[str]]:
    if args.metric is not None:
        print("warning: --metric is ignored for --view chord", file=sys.stderr)
    if args.task:
        return None, "error: --task is not supported for --view chord (cross-task view)"
    if args.drill_row is not None or args.drill_bin is not None:
        return None, "error: --drill-row/--drill-bin are not supported for --view chord"
    if not _trace_is_multi_core(trace):
        return None, "error: --view chord requires a multi-core trace (2+ cores)"
    dlg = _ChordDiagramDialog(trace, parent=None)
    if args.lo is not None and args.hi is not None:
        dlg._scope_lo, dlg._scope_hi = args.lo, args.hi
        dlg._scope_suffix = (
            f"  ({_format_time(args.lo, trace.time_scale)} \u2026 "
            f"{_format_time(args.hi, trace.time_scale)})")
        dlg._reload_data()
        dlg._rebuild()
    if not dlg._has_data():
        return None, "error: no migrations in scope for --view chord"
    dlg.show()
    _process_ui_events_safely()
    return dlg, None

def _cli_snapshot_plot(trace: "BtfTrace",
                       args: argparse.Namespace) -> Tuple[Optional["_MetricsPlotDialog"], Optional[str]]:
    metric = args.metric
    if metric is None:
        return None, "error: --metric is required for --view plot"
    if metric == "tick":
        if args.task:
            return None, "error: --task is not used with --metric tick (trace-wide)"
        mk = "__tick_dist__"
    elif metric == "interval":
        if not args.interval_id:
            return None, "error: --interval-id is required for --metric interval"
        mk, err = _cli_resolve_interval_id(trace, args.interval_id)
        if err:
            return None, err
    elif metric in ("tag", "tag_interval"):
        if not args.channel:
            return None, f"error: --channel is required for --metric {metric}"
        mk, err = _cli_resolve_tag_channel(trace, args.channel)
        if err:
            return None, err
    elif metric in ("pair_gap", "pair_rate"):
        if not args.from_core or not args.to_core:
            return None, (
                f"error: --from-core and --to-core are required for --metric {metric}")
        fc, err = _cli_resolve_core(trace, args.from_core)
        if err:
            return None, err.replace("matches", "matches --from-core", 1)
        tc, err = _cli_resolve_core(trace, args.to_core)
        if err:
            return None, err.replace("matches", "matches --to-core", 1)
        mk = _pair_plot_key(fc, tc)
        if args.task:
            print("warning: --task is not used with --metric pair_gap/pair_rate",
                  file=sys.stderr)
    else:
        if not args.task:
            return None, f"error: --task is required for --metric {metric}"
        mk, err = _cli_resolve_task(trace, args.task)
        if err:
            return None, err
        if args.interval_id:
            print("warning: --interval-id is only used with --metric interval", file=sys.stderr)
        if args.channel:
            print("warning: --channel is only used with --metric tag/tag_interval", file=sys.stderr)
    if metric == "interval" and args.task:
        print("warning: --task is not used with --metric interval (use --interval-id)", file=sys.stderr)
    if metric in ("tag", "tag_interval") and args.task:
        print("warning: --task is not used with --metric tag/tag_interval (use --channel)", file=sys.stderr)
    if metric not in ("pair_gap", "pair_rate"):
        if args.from_core or args.to_core:
            print("warning: --from-core/--to-core are only used with "
                  "--metric pair_gap/pair_rate", file=sys.stderr)

    panel = _StatsPanel.__new__(_StatsPanel)
    panel._trace = trace
    panel._export_scope_override = None
    panel._scope_to_cursors = False
    panel._cursor_times = []
    panel._cpu_budget_pct = 0.0
    panel._task_deadlines_ns = {}
    panel._is_dark = (args.theme != "light")
    panel._plot_preemptor = None
    panel._plot_interval_id = None
    if args.lo is not None and args.hi is not None:
        panel._export_scope_override = (args.lo, args.hi)

    if metric == "preempt":
        if not args.preemptor:
            return None, "error: --preemptor is required for --metric preempt"
        preemptor_mk, err = _cli_resolve_task(trace, args.preemptor)
        if err:
            return None, err
        raw = trace.task_repr.get(preemptor_mk, preemptor_mk)
        panel._plot_preemptor = _task_display_name(raw)
    elif args.preemptor:
        print("warning: --preemptor is only used with --metric preempt", file=sys.stderr)

    built = panel._build_plot_points(trace, mk, metric)
    if built is None or not built[1]:
        detail = args.task or (
            f"{args.from_core}→{args.to_core}" if metric.startswith("pair_") else "n/a")
        return None, f"error: no data to plot for --metric {metric} ({detail})"
    title, pts, color = built
    scoped, badge, detail = panel._plot_scope_banner()
    y_as_time = metric not in ("tag",)
    dlg = _MetricsPlotDialog(
        title, pts, trace.time_scale, color,
        on_point_click=None,
        is_dark=panel._is_dark,
        scope_scoped=scoped,
        scope_badge=badge,
        scope_detail=detail,
        y_as_time=y_as_time,
        show_variability=metric in ("exec", "block", "inter"),
        parent=None,
    )
    if args.width or args.height:
        dlg.resize(args.width or dlg.width(), args.height or dlg.height())
    dlg.show()
    _process_ui_events_safely()
    _process_ui_events_safely()
    return dlg, None

def _cli_snapshot_run(args: argparse.Namespace) -> int:
    err = _cli_validate_range_pair(args.lo, args.hi, "range")
    if err:
        print(err, file=sys.stderr)
        return 1

    path = os.path.abspath(args.trace)
    trace, err_load = _cli_load_trace(path)
    if err_load:
        print(err_load, file=sys.stderr)
        return 1

    fmt, out_path = _cli_snapshot_output_path(args.output, args.format)

    _platform_preflight()
    app = _bootstrap_qt_app()
    _cli_apply_theme_chrome(app, args.theme != "light")

    cpu_graph = None
    if args.view == "timeline":
        widget, err, cpu_graph = _cli_snapshot_timeline(trace, args)
        title = "BTF Timeline"
    elif args.view == "heatmap":
        if getattr(args, "view_mode", "task") != "task":
            print("warning: --view-mode is ignored for --view heatmap", file=sys.stderr)
        if getattr(args, "cpu_load", False):
            print("warning: --cpu-load is ignored for --view heatmap", file=sys.stderr)
        widget, err = _cli_snapshot_heatmap(trace, args)
        title = "Migration Heatmap"
    elif args.view == "chord":
        if getattr(args, "view_mode", "task") != "task":
            print("warning: --view-mode is ignored for --view chord", file=sys.stderr)
        if getattr(args, "cpu_load", False):
            print("warning: --cpu-load is ignored for --view chord", file=sys.stderr)
        widget, err = _cli_snapshot_chord(trace, args)
        title = "Migration Chord Diagram"
    else:
        if getattr(args, "view_mode", "task") != "task":
            print("warning: --view-mode is ignored for --view plot", file=sys.stderr)
        if getattr(args, "cpu_load", False):
            print("warning: --cpu-load is ignored for --view plot", file=sys.stderr)
        widget, err = _cli_snapshot_plot(trace, args)
        title = widget.windowTitle() if widget is not None else "Metric Plot"
    if err:
        print(err, file=sys.stderr)
        return 1

    try:
        if args.view == "timeline":
            if fmt == "svg":
                _cli_save_timeline_svg(widget, out_path, cpu_graph)
            else:
                _cli_save_timeline_png(widget, out_path, cpu_graph)
        elif args.view == "heatmap":
            if fmt == "svg":
                widget._canvas.render_full_svg(out_path, title)
            elif not widget._canvas.render_full_pixmap().save(out_path):
                print(f"error: could not save PNG: {out_path}", file=sys.stderr)
                return 1
        elif args.view == "chord":
            if fmt == "svg":
                widget._canvas.render_full_svg(out_path, title)
            elif not _cli_save_widget_png(widget._canvas, out_path):
                print(f"error: could not save PNG: {out_path}", file=sys.stderr)
                return 1
        else:
            if fmt == "svg":
                _cli_save_widget_svg(widget._content, out_path, title)
            elif not _cli_save_widget_png(widget._content, out_path):
                print(f"error: could not save PNG: {out_path}", file=sys.stderr)
                return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            if cpu_graph is not None:
                cpu_graph.close()
            widget.close()
        except Exception:
            pass

    print(out_path)
    return 0

def _cli_snapshot_main(argv: List[str]) -> int:
    args = _make_arg_parser()[1]["snapshot"].parse_args(argv)
    return _cli_snapshot_run(args)

def _cli_perfetto_run(args: argparse.Namespace) -> int:
    path = os.path.abspath(args.trace)
    if (args.lo is None) ^ (args.hi is None):
        print("error: --lo and --hi must be given together", file=sys.stderr)
        return 1
    if args.lo is not None and args.hi is not None and args.hi <= args.lo:
        print("error: --hi must be greater than --lo", file=sys.stderr)
        return 1
    trace, err_load = _cli_load_trace(path)
    if err_load:
        print(err_load, file=sys.stderr)
        return 1
    out = os.path.abspath(args.output)
    try:
        export_perfetto(trace, out, lo=args.lo, hi=args.hi)
    except (OSError, TypeError, ValueError, AttributeError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(out)
    return 0

def _cli_perfetto_main(argv: List[str]) -> int:
    args = _make_arg_parser()[1]["perfetto"].parse_args(argv)
    return _cli_perfetto_run(args)

_CLI_COMMANDS = {
    "report": _cli_report_main,
    "compare": _cli_compare_main,
    "info": _cli_info_main,
    "migrations": _cli_migrations_main,
    "snapshot": _cli_snapshot_main,
    "perfetto": _cli_perfetto_main,
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
