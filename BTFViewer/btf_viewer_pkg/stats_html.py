"""Statistics HTML report helpers (Desktop). Keep in sync with web statsHtmlReport.js."""
from __future__ import annotations

import html
from typing import Sequence

from .html_report import html_section_slug

STATS_TOC_GROUPS = (
    ("Overview and Findings", (
        "Analysis Scope", "Evidence Refs", "Analysis Findings",
        "Trace Health Check", "Investigation", "Trace Metadata",
    )),
    ("CPU and Scheduling", (
        "Core Utilisation", "Trace Health (TICK)", "Core Time Breakdown",
        "Concurrent Core Active Distribution", "Switch Reason Breakdown",
        "Scheduling Load Over Time", "Kernel Switch Overhead", "Idle Analysis",
        "Top Tasks by CPU",
    )),
    ("Migrations and Core Affinity", (
        "Core Migrations", "Core-Pair Migration Summary", "Core Affinity",
        "Task × Core", "Core Utilization Over Time", "Task Lifecycle",
        "Deadlines / CPU budget", "Task Health",
    )),
    ("Timing, Latency and Jitter", (
        "Investigate Anomalies", "Execution Time Per Slice",
        "Off-CPU Time", "Dispatch / Scheduling Latency", "Inter-Arrival Time",
        "Activation Latency", "Ready-Gap (Starvation)",
        "Period / Jitter", "Response Time", "Unified Jitter",
    )),
    ("Synchronization and Custom Events", (
        "Preemption Chain Analysis", "Preemption Matrix", "Priority Inheritance",
        "Mutex / Semaphore", "Waiter × Owner", "Mutex Blocking", "Queue",
        "Queue Backlog / Semaphore Level",
        "Interval Analysis", "Tag Analysis", "Statistics Notes",
    )),
)

STATS_DEFAULT_EXPANDED = (
    "Analysis Scope",
    "Analysis Findings",
    "Trace Health Check",
    "Core Utilisation (excl. IDLE/TICK)",
    "Trace Health (TICK)",
    "Investigate Anomalies",
)

STATS_HTML_EXTRA_CSS = """
:root { --line-strong: #c8d2e0; --stripe: #f7f9fc; }
.report.report-wide { max-width: 1160px; }
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.kpi {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: 0 2px 8px rgba(30, 60, 90, 0.06);
}
.kpi .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.6px; }
.kpi .v { margin-top: 4px; font-size: 20px; font-weight: 700; color: #0f2b47; }
.kpi .s { margin-top: 2px; font-size: 12px; color: var(--muted); }
.kpi.warn { border-color: #e0a020; }
.kpi.error { border-color: #c0392b; }
.kpi.ok { border-color: #5FCF6F; }
.notes { border-left: 4px solid var(--accent); }
.notes ul { margin: 8px 0 0 18px; padding: 0; }
.notes li { margin: 6px 0; line-height: 1.45; }
table { border-collapse: separate; border-spacing: 0; width: 100%; }
th, td { border-bottom: 1px solid var(--line); padding: 8px 10px; font-size: 13px; text-align: right; }
th:first-child, td:first-child { text-align: left; }
thead th {
  background: #f1f5fb;
  color: #284563;
  font-weight: 600;
  border-top: 1px solid var(--line-strong);
  border-bottom: 1px solid var(--line-strong);
}
tbody tr:nth-child(even) td { background: var(--stripe); }
.empty { text-align: center !important; color: var(--muted); }
.detail-note { margin: 6px 0 8px; font-size: 12px; color: var(--muted); }
h3.sub { margin: 14px 0 8px; font-size: 14px; color: #284563; font-weight: 600; }
.sev-error { color: #c0392b; font-weight: 600; }
.sev-warning { color: #9a4d00; font-weight: 600; }
.finding-info { color: var(--ink, var(--fg, #182230)); }
.finding-ok { color: #166534; font-weight: 600; }
.findings-list { margin: 8px 0 0 18px; padding: 0; }
.findings-list li { margin: 8px 0; line-height: 1.45; }
.analysis-findings { border-left: 4px solid #c0392b; }
.trace-health { border-left: 4px solid var(--accent); }
.trace-health-status { font-size: 14px; font-weight: 600; margin: 6px 0 10px; }
.trace-health-check { margin: 6px 0; padding: 6px 0; border-bottom: 1px solid var(--line); }
.trace-health-check:last-of-type { border-bottom: 0; }
.trace-health-check > summary { cursor: pointer; line-height: 1.45; }
.trace-health-check .finding-meta { margin-left: 16px; }
.investigation { border-left: 4px solid #7a5cc0; }
.investigation .finding-meta ul { margin: 4px 0 0 16px; padding: 0; }
.investigation h3.sub { margin-top: 16px; }
.finding-cards { display: grid; gap: 10px; }
.finding-card {
  border: 1px solid var(--line);
  border-left-width: 4px;
  border-radius: 10px;
  padding: 10px 12px;
  background: #fff;
}
.finding-card.sev-error { border-left-color: #c0392b; }
.finding-card.sev-warning { border-left-color: #e0a020; }
.finding-card.finding-info { border-left-color: var(--accent); }
.finding-card.finding-ok { border-left-color: #5FCF6F; }
.finding-card h3 { margin: 0 0 6px; font-size: 14px; color: #123355; }
.finding-meta { font-size: 12px; color: var(--muted); margin: 4px 0; }
.finding-card a { color: var(--accent); }
.scope-table th { width: 28%; }
.heat-wrap { overflow-x: auto; margin: 8px 0 12px; }
.heat-cell { font-size: 10px; text-anchor: middle; }
.table-tools { margin: 8px 0 12px; }
.table-toolbar {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px;
}
.table-search {
  font: inherit; font-size: 12px; padding: 4px 8px; border: 1px solid var(--line);
  border-radius: 6px; min-width: 160px;
}
.table-check { font-size: 12px; color: var(--muted); display: inline-flex; gap: 4px; align-items: center; }
.table-count { font-size: 12px; color: var(--muted); margin-left: auto; }
.table-scroll { overflow-x: auto; max-width: 100%; }
.table-scroll table { min-width: 100%; }
.table-scroll thead th { position: sticky; top: 0; z-index: 2; }
.table-scroll td:first-child, .table-scroll th:first-child {
  position: sticky; left: 0; z-index: 1; background: #fff;
}
.table-scroll tbody tr:nth-child(even) td:first-child { background: var(--stripe); }
.sortable { cursor: pointer; }
.sortable:hover { color: var(--accent); }
.report-tabs .tab-bar { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 10px; }
.report-tabs .tab-btn {
  font: inherit; font-size: 12px; padding: 4px 10px; border: 1px solid var(--line);
  border-radius: 999px; background: #f1f5fb; color: var(--accent); cursor: pointer;
}
.report-tabs .tab-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.pct-bar { display: flex; align-items: center; gap: 8px; margin: 4px 0; font-size: 12px; }
.pct-bar .lab { flex: 0 0 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pct-bar .track { flex: 1; height: 10px; background: #eef2f7; border-radius: 6px; overflow: hidden; }
.pct-bar .fill { height: 100%; border-radius: 6px; }
@media (prefers-color-scheme: dark) {
  :root { --line-strong: #3a4048; --stripe: #191d23; }
  .kpi { background: var(--paper); }
  .kpi .v { color: #dbe6f2; }
  thead th { background: #232830; color: #b6c2cf; }
  .finding-card, .finding-card.sev-error, .finding-card.sev-warning { background: var(--paper); }
  .finding-card h3 { color: #cfe1f7; }
  h3.sub { color: #b6c2cf; }
  .sev-warning { color: #e0a44a; }
  .sev-error { color: #e5776a; }
  .finding-ok { color: #57c191; }
  .table-search { background: var(--paper); color: var(--ink); }
  .table-scroll td:first-child, .table-scroll th:first-child { background: var(--paper); }
  .table-scroll tbody tr:nth-child(even) td:first-child { background: var(--stripe); }
  .report-tabs .tab-btn { background: #232830; }
  .pct-bar .track { background: #232830; }
  .heat-cell { fill: var(--ink); }
}
""".strip()


