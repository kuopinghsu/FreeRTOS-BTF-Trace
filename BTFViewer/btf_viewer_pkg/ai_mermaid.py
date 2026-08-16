"""Render a mermaid sequence/flowchart subset to SVG (no JS engine).

Used by the Desktop AI pane (QTextBrowser) and HTML export. Web uses the same
layout rules in ``web/src/utils/aiMermaid.js`` so diagrams stay in sync.
"""
from __future__ import annotations

import base64
import html
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .ai_tools import btf_highlight_href, btf_jump_href


def _svg_sans_family() -> str:
    """Qt SVG needs a real face; CSS ``sans-serif`` warns as ``Sans-serif``."""
    try:
        from .timeline_util import _get_sans_font_family
        return _get_sans_font_family()
    except Exception:
        return "Arial"

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
    r"^([A-Za-z0-9_]+)\s*(?:"
    r"\[([^\]]+)\]|\(([^\)]+)\)|\{\{([^}]+)\}\}|\{([^}]+)\})?\s*$"
)
_EDGE_RE = re.compile(
    r"^([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^\)]+)\))?"
    r"\s*-->(?:\|([^|]+)\|)?\s*"
    r"([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^\)]+)\))?\s*$"
)
_JUMP_RE = re.compile(r"jump:([0-9]+(?:\.[0-9]+)?)")


def _note_box_w(note: str) -> float:
    return float(min(200, 16 + 6 * min(len(note or ""), 36)))


