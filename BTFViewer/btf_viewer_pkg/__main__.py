"""Entry point for `python -m btf_viewer_pkg`."""
from __future__ import annotations

from ._bootstrap import install

install()

from .cli import main

if __name__ == "__main__":
    main()