def _esc(v: object) -> str:
    return html.escape(str(v), quote=True)


def html_inspect_href(section_title: str) -> str:
    return f"#sec-{html_section_slug(section_title)}"


def html_kpi(label: str, value: str, *, hint: str = "", kind: str = "") -> str:
    cls = f" kpi {kind}".rstrip() if kind else "kpi"
    extra = f'<div class="s">{_esc(hint)}</div>' if hint else ""
    return (
        f'<article class="{cls}"><div class="k">{_esc(label)}</div>'
        f'<div class="v">{_esc(value)}</div>{extra}</article>'
    )


def html_scope_identity_card(
    *,
    filename: str,
    scope_type: str,
    start: str,
    end: str,
    duration: str,
    cores: int,
    filters: str,
    timestamp_mode: str,
    task_count: int,
    sample_note: str = "",
) -> str:
    rows = [
        ("Trace file", filename or "—"),
        ("Scope", scope_type),
        ("Start", start),
        ("End", end),
        ("Duration", duration),
        ("Cores", f"{cores}"),
        ("Tasks in scope", f"{task_count:,}"),
        ("Filters", filters or "None"),
        ("Timestamps", timestamp_mode),
    ]
    body = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows
    )
    note = (
        f'<p class="detail-note">{_esc(sample_note)}</p>' if sample_note else ""
    )
    return (
        '<section class="report-card" id="sec-analysis-scope">'
        "<h2>Analysis Scope</h2>"
        f'<table class="meta-table scope-table"><tbody>{body}</tbody></table>'
        f"{note}</section>"
    )


