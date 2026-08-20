"""Bundle rewrite of in-function relative imports must bind names."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))


class BundleRelativeImportRewriteTests(unittest.TestCase):
    def test_as_alias_becomes_globals_get(self) -> None:
        from scripts.bundle_viewer import (  # noqa: WPS433
            _neutralize_body_relative_imports,
        )

        src = (
            "def f():\n"
            "    try:\n"
            "        from .mvvm.find_logic import recompute_find_hits as _recompute_find_hits\n"
            "    except ImportError:\n"
            "        _recompute_find_hits = None\n"
            "    return _recompute_find_hits\n"
        )
        out = _neutralize_body_relative_imports(src)
        self.assertIn(
            '_recompute_find_hits = globals().get("recompute_find_hits")', out)
        self.assertNotIn("from .mvvm.find_logic import", out)
        # Bare pass would leave the except-only assignment unbound when try
        # succeeds — that was the correlate_events / search_timeline crash.
        self.assertNotIn("try:\n        pass\n", out)

    def test_multi_name_import_binds_each(self) -> None:
        from scripts.bundle_viewer import (  # noqa: WPS433
            _neutralize_body_relative_imports,
        )

        src = "    from .parser import _task_merge_key, _task_display_name\n"
        out = _neutralize_body_relative_imports(src)
        self.assertIn('_task_merge_key = globals().get("_task_merge_key")', out)
        self.assertIn(
            '_task_display_name = globals().get("_task_display_name")', out)

    def test_bundled_search_timeline_hits_resolves_find_engine(self) -> None:
        """Monolith must not raise UnboundLocalError on search/correlate."""
        bundle = BTF_ROOT / "builds" / "btf_viewer.py"
        if not bundle.is_file():
            self.skipTest("builds/btf_viewer.py missing")
        text = bundle.read_text(encoding="utf-8")
        self.assertIn('globals().get("recompute_find_hits")', text)
        # Old broken pattern: try/pass then only assign in except.
        self.assertNotRegex(
            text,
            r"try:\n\s+pass\n\s+except ImportError:\n"
            r"\s+_recompute_find_hits = globals\(\)\.get",
        )


if __name__ == "__main__":
    unittest.main()
