"""extract_xtf_pack for shareable demo .xtf archives."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

BTF_ROOT = Path(__file__).resolve().parents[1]
if str(BTF_ROOT) not in sys.path:
    sys.path.insert(0, str(BTF_ROOT))

from btf_viewer_pkg._bootstrap import install  # noqa: E402

install()

from btf_viewer_pkg.parser import (  # noqa: E402
    _BTF_OPEN_FILTER,
    extract_xtf_pack,
    is_xtf_open_path,
)


class XtfExtractTests(unittest.TestCase):
    def test_is_xtf_open_path(self) -> None:
        self.assertTrue(is_xtf_open_path("demo_8cores.xtf"))
        self.assertFalse(is_xtf_open_path("demo.zip"))
        self.assertFalse(is_xtf_open_path("demo.btf.gz"))

    def test_open_filter_includes_xtf_in_default_entry(self) -> None:
        primary = _BTF_OPEN_FILTER.split(";;")[0]
        self.assertIn("*.xtf", primary)
        self.assertIn("*.xml", primary)
        self.assertIn("*.btf", primary)

    def test_extract_xtf_pack(self) -> None:
        with tempfile.TemporaryDirectory(prefix="btf_xtf_") as td:
            xtf = Path(td) / "demo.xtf"
            with zipfile.ZipFile(xtf, "w") as zf:
                zf.writestr("demo_8cores.xml", b"<demo/>")
                zf.writestr("demo_8cores.btf.gz", b"\x1f\x8b")
                zf.writestr("voice/en/01.mp3", b"x")
            xml, btf = extract_xtf_pack(str(xtf))
            self.assertTrue(os.path.isfile(xml))
            self.assertTrue(os.path.isfile(btf))
            self.assertTrue(xml.endswith("demo_8cores.xml"))
            self.assertTrue(btf.endswith("demo_8cores.btf.gz"))


if __name__ == "__main__":
    unittest.main()