def evidence_refs_from_findings(
    findings: Sequence[dict],
    *,
    format_ns=None,
    limit: int = 12,
) -> list:
    """Build ``{label, time_text}`` refs from Analysis Findings for HTML export."""
    out: list = []
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        label = str(f.get("title") or "Finding").strip() or "Finding"
        times: list = []
        for ev in f.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            for key in ("time", "start", "stop", "ns"):
                raw = ev.get(key)
                if raw is None:
                    continue
                try:
                    times.append(int(float(raw)))
                except (TypeError, ValueError):
                    continue
                break
        time_text = ""
        if times and callable(format_ns):
            try:
                time_text = ", ".join(str(format_ns(t)) for t in times[:3])
            except Exception:
                time_text = ", ".join(str(t) for t in times[:3])
        elif times:
            time_text = ", ".join(str(t) for t in times[:3])
        if not time_text:
            et = str(f.get("evidence_text") or "").strip()
            if et:
                time_text = et[:160]
        if not time_text:
            continue
        out.append({"label": label, "time_text": time_text})
        if len(out) >= max(1, int(limit or 12)):
            break
    return out


def html_evidence_refs_card(refs: Sequence[dict]) -> str:
    """Compact Evidence refs card (label + time) for investigation exports."""
    items = [r for r in (refs or []) if isinstance(r, dict) and (
        str(r.get("label") or "").strip() or str(r.get("time_text") or "").strip()
    )]
    if not items:
        return ""
    body = "".join(
        "<tr>"
        f"<td>{_esc(r.get('label') or 'Finding')}</td>"
        f"<td>{_esc(r.get('time_text') or '—')}</td>"
        "</tr>"
        for r in items
    )
    return (
        '<section class="report-card" id="sec-evidence-refs">'
        "<h2>Evidence Refs</h2>"
        '<p class="detail-note">Timestamps and measured evidence from Analysis Findings '
        "(export context; does not jump back into BTFViewer).</p>"
        '<table class="meta-table"><thead><tr><th>Finding</th><th>Evidence / Time</th>'
        f"</tr></thead><tbody>{body}</tbody></table></section>"
    )


def html_trace_metadata_card(
    *,
    span: str,
    tasks: int,
    segments: int,
    sti_events: int,
    context_switches: int,
    core_gap_avg: str = "",
    core_gap_max: str = "",
    scope_title: str = "",
) -> str:
    rows = [
        (f"Span{scope_title}", span),
        ("Tasks", f"{tasks:,}"),
        ("Segments", f"{segments:,}"),
        ("STI events", f"{sti_events:,}"),
        (f"Context switches{scope_title}", f"{context_switches:,}"),
    ]
    if core_gap_avg:
        rows.append((f"Core gap avg{scope_title}", core_gap_avg))
    if core_gap_max:
        rows.append((f"Core gap max{scope_title}", core_gap_max))
    body = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows
    )
    return (
        '<section class="report-card">'
        "<h2>Trace Metadata</h2>"
        '<p class="detail-note">Trace-size counts. Diagnostic KPIs above summarise health.</p>'
        f'<table class="meta-table"><tbody>{body}</tbody></table></section>'
    )


def html_diagnostic_kpi_grid(kpis: Sequence[dict]) -> str:
    parts = []
    for k in kpis or []:
        parts.append(html_kpi(
            k.get("label") or "",
            k.get("value") or "—",
            hint=k.get("hint") or "",
            kind=k.get("kind") or "",
        ))
    return f'<section class="kpi-grid">{"".join(parts)}</section>' if parts else ""


def _format_measured_values(values) -> str:
    """``[{name,value,unit,sample_count?}]`` → "Name value unit (n=…)" list.

    Kept separate from finding display text so exports stay reproducible and
    localizable (Investigation Findings data model).
    """
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return ""
    parts = []
    for mv in values:
        if not isinstance(mv, dict) or "name" not in mv or "value" not in mv:
            continue
        unit = str(mv.get("unit") or "")
        chunk = f"{mv['name']} {mv['value']}{unit}".rstrip()
        if mv.get("sample_count") is not None:
            chunk += f" (n={mv['sample_count']})"
        parts.append(chunk)
    return "; ".join(parts)


def html_finding_cards(findings: Sequence[dict], scope_title: str = "") -> str:
    if not findings:
        return ""
    cards = []
    for f in findings:
        sev = str(f.get("severity") or "info")
        cls = {
            "error": "sev-error",
            "warning": "sev-warning",
            "info": "finding-info",
        }.get(sev, "finding-info")
        if f.get("id") == "load_balance_ok":
            cls = "finding-ok"
        inspect = str(f.get("inspect") or "").strip()
        href = str(f.get("inspect_href") or "").strip()
        if inspect and not href:
            href = html_inspect_href(inspect)
        inspect_html = (
            f'<div class="finding-meta"><strong>Inspect:</strong> '
            f'<a href="{_esc(href)}">{_esc(inspect)}</a></div>'
            if inspect else ""
        )
        impact = str(f.get("impact") or "").strip()
        evidence = str(f.get("evidence_text") or "").strip()
        if not evidence:
            ev = f.get("evidence")
            if isinstance(ev, list) and ev:
                evidence = "; ".join(str(x) for x in ev if x)
            elif ev:
                evidence = str(ev)
        conf = str(f.get("confidence") or "").strip()
        basis = str(f.get("comparison_basis") or "").strip()
        measured = _format_measured_values(f.get("measured_values"))
        cards.append(
            f'<article class="finding-card {cls}">'
            f'<h3>{_esc(sev.title())} · {_esc(f.get("title") or "Finding")}</h3>'
            f'<p>{_esc(f.get("text") or "")}</p>'
            + (f'<div class="finding-meta"><strong>Impact:</strong> {_esc(impact)}</div>' if impact else "")
            + (f'<div class="finding-meta"><strong>Measured:</strong> {_esc(measured)}</div>' if measured else "")
            + (f'<div class="finding-meta"><strong>Basis:</strong> {_esc(basis)}</div>' if basis else "")
            + (f'<div class="finding-meta"><strong>Evidence:</strong> {_esc(evidence)}</div>' if evidence else "")
            + inspect_html
            + (f'<div class="finding-meta"><strong>Confidence:</strong> {_esc(conf)}</div>' if conf else "")
            + "</article>"
        )
    return (
        f'<section class="report-card notes analysis-findings">'
        f"<h2>Analysis Findings{_esc(scope_title)}</h2>"
        '<p class="detail-note">Heuristic summary of load balance, CPU consumers, '
        "off-CPU gaps, thrashing, deadlines, tick health, and sync. "
        "Exported links open the matching report section; they do not jump back into BTFViewer.</p>"
        f'<div class="finding-cards">{"".join(cards)}</div></section>'
    )


