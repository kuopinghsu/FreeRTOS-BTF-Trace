"""Mermaid subset → SVG for AI chat diagrams."""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from PySide6.QtWidgets import QApplication  # noqa: E402

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    format_ai_conversation_html,
    markdown_to_safe_html,
)
from btf_viewer_pkg.ai_mermaid import (  # noqa: E402
    decode_mermaid_zoom_token,
    hit_test_mermaid,
    mermaid_block_html,
    mermaid_hit_regions,
    mermaid_link_targets,
    mermaid_to_svg,
    mermaid_zoom_token,
)
from btf_viewer_pkg.ai_tools import (  # noqa: E402
    AI_MERMAID_MIGRATION_EXAMPLE,
    AI_MERMAID_SEQUENCE_EXAMPLE,
)


class AiMermaidTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if QApplication.instance() is None:
            QApplication([])

    def test_sequence_svg(self) -> None:
        src = (
            "sequenceDiagram\n"
            "  participant L as Low[266] (Core 0)\n"
            "  participant H as High[268] (Core 0)\n"
            "  L->>H: take\n"
            "  Note over L: boost\n"
        )
        svg = mermaid_to_svg(src)
        self.assertIn("<svg", svg)
        self.assertIn("Low[266]", svg)
        self.assertIn("take", svg)
        self.assertTrue(any(k == "highlight" for k, _v in mermaid_link_targets(src)))

    def test_flowchart_svg(self) -> None:
        src = "graph LR\n  C0[Core_0] -->|12| C1[Core_1]\n"
        svg = mermaid_to_svg(src)
        self.assertIn("<svg", svg)
        self.assertIn("Core_0", svg)
        self.assertIn("btfhighlight:task/", svg)
        self.assertIn("12", svg)
        labels = [v for k, v in mermaid_link_targets(src) if k == "highlight"]
        self.assertIn("Core_0", labels)
        self.assertIn("Core_1", labels)

    def test_flowchart_node_wraps_long_labels(self) -> None:
        from btf_viewer_pkg.ai_mermaid import wrap_node_label

        label = (
            "Mutex contention on the shared queue blocks the high priority worker"
        )
        lines = wrap_node_label(label)
        self.assertGreater(len(lines), 1)
        self.assertEqual(" ".join(lines), label)
        self.assertTrue(all(len(ln) <= 22 for ln in lines))
        src = f"graph TD\n  S0[{label}]\n"
        svg = mermaid_to_svg(src)
        for word in ("Mutex", "contention", "priority", "worker"):
            self.assertIn(word, svg)
        self.assertNotIn("<tspan", svg)
        hs = [float(h) for h in re.findall(r'height="([\d.]+)" rx="6"', svg)]
        self.assertTrue(any(h > 32 for h in hs), hs)
        hits = mermaid_hit_regions(src)
        self.assertEqual(hits[0]["value"], label)
        self.assertGreater(hits[0]["h"], 32)

    def test_flowchart_bidirectional_counts_stay_on_their_arrows(self) -> None:
        src = (
            "graph LR\n"
            "  C0[Core_0] -->|12| C1[Core_1]\n"
            "  C1 -->|3| C0\n"
        )
        svg = mermaid_to_svg(src)
        m12 = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*>12</text>', svg)
        m3 = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*>3</text>', svg)
        self.assertIsNotNone(m12)
        self.assertIsNotNone(m3)
        y12, y3 = float(m12.group(2)), float(m3.group(2))
        self.assertGreater(abs(y12 - y3), 8.0)
        self.assertGreater(y12, y3)

    def test_markdown_renders_mermaid(self) -> None:
        html = markdown_to_safe_html(AI_MERMAID_SEQUENCE_EXAMPLE)
        self.assertIn("ai-mermaid", html)
        self.assertIn("data:image/png", html)
        self.assertIn("btfhighlight:", html)
        self.assertIn("btfmermaid:zoom/", html)
        self.assertIn("ai-mermaid-zoom", html)

    def test_zoom_token_roundtrip(self) -> None:
        src = "graph LR\n  C0[Core_0] --> C1[Core_1]\n"
        token = mermaid_zoom_token(src)
        self.assertNotIn(":", token)
        self.assertEqual(decode_mermaid_zoom_token(token), src)
        html = mermaid_block_html(src, as_img=True)
        self.assertIn(f"btfmermaid:zoom/{token}", html)

    def test_html_export_keeps_clickable_svg(self) -> None:
        chat = markdown_to_safe_html(AI_MERMAID_SEQUENCE_EXAMPLE, as_img=True)
        self.assertIn("data:image/png", chat)
        exported = markdown_to_safe_html(AI_MERMAID_SEQUENCE_EXAMPLE, as_img=False)
        self.assertIn("<svg", exported)
        self.assertNotIn("data:image/svg+xml", exported)
        self.assertNotIn("btfmermaid:", exported)
        doc = format_ai_conversation_html([
            {"role": "assistant", "text": AI_MERMAID_SEQUENCE_EXAMPLE},
        ])
        self.assertIn("<svg", doc)
        self.assertIn("btfhighlight:", doc)
        self.assertNotIn("data:image/svg+xml", doc)
        self.assertNotIn("btfmermaid:", doc)

    def test_hit_regions_match_sequence_boxes(self) -> None:
        src = (
            "sequenceDiagram\n"
            "  participant L as Low[266] (Core 0)\n"
            "  participant H as High[268] (Core 0)\n"
            "  L->>H: take\n"
        )
        hits = mermaid_hit_regions(src)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["value"], "Low[266] (Core 0)")
        cx = hits[0]["x"] + hits[0]["w"] / 2
        cy = hits[0]["y"] + hits[0]["h"] / 2
        self.assertEqual(hit_test_mermaid(src, cx, cy), ("highlight", "Low[266] (Core 0)"))
        self.assertIsNone(hit_test_mermaid(src, 2, 2))
        html = mermaid_block_html(src, as_img=True)
        self.assertRegex(html, r'width="\d+')
        self.assertRegex(html, r'height="\d+')

    def test_svg_has_no_marker_blob_and_boxes_stay_in_view(self) -> None:
        seq_src = AI_MERMAID_SEQUENCE_EXAMPLE.replace("```mermaid", "").replace("```", "").strip()
        flow_src = AI_MERMAID_MIGRATION_EXAMPLE.replace("```mermaid", "").replace("```", "").strip()
        for src in (seq_src, flow_src):
            svg = mermaid_to_svg(src)
            self.assertNotIn("<marker", svg.lower())
            self.assertNotIn("marker-end", svg)
            self.assertNotIn("system-ui", svg)
            self.assertNotIn("sans-serif", svg.lower())
            xs = [float(x) for x in re.findall(r'<rect[^>]*\bx="(-?[\d.]+)"', svg)]
            self.assertTrue(xs, src)
            self.assertTrue(all(x >= 0 for x in xs), xs)
            for hit in mermaid_hit_regions(src):
                self.assertGreaterEqual(hit["x"], 0)
                self.assertGreaterEqual(hit["y"], 0)

    def test_block_fallback(self) -> None:
        html = mermaid_block_html("not a diagram", as_img=True)
        self.assertIn("language-mermaid", html)

    def test_rasterize_svg_caps_long_edge(self) -> None:
        from btf_viewer_pkg.config import _SVG_RASTER_MAX_EDGE, rasterize_svg_pixmap

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="20000" height="80" '
            'viewBox="0 0 20000 80">'
            '<rect width="20000" height="80" fill="#224466"/></svg>'
        )
        pm, user_scale = rasterize_svg_pixmap(svg, scale=2.0)
        self.assertFalse(pm.isNull())
        self.assertLessEqual(max(pm.width(), pm.height()), _SVG_RASTER_MAX_EDGE)
        self.assertLess(user_scale, 2.0)

    def test_hexagon_nodes_and_jump_clicks(self) -> None:
        src = (
            "graph TD\n"
            "  F[Finding]\n"
            "  E0{{preempt Low jump:12345}}\n"
            "  F --> E0\n"
        )
        svg = mermaid_to_svg(src)
        self.assertIn("preempt Low", svg)
        self.assertIn("btfjump:time/12345", svg)
        hits = mermaid_hit_regions(src)
        ev = next(h for h in hits if "preempt" in str(h["value"]) or h["kind"] == "jump")
        self.assertEqual(ev["kind"], "jump")
        self.assertEqual(ev["value"], "12345")
        cx, cy = ev["x"] + ev["w"] / 2, ev["y"] + ev["h"] / 2
        self.assertEqual(hit_test_mermaid(src, cx, cy), ("jump", "12345"))

    def test_light_theme_flowchart_uses_readable_ink(self) -> None:
        from btf_viewer_pkg.ai_mermaid import mermaid_palette

        src = "graph TD\n  F[Finding]\n  E0[evidence]\n  F --> E0\n"
        dark = mermaid_to_svg(src, is_dark=True)
        light = mermaid_to_svg(src, is_dark=False)
        pal = mermaid_palette(False)
        self.assertIn(mermaid_palette(True)["bg"], dark)
        self.assertIn(pal["bg"], light)
        self.assertIn(pal["node_text"], light)
        self.assertNotIn("#12161d", light)
        self.assertNotIn("#dbe2ea", light)
        html = markdown_to_safe_html(
            "```mermaid\n" + src + "```", as_img=False, is_dark=False)
        self.assertIn(pal["bg"], html)


if __name__ == "__main__":
    unittest.main()
