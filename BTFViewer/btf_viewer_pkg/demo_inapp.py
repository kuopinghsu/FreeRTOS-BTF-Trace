"""In-app desktop demo tour (Web overlay runner parity; no pyautogui)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Union

from PySide6.QtCore import (
    QEasingCurve, QEvent, QLoggingCategory, QPoint, QPointF, QRect, QSize, Qt,
    QUrl, QVariantAnimation, Signal,
)
from PySide6.QtGui import QColor, QHoverEvent, QMouseEvent, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QApplication, QComboBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QWidget,
)

from .config import (
    _IC_DEMO_NEXT, _IC_DEMO_PAUSE, _IC_DEMO_PLAY, _IC_DEMO_PREV, _svg_icon,
)
from .demo_api import DemoApiBridge
from .parser import is_btf_open_path

_VAR_RE = re.compile(r"\$\{([A-Za-z0-9_./-]+)\}")
SKIP_TAGS = frozenset({
    "hotkey", "type", "focus", "voice", "note", "comment", "log", "title",
})
_LANG_RE = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)?$", re.I)
_AUDIO_RE = re.compile(r"\.(mp3|wav|m4a|ogg|flac|aac|aiff|aif)$", re.I)
_DEMO_MEDIA_LOG_RULES = "qt.multimedia.ffmpeg=false"


def silence_demo_media_logs() -> None:
    """Quiet Qt FFmpeg / PipeWire chatter from in-app AAC playback."""
    os.environ.setdefault("PIPEWIRE_DEBUG", "0")
    os.environ.setdefault("WIREPLUMBER_DEBUG", "0")
    cur = (os.environ.get("QT_LOGGING_RULES") or "").strip()
    if _DEMO_MEDIA_LOG_RULES not in cur:
        os.environ["QT_LOGGING_RULES"] = (
            f"{cur};{_DEMO_MEDIA_LOG_RULES}" if cur else _DEMO_MEDIA_LOG_RULES
        )
    try:
        rules = os.environ["QT_LOGGING_RULES"].replace(",", "\n").replace(";", "\n")
        QLoggingCategory.setFilterRules(rules)
    except Exception:
        pass
_VOICE_LABELS = {
    "en": "English",
    "zh": "简体中文",
    "zh-tw": "中文",
    "ja": "日本語",
    "ko": "한국어",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
}
PathLike = Union[str, Path]


class DemoAborted(Exception):
    pass


class DemoSkip(Exception):
    def __init__(self, direction: int = 1) -> None:
        super().__init__("demo skip")
        self.direction = 0 if direction == 0 else (-1 if direction < 0 else 1)


def expand_vars(text: Optional[str], variables: Dict[str, str]) -> str:
    if text is None:
        return ""
    out = str(text)
    for _ in range(8):
        nxt = _VAR_RE.sub(
            lambda m: variables[m.group(1)] if m.group(1) in variables else m.group(0),
            out,
        )
        if nxt == out:
            break
        out = nxt
    return out


expand = expand_vars


def text_content(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    parts: List[str] = [el.text or ""]
    for child in el:
        parts.append(text_content(child))
        parts.append(child.tail or "")
    return "".join(parts).strip()


def truthy(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() not in ("0", "false", "no", "off")


def normalize_voice_lang(raw: Any) -> str:
    s = str(raw or "").strip().replace("_", "-").lower()
    if not s:
        return ""
    parts = s.split("-")
    a = parts[0]
    b = parts[1] if len(parts) > 1 else ""
    if a == "zh" and b in ("tw", "hant", "hk", "mo"):
        return "zh-tw"
    if a == "zh" and b in ("cn", "sg", "hans"):
        return "zh"
    return a or ""


def pick_voice_lang(
    preferred: Any,
    available: Sequence[str],
    fallback: str = "en",
) -> str:
    ids = [normalize_voice_lang(x) for x in available if normalize_voice_lang(x)]
    want = normalize_voice_lang(preferred)
    if want and want in ids:
        return want
    if want:
        prefix = want.split("-")[0]
        for item in ids:
            if item == prefix or item.startswith(prefix + "-"):
                return item
    fb = normalize_voice_lang(fallback) or "en"
    if fb in ids:
        return fb
    if "en" in ids:
        return "en"
    return ids[0] if ids else fb


def preferred_voice_lang(variables: Optional[Dict[str, str]] = None) -> str:
    """Explicit demo language only — not the process locale.

    Order: ``VOICE_LANG`` / ``LANG`` extras, then ``BTFVIEWER_DEMO_LANG``.
    Empty means the XML ``<languages default>`` (or UI locale / saved Voice).
    """
    vars_ = variables or {}
    for cand in (
        vars_.get("VOICE_LANG"),
        vars_.get("LANG"),
        os.environ.get("BTFVIEWER_DEMO_LANG"),
    ):
        if cand and str(cand).strip():
            return str(cand).strip()
    return ""


def voice_path_candidates(
    rel: PathLike,
    lang: str,
    default_lang: str = "en",
) -> List[Any]:
    as_path = isinstance(rel, Path)
    n = rel.as_posix() if as_path else str(rel or "")
    n = n.replace("\\", "/")
    if n.startswith("./"):
        n = n[2:]
    n = n.replace("//", "/")
    if not n:
        return []
    parts = n.split("/")
    try:
        voice_idx = next(i for i, p in enumerate(parts) if p.lower() == "voice")
    except StopIteration:
        return [rel] if as_path else [n]
    prefix = "/".join(parts[: voice_idx + 1])
    rest = parts[voice_idx + 1:]
    basename = "/".join(rest)
    if rest and _LANG_RE.match(rest[0] or ""):
        basename = "/".join(rest[1:])
    out: List[str] = []

    def add(p: str) -> None:
        s = p.replace("\\", "/").replace("//", "/")
        if s and s not in out:
            out.append(s)

    lang_n = normalize_voice_lang(lang)
    def_n = normalize_voice_lang(default_lang) or "en"
    if lang_n:
        add(f"{prefix}/{lang_n}/{basename}")
    add(f"{prefix}/{basename}")
    if def_n and def_n != lang_n:
        add(f"{prefix}/{def_n}/{basename}")
    add(n)
    return [Path(s) for s in out] if as_path else out


def discover_voice_langs(root: Path, default_lang: str = "en") -> List[str]:
    found: Set[str] = set()
    flat = False
    voice = Path(root) / "voice"
    if not voice.is_dir():
        return []
    for dirpath, _dirs, files in os.walk(voice):
        rel = Path(dirpath).relative_to(root).as_posix()
        for name in files:
            if not _AUDIO_RE.search(name):
                continue
            nested = re.match(
                r"(?:^|/)voice/([^/]+)/[^/]+\.(mp3|wav|m4a|ogg|flac|aac|aiff|aif)$",
                f"{rel}/{name}",
                re.I,
            )
            if nested:
                found.add(normalize_voice_lang(nested.group(1)))
            elif re.match(
                    r"^voice/[^/]+\.(mp3|wav|m4a|ogg|flac|aac|aiff|aif)$",
                    f"{rel}/{name}", re.I):
                flat = True
    if flat:
        found.add(normalize_voice_lang(default_lang) or "en")
    return [x for x in found if x]


def merge_voice_langs(
    parsed: Optional[Dict[str, Any]],
    discovered: Sequence[Any],
) -> Dict[str, Any]:
    parsed = parsed or {}
    raw_list = parsed.get("list") or []
    base: List[Dict[str, str]] = (
        [{"id": x["id"], "label": x["label"]} for x in raw_list]
        if raw_list
        else [{"id": "en", "label": "English"}]
    )
    for item in discovered or []:
        n = normalize_voice_lang(item)
        if n and not any(x["id"] == n for x in base):
            base.append({"id": n, "label": _VOICE_LABELS.get(n, n)})
    default_id = parsed.get("defaultId") or "en"
    if not any(x["id"] == default_id for x in base):
        default_id = base[0]["id"]
    return {"defaultId": default_id, "list": base}


def resolve_media_path(raw: str, variables: Dict[str, str]) -> Path:
    """Resolve an audio/media path with ${vars} and ``voice/<lang>/`` fallbacks."""
    expanded = expand_vars(raw, variables).strip()
    p = Path(expanded).expanduser()
    bases = [
        Path(variables.get("XML_DIR", ".")),
        Path(variables.get("CWD", ".")),
        Path(variables.get("BTF", ".")),
        Path(variables.get("REPO", ".")),
        Path("."),
    ]
    lang = variables.get("LANG") or variables.get("VOICE_LANG") or ""
    default_lang = variables.get("VOICE_DEFAULT") or "en"
    roots = voice_path_candidates(p, lang, default_lang) or [p]
    exts = (".mp3", ".aac", ".wav", ".m4a", ".aiff", ".aif", ".ogg", ".flac")
    seen: List[Path] = []
    for root_p in roots:
        cands = [root_p]
        if not root_p.is_absolute():
            cands.extend(b / root_p for b in bases)
        for cand in cands:
            for variant in (cand, cand.with_suffix("") if cand.suffix else cand):
                probe = [variant]
                if variant.suffix:
                    probe.append(variant)
                else:
                    probe.extend(variant.with_suffix(ext) for ext in exts)
                    probe.append(variant)
                for item in probe:
                    if item not in seen:
                        seen.append(item)
                    if item.is_file():
                        return item
    return Path(expanded)


def load_demo_xml(path: Path) -> ET.Element:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "demo":
        raise ValueError(f"root element must be <demo>, got <{root.tag}>")
    return root


def is_demo_xml_path(path: str) -> bool:
    if not str(path or "").lower().endswith(".xml"):
        return False
    try:
        load_demo_xml(Path(path))
        return True
    except (OSError, ET.ParseError, ValueError):
        return False


def _first_btf_in(folder: Path) -> Optional[Path]:
    try:
        found = sorted(
            child for child in folder.iterdir()
            if child.is_file() and is_btf_open_path(str(child))
        )
    except OSError:
        return None
    return found[0] if found else None


def discover_demo_pack(path: str) -> Optional[Tuple[str, str]]:
    """Return ``(xml_path, btf_path)`` if *path* is a demo XML or pack folder."""
    raw = Path(os.path.abspath(os.path.expanduser(path)))
    xml: Optional[Path] = None
    folder: Optional[Path] = None
    if raw.is_file() and raw.suffix.lower() == ".xml":
        xml = raw
        folder = raw.parent
    elif raw.is_dir():
        folder = raw
        xmls = sorted(p for p in raw.glob("*.xml") if p.is_file())
        demoish = [p for p in xmls if "demo" in p.name.lower()]
        for cand in demoish or xmls:
            try:
                load_demo_xml(cand)
                xml = cand
                break
            except (OSError, ET.ParseError, ValueError):
                continue
    if xml is None or folder is None:
        return None
    try:
        load_demo_xml(xml)
    except (OSError, ET.ParseError, ValueError):
        return None
    btf = _first_btf_in(folder)
    if btf is None:
        return None
    return str(xml), str(btf)


def build_variables(
    root: ET.Element, xml_path: Path, extras: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    xml_path = Path(xml_path).resolve()
    vars_: Dict[str, str] = {
        "XML": str(xml_path),
        "XML_DIR": str(xml_path.parent),
        "HOME": str(Path.home()),
        "CWD": str(Path.cwd()),
        "PYTHON": sys.executable,
        "REPO": str(xml_path.parent),
        "BTF": str(xml_path.parent),
        "MOD": "mod",
    }
    meta = root.find("meta")
    if meta is not None:
        for child in meta:
            if child.tag in ("title", "description", "author", "languages"):
                continue
            if child.tag == "var":
                name = child.attrib.get("name", "").strip()
                if name:
                    vars_[name] = expand_vars(
                        text_content(child) or child.attrib.get("value", ""), vars_)
                continue
            vars_[child.tag] = expand_vars(
                text_content(child) or child.attrib.get("value", ""), vars_)
    if extras:
        vars_.update(extras)
    for _ in range(3):
        vars_ = {k: expand_vars(v, vars_) for k, v in vars_.items()}
    return vars_


def parse_languages(root: ET.Element) -> Dict[str, Any]:
    wrap = root.find("languages")
    if wrap is None:
        meta = root.find("meta")
        if meta is not None:
            wrap = meta.find("languages")
    items: List[Dict[str, str]] = []
    default_id = "en"
    if wrap is not None:
        default_id = normalize_voice_lang(
            wrap.attrib.get("default") or wrap.attrib.get("lang") or "en"
        ) or "en"
        for el in wrap.findall("language"):
            lang_id = normalize_voice_lang(
                el.attrib.get("id") or el.attrib.get("lang") or "")
            if not lang_id:
                continue
            label = (el.attrib.get("label") or el.attrib.get("name") or lang_id).strip() or lang_id
            if not any(x["id"] == lang_id for x in items):
                items.append({"id": lang_id, "label": label})
    if not items:
        items.append({"id": "en", "label": "English"})
    if not any(x["id"] == default_id for x in items):
        default_id = items[0]["id"]
    return {"defaultId": default_id, "list": items}


def parse_targets(root: ET.Element) -> Dict[str, Tuple[float, float]]:
    out: Dict[str, Tuple[float, float]] = {}
    wrap = root.find("targets")
    if wrap is None:
        return out
    for pt in wrap.findall("point"):
        name = pt.attrib.get("name", "").strip()
        if not name:
            continue
        out[name] = (float(pt.attrib["x"]), float(pt.attrib["y"]))
    return out


def parse_macros(root: ET.Element) -> Dict[str, List[ET.Element]]:
    out: Dict[str, List[ET.Element]] = {}
    wrap = root.find("macros")
    if wrap is None:
        return out
    for macro in wrap.findall("macro"):
        name = macro.attrib.get("name", "").strip()
        if name:
            out[name] = list(macro)
    return out


def parse_defaults(root: ET.Element) -> Dict[str, float]:
    el = root.find("defaults")
    if el is None:
        return {
            "after_voice": 1.5,
            "pause": 0.8,
            "ai_wait": 35.0,
            "move_duration": 0.35,
            "audio_block": 0.0,
        }

    def f(name: str, default: float) -> float:
        return float(el.attrib.get(name, default))

    return {
        "after_voice": f("after_voice", 1.5),
        "pause": f("pause", 0.8),
        "ai_wait": f("ai_wait", 35.0),
        "move_duration": f("move_duration", 0.35),
        "audio_block": 1.0 if truthy(el.attrib.get("audio_block"), False) else 0.0,
    }


def parse_steps(root: ET.Element) -> List[Dict[str, Any]]:
    wrap = root.find("steps")
    if wrap is None:
        return []
    out = []
    for el in wrap.findall("step"):
        tags = {t.strip() for t in el.attrib.get("tags", "").split(",") if t.strip()}
        out.append({
            "id": el.attrib.get("id", "?"),
            "title": el.attrib.get("title", ""),
            "optional": truthy(el.attrib.get("optional"), False),
            "tags": tags,
            "el": el,
        })
    return out


def should_skip_step(
    step: Dict[str, Any], *, skip_optional: bool = False, skip_tags: Any = (),
) -> bool:
    if skip_optional and step.get("optional"):
        return True
    skip = skip_tags if isinstance(skip_tags, set) else set(skip_tags or [])
    for t in step.get("tags") or []:
        if t in skip:
            return True
    return False


def _event_is_trusted(event: Any) -> bool:
    """Web ``event.isTrusted``; Qt maps that to ``QEvent.spontaneous()``."""
    if event is None:
        return False
    if isinstance(event, dict):
        return bool(event.get("isTrusted"))
    trusted = getattr(event, "isTrusted", None)
    if trusted is not None:
        return bool(trusted)
    spontaneous = getattr(event, "spontaneous", None)
    if callable(spontaneous):
        return bool(spontaneous())
    return False


def should_hide_native_cursor(_owner_list: Any = None) -> bool:
    """Lockstep with Web ``shouldHideNativeCursor`` (always false)."""
    return False


def should_hide_simulated_cursor_on_move(event: Any, owner_list: Any = None) -> bool:
    """Real mouse motion hides the parked demo overlay (Web lockstep)."""
    if not _event_is_trusted(event):
        return False
    owners = owner_list if isinstance(owner_list, set) else set(owner_list or [])
    if "record" in owners and "demo" not in owners:
        return False
    return "demo" in owners


_DEMO_MOVE_EVENT_TYPES = {QEvent.Type.MouseMove, QEvent.Type.HoverMove}
_ptr_move = getattr(QEvent.Type, "PointerMove", None)
if _ptr_move is not None:
    _DEMO_MOVE_EVENT_TYPES.add(_ptr_move)


# ---------------------------------------------------------------------------
# Overlay + banner
# ---------------------------------------------------------------------------

class DemoPointerOverlay(QWidget):
    """Mouse-transparent pointer drawn over the main window (Web overlay)."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(24, 24)
        self.hide()
        self._anim: Optional[QVariantAnimation] = None
        self._anim_done: Optional[Callable[[], None]] = None
        self._user_hidden = False
        self.on_moved: Optional[Callable[[QPoint], None]] = None
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        try:
            et = event.type()
        except Exception:
            return False
        if et in _DEMO_MOVE_EVENT_TYPES and should_hide_simulated_cursor_on_move(
                event, ("demo",)):
            self.hide_pointer()
        return False

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.moveTo(5.0, 3.2)
        path.lineTo(5.0, 20.6)
        path.lineTo(9.5, 16.0)
        path.lineTo(12.4, 22.9)
        path.lineTo(14.8, 21.9)
        path.lineTo(11.9, 15.1)
        path.lineTo(18.0, 15.1)
        path.closeSubpath()
        p.setPen(QColor(17, 17, 17, 230))
        p.setBrush(QColor(255, 255, 255, 245))
        p.drawPath(path)
        p.end()

    def _stop_anim(self, *, complete: bool) -> None:
        anim = self._anim
        cb = self._anim_done
        self._anim = None
        self._anim_done = None
        if anim is not None:
            anim.stop()
        if complete and cb is not None:
            cb()

    def _place(self, local: QPoint) -> None:
        if self._user_hidden:
            return
        self.move(local.x(), local.y())
        self.raise_()
        self.show()
        if self.on_moved:
            self.on_moved(local)

    def jump_to_window(self, local: QPoint) -> None:
        self._user_hidden = False
        self._stop_anim(complete=True)
        self._place(local)

    def animate_to_window(self, local: QPoint, duration_s: float, done: Callable[[], None]) -> None:
        self._user_hidden = False
        start = QPoint(self.x(), self.y()) if self.isVisible() else local
        self._stop_anim(complete=True)
        ms = max(0, int(duration_s * 1000))
        if ms <= 0 or start == local:
            self._place(local)
            done()
            return
        anim = QVariantAnimation(self)
        anim.setDuration(ms)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.setStartValue(QPointF(start))
        anim.setEndValue(QPointF(local))

        def _step(value) -> None:
            if isinstance(value, QPoint):
                pt = value
            else:
                pt = QPoint(int(round(value.x())), int(round(value.y())))
            self._place(pt)

        anim.valueChanged.connect(_step)

        def _finished() -> None:
            if self._anim is not anim:
                return
            self._anim = None
            self._anim_done = None
            self._place(local)
            done()

        anim.finished.connect(_finished)
        self._anim = anim
        self._anim_done = done
        self.show()
        anim.start()

    def hide_pointer(self) -> None:
        self._user_hidden = True
        self._stop_anim(complete=True)
        self.hide()