_TRACE_HEALTH_STATUS_META = {
    "pass": ("finding-ok", "Pass"),
    "caution": ("sev-warning", "Caution"),
    "insufficient": ("sev-error", "Insufficient data"),
}


def html_trace_health_card(
    result: dict,
    *,
    format_ns=None,
    scope_title: str = "",
) -> str:
    """Structural Trace Health section (status + per-check detail + limitations).

    Distinct from *Trace Health (TICK)*: this reports whether the parsed event
    model is internally consistent enough to trust the derived statistics.
    Keep in sync with ``web/src/utils/statsHtmlReport.js``.
    """
    if not result:
        return ""
    status = str(result.get("status") or "pass")
    cls, label = _TRACE_HEALTH_STATUS_META.get(status, ("finding-info", status.title()))
    checks = list(result.get("checks") or [])
    n = int(result.get("issue_count") or 0)

    def _fmt(v) -> str:
        if callable(format_ns):
            try:
                return str(format_ns(int(v)))
            except Exception:
                return str(v)
        return str(v)

    rows = []
    for c in checks:
        sev = str(c.get("severity") or "info")
        sev_cls = {"error": "sev-error", "warning": "sev-warning"}.get(sev, "finding-info")
        meta_bits = []
        rng = c.get("affected_range")
        if isinstance(rng, dict) and rng.get("start") is not None:
            meta_bits.append(
                f"<strong>Range:</strong> {_esc(_fmt(rng.get('start')))} – "
                f"{_esc(_fmt(rng.get('end')))}"
            )
        ents = [str(e) for e in (c.get("affected_entities") or []) if str(e)]
        if ents:
            meta_bits.append(
                f"<strong>Affected:</strong> {_esc(', '.join(ents[:12]))}"
            )
        refs = [str(r) for r in (c.get("evidence_refs") or []) if str(r)]
        if refs:
            meta_bits.append(
                f"<strong>Evidence:</strong> {_esc('; '.join(refs))}"
            )
        lims = [str(m) for m in (c.get("metric_limitations") or []) if str(m)]
        if lims:
            meta_bits.append(
                f"<strong>Limited:</strong> {_esc(', '.join(lims))}"
            )
        meta_html = "".join(
            f'<div class="finding-meta">{bit}</div>' for bit in meta_bits
        )
        rows.append(
            f'<details class="trace-health-check {sev_cls}">'
            f"<summary>{_esc(sev.title())} · {_esc(c.get('summary') or '')}</summary>"
            f"{meta_html}</details>"
        )

    if checks:
        detail = "".join(rows)
    else:
        detail = (
            '<p class="detail-note">No structural inconsistencies found in the '
            "parsed event model under the current checks.</p>"
        )

    limitations = [str(m) for m in (result.get("metric_limitations") or []) if str(m)]
    lim_html = ""
    if limitations:
        lis = "".join(f"<li>{_esc(m)}</li>" for m in limitations)
        lim_html = (
            '<h3 class="sub">Limited metrics</h3>'
            '<p class="detail-note">These sections may show <em>Insufficient data</em> '
            "or a limitation notice instead of a value.</p>"
            f"<ul>{lis}</ul>"
        )

    return (
        '<section class="report-card notes trace-health">'
        f"<h2>Trace Health Check{_esc(scope_title)}</h2>"
        '<p class="detail-note">Deterministic structural checks on the parsed '
        "event model. Independent of AI and of <em>Trace Health (TICK)</em>, "
        "which only measures tick regularity.</p>"
        f'<p class="trace-health-status"><span class="{cls}">Status: {_esc(label)}</span>'
        f" &middot; {n} issue(s)</p>"
        f"{detail}{lim_html}</section>"
    )


def _heat_color(frac: float) -> str:
    f = max(0.0, min(1.0, float(frac)))
    r = int(241 + (192 - 241) * f)
    g = int(245 + (57 - 245) * f)
    b = int(251 + (43 - 251) * f)
    return f"rgb({r},{g},{b})"


