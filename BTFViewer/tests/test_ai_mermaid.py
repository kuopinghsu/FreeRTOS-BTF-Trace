"""Mermaid subset → SVG for AI chat diagrams."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.ai_assistant import (  # noqa: E402
    format_ai_conversation_html,
    markdown_to_safe_html,
)
from btf_viewer_pkg.ai_mermaid import (  # noqa: E402
    decode_mermaid_zoom_token,
    mermaid_block_html,
    mermaid_link_targets,
    mermaid_to_svg,
    mermaid_zoom_token,
)
from btf_viewer_pkg.ai_tools import AI_MERMAID_SEQUENCE_EXAMPLE  # noqa: E402


class AiMermaidTests(unittest.TestCase):
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
        self.assertIn("12", svg)
        labels = [v for k, v in mermaid_link_targets(src) if k == "highlight"]
        self.assertIn("Core_0", labels)
        self.assertIn("Core_1", labels)

    def test_markdown_renders_mermaid(self) -> None:
        html = markdown_to_safe_html(AI_MERMAID_SEQUENCE_EXAMPLE)
        self.assertIn("ai-mermaid", html)
        self.assertIn("data:image/svg+xml", html)
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
        self.assertIn("data:image/svg+xml", chat)
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

    def test_block_fallback(self) -> None:
        html = mermaid_block_html("not a diagram", as_img=True)
        self.assertIn("language-mermaid", html)


if __name__ == "__main__":
    unittest.main()