def _svg_arrowhead(x1: float, y1: float, x2: float, y2: float, color: str, size: float = 8.0) -> str:
    """Triangle at (x2,y2); Qt paints ``<marker>`` as a stray blob at the origin."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    tip_x, tip_y = x2, y2
    bx, by = tip_x - ux * size, tip_y - uy * size
    px, py = -uy * size * 0.45, ux * size * 0.45
    return (
        f'<polygon points="{tip_x:.1f},{tip_y:.1f} {bx + px:.1f},{by + py:.1f} '
        f'{bx - px:.1f},{by - py:.1f}" fill="{color}"/>'
    )


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
            _add_hl(
                nm.group(2) or nm.group(3) or nm.group(4)
                or nm.group(5) or nm.group(1) or ""
            )
    return found


def mermaid_hit_regions(source: str) -> List[Dict[str, Any]]:
    """Clickable node boxes in SVG user units: ``x,y,w,h,kind,value``."""
    text = (source or "").strip()
    if not text:
        return []
    first = ""
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("%%"):
            first = s.lower()
            break
    if first.startswith("sequencediagram"):
        return _sequence_hits(text)
    if first.startswith("graph ") or first.startswith("flowchart "):
        return _flowchart_hits(text)
    return []


def mermaid_node_action(label: str) -> Tuple[str, str]:
    """Click action for a diagram node: ``jump`` if the label has jump:TIME."""
    text = str(label or "").strip()
    m = _JUMP_RE.search(text)
    if m:
        return "jump", m.group(1)
    return "highlight", text


def _node_href_attr(label: str) -> str:
    kind, value = mermaid_node_action(label)
    if kind == "jump":
        return f' href="{html.escape(btf_jump_href(value), quote=True)}"'
    return f' href="{html.escape(btf_highlight_href(value), quote=True)}"'


def hit_test_mermaid(
    source: str,
    local_x: float,
    local_y: float,
    *,
    scale: float = 1.0,
) -> Optional[Tuple[str, str]]:
    """Return ``(kind, value)`` if ``(local_x, local_y)`` hits a node."""
    sx = float(scale) if scale else 1.0
    if sx <= 0:
        sx = 1.0
    px, py = float(local_x), float(local_y)
    for hit in mermaid_hit_regions(source):
        x = float(hit["x"]) * sx
        y = float(hit["y"]) * sx
        w = float(hit["w"]) * sx
        h = float(hit["h"]) * sx
        if x <= px <= x + w and y <= py <= y + h:
            return str(hit["kind"]), str(hit["value"])
    return None


def _svg_to_png_bytes(svg: str) -> Optional[Tuple[bytes, int, int]]:
    """Rasterize SVG for QTextBrowser (avoids Qt's oversized SVG buffer warning)."""
    try:
        from ._imports import QBuffer, QByteArray, QColor, QIODevice
        from .config import rasterize_svg_pixmap
    except Exception:
        return None
    pm, _ = rasterize_svg_pixmap(svg, fill=QColor("#12161d"))
    if pm.isNull():
        return None
    ba = QByteArray()
    buf = QBuffer(ba)
    if not buf.open(QIODevice.OpenModeFlag.WriteOnly):
        return None
    if not pm.save(buf, "PNG"):
        return None
    return bytes(ba.data()), int(pm.width()), int(pm.height())


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
        png = _svg_to_png_bytes(svg)
        if png:
            raw, iw, ih = png
            b64 = base64.b64encode(raw).decode("ascii")
            fig = (
                f'<img class="ai-mermaid-img" alt="mermaid diagram" '
                f'width="{iw}" height="{ih}" '
                f'src="data:image/png;base64,{b64}">'
            )
        else:
            b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
            wm = re.search(r'\bwidth="(\d+(?:\.\d+)?)"', svg)
            hm = re.search(r'\bheight="(\d+(?:\.\d+)?)"', svg)
            size_attr = ""
            if wm and hm:
                size_attr = f' width="{wm.group(1)}" height="{hm.group(1)}"'
            fig = (
                f'<img class="ai-mermaid-img" alt="mermaid diagram"{size_attr} '
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
                f'<a href="{html.escape(btf_jump_href(value), quote=True)}" '
                f'class="ai-jump">jump:{esc}</a>'
            )
        else:
            parts.append(
                f'<a href="{html.escape(btf_highlight_href(value), quote=True)}" '
                f'class="ai-hl">{esc}</a>'
            )
    if not parts:
        return ""
    return '<p class="ai-mermaid-links">' + " · ".join(parts) + "</p>"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _parse_sequence(source: str) -> Tuple[List[Tuple[str, str]], Dict[str, int], List[Tuple[str, Any]]]:
    participants: List[Tuple[str, str]] = []
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
    return participants, index, rows


def _sequence_geom(source: str) -> Optional[Dict[str, Any]]:
    participants, index, rows = _parse_sequence(source)
    if not participants:
        return None
    box_w = 120.0
    col_w = 150.0
    top = 32.0
    row_h = 40.0
    half = box_w / 2.0
    for row in rows:
        if row[0] == "note":
            half = max(half, _note_box_w(row[2]) / 2.0)
    pad = half + 16.0
    width = pad * 2 + max(len(participants) - 1, 0) * col_w
    height = top + 36 + max(len(rows), 1) * row_h + 24
    xs = [pad + i * col_w for i in range(len(participants))]
    return {
        "participants": participants, "index": index, "rows": rows,
        "box_w": box_w, "top": top, "row_h": row_h,
        "width": width, "height": height, "xs": xs,
    }


def _sequence_hits(source: str) -> List[Dict[str, Any]]:
    geom = _sequence_geom(source)
    if not geom:
        return []
    top, box_w = geom["top"], geom["box_w"]
    hits: List[Dict[str, Any]] = []
    for i, (_pid, label) in enumerate(geom["participants"]):
        x = geom["xs"][i]
        kind, value = mermaid_node_action(label)
        hits.append({
            "x": x - box_w / 2, "y": top - 14, "w": float(box_w), "h": 28.0,
            "kind": kind, "value": value,
        })
    return hits


def _sequence_svg(source: str, *, interactive: bool) -> str:
    geom = _sequence_geom(source)
    if not geom:
        return ""
    participants, index, rows = geom["participants"], geom["index"], geom["rows"]
    box_w, top, row_h = geom["box_w"], geom["top"], geom["row_h"]
    width, height, xs = geom["width"], geom["height"], geom["xs"]
    fam = _esc(_svg_sans_family())

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" class="ai-mermaid-seq">',
        f'<rect x="0" y="0" width="{width:.0f}" height="{height:.0f}" fill="#12161d"/>',
    ]
    for i, (_pid, label) in enumerate(participants):
        x = xs[i]
        bx = x - box_w / 2
        href = _node_href_attr(label) if interactive else ""
        parts.append(
            f'<line x1="{x}" y1="{top + 22}" x2="{x}" y2="{height - 12}" '
            f'stroke="#3a4658" stroke-dasharray="4 3"/>'
        )
        parts.append(
            f'<a{href}>'
            f'<rect x="{bx}" y="{top - 14}" width="{box_w}" height="28" rx="4" '
            f'fill="#1e3348" stroke="#5b9bd5"/>'
            f'<text x="{x}" y="{top + 5}" text-anchor="middle" fill="#dbe2ea" '
            f'font-size="11" font-family="{fam}">{_esc(label[:28])}</text>'
            f"</a>"
        )

    y = top + 44
    for row in rows:
        if row[0] == "arrow":
            _src, _dst, arrow, msg = row[1], row[2], row[3], row[4]
            x1 = xs[index[_src]]
            x2 = xs[index[_dst]]
            dashed = " stroke-dasharray=\"5 3\"" if arrow.startswith("--") else ""
            tip = 8 if x2 >= x1 else -8
            parts.append(
                f'<line x1="{x1}" y1="{y}" x2="{x2 - tip}" y2="{y}" '
                f'stroke="#6fbf9a" stroke-width="1.4"{dashed}/>'
            )
            parts.append(_svg_arrowhead(x1, y, x2, y, "#6fbf9a"))
            mx = (x1 + x2) / 2
            parts.append(
                f'<text x="{mx}" y="{y - 6}" text-anchor="middle" fill="#a8b4c4" '
                f'font-size="10" font-family="{fam}">{_esc(msg[:48])}</text>'
            )
        else:
            who, note = row[1], row[2]
            x = xs[index[who]]
            nw = _note_box_w(note)
            parts.append(
                f'<rect x="{x - nw / 2}" y="{y - 16}" width="{nw}" height="28" '
                f'rx="3" fill="#2a2418" stroke="#c9a227"/>'
                f'<text x="{x}" y="{y + 3}" text-anchor="middle" fill="#e6d48a" '
                f'font-size="10" font-family="{fam}">{_esc(note[:40])}</text>'
            )
        y += row_h

    parts.append("</svg>")
    return "".join(parts)