def html_matrix_heatmap(
    row_labels: Sequence[str],
    col_labels: Sequence[str],
    cells: Sequence[Sequence[float]],
    *,
    title: str,
    unit: str = "%",
    width: int = 640,
) -> str:
    rows = list(row_labels or [])
    cols = list(col_labels or [])
    if not rows or not cols:
        return ""
    max_v = 0.0
    for line in cells or []:
        for v in line:
            try:
                max_v = max(max_v, float(v or 0))
            except (TypeError, ValueError):
                pass
    max_v = max(max_v, 1.0)
    label_w = 88
    head_h = 36
    cell = 22
    w = max(width, label_w + 12 + len(cols) * cell)
    h = head_h + 8 + len(rows) * cell + 8
    parts = [
        f'<div class="heat-wrap"><svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
        f'aria-label="{_esc(title)}">',
        f'<text x="8" y="16" font-size="12" fill="#123355" font-weight="600">'
        f"{_esc(title)}</text>",
    ]
    for j, col in enumerate(cols):
        x = label_w + j * cell + cell / 2
        lab = _esc(str(col)[:10])
        parts.append(
            f'<text x="{x:.1f}" y="{head_h - 4}" font-size="9" fill="#5f6f82" '
            f'text-anchor="middle">{lab}</text>'
        )
    for i, row in enumerate(rows):
        y = head_h + i * cell
        parts.append(
            f'<text x="8" y="{y + 15}" font-size="10" fill="#182230">'
            f"{_esc(str(row)[:14])}</text>"
        )
        line = cells[i] if i < len(cells) else []
        for j, _col in enumerate(cols):
            raw = line[j] if j < len(line) else 0
            try:
                val = float(raw or 0)
            except (TypeError, ValueError):
                val = 0.0
            x = label_w + j * cell
            color = _heat_color(val / max_v) if val > 0 else "#f7f9fc"
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell - 2}" height="{cell - 2}" '
                f'rx="3" fill="{color}"/>'
            )
            if val > 0:
                label = f"{val:.0f}{unit}" if unit == "%" else f"{val:.0f}"
                parts.append(
                    f'<text class="heat-cell" x="{x + (cell - 2) / 2:.1f}" y="{y + 14:.1f}" '
                    f'fill="#123355">{_esc(label)}</text>'
                )
    parts.append("</svg></div>")
    return "".join(parts)


def html_percentile_bars(
    rows: Sequence[dict],
    *,
    title: str = "Response P50–P99",
    width: int = 640,
) -> str:
    items = [r for r in (rows or []) if isinstance(r, dict)][:12]
    if not items:
        return ""
    max_v = 1.0
    for r in items:
        max_v = max(max_v, float(r.get("p99_ns") or r.get("max_ns") or 0), 1.0)
    label_w = 110
    pad = 12
    row_h = 22
    header = 28
    h = header + len(items) * row_h + 10
    plot_w = max(80.0, width - label_w - pad - 80)
    parts = [
        f'<div class="heat-wrap"><svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {h}" width="{width}" height="{h}" role="img" '
        f'aria-label="{_esc(title)}">',
        f'<text x="{pad}" y="16" font-size="12" fill="#123355" font-weight="600">'
        f"{_esc(title)}</text>",
        f'<text x="{width - pad}" y="16" text-anchor="end" font-size="11" fill="#5f6f82">'
        "interval = P50–P99</text>",
    ]
    for i, r in enumerate(items):
        y = header + i * row_h
        lab = _esc(str(r.get("task") or "")[:16])
        p50 = float(r.get("p50_ns") or 0)
        p95 = float(r.get("p95_ns") or 0)
        p99 = float(r.get("p99_ns") or 0)
        x0 = label_w + plot_w * p50 / max_v
        x1 = label_w + plot_w * max(p99, p50) / max_v
        x95 = label_w + plot_w * p95 / max_v
        parts.append(f'<text x="8" y="{y + 14}" font-size="11" fill="#182230">{lab}</text>')
        parts.append(
            f'<rect x="{x0:.1f}" y="{y + 6}" width="{max(x1 - x0, 2):.1f}" height="8" '
            f'rx="3" fill="#9ec5e8"/>'
        )
        parts.append(
            f'<line x1="{x95:.1f}" y1="{y + 4}" x2="{x95:.1f}" y2="{y + 16}" '
            f'stroke="#2a6fb2" stroke-width="2"/>'
        )
    parts.append("</svg></div>")
    return "".join(parts)


def html_health_bars(rows: Sequence[dict], *, width: int = 640) -> str:
    items = [r for r in (rows or []) if isinstance(r, dict)]
    items = sorted(items, key=lambda r: int(r.get("score") or 0))[:16]
    if not items:
        return ""
    parts = ['<div class="health-bars">']
    for r in items:
        score = int(r.get("score") or 0)
        marks = r.get("marks") or {}
        reasons = [k for k, v in marks.items() if v]
        reason = ", ".join(reasons) if reasons else "no deductions"
        color = "#c0392b" if score < 50 else "#e0a020" if score < 80 else "#1a8a2a"
        parts.append(
            f'<div class="pct-bar"><span class="lab" title="{_esc(r.get("task") or "")}">'
            f'{_esc(str(r.get("task") or "")[:18])}</span>'
            f'<div class="track"><div class="fill" style="width:{score}%;background:{color}"></div></div>'
            f'<span>{score} · {_esc(reason)}</span></div>'
        )
    parts.append("</div>")
    del width
    return "".join(parts)


