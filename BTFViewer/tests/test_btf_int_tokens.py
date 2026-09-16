"""Decimal and 0x-hex acceptance for BTF numeric tokens (Desktop ↔ Web lockstep)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from btf_viewer_pkg.parser import (  # noqa: E402
    _normalize_sync_ptr,
    _parse_create_priority,
    _parse_int_token,
    _parse_priority_sti_note,
    _parse_sync_object_note,
    _try_parse_btf_int,
    _interpret_tag_value,
)


class BtfIntTokenTests(unittest.TestCase):
    def test_try_parse_decimal_and_hex(self) -> None:
        self.assertEqual(_try_parse_btf_int("42"), 42)
        self.assertEqual(_try_parse_btf_int("0x2a"), 42)
        self.assertEqual(_try_parse_btf_int("0X2A"), 42)
        self.assertEqual(_try_parse_btf_int("+0x10"), 16)
        self.assertEqual(_try_parse_btf_int("-0x10"), -16)
        self.assertEqual(_try_parse_btf_int("0011"), 11)
        self.assertIsNone(_try_parse_btf_int(""))
        self.assertIsNone(_try_parse_btf_int("pri:4"))
        self.assertIsNone(_try_parse_btf_int("3.14"))

    def test_parse_int_token_defaults(self) -> None:
        self.assertEqual(_parse_int_token("0xB"), 11)
        self.assertEqual(_parse_int_token("bad", default=-1), -1)

    def test_tag_values_decimal_and_hex(self) -> None:
        self.assertEqual(_interpret_tag_value("255", "uint32"), 255.0)
        self.assertEqual(_interpret_tag_value("0xff", "uint32"), 255.0)
        self.assertEqual(_interpret_tag_value("0xFFFFFFFF", "int32"), -1.0)

    def test_priority_notes_accept_hex(self) -> None:
        self.assertEqual(_parse_create_priority("create pri:4"), 4)
        self.assertEqual(_parse_create_priority("create pri:0x4"), 4)
        parsed = _parse_priority_sti_note("set_priority Worker[1] pri:0xA")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed[2], 10)

    def test_sync_ptr_normalizes_decimal_and_hex(self) -> None:
        self.assertEqual(_normalize_sync_ptr("42"), "0x2a")
        self.assertEqual(_normalize_sync_ptr("0x2A"), "0x2a")
        self.assertEqual(
            _parse_sync_object_note("take 42"),
            ("take", "0x2a"),
        )
        self.assertEqual(
            _parse_sync_object_note("take 0x2a"),
            ("take", "0x2a"),
        )
        self.assertEqual(
            _parse_sync_object_note("give"),
            ("give", "0x0"),
        )


if __name__ == "__main__":
    unittest.main()