def _parse_flowchart(
    source: str,
) -> Tuple[Dict[str, str], List[str], List[Tuple[str, str, str]]]:
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
            _add_node(
                nm.group(1),
                nm.group(2) or nm.group(3) or nm.group(4) or nm.group(5),
            )
    return nodes, order, edges


def wrap_node_label(label: str, max_chars: int = 22) -> List[str]:
    """Word-wrap a flowchart node label so the SVG rectangle can grow."""
    text = re.sub(r"\s+", " ", str(label or "")).strip()
    if not text:
        return [""]
    lines: List[str] = []
    cur = ""

    def _flush() -> None:
        nonlocal cur
        if cur:
            lines.append(cur)
            cur = ""

    for word in text.split(" "):
        while len(word) > max_chars:
            room = max_chars - (len(cur) + (1 if cur else 0))
            if room < 1:
                _flush()
                room = max_chars
            if cur:
                cur += " "
            cur += word[:room]
            word = word[room:]
            _flush()
        if not word:
            continue
        trial = word if not cur else f"{cur} {word}"
        if len(trial) <= max_chars:
            cur = trial
        else:
            _flush()
            cur = word
    _flush()
    return lines or [""]


def _node_box_size(label: str) -> Tuple[float, float, List[str]]:
    """Return ``(width, height, wrapped_lines)`` for a flowchart node."""
    lines = wrap_node_label(label)
    longest = max((len(ln) for ln in lines), default=0)
    bw = float(max(72.0, min(156.0, 14.0 + 6.6 * longest)))
    bh = float(10.0 * 2 + 14.0 * max(len(lines), 1))
    return bw, bh, lines


def _node_ray_r(bw: float, bh: float, ux: float, uy: float) -> float:
    """Distance from node centre to the ellipse that bounds the rectangle."""
    hw, hh = bw / 2.0 + 2.0, bh / 2.0 + 2.0
    denom = math.hypot(ux * hh, uy * hw) or 1.0
    return (hw * hh) / denom


def _flowchart_geom(source: str) -> Optional[Dict[str, Any]]:
    nodes, order, edges = _parse_flowchart(source)
    if not nodes:
        return None
    sizes = {nid: _node_box_size(nodes[nid]) for nid in order}
    cols = min(4, max(1, len(order)))
    max_bw = max(sz[0] for sz in sizes.values())
    col_w = max(160.0, max_bw + 24.0)
    row_h: Dict[int, float] = {}
    for i, nid in enumerate(order):
        r = i // cols
        row_h[r] = max(row_h.get(r, 0.0), sizes[nid][1])
    max_half = max(sz[0] / 2.0 for sz in sizes.values())
    pad = max_half + 18.0
    top = 36.0
    row_cy: Dict[int, float] = {}
    y = top
    for r in range(max(row_h) + 1 if row_h else 0):
        h = row_h.get(r, 32.0)
        row_cy[r] = y + h / 2.0
        y += h + 28.0
    pos: Dict[str, Tuple[float, float]] = {}
    for i, nid in enumerate(order):
        c, r = i % cols, i // cols
        pos[nid] = (pad + c * col_w, row_cy[r])
    right = max(
        pos[nid][0] + sizes[nid][0] / 2.0 for nid in order
    )
    bottom = y - 28.0
    width = right + pad
    height = bottom + 24.0
    return {
        "nodes": nodes, "order": order, "edges": edges, "pos": pos,
        "sizes": sizes, "width": width, "height": height,
    }


