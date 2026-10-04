"""Sync span kinds, object lifecycle generations, and post-create give exclusions."""
from __future__ import annotations

import os
import tempfile
import unittest

from btf_viewer_pkg import _bootstrap

_bootstrap.install()

from btf_viewer_pkg.parser import (  # noqa: E402
    _parse_btf,
    _sync_exclusion_note,
    _sync_kind_display,
    _sync_object_hold_detail_rows,
    _sync_object_stats_rows,
)


_TEXT = "\n".join([
    "#version 2.2.0",
    "#timeScale ns",
    "0,Core_0,0,T,[0/0001]A,0,resume,",
    "10,Core_0,0,STI,mutex,0,trigger,create 0x1",
    "12,Core_0,0,STI,mutex,0,trigger,give 0x1",
    "1500,Core_0,0,STI,mutex,0,trigger,take 0x1",
    "1600,Core_0,0,STI,mutex,0,trigger,give 0x1",
    "900,Core_0,0,STI,sem,0,trigger,create 0x2",
    "2000,Core_0,0,STI,sem,0,trigger,give 0x2",
    "2100,Core_0,0,STI,sem,0,trigger,take 0x2",
    "2200,Core_0,0,STI,queue,0,trigger,send 0x3",
    "2300,Core_0,0,STI,queue,0,trigger,recv 0x3",
    "2400,Core_0,0,STI,mutex,0,trigger,delete 0x1",
    "2500,Core_0,0,STI,mutex,0,trigger,create 0x1",
    "2510,Core_0,0,STI,mutex,0,trigger,give 0x1",
    "3600,Core_0,0,STI,mutex,0,trigger,take 0x1",
    "3700,Core_0,0,STI,mutex,0,trigger,give 0x1",
    "5000,Core_0,0,T,[0/0001]A,0,preempt,",
    "",
])


def _parse(text: str):
    fd, path = tempfile.mkstemp(suffix=".btf")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    try:
        return _parse_btf(path)
    finally:
        os.unlink(path)


class SyncSpanKindTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.trace = _parse(_TEXT)
        cls.rows = {r[3]: r for r in _sync_object_stats_rows(cls.trace)}

    def test_span_kind_per_object_type(self) -> None:
        kinds = {h["span_kind"] for o in self.trace.sync_objects.values()
                 for h in o["holds"]}
        self.assertEqual(kinds, {"mutex_hold", "sem_give_take", "queue_send_recv"})
        self.assertEqual(_sync_kind_display(self.rows["sem 0x2"]), "sem · give→take")
        self.assertEqual(_sync_kind_display(self.rows["queue 0x3"]), "queue · send→recv")

    def test_recreated_handle_gets_own_generation(self) -> None:
        self.assertIn("mutex:0x1#1", self.trace.sync_objects)
        self.assertEqual(self.trace.sync_objects["mutex:0x1"]["generation"], 2)
        gen1 = self.rows["mutex 0x1 (gen 1)"]
        gen2 = self.rows["mutex 0x1 (gen 2)"]
        self.assertEqual(gen1[1], "mutex")
        self.assertEqual(_sync_kind_display(gen2), "mutex · hold")
        details = {(d["object"], d["span"]) for d in _sync_object_hold_detail_rows(self.trace)}
        self.assertIn(("mutex 0x1 (gen 1)", "hold"), details)
        self.assertIn(("mutex 0x1 (gen 2)", "hold"), details)

    def test_post_create_gives_counted_in_note(self) -> None:
        self.assertEqual(sum(r[21] for r in self.rows.values()), 2)
        self.assertIn("2 kernel give(s) right after create",
                      _sync_exclusion_note(list(self.rows.values())))


if __name__ == "__main__":
    unittest.main()
