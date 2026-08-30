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
        self.assertIn('globals().get("FIND_RECOMPUTE")', text)
        self.assertIn('globals().get("recompute_find_hits")', text)
        # Old broken pattern: try/pass then only assign in except.
        self.assertNotRegex(
            text,
            r"try:\n\s+pass\n\s+except ImportError:\n"
            r"\s+_recompute_find_hits = globals\(\)\.get",
        )

    def test_bundled_correlate_med267_no_such_group(self) -> None:
        """Desktop monolith: ai_mermaid must not clobber ai_tools task-id RE.

        A shared ``_TASK_ID_RE`` name made ``_task_match_aliases('Med[267]')``
        call ``m.group(1)`` on a pattern with no groups → IndexError
        ``no such group``, failing correlate/critical-path in the GUI only.
        """
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        bundle = BTF_ROOT / "builds" / "btf_viewer.py"
        if not bundle.is_file():
            self.skipTest("builds/btf_viewer.py missing")
        text = bundle.read_text(encoding="utf-8")
        self.assertIn("_TASK_ID_SUFFIX_RE", text)
        self.assertIn("_MERMAID_TASK_ID_RE", text)
        # Capturing suffix pattern must remain the binding used by aliases.
        self.assertIn(r'_TASK_ID_SUFFIX_RE = re.compile(r"\[(\d+)\]\s*$")', text)

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "btf_viewer_bundle_med267", bundle)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["btf_viewer_bundle_med267"] = mod
        spec.loader.exec_module(mod)

        aliases = mod._task_match_aliases("Med[267]")
        self.assertIn("267", aliases)
        self.assertIn("Med", aliases)

        trace_path = BTF_ROOT.parent / "tracedata" / "example-8cores.btf.gz"
        if not trace_path.is_file():
            self.skipTest("missing example-8cores.btf.gz")
        tr = mod._parse_btf(str(trace_path))
        corr = mod.correlate_task_events(
            tr, "Med[267]", around_time=3087000.0, window=2000.0)
        self.assertTrue(corr.get("ok"), corr.get("message"))
        self.assertNotIn("no such group", str(corr.get("message") or "").lower())
        cp = mod.find_critical_path_task(tr, "Med[267]", timestamp=3087000.0)
        self.assertTrue(cp.get("ok"), cp.get("message"))

    def test_bundled_compare_rows_time_units_scale(self) -> None:
        """Desktop monolith: Trace Compare cells must upscale ns→µs→ms→s.

        ``numeric_format`` (dead in the package, still bundled) once defined its
        own ``_format_time_trim`` that shadowed ``timeline_util``'s unit-scaling
        one in the flat monolith namespace, so every ``_build_trace_compare_rows``
        cell rendered as raw ``2.42e+06 us`` in the shipped app only.
        """
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        bundle = BTF_ROOT / "builds" / "btf_viewer.py"
        if not bundle.is_file():
            self.skipTest("builds/btf_viewer.py missing")
        text = bundle.read_text(encoding="utf-8")
        # Exactly one top-level `_format_time_trim` def survives in the monolith.
        self.assertEqual(text.count("\ndef _format_time_trim("), 1)

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "btf_viewer_bundle_cmpunits", bundle)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules["btf_viewer_bundle_cmpunits"] = mod
        spec.loader.exec_module(mod)

        # A µs-scale trace: deltas below 1000 µs stay µs, ≥1000 µs roll up to ms.
        self.assertEqual(mod._format_time_trim(23000, "us"), "23 ms")
        self.assertEqual(mod._fmt_signed_time_delta(23000, "us"), "+23 ms")

        trace_path = BTF_ROOT.parent / "tracedata" / "example-8cores.btf.gz"
        if not trace_path.is_file():
            self.skipTest("missing example-8cores.btf.gz")
        tr = mod._parse_btf(str(trace_path))
        rows = mod._build_trace_compare_rows(tr, tr)
        span = next(r for r in rows["summary"] if r[0] == "Span")
        # Same trace vs itself → delta "0"; the A/B cells must still be scaled,
        # never scientific-notation raw units.
        for cell in (span[1], span[2]):
            self.assertNotIn("e+", str(cell))
            self.assertRegex(str(cell), r"\d\s(ns|µs|us|ms|s)$")


if __name__ == "__main__":
    unittest.main()