def _flowchart_edge_paths(geom: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Offset reverse edges so Core_0→Core_1 and Core_1→Core_0 counts do not stack."""
    edges, pos = geom["edges"], geom["pos"]
    pairs = {(src, dst) for src, dst, _lab in edges}
    paths: List[Dict[str, float]] = []
    for src, dst, label in edges:
        x1, y1 = pos[src]
        x2, y2 = pos[dst]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux
        sep = 12.0 if (dst, src) in pairs else 0.0
        ox, oy = nx * sep, ny * sep
        src_bw, src_bh, _sl = geom["sizes"][src]
        dst_bw, dst_bh, _dl = geom["sizes"][dst]
        src_r = _node_ray_r(src_bw, src_bh, ux, uy)
        dst_r = _node_ray_r(dst_bw, dst_bh, ux, uy)
        sx = x1 + ux * src_r + ox
        sy = y1 + uy * src_r + oy
        ex = x2 - ux * dst_r + ox
        ey = y2 - uy * dst_r + oy
        extra = 10.0 if sep else 8.0
        paths.append({
            "sx": sx, "sy": sy, "ex": ex, "ey": ey,
            "lx": (sx + ex) / 2.0 + nx * extra,
            "ly": (sy + ey) / 2.0 + ny * extra,
            "label": label,
        })
    return paths


def _flowchart_hits(source: str) -> List[Dict[str, Any]]:
    geom = _flowchart_geom(source)
    if not geom:
        return []
    hits: List[Dict[str, Any]] = []
    for nid in geom["order"]:
        x, y = geom["pos"][nid]
        label = geom["nodes"][nid]
        bw, bh, _lines = geom["sizes"][nid]
        kind, value = mermaid_node_action(label)
        hits.append({
            "x": x - bw / 2, "y": y - bh / 2, "w": float(bw), "h": float(bh),
            "kind": kind, "value": value,
        })
    return hits


def _flowchart_svg(source: str, *, interactive: bool) -> str:
    geom = _flowchart_geom(source)
    if not geom:
        return ""
    nodes, order, pos = geom["nodes"], geom["order"], geom["pos"]
    width, height = geom["width"], geom["height"]
    fam = _esc(_svg_sans_family())

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" class="ai-mermaid-flow">',
        f'<rect x="0" y="0" width="{width:.0f}" height="{height:.0f}" fill="#12161d"/>',
    ]
    for edge in _flowchart_edge_paths(geom):
        sx, sy, ex, ey = edge["sx"], edge["sy"], edge["ex"], edge["ey"]
        parts.append(
            f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
            f'stroke="#5b9bd5" stroke-width="1.3"/>'
        )
        parts.append(_svg_arrowhead(sx, sy, ex, ey, "#5b9bd5"))
        label = str(edge.get("label") or "")
        if label:
            parts.append(
                f'<text x="{edge["lx"]:.1f}" y="{edge["ly"]:.1f}" text-anchor="middle" '
                f'fill="#c5d0dc" font-size="10" font-family="{fam}">'
                f"{_esc(label[:16])}</text>"
            )
    for nid in order:
        x, y = pos[nid]
        label = nodes[nid]
        href = _node_href_attr(label) if interactive else ""
        bw, bh, lines = geom["sizes"][nid]
        y0 = y - bh / 2.0 + 10.0 + 11.0
        # Separate <text> nodes: Qt's SVG renderer ignores <tspan>, so a
        # single <text> with tspans paints empty rectangles on Desktop.
        labels = []
        for i, line in enumerate(lines):
            labels.append(
                f'<text x="{x:.1f}" y="{y0 + i * 14.0:.1f}" text-anchor="middle" '
                f'fill="#dbe2ea" font-size="11" font-family="{fam}">'
                f"{_esc(line)}</text>"
            )
        parts.append(
            f'<a{href}>'
            f'<rect x="{x - bw / 2:.1f}" y="{y - bh / 2:.1f}" width="{bw:.1f}" '
            f'height="{bh:.1f}" rx="6" fill="#1e3348" stroke="#5b9bd5"/>'
            f"{''.join(labels)}"
            f"</a>"
        )
    parts.append("</svg>")
    return "".join(parts)
