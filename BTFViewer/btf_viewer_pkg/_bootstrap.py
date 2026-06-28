"""Merge btf_viewer_pkg module globals to mirror the monolith flat namespace.

Private names (leading _) are not re-exported by `from .foo import *`; after all
modules load, symbols from earlier modules are injected into each module dict so
cross-module references like `_parse_btf()` resolve at runtime in dev mode.
"""
from __future__ import annotations

import importlib
from typing import Iterable

# Load order: dependencies before dependents.
IMPORT_ORDER: tuple[str, ...] = (
    "config",
    "parser",
    "timeline_util",
    "graphics_items",
    "scene",
    "view",
    "stats",
    "mvvm.base",
    "mvvm.models",
    "mvvm.app_settings",
    "mvvm.stats_vm",
    "mvvm.find_logic",
    "mvvm.tab_viewport",
    "mvvm.trace_tab_vm",
    "mvvm.main_vm",
    "mvvm.bindings",
    "mvvm",
    "mainwindow",
    "platform",
    "cli",
)

_PKG = __name__.rsplit(".", 1)[0] if "." in __name__ else "btf_viewer_pkg"
_installed = False

def _flatten(modules: Iterable[object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for mod in modules:
        for key, val in mod.__dict__.items():
            if key.startswith("__"):
                continue
            out[key] = val
    return out

def install() -> None:
    global _installed
    if _installed:
        return
    mods = [importlib.import_module(f".{name}", _PKG) for name in IMPORT_ORDER]
    flat = _flatten(mods)
    for mod in mods:
        mod.__dict__.update(flat)
    _installed = True