class DemoStatusBanner(QWidget):
    prevClicked = Signal()
    pauseClicked = Signal()
    nextClicked = Signal()
    voiceChanged = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("demo_status_banner")
        self.setVisible(False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(4)
        self._nav_armed = False
        self._paused = False
        self._can_prev = False
        self._can_next = False
        fg = "#cdefff"
        self._btn_prev = self._nav_btn(_IC_DEMO_PREV, "Previous section", self.prevClicked)
        self._btn_pause = self._nav_btn(_IC_DEMO_PAUSE, "Pause demo", self.pauseClicked)
        self._btn_next = self._nav_btn(_IC_DEMO_NEXT, "Next section", self.nextClicked)
        lay.addWidget(self._btn_prev)
        lay.addWidget(self._btn_pause)
        lay.addWidget(self._btn_next)
        self._status = QLabel("")
        self._status.setObjectName("demo_status_text")
        self._status.setStyleSheet(f"color:{fg};")
        self._status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(self._status, 1)
        self._lang_wrap = QWidget()
        lang_lay = QHBoxLayout(self._lang_wrap)
        lang_lay.setContentsMargins(6, 0, 0, 0)
        lang_lay.setSpacing(4)
        lab = QLabel("Voice")
        lab.setStyleSheet(f"color:{fg}; font-size:11px;")
        self._lang = QComboBox()
        self._lang.setObjectName("demo_lang_select")
        self._lang.setFixedHeight(22)
        self._lang.currentIndexChanged.connect(self._on_lang)
        lang_lay.addWidget(lab)
        lang_lay.addWidget(self._lang)
        self._lang_wrap.setVisible(False)
        lay.addWidget(self._lang_wrap)
        self._hint = QLabel("Esc twice to stop")
        self._hint.setObjectName("demo_status_hint")
        self._hint.setStyleSheet(f"color:{fg}; font-size:11px;")
        lay.addWidget(self._hint)
        self._updating_lang = False

    def _nav_btn(self, path: str, tip: str, sig: Signal) -> QPushButton:
        btn = QPushButton()
        btn.setIcon(_svg_icon(path, "#cdefff", 14))
        btn.setIconSize(QSize(14, 14))
        btn.setFixedSize(22, 22)
        btn.setToolTip(tip)
        btn.setFlat(True)
        btn.clicked.connect(lambda: self._emit_nav(sig))
        return btn

    def _emit_nav(self, sig: Signal) -> None:
        if self._nav_armed:
            sig.emit()

    def set_armed(self, on: bool) -> None:
        self._nav_armed = bool(on)
        self._btn_prev.setEnabled(self._nav_armed and self._can_prev)
        self._btn_pause.setEnabled(self._nav_armed)
        self._btn_next.setEnabled(self._nav_armed and self._can_next)

    def set_status(self, text: str) -> None:
        self._status.setText(text or "")

    def set_nav(self, nav: Optional[Dict[str, Any]]) -> None:
        nav = nav or {}
        self._can_prev = bool(nav.get("canPrev"))
        self._can_next = bool(nav.get("canNext"))
        self._btn_prev.setEnabled(self._nav_armed and self._can_prev)
        self._btn_next.setEnabled(self._nav_armed and self._can_next)

    def set_paused(self, on: bool) -> None:
        self._paused = bool(on)
        path = _IC_DEMO_PLAY if self._paused else _IC_DEMO_PAUSE
        self._btn_pause.setIcon(_svg_icon(path, "#cdefff", 14))
        self._btn_pause.setToolTip("Resume demo" if self._paused else "Pause demo")
        self._hint.setText("Paused · Esc twice to stop" if self._paused else "Esc twice to stop")

    def set_languages(self, langs: Sequence[Dict[str, str]], current: str) -> None:
        self._updating_lang = True
        self._lang.blockSignals(True)
        self._lang.clear()
        for item in langs:
            self._lang.addItem(item.get("label") or item["id"], item["id"])
        self._lang_wrap.setVisible(len(langs) > 1)
        idx = max(0, self._lang.findData(current))
        self._lang.setCurrentIndex(idx)
        self._lang.blockSignals(False)
        self._updating_lang = False

    def _on_lang(self, _idx: int) -> None:
        if self._updating_lang:
            return
        data = self._lang.currentData()
        if data:
            self.voiceChanged.emit(str(data))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class InAppDemoRunner:
    """Execute a demo XML pack against MainWindow._demo_handle + overlay."""

    def __init__(
        self,
        window: QWidget,
        handle: Callable[[Dict[str, Any]], Any],
        overlay: DemoPointerOverlay,
        *,
        xml_path: Path,
        voice_lang: str = "",
        ai_wait_cap_sec: float = 4.0,
        on_status: Optional[Callable[[str], None]] = None,
        on_nav: Optional[Callable[[Optional[Dict[str, Any]]], None]] = None,
        on_paused: Optional[Callable[[bool], None]] = None,
        on_voice: Optional[Callable[[str], None]] = None,
        on_toast: Optional[Callable[[str, str], None]] = None,
        press_escape: Optional[Callable[[], None]] = None,
    ) -> None:
        self._window = window
        self._handle = handle
        self._overlay = overlay
        self._bridge = DemoApiBridge(parent=window)
        self._xml_path = Path(xml_path)
        self._root = load_demo_xml(self._xml_path)
        self._vars = build_variables(self._root, self._xml_path)
        self._defaults = parse_defaults(self._root)
        self._targets = parse_targets(self._root)
        self._macros = parse_macros(self._root)
        parsed_langs = parse_languages(self._root)
        discovered = discover_voice_langs(self._xml_path.parent)
        self.languages = merge_voice_langs(parsed_langs, discovered)
        ids = [x["id"] for x in self.languages["list"]]
        self._voice_lang = pick_voice_lang(
            voice_lang, ids, self.languages["defaultId"])
        self._vars["LANG"] = self._voice_lang
        self._vars["VOICE_LANG"] = self._voice_lang
        self._vars["VOICE_DEFAULT"] = self.languages["defaultId"]
        self._ai_wait_cap = float(ai_wait_cap_sec)
        self._on_status = on_status
        self._on_nav = on_nav
        self._on_paused = on_paused
        self._on_voice = on_voice
        self._on_toast = on_toast
        self._press_escape = press_escape
        self._abort = threading.Event()
        self._skip_dir = 0
        self._skip_restart = False
        self._skip_gate = threading.Event()
        self._paused = False
        self._pause_gate = threading.Event()
        self._pause_gate.set()
        self._audio_proc: Optional[subprocess.Popen] = None
        self._audio_player: Any = None
        self._audio_done = threading.Event()
        self._audio_done.set()
        self.aborted = False
        silence_demo_media_logs()

    @property
    def voice_lang(self) -> str:
        return self._voice_lang

    @property
    def paused(self) -> bool:
        return self._paused

    def gui(self, fn: Callable[[], Any]) -> Any:
        return self._bridge.call(fn)

    def _ui(self, fn: Callable[[], None]) -> None:
        if fn is None:
            return
        try:
            self.gui(fn)
        except Exception:
            pass

    def stop(self) -> None:
        self.aborted = True
        self._abort.set()
        self._paused = False
        self._pause_gate.set()
        self._skip_gate.set()
        self._stop_audio()
        if self._on_paused:
            self._ui(lambda: self._on_paused(False))

    def skip_prev(self) -> None:
        self._request_skip(-1)

    def skip_next(self) -> None:
        self._request_skip(1)

    def toggle_pause(self) -> None:
        self._set_paused(not self._paused)

    def set_voice_lang(self, lang_id: str) -> str:
        ids = [x["id"] for x in self.languages["list"]]
        nxt = pick_voice_lang(lang_id, ids, self.languages["defaultId"])
        if nxt == self._voice_lang:
            return nxt
        self._voice_lang = nxt
        self._vars["LANG"] = nxt
        self._vars["VOICE_LANG"] = nxt
        if self._on_voice:
            self._ui(lambda: self._on_voice(nxt))
        self._skip_restart = True
        self._skip_dir = 0
        self._stop_audio()
        if self._paused:
            self._set_paused(False)
        self._skip_gate.set()
        return nxt

    def _request_skip(self, direction: int) -> None:
        if self._abort.is_set():
            return
        self._skip_restart = False
        self._skip_dir = -1 if direction < 0 else 1
        self._stop_audio()
        if self._paused:
            self._set_paused(False)
        self._skip_gate.set()

    def _set_paused(self, on: bool) -> None:
        if self._abort.is_set():
            return
        nxt = bool(on)
        if self._paused == nxt:
            return
        self._paused = nxt
        if self._paused:
            self._pause_gate.clear()
            self._pause_audio()
        else:
            self._pause_gate.set()
            self._resume_audio()
        if self._on_paused:
            self._ui(lambda: self._on_paused(self._paused))

    def _check(self) -> None:
        if self._abort.is_set():
            raise DemoAborted()
        if self._skip_restart:
            raise DemoSkip(0)
        if self._skip_dir:
            raise DemoSkip(self._skip_dir)

    def _reset_skip(self) -> None:
        self._skip_dir = 0
        self._skip_restart = False
        self._skip_gate.clear()

    def _wait_interruptible(self, seconds: float) -> None:
        left = max(0.0, float(seconds))
        while True:
            while self._paused and not self._abort.is_set() and not self._skip_dir and not self._skip_restart:
                self._pause_gate.wait(0.1)
            self._check()
            if left <= 0:
                return
            slice_s = min(0.05, left)
            fired = self._skip_gate.wait(slice_s)
            self._check()
            if fired:
                self._check()
            left -= slice_s

    def _attr(self, el: ET.Element, name: str, fallback: str = "") -> str:
        if name not in el.attrib:
            return fallback
        return expand_vars(el.attrib.get(name, ""), self._vars)

    def _api(self, payload: Dict[str, Any], settle: float = 0.0) -> Any:
        def _go() -> Any:
            return self._handle(payload)

        out = self.gui(_go)
        if settle:
            self._wait_interruptible(settle)
        return out

    def _window_box(self) -> QRect:
        def _go() -> QRect:
            return QRect(0, 0, max(1, self._window.width()), max(1, self._window.height()))

        return self.gui(_go)

    def _resolve_xy(self, el: ET.Element) -> Optional[QPoint]:
        name = self._attr(el, "target").strip()
        if name:
            try:
                hit = self._api({"op": "target", "name": name}, settle=0.0)
                gx = int(hit.get("x"))
                gy = int(hit.get("y"))

                def _local() -> QPoint:
                    return self._window.mapFromGlobal(QPoint(gx, gy))

                return self.gui(_local)
            except Exception:
                pt = self._targets.get(name)
                if pt is None:
                    return None
                fx, fy = pt
        else:
            try:
                fx = float(self._attr(el, "x", "0.5"))
                fy = float(self._attr(el, "y", "0.5"))
            except ValueError:
                return None
        box = self._window_box()
        x = fx if abs(fx) > 1 else fx * box.width()
        y = fy if abs(fy) > 1 else fy * box.height()
        return QPoint(int(round(x)), int(round(y)))

    def _hover_at(self, local: QPoint) -> None:
        gp = self._window.mapToGlobal(local)
        w = QApplication.widgetAt(gp)
        if w is None:
            return
        lp = w.mapFromGlobal(gp)
        try:
            hover = QHoverEvent(
                QEvent.Type.HoverMove,
                QPointF(lp),
                QPointF(gp),
                QPointF(lp),
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.sendEvent(w, hover)
        except TypeError:
            pass
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(lp),
            QPointF(gp),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(w, move)

    def _move_overlay(self, local: QPoint, duration: float) -> None:
        done = threading.Event()

        def _go() -> None:
            self._overlay.on_moved = self._hover_at
            self._overlay.animate_to_window(local, duration, done.set)

        self.gui(_go)
        while not done.wait(0.05):
            self._check()

    def _click_overlay(self, local: QPoint) -> None:
        def _go() -> None:
            gp = self._window.mapToGlobal(local)
            w = QApplication.widgetAt(gp)
            skip = w
            while skip is not None:
                if isinstance(skip, DemoStatusBanner) or skip.objectName() == "demo_status_banner":
                    return
                skip = skip.parentWidget()
            if w is None:
                return
            lp = w.mapFromGlobal(gp)
            press = QMouseEvent(
                QEvent.Type.MouseButtonPress,
                QPointF(lp),
                QPointF(gp),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
            rel = QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                QPointF(lp),
                QPointF(gp),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.sendEvent(w, press)
            QApplication.sendEvent(w, rel)

        self.gui(_go)

    def _stop_audio(self) -> None:
        proc = self._audio_proc
        self._audio_proc = None
        player = self._audio_player
        self._audio_player = None
        self._audio_done.set()

        def _stop_player() -> None:
            if player is None:
                return
            try:
                player.stop()
            except Exception:
                pass

        try:
            self.gui(_stop_player)
        except Exception:
            pass
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=0.4)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def _pause_audio(self) -> None:
        player = self._audio_player
        if player is not None:
            try:
                self.gui(player.pause)
            except Exception:
                pass
            return
        proc = self._audio_proc
        if proc is None or proc.poll() is not None:
            return
        if hasattr(os, "kill") and getattr(os, "WUNTRACED", None) is not None:
            try:
                os.kill(proc.pid, 19)  # SIGSTOP
            except Exception:
                pass

    def _resume_audio(self) -> None:
        player = self._audio_player
        if player is not None:
            try:
                self.gui(player.play)
            except Exception:
                pass
            return
        proc = self._audio_proc
        if proc is None or proc.poll() is not None:
            return
        try:
            os.kill(proc.pid, 18)  # SIGCONT
        except Exception:
            pass

    def _play_audio(self, path: Path, block: bool) -> None:
        self._stop_audio()
        self._audio_done.clear()
        started = self.gui(lambda: self._start_audio_gui(path))
        if not started:
            self._audio_done.set()
            return
        if block:
            self._wait_audio()

    def _start_audio_gui(self, path: Path) -> bool:
        silence_demo_media_logs()
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except ImportError:
            QMediaPlayer = None  # type: ignore[assignment]
            QAudioOutput = None  # type: ignore[assignment]
        if QMediaPlayer is not None and QAudioOutput is not None:
            try:
                player = QMediaPlayer(self._window)
                output = QAudioOutput(self._window)
                player.setAudioOutput(output)
                player.setSource(QUrl.fromLocalFile(str(path)))

                def _done(status) -> None:
                    try:
                        end = QMediaPlayer.MediaStatus.EndOfMedia
                    except Exception:
                        end = None
                    if end is not None and status == end:
                        self._audio_done.set()

                player.mediaStatusChanged.connect(_done)
                player.errorOccurred.connect(lambda *_: self._audio_done.set())
                self._audio_player = player
                player.play()
                return True
            except Exception:
                self._audio_player = None
        cmd: Optional[List[str]] = None
        helper = Path(__file__).resolve().parents[1] / "scripts" / "play_audio_clip.py"
        if not helper.is_file():
            helper = Path(sys.argv[0]).resolve().parent / "scripts" / "play_audio_clip.py"
        if helper.is_file():
            cmd = [sys.executable, str(helper), str(path)]
        elif shutil.which("ffplay"):
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
        elif shutil.which("afplay"):
            cmd = ["afplay", str(path)]
        elif shutil.which("paplay"):
            cmd = ["paplay", str(path)]
        if not cmd:
            if self._on_toast:
                self._on_toast(f"Demo audio missing player: {path.name}", "error")
            return False
        try:
            self._audio_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            if self._on_toast:
                self._on_toast(str(exc), "error")
            return False

        def _wait() -> None:
            try:
                if self._audio_proc is not None:
                    self._audio_proc.wait()
            except Exception:
                pass
            self._audio_done.set()

        threading.Thread(target=_wait, daemon=True).start()
        return True

    def _wait_audio(self) -> None:
        while not self._audio_done.is_set():
            self._check()
            self._audio_done.wait(0.05)
        self._check()

    def _run_macro(self, name: str, call_el: Optional[ET.Element]) -> None:
        if name == "fit":
            self._api({"op": "fit"}, settle=0.4)
            return
        if name == "clear_cursors":
            self._api({"op": "clear_cursors"})
            return
        if name == "clear_bookmarks":
            self._api({"op": "clear_bookmarks"})
            return
        if name == "clear_annotations":
            self._api({"op": "clear_annotations"})
            return
        if name == "settings":
            self._api({"op": "settings", "page": "appearance"}, settle=0.5)
            return
        body = self._macros.get(name)
        if not body:
            return
        saved = dict(self._vars)
        if call_el is not None:
            for k, v in call_el.attrib.items():
                if k in ("ref", "name"):
                    continue
                self._vars[k] = expand_vars(v, saved)
            for p in call_el.findall("param"):
                pn = p.attrib.get("name", "")
                if pn:
                    self._vars[pn] = expand_vars(
                        text_content(p) or p.attrib.get("value", ""), saved)
        try:
            for child in body:
                self._run_action(child)
        finally:
            self._vars.clear()
            self._vars.update(saved)

    def _run_action(self, el: ET.Element) -> None:
        while self._paused and not self._abort.is_set() and not self._skip_dir and not self._skip_restart:
            self._pause_gate.wait(0.1)
        self._check()
        tag = el.tag
        if tag in SKIP_TAGS:
            if tag == "hotkey":
                keys = self._attr(el, "keys").lower()
                if keys in ("esc", "escape") and self._press_escape:
                    self.gui(self._press_escape)
            return
        if tag in ("move", "click"):
            xy = self._resolve_xy(el)
            if xy is not None:
                dur = float(el.attrib["duration"]) if "duration" in el.attrib else self._defaults["move_duration"]
                self._move_overlay(xy, dur)
                if tag == "click":
                    self._click_overlay(xy)
            return
        if tag == "sweep":
            box = self._window_box()
            yf = float(el.attrib.get("y", "0.055"))
            x0 = float(el.attrib.get("x0", "0.1"))
            x1 = float(el.attrib.get("x1", "0.85"))
            steps = max(1, int(el.attrib.get("steps", "8")))
            pause = float(el.attrib.get("pause", "0.3"))
            y = int(yf * box.height())
            for i in range(steps):
                self._check()
                fx = x0 + (x1 - x0) * (i / max(1, steps - 1))
                self._move_overlay(QPoint(int(fx * box.width()), y), 0.2)
                self._wait_interruptible(pause)
            return
        if tag == "scroll":
            return
        if tag == "press":
            key = self._attr(el, "key").lower()
            if key in ("esc", "escape") and self._press_escape:
                self.gui(self._press_escape)
            return
        if tag == "confirm":
            prompt = expand_vars(el.attrib.get("prompt", "") or text_content(el), self._vars)
            if prompt and self._on_toast:
                msg = prompt
                self._ui(lambda: self._on_toast(msg, "info"))
            return
        if tag in ("audio", "play"):
            rel = self._attr(el, "file")
            path = None
            for cand in voice_path_candidates(
                    rel, self._voice_lang, self.languages["defaultId"]):
                p = Path(expand_vars(str(cand), self._vars))
                if not p.is_absolute():
                    p = self._xml_path.parent / p
                if p.is_file():
                    path = p
                    break
            if path is None:
                try:
                    got = resolve_media_path(rel, self._vars)
                    if got.is_file():
                        path = got
                except Exception:
                    path = None
            block = truthy(el.attrib.get("block"), bool(self._defaults.get("audio_block")))
            if path is None:
                if self._on_toast:
                    self._ui(lambda: self._on_toast(f"Demo audio missing: {rel}", "error"))
                return
            self._play_audio(path, block)
            return
        if tag == "wait_audio":
            self._wait_audio()
            return
        if tag == "stop_audio":
            self._stop_audio()
            return
        if tag == "wait":
            is_ai = truthy(el.attrib.get("ai"), False)
            if is_ai:
                sec = float(el.attrib.get("seconds", self._defaults["ai_wait"]))
                sec = min(sec, self._ai_wait_cap)
            else:
                sec = float(el.attrib.get("seconds", "1"))
            self._wait_interruptible(sec)
            return
        if tag == "macro":
            self._run_macro(self._attr(el, "ref", self._attr(el, "name")), el)
            return
        if tag == "highlight":
            self._api({"op": "highlight", "task": self._attr(el, "task", self._attr(el, "name"))})
            return
        if tag == "clear_highlight":
            self._api({"op": "clear_highlight"})
            return
        if tag == "cursors":
            payload: Dict[str, Any] = {
                "op": "cursors",
                "times": self._attr(el, "times", self._attr(el, "timestamps")),
            }
            if "unit" in el.attrib:
                payload["unit"] = self._attr(el, "unit")
            if "limit" in el.attrib:
                payload["limit"] = self._attr(el, "limit")
            if "zoom" in el.attrib:
                payload["zoom"] = self._attr(el, "zoom")
            self._api(payload, settle=0.5)
            return
        if tag == "clear_cursors":
            self._api({"op": "clear_cursors"})
            return
        if tag == "clear_bookmarks":
            self._api({"op": "clear_bookmarks"})
            return
        if tag == "clear_annotations":
            self._api({"op": "clear_annotations"})
            return
        if tag == "zoom_range":
            payload = {
                "op": "zoom_range",
                "start": self._attr(el, "start"),
                "end": self._attr(el, "end"),
            }
            if "unit" in el.attrib:
                payload["unit"] = self._attr(el, "unit")
            if not payload["start"] and el.attrib.get("times"):
                payload["times"] = self._attr(el, "times")
                payload.pop("start", None)
                payload.pop("end", None)
            self._api(payload, settle=0.6)
            return
        if tag in ("fit_view", "fit_api"):
            self._api({"op": "fit"}, settle=0.4)
            return
        if tag in ("zoom_1to1", "one_to_one", "1to1"):
            self._api({"op": "zoom_1to1"}, settle=0.4)
            return
        if tag == "limit":
            self._api({
                "op": "limit",
                "on": self._attr(el, "on", self._attr(el, "enabled", "true")),
            })
            return
        if tag == "stats_section":
            payload = {
                "op": "stats_section",
                "id": self._attr(el, "id", self._attr(el, "section")),
            }
            for key in ("expand", "collapse_others", "scroll"):
                if key in el.attrib:
                    payload[key] = self._attr(el, key)
            settle = 0.35 if str(payload.get("expand", "true")).lower() in (
                "0", "false", "no", "off") else 0.55
            self._api(payload, settle=settle)
            return
        if tag in ("stats_reset", "stats_done"):
            self._api({
                "op": "stats_section",
                "id": "",
                "expand": "false",
                "collapse_others": "true",
                "scroll": "top",
            }, settle=0.4)
            return
        if tag == "jump_wcet":
            self._api({
                "op": "jump_wcet",
                "task": self._attr(el, "task", self._attr(el, "name")),
            }, settle=0.7)
            return
        if tag == "panel":
            self._api({
                "op": "panel",
                "name": self._attr(el, "name", self._attr(el, "tab", "stats")),
            })
            return
        if tag in ("view_mode", "view"):
            self._api({
                "op": "view_mode",
                "mode": self._attr(el, "mode", self._attr(el, "name", "task")),
            }, settle=0.45)
            return
        if tag in ("cpu_load", "load"):
            self._api({
                "op": "cpu_load",
                "on": self._attr(el, "on", self._attr(el, "enabled", "true")),
            }, settle=0.4)
            return
        if tag == "analysis":
            payload = {"op": "analysis"}
            for key in ("open", "close", "action"):
                if key in el.attrib:
                    payload[key] = self._attr(el, key)
            self._api(payload, settle=0.45 if "close" in el.attrib else 0.7)
            return
        if tag in ("tick_dist", "tick_distribution"):
            payload = {"op": "tick_dist"}
            if "close" in el.attrib:
                payload["close"] = self._attr(el, "close")
            if "action" in el.attrib:
                payload["action"] = self._attr(el, "action")
            self._api(payload, settle=0.4)
            return
        if tag == "find":
            payload = {"op": "find"}
            for key in ("query", "text", "q", "clear", "next"):
                if key in el.attrib:
                    payload[key] = self._attr(el, key)
            if not any(k in payload for k in ("query", "text", "q", "clear")):
                payload["query"] = expand_vars(text_content(el), self._vars)
            self._api(payload, settle=0.45)
            return
        if tag == "settings":
            payload = {"op": "settings"}
            for key in ("page", "name", "open", "close", "action"):
                if key in el.attrib:
                    payload[key] = self._attr(el, key)
            if "page" not in payload and "name" not in payload and "close" not in payload:
                payload["page"] = "Appearance"
            self._api(payload, settle=0.4 if "close" in el.attrib else 0.5)
            return
        if tag in ("ui", "command"):
            payload = {"op": "ui"}
            for k, v in el.attrib.items():
                payload[k] = expand_vars(v, self._vars)
            self._api(payload)
            return
        if tag == "demo_api":
            payload = {"op": self._attr(el, "op")}
            for k, v in el.attrib.items():
                if k != "op":
                    payload[k] = expand_vars(v, self._vars)
            self._api(payload)

    def run(self) -> None:
        steps = [s for s in parse_steps(self._root) if not should_skip_step(s)]
        total = len(steps)
        i = 0
        try:
            while i < total:
                if self._abort.is_set():
                    raise DemoAborted()
                self._reset_skip()
                step = steps[i]
                title = step.get("title") or step.get("id") or ""
                if self._on_status:
                    text = f"Demo: {i + 1}/{total} — {title}"
                    self._ui(lambda t=text: self._on_status(t))
                if self._on_nav:
                    nav = {
                        "index": i,
                        "total": total,
                        "title": title,
                        "canPrev": i > 0,
                        "canNext": i < total - 1,
                    }
                    self._ui(lambda n=nav: self._on_nav(n))
                try:
                    for child in list(step["el"]):
                        self._run_action(child)
                    self._wait_audio()
                    self._check()
                    self._wait_interruptible(self._defaults.get("pause") or 0)
                    i += 1
                except DemoSkip as err:
                    direction = 0 if self._skip_restart else (self._skip_dir or err.direction or 1)
                    self._reset_skip()
                    if direction == 0:
                        continue
                    i = max(0, i - 1) if direction < 0 else i + 1
                    continue
            if self._on_status:
                self._ui(lambda: self._on_status(""))
            if self._on_nav:
                self._ui(lambda: self._on_nav(None))
        except DemoAborted:
            if self._on_status:
                self._ui(lambda: self._on_status(""))
            if self._on_nav:
                self._ui(lambda: self._on_nav(None))
        finally:
            self._stop_audio()
            self.gui(self._overlay.hide_pointer)
