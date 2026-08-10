"""Render a mermaid sequence/flowchart subset to SVG (no JS engine).

Used by the Desktop AI pane (QTextBrowser) and HTML export. Web uses the same
layout rules in ``web/src/utils/aiMermaid.js`` so diagrams stay in sync.
"""
from __future__ import annotations

import base64
import html
import re
from typing import Dict, List, Optional, Sequence, Tuple

_PARTICIPANT_RE = re.compile(
    r"^participant\s+(\S+)(?:\s+as\s+(.+))?$", re.IGNORECASE
)
_ARROW_RE = re.compile(
    r"^(\S+)\s*(-->>|->>|->|--x|-x|-->)\s*(\S+)\s*:\s*(.*)$"
)
_NOTE_RE = re.compile(
    r"^Note\s+(?:over|left of|right of)\s+([^:]+):\s*(.*)$", re.IGNORECASE
)
_NODE_RE = re.compile(
    r"^([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^\)]+)\)|\{([^}]+)\})?\s*$"
)
_EDGE_RE = re.compile(
    r"^([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^\)]+)\))?"
    r"\s*-->(?:\|([^|]+)\|)?\s*"
    r"([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^\)]+)\))?\s*$"
)
_JUMP_RE = re.compile(r"jump:([0-9]+(?:\.[0-9]+)?)")


