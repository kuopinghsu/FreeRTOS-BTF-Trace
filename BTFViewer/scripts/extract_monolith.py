#!/usr/bin/env python3
"""One-shot extractor: split btf_viewer.py monolith into btf_viewer_pkg/ modules.

Run from BTFViewer/ after editing the monolith, or once during initial migration.
"""
from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MONOLITH = ROOT / "builds" / "btf_viewer.py"
PKG = ROOT / "btf_viewer_pkg"

# (module_name, start_line, end_line) — 1-based inclusive line numbers in monolith.
# Bundle order matches monolith order (scene before graphics_items is intentional).
SECTIONS: list[tuple[str, int, int]] = [
    ("config", 187, 765),
    ("parser", 766, 3933),
    ("timeline_util", 3935, 4556),
    ("scene", 4557, 7614),
    ("graphics_items", 7615, 8957),
    ("view", 8959, 12659),
    ("stats", 12661, 20899),
    ("mainwindow", 20901, 26863),
    ("platform", 0, 0),  # special — filled below
    ("cli", 26977, 27597),
]

# Package import order (dev mode): load dependencies before dependents.
IMPORT_ORDER: list[str] = [
    "config",
    "parser",
    "timeline_util",
    "graphics_items",
    "scene",
    "view",
    "stats",
    "mainwindow",
    "platform",
    "cli",
]

# Per-module relative imports for dev mode (star-import from lower layers).
IMPORT_FROM: dict[str, list[str]] = {
    "config": [],
    "parser": ["config"],
    "timeline_util": ["config", "parser"],
    "graphics_items": ["config", "parser", "timeline_util"],
    "scene": ["config", "parser", "timeline_util", "graphics_items"],
    "view": ["config", "parser", "timeline_util", "graphics_items", "scene"],
    "stats": ["config", "parser", "timeline_util", "graphics_items", "scene", "view"],
    "mainwindow": [
        "config", "parser", "timeline_util", "graphics_items", "scene", "view", "stats",
    ],
    "platform": ["config"],
    "cli": [
        "config", "parser", "timeline_util", "graphics_items", "scene", "view",
        "stats", "mainwindow", "platform",
    ],
}

PLATFORM_LINES = (81, 137)  # macOS stderr filter in monolith header
PLATFORM_CLI_LINES = (26868, 26976)  # xcb preflight + _configure_qt_startup


def _slice_lines(all_lines: list[str], start: int, end: int) -> str:
    if start <= 0 or end <= 0:
        return ""
    return "".join(all_lines[start - 1 : end])


def _module_header(name: str, body: str) -> str:
    imports = IMPORT_FROM.get(name, [])
    lines = [
        '"""BTF Viewer — %s module (source). Do not edit btf_viewer.py; run make bundle."""'
        % name,
        "from __future__ import annotations",
        "",
        "from ._imports import *  # noqa: F403,F401",
    ]
    for dep in imports:
        lines.append(f"from .{dep} import *  # noqa: F403,F401")
    lines.append("")
    return "\n".join(lines) + (body if body.startswith("\n") else "\n" + body)


def extract(monolith_path: Path, pkg_dir: Path) -> None:
    text = monolith_path.read_text(encoding="utf-8")
    if text.startswith("# GENERATED"):
        raise SystemExit(
            f"refusing to extract from generated file: {monolith_path}\n"
            "Use the git monolith or edit btf_viewer_pkg/ directly."
        )
    all_lines = text.splitlines(keepends=True)

    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text(
        '"""BTF Viewer source package — use `python -m btf_viewer_pkg` in development."""\n',
        encoding="utf-8",
    )

    platform_body = _slice_lines(all_lines, *PLATFORM_LINES) + _slice_lines(
        all_lines, *PLATFORM_CLI_LINES
    )

    for name, start, end in SECTIONS:
        if name == "platform":
            body = platform_body
        else:
            body = _slice_lines(all_lines, start, end)
        if not body.strip():
            raise SystemExit(f"empty section {name!r}")
        out = _module_header(name, body if body.startswith("\n") else "\n" + body)
        (pkg_dir / f"{name}.py").write_text(out, encoding="utf-8")

    main_py = textwrap.dedent(
        '''\
        """Entry point for `python -m btf_viewer_pkg`."""
        from __future__ import annotations

        from ._bootstrap import install

        install()

        from .cli import main

        if __name__ == "__main__":
            main()
        '''
    )
    (pkg_dir / "__main__.py").write_text(main_py, encoding="utf-8")
    print(f"Extracted {len(SECTIONS)} modules + __main__.py -> {pkg_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-i", "--input", type=Path, default=MONOLITH)
    ap.add_argument("-o", "--output", type=Path, default=PKG)
    args = ap.parse_args()
    extract(args.input, args.output)


if __name__ == "__main__":
    main()
