"""HTML report chrome: TOC expand/collapse used by Statistics and Trace Compare."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg import _bootstrap  # noqa: E402

_bootstrap.install()

from btf_viewer_pkg.html_report import (  # noqa: E402
    HTML_REPORT_TOC_SCRIPT,
    html_apply_collapsible_toc,
)


class HtmlReportTocTests(unittest.TestCase):
    def test_statistics_html_toc_has_expand_collapse_all(self):
        body = (
            "<!--TOC-->\n"
            '<section class="report-card analysis-findings">'
            "<h2>Analysis Findings</h2><p>x</p></section>\n"
            '<section class="report-card notes">'
            "<h2>Statistics Notes</h2><p>y</p></section>\n"
            '<section class="report-card">'
            "<h2>Core Migrations</h2><p>z</p></section>\n"
            + HTML_REPORT_TOC_SCRIPT
        )
        html = html_apply_collapsible_toc(
            body,
            default_expanded=(
                "Analysis Findings",
                "Statistics Notes",
                "Core Utilisation (excl. IDLE/TICK)",
                "Top Tasks by CPU (excl. IDLE/TICK)",
                "Trace Health (TICK)",
            ),
        )
        self.assertIn("Expand all", html)
        self.assertIn("Collapse all", html)
        self.assertIn('data-toc="expand"', html)
        self.assertIn('data-toc="collapse"', html)
        self.assertIn("setAllOpen", html)
        self.assertIn('id="sec-1" open', html)
        self.assertIn("Core Migrations", html)
        self.assertNotIn('id="sec-3" open', html)


if __name__ == "__main__":
    unittest.main()