def extract_mermaid_fences(text: str) -> List[str]:
    """Return mermaid code bodies from fenced blocks."""
    out: List[str] = []
    lines = (text or "").replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            lang = stripped[3:].strip().lower()
            i += 1
            body: List[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            if lang == "mermaid":
                out.append("\n".join(body).strip())
            continue
        i += 1
    return out


def mermaid_link_targets(source: str) -> List[Tuple[str, str]]:
    """``(kind, value)`` pairs: jump times and highlight labels from a diagram."""
    found: List[Tuple[str, str]] = []
    seen = set()

    def _add_hl(label: str) -> None:
        label = (label or "").strip()
        if not label or ("highlight", label) in seen:
            return
        seen.add(("highlight", label))
        found.append(("highlight", label))

    for m in _JUMP_RE.finditer(source or ""):
        key = ("jump", m.group(1))
        if key not in seen:
            seen.add(key)
            found.append(key)
    for line in (source or "").splitlines():
        s = line.strip().rstrip(";")
        low = s.lower()
        if not s or low.startswith(("graph ", "flowchart ", "sequencediagram", "%%")):
            continue
        pm = _PARTICIPANT_RE.match(s)
        if pm:
            _add_hl(pm.group(2) or pm.group(1) or "")
            continue
        em = _EDGE_RE.match(s)
        if em:
            _add_hl(em.group(2) or em.group(3) or em.group(1) or "")
            _add_hl(em.group(6) or em.group(7) or em.group(5) or "")
            continue
        nm = _NODE_RE.match(s)
        if nm:
            _add_hl(nm.group(2) or nm.group(3) or nm.group(4) or nm.group(1) or "")
    return found


def mermaid_to_svg(source: str, *, interactive: bool = True) -> str:
    """Return an SVG string, or empty if the dialect is unsupported."""
    text = (source or "").strip()
    if not text:
        return ""
    first = ""
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("%%"):
            first = s.lower()
            break
    if first.startswith("sequencediagram"):
        return _sequence_svg(text, interactive=interactive)
    if first.startswith("graph ") or first.startswith("flowchart "):
        return _flowchart_svg(text, interactive=interactive)
    return ""


def mermaid_zoom_token(source: str) -> str:
    """URL-safe token for ``btfmermaid:zoom/…`` (no extra colons)."""
    return base64.urlsafe_b64encode((source or "").encode("utf-8")).decode("ascii").rstrip("=")


def decode_mermaid_zoom_token(token: str) -> str:
    """Inverse of ``mermaid_zoom_token``; empty on bad input."""
    raw = str(token or "").strip()
    if not raw:
        return ""
    pad = "=" * ((4 - len(raw) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(raw + pad).decode("utf-8")
    except (ValueError, TypeError):
        return ""


def mermaid_block_html(source: str, *, as_img: bool = True, zoomable: bool = True) -> str:
    """Wrap a mermaid source in HTML (img for QTextBrowser, inline SVG for export)."""
    svg = mermaid_to_svg(source, interactive=not as_img)
    if not svg:
        esc = html.escape(source)
        return f'<pre><code class="language-mermaid">{esc}</code></pre>'
    if as_img:
        b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        fig = (
            f'<img class="ai-mermaid-img" alt="mermaid diagram" '
            f'src="data:image/svg+xml;base64,{b64}">'
        )
    else:
        fig = f'<div class="ai-mermaid-svg">{svg}</div>'
    if zoomable:
        token = html.escape(mermaid_zoom_token(source), quote=True)
        fig = (
            f'<a href="btfmermaid:zoom/{token}" class="ai-mermaid-zoom" '
            f'title="Open larger view">{fig}</a>'
        )
    links = _link_row_html(source)
    return f'<div class="ai-mermaid">{fig}{links}</div>'


def _link_row_html(source: str) -> str:
    parts: List[str] = []
    for kind, value in mermaid_link_targets(source):
        esc = html.escape(value)
        if kind == "jump":
            parts.append(
                f'<a href="btfjump:{esc}" class="ai-jump">jump:{esc}</a>'
            )
        else:
            parts.append(
                f'<a href="btfhighlight:{esc}" class="ai-hl">{esc}</a>'
            )
    if not parts:
        return ""
    return '<p class="ai-mermaid-links">' + " · ".join(parts) + "</p>"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _sequence_svg(source: str, *, interactive: bool) -> str:
    participants: List[Tuple[str, str]] = []  # id, label
    index: Dict[str, int] = {}
    rows: List[Tuple[str, Any]] = []

    def _ensure(pid: str, label: Optional[str] = None) -> None:
        key = pid.strip()
        if not key:
            return
        if key not in index:
            index[key] = len(participants)
            participants.append((key, (label or key).strip() or key))
        elif label:
            i = index[key]
            participants[i] = (key, label.strip() or participants[i][1])

    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.lower() == "sequencediagram" or line.lower() == "autonumber":
            continue
        if line.lower().startswith("title "):
            continue
        pm = _PARTICIPANT_RE.match(line)
        if pm:
            _ensure(pm.group(1), pm.group(2))
            continue
        am = _ARROW_RE.match(line)
        if am:
            _ensure(am.group(1))
            _ensure(am.group(3))
            rows.append(("arrow", am.group(1), am.group(3), am.group(2), am.group(4).strip()))
            continue
        nm = _NOTE_RE.match(line)
        if nm:
            who = nm.group(1).split(",")[0].strip()
            _ensure(who)
            rows.append(("note", who, nm.group(2).strip()))
            continue

    if not participants:
        return ""

    col_w = 150
    left = 36
    top = 28
    row_h = 40
    width = left * 2 + max(len(participants) - 1, 0) * col_w + 40
    height = top + 36 + max(len(rows), 1) * row_h + 24
    xs = [left + i * col_w for i in range(len(participants))]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" class="ai-mermaid-seq">',
        '<rect width="100%" height="100%" fill="#12161d"/>',
    ]
    for i, (pid, label) in enumerate(participants):
        x = xs[i]
        box_w = 120
        bx = x - box_w / 2
        href = f' href="btfhighlight:{_esc(label)}"' if interactive else ""
        parts.append(
            f'<line x1="{x}" y1="{top + 22}" x2="{x}" y2="{height - 12}" '
            f'stroke="#3a4658" stroke-dasharray="4 3"/>'
        )
        parts.append(
            f'<a{href}>'
            f'<rect x="{bx}" y="{top - 14}" width="{box_w}" height="28" rx="4" '
            f'fill="#1e3348" stroke="#5b9bd5"/>'
            f'<text x="{x}" y="{top + 5}" text-anchor="middle" fill="#dbe2ea" '
            f'font-size="11" font-family="system-ui,sans-serif">{_esc(label[:28])}</text>'
            f"</a>"
        )

    y = top + 44
    for row in rows:
        if row[0] == "arrow":
            _src, _dst, arrow, msg = row[1], row[2], row[3], row[4]
            x1 = xs[index[_src]]
            x2 = xs[index[_dst]]
            dashed = " stroke-dasharray=\"5 3\"" if arrow.startswith("--") else ""
            parts.append(
                f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" '
                f'stroke="#6fbf9a" stroke-width="1.4"{dashed} '
                f'marker-end="url(#aiArr)"/>'
            )
            mx = (x1 + x2) / 2
            parts.append(
                f'<text x="{mx}" y="{y - 6}" text-anchor="middle" fill="#a8b4c4" '
                f'font-size="10" font-family="system-ui,sans-serif">{_esc(msg[:48])}</text>'
            )
        else:
            who, note = row[1], row[2]
            x = xs[index[who]]
            nw = min(200, 16 + 6 * min(len(note), 36))
            parts.append(
                f'<rect x="{x - nw / 2}" y="{y - 16}" width="{nw}" height="28" '
                f'rx="3" fill="#2a2418" stroke="#c9a227"/>'
                f'<text x="{x}" y="{y + 3}" text-anchor="middle" fill="#e6d48a" '
                f'font-size="10" font-family="system-ui,sans-serif">{_esc(note[:40])}</text>'
            )
        y += row_h

    marker = (
        '<defs><marker id="aiArr" markerWidth="8" markerHeight="8" '
        'refX="7" refY="3" orient="auto">'
        '<path d="M0,0 L8,3 L0,6 Z" fill="#6fbf9a"/></marker></defs>'
    )
    parts.insert(1, marker)
    parts.append("</svg>")
    return "".join(parts)


def _flowchart_svg(source: str, *, interactive: bool) -> str:
    nodes: Dict[str, str] = {}
    edges: List[Tuple[str, str, str]] = []
    order: List[str] = []

    def _add_node(nid: str, label: Optional[str]) -> None:
        key = nid.strip()
        if not key:
            return
        if key not in nodes:
            nodes[key] = (label or key).strip() or key
            order.append(key)
        elif label:
            nodes[key] = label.strip()

    for raw in source.splitlines():
        line = raw.strip().rstrip(";")
        if not line or line.lower().startswith("graph ") or line.lower().startswith("flowchart "):
            continue
        if line.startswith("%%"):
            continue
        em = _EDGE_RE.match(line)
        if em:
            _add_node(em.group(1), em.group(2) or em.group(3))
            _add_node(em.group(5), em.group(6) or em.group(7))
            edges.append((em.group(1), em.group(5), (em.group(4) or "").strip()))
            continue
        nm = _NODE_RE.match(line)
        if nm:
            _add_node(nm.group(1), nm.group(2) or nm.group(3) or nm.group(4))

    if not nodes:
        return ""

    col_w, row_h = 150, 70
    cols = min(4, max(1, len(order)))
    left, top = 30, 28
    width = left * 2 + (cols - 1) * col_w + 100
    rows_n = (len(order) + cols - 1) // cols
    height = top + rows_n * row_h + 40
    pos: Dict[str, Tuple[float, float]] = {}
    for i, nid in enumerate(order):
        c, r = i % cols, i // cols
        pos[nid] = (left + 50 + c * col_w, top + 20 + r * row_h)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" class="ai-mermaid-flow">',
        '<rect width="100%" height="100%" fill="#12161d"/>',
        '<defs><marker id="aiFArr" markerWidth="8" markerHeight="8" '
        'refX="7" refY="3" orient="auto">'
        '<path d="M0,0 L8,3 L0,6 Z" fill="#5b9bd5"/></marker></defs>',
    ]
    for src, dst, label in edges:
        x1, y1 = pos[src]
        x2, y2 = pos[dst]
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="#5b9bd5" stroke-width="1.3" marker-end="url(#aiFArr)"/>'
        )
        if label:
            parts.append(
                f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 - 6}" text-anchor="middle" '
                f'fill="#8b98a8" font-size="10" font-family="system-ui,sans-serif">'
                f"{_esc(label[:16])}</text>"
            )
    for nid in order:
        x, y = pos[nid]
        label = nodes[nid]
        href = f' href="btfhighlight:{_esc(label)}"' if interactive else ""
        bw = max(72, min(130, 12 + 7 * len(label[:18])))
        parts.append(
            f'<a{href}>'
            f'<rect x="{x - bw / 2}" y="{y - 16}" width="{bw}" height="32" rx="6" '
            f'fill="#1e3348" stroke="#5b9bd5"/>'
            f'<text x="{x}" y="{y + 5}" text-anchor="middle" fill="#dbe2ea" '
            f'font-size="11" font-family="system-ui,sans-serif">{_esc(label[:18])}</text>'
            f"</a>"
        )
    parts.append("</svg>")
    return "".join(parts)