def html_tag_overview(
    samples: Sequence[dict],
    *,
    time_fmt,
    max_rows: int = 12,
) -> str:
    by_label: dict = {}
    for s in samples or []:
        if not isinstance(s, dict):
            continue
        lab = str(s.get("label") or s.get("tag") or "")
        by_label.setdefault(lab, []).append(s)
    if not by_label:
        return '<p class="empty">No tag samples in scope</p>'
    blocks = []
    for lab, group in list(by_label.items())[:8]:
        vals = []
        for s in group:
            try:
                vals.append(float(str(s.get("value") or "0").replace(",", "")))
            except (TypeError, ValueError):
                continue
        if not vals:
            continue
        transitions = 0
        plateau = 1
        run = 1
        for i in range(1, len(vals)):
            if vals[i] != vals[i - 1]:
                transitions += 1
                plateau = max(plateau, run)
                run = 1
            else:
                run += 1
        plateau = max(plateau, run)
        unique = len(set(vals))
        mn, mx = min(vals), max(vals)
        spark = _sparkline(vals)
        extrema = sorted(group, key=lambda s: float(str(s.get("value") or 0).replace(",", "") or 0))
        shown = []
        if extrema:
            shown.append(extrema[0])
            if extrema[-1] is not extrema[0]:
                shown.append(extrema[-1])
            shown.append(group[0])
            if group[-1] not in shown:
                shown.append(group[-1])
        rows = "".join(
            f"<tr><td>{_esc(s.get('time') if not callable(time_fmt) else time_fmt(s))}</td>"
            f"<td>{_esc(s.get('value'))}</td><td>{_esc(s.get('core') or '—')}</td></tr>"
            for s in shown[:max_rows]
        )
        blocks.append(
            f"<h3 class=\"sub\">{_esc(lab)}</h3>"
            f'<p class="detail-note">{len(group)} samples · {unique} distinct values · '
            f"{transitions} transitions · longest plateau {plateau} · "
            f"min {mn:g} / max {mx:g}</p>"
            f"{spark}"
            f"<table><thead><tr><th>Time</th><th>Value</th><th>Core</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    return "".join(blocks) or '<p class="empty">No tag samples in scope</p>'


def _sparkline(vals: Sequence[float], *, width: int = 420, height: int = 48) -> str:
    if len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals)
    span = (mx - mn) or 1.0
    n = len(vals)
    pts = []
    for i, v in enumerate(vals[:200]):
        x = 4 + (width - 8) * i / max(n - 1, 1)
        y = height - 6 - (height - 12) * ((v - mn) / span)
        pts.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="Tag time series">'
        f'<polyline fill="none" stroke="#2a6fb2" stroke-width="1.5" '
        f'points="{" ".join(pts)}"/></svg>'
    )


_BM_TYPE_LABELS = {
    "observation": "Observation",
    "hypothesis": "Hypothesis",
    "supporting": "Supporting evidence",
    "contradicting": "Contradicting evidence",
    "verification": "Verification step",
    "conclusion": "Conclusion",
}
_FACT_TYPES = ("observation", "supporting", "verification")


def _fmt_ref(ref: dict, format_ns=None) -> str:
    kind = str(ref.get("kind") or "")
    if kind == "finding":
        return f"finding <code>{_esc(ref.get('rule_id') or ref.get('label') or '?')}</code>"
    if kind == "metric":
        return f"metric “{_esc(ref.get('metric') or ref.get('label') or '?')}”"
    if kind == "entity":
        return f"entity <code>{_esc(ref.get('entity') or ref.get('label') or '?')}</code>"
    if kind in ("range", "evidence"):
        rng = ref.get("range") or {}
        def _f(v):
            if callable(format_ns):
                try:
                    return str(format_ns(int(v)))
                except Exception:
                    return str(v)
            return str(v)
        if rng.get("start") is not None:
            return f"range {_esc(_f(rng['start']))} – {_esc(_f(rng['end']))}"
        if ref.get("time") is not None:
            return f"time {_esc(_f(ref['time']))}"
    return _esc(ref.get("label") or kind or "ref")


