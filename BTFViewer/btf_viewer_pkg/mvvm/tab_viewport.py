"""Per-tab timeline viewport capture/apply (no widgets in model layer)."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..config import _sanitize_tab_filters, _snapshot_tab_filters
from .models import TabViewportModel

if TYPE_CHECKING:
    from ..view import TimelineView


def capture_viewport(view: "TimelineView") -> TabViewportModel:
    """Read zoom, cursors, and legend filters from a timeline view."""
    sc = view._scene
    fit = bool(view._fit_mode)
    return TabViewportModel(
        fit_mode=fit,
        zoom_tpp=-1.0 if fit else float(sc.timescale_per_px),
        cursors=list(sc.cursor_times()),
        filters=_snapshot_tab_filters(sc),
    )


def apply_viewport(view: "TimelineView", vp: TabViewportModel) -> None:
    """Restore zoom, cursors, and legend filters onto a timeline view."""
    sc = view._scene
    if vp.fit_mode:
        view.zoom_fit()
    elif vp.zoom_tpp > 0:
        sc._timescale_per_px = max(sc._timescale_per_px_default, vp.zoom_tpp)
        view._fit_mode = False
        sc.rebuild()
        view.zoom_changed.emit(sc.timescale_per_px)
    else:
        view.zoom_changed.emit(sc.timescale_per_px)

    for ns in vp.cursors:
        try:
            sc.add_cursor(int(ns))
        except (ValueError, TypeError):
            pass
    if sc.cursor_times():
        view.cursors_changed.emit(sc.cursor_times())

    filters = _sanitize_tab_filters(vp.filters)
    if filters:
        sc.apply_tab_filters(filters, rebuild=False)
        sc.rebuild()
        sc.task_filter_changed.emit()

    view._refresh_nav_pan_window(force_show=view._navigator_eligible())


def viewport_to_rc_payload(vp: TabViewportModel) -> Dict[str, Any]:
    return {
        "fit_mode": vp.fit_mode,
        "zoom": vp.zoom_tpp,
        "cursors": list(vp.cursors),
        "filters": dict(vp.filters),
    }


def viewport_from_rc_payload(payload: Dict[str, Any]) -> TabViewportModel:
    fit_mode = bool(payload.get("fit_mode", True))
    zoom = float(payload.get("zoom", -1))
    cursors: List[int] = []
    for ns in payload.get("cursors", []):
        try:
            cursors.append(int(ns))
        except (ValueError, TypeError):
            pass
    raw_filters = payload.get("filters") or {}
    filters = _sanitize_tab_filters(raw_filters) or {}
    return TabViewportModel(
        fit_mode=fit_mode,
        zoom_tpp=-1.0 if fit_mode else zoom,
        cursors=cursors,
        filters=filters,
    )


def viewport_to_json(vp: TabViewportModel) -> str:
    return json.dumps(viewport_to_rc_payload(vp), ensure_ascii=True)


def viewport_from_json(raw: str) -> Optional[TabViewportModel]:
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return viewport_from_rc_payload(payload)
