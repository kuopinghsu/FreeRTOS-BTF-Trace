"""Portable Workspace (.btfw): save/open round-trip, safety, migration, freshness.

Parity with ``web/tests/workspace.test.js``.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg.investigation_notebook import (  # noqa: E402
    add_bookmark, new_investigation, set_conclusion,
)
from btf_viewer_pkg.workspace import (  # noqa: E402
    MANIFEST,
    MAX_ENTRIES,
    TRACE_MEMBER,
    WORKSPACE_SCHEMA,
    extract_workspace,
    is_safe_member,
    migrate_manifest,
    open_workspace,
    read_manifest,
    save_workspace,
    workspace_sha256,
    workspace_trace_status,
)

_TRACE = b"#version 2.2.0\n#timeScale us\n100,Core_0,0,T,[0/1]W,0,resume,\n"


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.path = str(self.tmp / "w.btfw")

    def _inv(self):
        inv = new_investigation(title="Case")
        inv = add_bookmark(inv, type="observation", title="obs", bookmark_id="o")
        inv = add_bookmark(inv, type="conclusion", title="done", bookmark_id="c")
        return set_conclusion(inv, "final")

    def test_save_open_round_trip(self):
        man = save_workspace(
            self.path, trace_bytes=_TRACE, trace_name="mini.btf",
            view_state={"cursors": [1, 2], "limit": True,
                        "marks": [{"id": 1, "ns": 50, "label": "b", "type": "bookmark"}]},
            health={"status": "pass"},
            findings=[{"id": "blocking", "rule_id": "blocking", "severity": "info"}],
            investigation=self._inv(),
            ai_case={"investigation_case": {"finding": {"id": "f1"}}, "messages": [
                {"role": "user", "content": "why?"}]},
            report_html="<html>r</html>",
            attachments={"note.txt": b"hi"},
            btfviewer_version="1.4.0", locale="en", rule_set_version="wf/1",
        )
        self.assertEqual(man["schema"], WORKSPACE_SCHEMA)
        self.assertEqual(man["trace"]["sha256"], hashlib.sha256(_TRACE).hexdigest())
        self.assertTrue(man["trace"]["embedded"])

        ws = open_workspace(self.path)
        self.assertEqual(ws["trace_bytes"], _TRACE)
        self.assertEqual(ws["view_state"]["cursors"], [1, 2])
        self.assertEqual(ws["view_state"]["marks"][0]["label"], "b")
        self.assertEqual(ws["ai_case"]["messages"][0]["content"], "why?")
        self.assertEqual(ws["health"], {"status": "pass"})
        self.assertEqual(ws["findings"][0]["rule_id"], "blocking")
        self.assertEqual(ws["investigation"]["conclusion"], "final")
        self.assertEqual([b["id"] for b in ws["investigation"]["bookmarks"]], ["o", "c"])
        self.assertEqual(ws["report_html"], "<html>r</html>")
        self.assertEqual(ws["attachments"], {"note.txt": b"hi"})
        self.assertFalse(ws["read_only"])
        self.assertFalse(ws["migrated"])
        self.assertEqual(ws["warnings"], [])

    def test_ai_case_member_is_optional(self):
        save_workspace(self.path, trace_bytes=_TRACE, trace_name="t.btf",
                       investigation=self._inv())
        with zipfile.ZipFile(self.path) as zf:
            self.assertNotIn("investigation/ai_case.json", zf.namelist())
        self.assertIsNone(open_workspace(self.path)["ai_case"])

    def test_container_is_plain_zip(self):
        save_workspace(self.path, trace_bytes=_TRACE, trace_name="t.btf",
                       investigation=self._inv())
        self.assertTrue(zipfile.is_zipfile(self.path))
        with zipfile.ZipFile(self.path) as zf:
            self.assertIn(MANIFEST, zf.namelist())
            self.assertIn(TRACE_MEMBER, zf.namelist())
            self.assertIn("investigation/bookmarks.json", zf.namelist())

    def test_external_trace_reference(self):
        man = save_workspace(
            self.path, trace_bytes=None, trace_ref="/traces/foo.btf",
            trace_name="foo.btf", trace_sha256="deadbeef", trace_size=999,
            embed_trace=False, investigation=self._inv())
        self.assertFalse(man["trace"]["embedded"])
        self.assertEqual(man["trace"]["ref"], "/traces/foo.btf")
        ws = open_workspace(self.path)
        self.assertIsNone(ws["trace_bytes"])
        self.assertEqual(ws["trace_ref"], "/traces/foo.btf")

    def test_atomic_save_no_tmp_left_and_prev_survives_failure(self):
        save_workspace(self.path, trace_bytes=b"v1", trace_name="t.btf")
        first = Path(self.path).read_bytes()
        # A failing serialisation must not clobber the existing file.
        try:
            save_workspace(self.path, trace_bytes=b"v2", trace_name="t.btf",
                           view_state={"bad": {1, 2}})  # set is not JSON-serialisable
        except TypeError:
            pass
        self.assertEqual(Path(self.path).read_bytes(), first)
        self.assertFalse(list(self.tmp.glob("*.tmp")))

    def test_read_manifest_is_quick_path(self):
        save_workspace(self.path, trace_bytes=_TRACE, trace_name="t.btf")
        man = read_manifest(self.path)
        self.assertEqual(man["schema"], WORKSPACE_SCHEMA)

    def test_reproducible_bytes(self):
        kw = dict(trace_bytes=_TRACE, trace_name="t.btf", investigation=self._inv(),
                  view_state={"a": 1})
        p1 = str(self.tmp / "a.btfw")
        p2 = str(self.tmp / "b.btfw")
        save_workspace(p1, created="2020-01-01T00:00:00+00:00",
                       modified="2020-01-01T00:00:00+00:00", **kw)
        save_workspace(p2, created="2020-01-01T00:00:00+00:00",
                       modified="2020-01-01T00:00:00+00:00", **kw)
        self.assertEqual(Path(p1).read_bytes(), Path(p2).read_bytes())

    def test_safe_extract_to_disk(self):
        save_workspace(self.path, trace_bytes=_TRACE, trace_name="t.btf",
                       investigation=self._inv(), report_html="<h1>x</h1>")
        dest = self.tmp / "out"
        written = extract_workspace(self.path, str(dest))
        self.assertTrue((dest / "manifest.json").is_file())
        self.assertTrue((dest / "trace" / "source.btf").is_file())
        self.assertTrue(all(str(dest) in p for p in written))


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _zip(self, name, members):
        p = str(self.tmp / name)
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
            for m, data in members:
                zf.writestr(m, data)
        return p

    _OK_MANIFEST = '{"schema":"btf-viewer-workspace/1","trace":{"embedded":false}}'

    def test_is_safe_member(self):
        for n in ("a/b.txt", "manifest.json", "trace/source.btf", "a/b/"):
            self.assertTrue(is_safe_member(n), n)
        for n in ("../x", "a/../b", "/x", "C:\\x", "a\\b", "  s", "", "a/./b", "~/x"):
            self.assertFalse(is_safe_member(n), n)

    def test_path_traversal_members_skipped_not_extracted(self):
        p = self._zip("t.btfw", [
            (MANIFEST, self._OK_MANIFEST),
            ("../../etc/passwd", "pwned"),
            ("/abs", "pwned"),
        ])
        ws = open_workspace(p)
        self.assertEqual(len(ws["warnings"]), 2)
        self.assertEqual(ws["extra_members"], [])

    def test_too_many_entries_rejected(self):
        members = [(MANIFEST, self._OK_MANIFEST)]
        members += [(f"attachments/f{i}.txt", "x") for i in range(MAX_ENTRIES + 2)]
        p = self._zip("many.btfw", members)
        with self.assertRaises(ValueError):
            open_workspace(p)

    def test_compression_bomb_rejected(self):
        p = self._zip("bomb.btfw", [
            (MANIFEST, self._OK_MANIFEST),
            ("attachments/big.bin", b"\0" * (4 * 1024 * 1024)),
        ])
        with self.assertRaises(ValueError):
            open_workspace(p)

    def test_decompressed_size_cap(self):
        with self.assertRaises(ValueError):
            open_workspace(
                self._zip("big.btfw", [
                    (MANIFEST, self._OK_MANIFEST),
                    ("attachments/a.bin", os.urandom(1024)),
                ]),
                max_uncompressed=100,
            )

    def test_not_a_zip(self):
        p = str(self.tmp / "j.btfw")
        Path(p).write_bytes(b"not a zip at all")
        with self.assertRaises(ValueError):
            open_workspace(p)

    def test_missing_manifest(self):
        p = self._zip("nom.btfw", [("state/view.json", "{}")])
        with self.assertRaises(ValueError):
            open_workspace(p)

    def test_extract_refuses_escape(self):
        p = self._zip("esc.btfw", [
            (MANIFEST, self._OK_MANIFEST), ("ok/f.txt", "x")])
        # is_safe_member already screens names; extraction also re-checks the
        # resolved target stays under dest.
        self.assertEqual(
            [Path(x).name for x in extract_workspace(p, str(self.tmp / "d"))],
            ["manifest.json", "f.txt"],
        )


class MigrationAndFreshnessTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_newer_schema_opens_read_only_and_keeps_unknown_fields(self):
        p = str(self.tmp / "future.btfw")
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr(MANIFEST, json.dumps({
                "schema": "btf-viewer-workspace/99",
                "trace": {"embedded": False},
                "_new_field": {"x": 1},
            }))
        ws = open_workspace(p)
        self.assertTrue(ws["read_only"])
        self.assertEqual(ws["manifest"]["_new_field"], {"x": 1})

    def test_migrate_manifest_identity_for_current(self):
        m = {"schema": WORKSPACE_SCHEMA, "trace": {}}
        out, changed = migrate_manifest(m)
        self.assertFalse(changed)
        self.assertEqual(out["schema"], WORKSPACE_SCHEMA)

    def test_migrate_manifest_stamps_unknown_old(self):
        out, changed = migrate_manifest({"schema": "btf-viewer-workspace/0", "trace": {}})
        self.assertTrue(changed)
        self.assertEqual(out["schema"], WORKSPACE_SCHEMA)

    def test_trace_status_detects_change_and_missing_hash(self):
        save_workspace(str(self.tmp / "w.btfw"), trace_bytes=_TRACE, trace_name="t.btf")
        man = read_manifest(str(self.tmp / "w.btfw"))
        same = workspace_trace_status(man, current_sha256=workspace_sha256(_TRACE))
        self.assertTrue(same["matches"])
        diff = workspace_trace_status(man, current_sha256=workspace_sha256(b"other"))
        self.assertFalse(diff["matches"])
        self.assertIn("changed", diff["reason"])
        none = workspace_trace_status(man)
        self.assertIsNone(none["matches"])
        no_hash = workspace_trace_status({"trace": {"embedded": True}},
                                        current_sha256="abc")
        self.assertIsNone(no_hash["matches"])

    def test_trace_status_size_fallback(self):
        st = workspace_trace_status(
            {"trace": {"sha256": "x", "size": 100, "embedded": False}},
            current_size=200)
        self.assertFalse(st["matches"])
        self.assertIn("size", st["reason"])


class ParityTests(unittest.TestCase):
    def test_module_and_js_in_step(self):
        py = (BTF_ROOT / "btf_viewer_pkg" / "workspace.py").read_text("utf-8")
        js = (BTF_ROOT / "web" / "src" / "utils" / "workspace.js").read_text("utf-8")
        for member in ("manifest.json", "trace/source.btf", "state/view.json",
                       "analysis/health.json", "analysis/findings.json",
                       "investigation/bookmarks.json", "investigation/ai_case.json",
                       "reports/report.html", "attachments/"):
            self.assertIn(f'"{member}"', py, member)
            self.assertIn(f"'{member}'", js, member)
        for py_name, js_name in (
            ("def build_manifest", "export function buildManifest"),
            ("def migrate_manifest", "export function migrateManifest"),
            ("def workspace_trace_status", "export function workspaceTraceStatus"),
            ("def workspace_sha256", "export function workspaceSha256Hex"),
            ("WORKSPACE_SCHEMA", "export const WORKSPACE_SCHEMA"),
        ):
            self.assertIn(py_name, py, py_name)
            self.assertIn(js_name, js, js_name)
        # The archive is opened through the shared hardened container reader on
        # both platforms (see tests/test_zip_container.py for its own parity).
        self.assertIn("from .zip_container import", py)
        self.assertIn("read_zip_container", py)
        self.assertIn("safe_extract_all", py)
        self.assertIn("from './zipContainer.js'", js)
        self.assertIn("readZipContainer", js)
        self.assertIn("isSafeMember", js)


if __name__ == "__main__":
    unittest.main()
