"""Shared semantic UI tokens and control styles.

Lockstep with ``web/src/utils/uiTheme.js``. Trace-data colors stay elsewhere.
"""
from __future__ import annotations

from typing import Dict

# Modern UX palette. Existing shell tokens (accent, win_bg, …) remain the live
# chrome backgrounds; text roles and new surfaces use these keys.
# ``divider`` is decorative (no contrast target); ``control_border`` outlines
# interactive controls and must reach 3:1 against workspace and surface.
UI_THEME: Dict[str, Dict[str, object]] = {
    "dark": {
        "workspace": "#151A22",
        "surface": "#1D2430",
        "fg": "#E6EDF5",
        "fg_dim": "#A6B3C4",
        "divider": "#344052",
        "control_border": "#6B7C93",
        "accent_ui": "#78A9FF",
        "on_accent": "#0B1220",
        "warning": "#E67E22",
        "success": "#7DCEA0",
        "focus": "#78A9FF",
        "destructive": "#FF8585",
        "ctrl_h": 28,
        "radius_ctrl": 6,
        "radius_card": 8,
        "sp_1": 4,
        "sp_2": 8,
        "sp_3": 12,
        "sp_4": 16,
    },
    "light": {
        "workspace": "#F5F7FA",
        "surface": "#FFFFFF",
        "fg": "#182230",
        "fg_dim": "#526173",
        "divider": "#DCE3EC",
        "control_border": "#7A8799",
        "accent_ui": "#2563EB",
        "on_accent": "#FFFFFF",
        "warning": "#9A4D00",
        "success": "#166534",
        "focus": "#2563EB",
        "destructive": "#B3261E",
        "ctrl_h": 28,
        "radius_ctrl": 6,
        "radius_card": 8,
        "sp_1": 4,
        "sp_2": 8,
        "sp_3": 12,
        "sp_4": 16,
    },
}

BUTTON_ROLES = ("primary", "secondary", "quiet", "destructive")

REPORT_EXPAND_TABS = ("stats", "ai")
REPORT_EXPAND_FRACTION = 0.82
REPORT_EXPAND_MIN_TIMELINE = 240
REPORT_EXPAND_MIN_REPORT = 180

TEXT_CONTRAST_MIN = 4.5
UI_CONTRAST_MIN = 3.0


def ui_theme_tokens(is_dark: bool) -> Dict[str, object]:
    """Return a copy of the semantic token table for *is_dark*."""
    return dict(UI_THEME["dark" if is_dark else "light"])


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    chans = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in chans]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two ``#RRGGBB`` colors."""
    la, lb = sorted((_relative_luminance(a), _relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def report_expand_allowed(tab: str) -> bool:
    return tab in REPORT_EXPAND_TABS


def expanded_report_width(
    available_px: float,
    fraction: float = REPORT_EXPAND_FRACTION,
    min_report: int = REPORT_EXPAND_MIN_REPORT,
    current: int = 0,
) -> int:
    """Report width in expanded mode: ~82% of the workspace, but always leaving
    the timeline ``REPORT_EXPAND_MIN_TIMELINE`` px, never below the panel
    minimum, and never narrower than the report already is (*current*)."""
    avail = max(0, int(available_px or 0))
    wanted = min(int(avail * fraction), avail - REPORT_EXPAND_MIN_TIMELINE)
    return max(min_report, wanted, int(current or 0))


STATUS_CUES: Dict[str, str] = {"error": "✖", "warning": "⚠", "success": "✓", "info": ""}


def status_cue_text(msg: str, severity: str = "info") -> str:
    """Prefix a status line with a severity glyph so meaning never depends on
    color alone. Idempotent; info lines stay quiet."""
    text = str(msg or "")
    cue = STATUS_CUES.get(severity, "")
    if not text or not cue or text.startswith(cue):
        return text
    return f"{cue} {text}"


def report_expand_button(expanded: bool, return_pending: bool = False) -> Dict[str, str]:
    """Header button state for the report expand / restore / return cycle."""
    if expanded:
        return {"label": "Restore layout", "tooltip": "Restore the previous panel width"}
    if return_pending:
        return {"label": "Back to report", "tooltip": "Re-expand the report you were reading"}
    return {"label": "Expand report", "tooltip": "Give the report most of the workspace"}


def button_qss(role: str, tokens: Dict[str, object], *, object_name: str = "") -> str:
    """QSS for a primary / secondary / quiet / destructive push button."""
    if role not in BUTTON_ROLES:
        raise ValueError(f"unknown button role: {role}")
    sel = f"QPushButton#{object_name}" if object_name else "QPushButton"
    radius = int(tokens["radius_ctrl"])
    height = int(tokens["ctrl_h"])
    pad = f"{int(tokens['sp_1'])}px {int(tokens['sp_3'])}px"
    accent = str(tokens["accent_ui"])
    on_accent = str(tokens["on_accent"])
    fg = str(tokens["fg"])
    fg_dim = str(tokens["fg_dim"])
    divider = str(tokens["divider"])
    border = str(tokens["control_border"])
    surface = str(tokens["surface"])
    destructive = str(tokens["destructive"])
    focus = str(tokens["focus"])
    focus_rule = f"{sel}:focus {{ border:2px solid {focus}; }}"
    if role == "primary":
        return (
            f"{sel} {{ background:{accent}; color:{on_accent}; border:1px solid {accent};"
            f" border-radius:{radius}px; min-height:{height}px; padding:{pad}; }}"
            f"{sel}:hover {{ border-color:{fg}; }}"
            f"{sel}:disabled {{ background:{divider}; color:{fg_dim}; border-color:{divider}; }}"
            + focus_rule
        )
    if role == "destructive":
        return (
            f"{sel} {{ background:transparent; color:{destructive}; border:1px solid {destructive};"
            f" border-radius:{radius}px; min-height:{height}px; padding:{pad}; }}"
            f"{sel}:hover {{ background:{destructive}; color:{surface}; }}"
            + focus_rule
        )
    if role == "quiet":
        return (
            f"{sel} {{ background:transparent; color:{fg_dim}; border:1px solid transparent;"
            f" border-radius:{radius}px; min-height:{height}px; padding:{pad}; }}"
            f"{sel}:hover {{ color:{fg}; border-color:{border}; }}"
            + focus_rule
        )
    return (
        f"{sel} {{ background:{surface}; color:{fg}; border:1px solid {border};"
        f" border-radius:{radius}px; min-height:{height}px; padding:{pad}; }}"
        f"{sel}:hover {{ border-color:{accent}; }}"
        + focus_rule
    )
