"""Entry point for `python -m btf_viewer_pkg`."""
from __future__ import annotations

from .platform import _configure_qt_startup, _platform_preflight

_platform_preflight()
_configure_qt_startup()

from ._bootstrap import install

install()

from .cli import main

if __name__ == "__main__":
    main()
