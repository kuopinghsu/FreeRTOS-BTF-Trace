"""Semantic vs data color roles (Step 3).

Lockstep with ``web/src/utils/semanticColors.js``.
"""
from __future__ import annotations

from typing import Dict

SEMANTIC_ROLES: Dict[str, str] = {
    "error": "error",
    "warning": "warning",
    "improvement": "improvement",
    "focus": "focus",
    "selection": "selection",
}

SEMANTIC_CSS_VARS: Dict[str, str] = {
    "error": "--semantic-error",
    "warning": "--semantic-warning",
    "improvement": "--semantic-improvement",
    "focus": "--semantic-focus",
    "selection": "--semantic-selection",
}

COMPARE_SEMANTIC: Dict[str, str] = {
    "regressed": "#e74c3c",
    "improved": "#27ae60",
    "neutral": "#95a5a6",
    "focus": "#4F8BFF",
}

SEMANTIC_GLYPHS: Dict[str, str] = {
    "error": "✕",
    "warning": "⚠",
    "improvement": "↓",
    "improved": "↓",
    "regressed": "↑",
}


def semantic_css_var(role: str) -> str:
    if role == "improved":
        return SEMANTIC_CSS_VARS["improvement"]
    if role == "regressed":
        return SEMANTIC_CSS_VARS["error"]
    return SEMANTIC_CSS_VARS.get(role, SEMANTIC_CSS_VARS["focus"])


def semantic_label(text: str, role: str, colorblind: bool = False) -> str:
    glyph = SEMANTIC_GLYPHS.get(role, "")
    if colorblind and glyph:
        return f"{glyph} {text}"
    return text


def format_semantic_delta(text: str, status: str, colorblind: bool = False) -> str:
    """Prefix a signed delta / status cell for colorblind-safe Compare tables."""
    s = str(status or "").lower()
    if s in ("improved", "improvement"):
        return semantic_label(text, "improved", colorblind)
    if s in ("regressed", "error"):
        return semantic_label(text, "regressed", colorblind)
    if s in ("warning", "warn"):
        return semantic_label(text, "warning", colorblind)
    return text