def html_investigation_section(
    investigation: dict,
    *,
    format_ns=None,
    broken_refs: dict = None,
    chains: "Sequence[dict]" = None,
    scope_title: str = "",
) -> str:
    """Investigation Bookmarks and Evidence Chain section for the HTML report.

    Facts, hypotheses, contradicting evidence and conclusions are kept in
    separate blocks; every conclusion lists the bookmarks that back it. Stale
    references are flagged. Keep in sync with
    ``web/src/utils/statsHtmlReport.js:htmlInvestigationSection``.
    """
    if not investigation:
        return ""
    bookmarks = list(investigation.get("bookmarks") or [])
    if not bookmarks and not str(investigation.get("conclusion") or "").strip():
        return ""

    broken = broken_refs or {}
    broken_by_bm: dict = {}
    for iss in broken.get("issues") or []:
        broken_by_bm.setdefault(str(iss.get("bookmark_id")), []).append(iss)

    chains_by_id = {
        str(c.get("conclusion_id")): c for c in (chains or [])
        if isinstance(c, dict)
    }

    def _bm_card(b: dict) -> str:
        bid = str(b.get("id") or "")
        refs = b.get("refs") or []
        ref_html = ""
        if refs:
            items = "".join(f"<li>{_fmt_ref(r, format_ns)}</li>" for r in refs)
            ref_html = f'<div class="finding-meta"><strong>References:</strong><ul>{items}</ul></div>'
        note = str(b.get("note") or "").strip()
        note_html = f"<p>{_esc(note)}</p>" if note else ""
        bad = broken_by_bm.get(bid) or []
        bad_html = ""
        if bad:
            reasons = "; ".join(_esc(i.get("reason") or "stale reference") for i in bad)
            bad_html = f'<div class="finding-meta sev-warning"><strong>Stale:</strong> {reasons}</div>'
        return (
            f'<article class="finding-card">'
            f'<h3>{_esc(_BM_TYPE_LABELS.get(b.get("type"), "Bookmark"))} · {_esc(b.get("title") or "Bookmark")}</h3>'
            f"{note_html}{ref_html}{bad_html}</article>"
        )

    def _group(title: str, types) -> str:
        rows = [_bm_card(b) for b in bookmarks if b.get("type") in types]
        if not rows:
            return ""
        return f'<h3 class="sub">{_esc(title)}</h3><div class="finding-cards">{"".join(rows)}</div>'

    facts = _group("Facts", _FACT_TYPES)
    hyps = _group("Hypotheses", ("hypothesis",))
    contra = _group("Contradicting evidence", ("contradicting",))

    # Conclusions + their evidence chains.
    concl_rows = []
    for b in bookmarks:
        if b.get("type") != "conclusion":
            continue
        chain = chains_by_id.get(str(b.get("id")))
        chain_html = ""
        if chain and chain.get("evidence"):
            items = "".join(
                f"<li>{_esc(_BM_TYPE_LABELS.get(e.get('type'), 'Bookmark'))}: {_esc(e.get('title') or e.get('id'))}</li>"
                for e in chain["evidence"]
            )
            chain_html = f'<div class="finding-meta"><strong>Backed by:</strong><ul>{items}</ul></div>'
        elif chain is not None:
            chain_html = '<div class="finding-meta sev-warning"><strong>Not grounded:</strong> no linked evidence.</div>'
        concl_rows.append(
            f'<article class="finding-card finding-ok">'
            f'<h3>Conclusion · {_esc(b.get("title") or "Conclusion")}</h3>'
            + (f"<p>{_esc(b.get('note'))}</p>" if str(b.get("note") or "").strip() else "")
            + chain_html + "</article>"
        )
    free_concl = str(investigation.get("conclusion") or "").strip()
    if free_concl:
        concl_rows.append(
            f'<article class="finding-card finding-ok"><h3>Conclusion</h3>'
            f"<p>{_esc(free_concl)}</p></article>"
        )
    concl_html = (
        f'<h3 class="sub">Conclusions</h3><div class="finding-cards">{"".join(concl_rows)}</div>'
        if concl_rows else ""
    )

    questions = [str(q) for q in (investigation.get("unresolved_questions") or []) if str(q).strip()]
    q_html = ""
    if questions:
        lis = "".join(f"<li>{_esc(q)}</li>" for q in questions)
        q_html = f'<h3 class="sub">Unresolved questions</h3><ul>{lis}</ul>'

    stale_banner = ""
    if broken.get("stale_trace"):
        stale_banner = (
            '<p class="detail-note sev-warning">The source trace changed since '
            "these notes were written — references may not line up.</p>"
        )

    ident = investigation.get("trace_identity") or {}
    rng = investigation.get("analysis_range") or {}
    ident_bits = []
    if ident.get("file"):
        ident_bits.append(f"Trace: {_esc(ident['file'])}")
    if isinstance(rng, dict) and rng.get("start") is not None and callable(format_ns):
        try:
            ident_bits.append(
                f"Range: {_esc(str(format_ns(int(rng['start']))))} – "
                f"{_esc(str(format_ns(int(rng['end']))))}")
        except Exception:
            pass
    ident_html = (
        f'<p class="detail-note">{" · ".join(ident_bits)}</p>' if ident_bits else ""
    )

    title = str(investigation.get("title") or "").strip()
    heading = f"Investigation{_esc(scope_title)}"
    return (
        '<section class="report-card notes investigation">'
        f"<h2>{heading}</h2>"
        + (f'<p class="detail-note"><strong>{_esc(title)}</strong></p>' if title else "")
        + '<p class="detail-note">User-authored bookmarks and the evidence chain. '
        "Facts, hypotheses, contradicting evidence and conclusions are separated; "
        "notes never change measured values.</p>"
        + stale_banner + ident_html
        + facts + hyps + contra + concl_html + q_html
        + "</section>"
    )


def html_investigate_anomalies(
    *,
    anomalies_table: str,
    worst_table: str,
    patterns_table: str,
    crit_path_table: str,
    crit_note: str,
    scope_title: str = "",
) -> str:
    return (
        f'<section class="report-card"><h2>Investigate Anomalies{_esc(scope_title)}</h2>'
        '<p class="detail-note">Timeline anomalies, longest events, repeating kinds, '
        "and the longest heuristic ready-to-completion windows. "
        "Critical Path components can overlap; they are not additive parts of Duration.</p>"
        '<div class="report-tabs">'
        '<div class="tab-bar">'
        '<button type="button" class="tab-btn" data-tab="anomalies">Timeline Anomalies</button>'
        '<button type="button" class="tab-btn" data-tab="worst">Worst Events</button>'
        '<button type="button" class="tab-btn" data-tab="patterns">Recurring Patterns</button>'
        '<button type="button" class="tab-btn" data-tab="crit">Critical Path</button>'
        "</div>"
        f'<div data-panel="anomalies">{anomalies_table}</div>'
        f'<div data-panel="worst">{worst_table}</div>'
        f'<div data-panel="patterns">{patterns_table}</div>'
        f'<div data-panel="crit">{crit_note}{crit_path_table}</div>'
        "</div></section>"
    )


def html_glossary(*, range_note: str = "") -> str:
    note = (range_note or "").strip()
    if note.startswith("<li>") and note.endswith("</li>"):
        note = note[4:-5].strip()
    items = [
        note,
        "<strong>Execution Time Per Slice:</strong> Duration of each continuous task run between two context switches.",
        "<strong>Highest CPU consumers</strong> are tasks with the largest share of active CPU time. "
        "They are not automatically WCET candidates. Largest execution-time maxima live in Execution Time Per Slice.",
        "<strong>Inter-Arrival Time:</strong> Time between consecutive activations of the same task (slice start to next slice start).",
        "<strong>Off-CPU Time (Blocking Time):</strong> Gap between the end of one slice and the start of the next for the same task. "
        "It may include preemption, suspension, periodic waiting, or scheduling delay — not necessarily resource blocking. "
        "It is not end-to-end response time.",
        "<strong>CPU% (task):</strong> Share of total non-IDLE/TICK <em>active CPU time</em> in scope, not wall-clock span and not total multicore capacity.",
        "<strong>Core utilisation:</strong> Non-IDLE/TICK active time on that core divided by the scoped wall-clock span (one-core capacity = 100%).",
        "<strong>Load Balance Score:</strong> 100% × (1 − Gini of core utilisation). "
        "100 = evenly distributed utilisation; 0 = highly uneven. Even overload or even idle can still score high.",
        "<strong>Preemption Chain Analysis:</strong> For each off-CPU gap of a victim task, which task ran on the same core during that gap.",
        "<strong>Priority Inheritance:</strong> Tasks boosted above base priority when <code>create pri:N</code> and <code>set_priority</code> STI events are present.",
        "<strong>Mutex / Semaphore:</strong> Paired <code>take</code>/<code>give</code> STI events by object pointer.",
        "<strong>Interval Analysis:</strong> Paired <code>interval_start</code> / <code>interval_stop</code> STI events by id.",
        "<strong>Tag Analysis:</strong> Numeric samples from tag STI channels. Repeated identical values are summarised as a time series, not dumped row-by-row.",
        "<strong>Task × Core:</strong> Per-task execution share of the scoped span on each core.",
        "<strong>Task Health:</strong> Heuristic 0–100 score from measured statistics, not an AI probability.",
        "<strong>Response Time:</strong> Heuristic ready→completion from adjacent slices. Not an explicit BTF release/completion pair.",
        "<strong>Critical Path:</strong> Longest heuristic response windows. Exec is own on-CPU time; Off-CPU is Duration − Exec. "
        "Preempt, Wait, and Migration overlap and are not a stacked split of Duration.",
        "<strong>Period / Jitter:</strong> Median inter-arrival as expected period, with RMS jitter, CV, missed (&gt; 1.5×) and extra (&lt; 0.5×) activations.",
        "<strong>Min:</strong> Smallest observed sample in scope. It does not prove zero system load.",
        "<strong>Max:</strong> Largest observed sample in scope. It is an observed peak, not a guaranteed WCET.",
        "<strong>Average (Mean):</strong> Arithmetic mean; outliers can skew it.",
        "<strong>TrimMean(5%):</strong> Mean after dropping the fastest and slowest 5%.",
        "<strong>Jitter:</strong> Observed spread (Max − Min) for samples in scope.",
        "<strong>σ:</strong> Population standard deviation of samples in scope.",
        "<strong>P50 (Median):</strong> Half the samples are at or below this value.",
        "<strong>P95 / P99:</strong> Percentile of the observed distribution. Usefulness depends on the deadline or acceptance criterion; P95 is not universally the best user-experience metric for real-time systems.",
    ]
    lis = "".join(f"<li>{item}</li>" for item in items if item)
    return (
        '<section class="report-card notes"><h2>Statistics Notes</h2>'
        '<p class="detail-note">Glossary of metric definitions used in this report.</p>'
        f"<ul>{lis}</ul></section>"
    )


