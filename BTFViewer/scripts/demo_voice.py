#!/usr/bin/env python3
"""Uniform demo voice packs: ``text/<lang>/`` + ``voice/<lang>/`` + ``voice.json``.

Every language is packed the same way. XML keeps
``<audio file="${XML_DIR}/voice/01_title.mp3"/>``; the runner resolves
``voice/<lang>/<file>`` then flat ``voice/<file>`` then ``voice/<default>/``.

On-disk layout inside a demo folder::

    text/<lang>/01_title.txt
    voice/<lang>/01_title.mp3
    voice/<lang>/voice.json

Shareable zip (install/export)::

    voice.json
    text/01_title.txt
    voice/01_title.mp3

Legacy flat ``text/*.txt`` / ``voice/*.mp3`` is treated as the default
language (``en``) until ``normalize`` moves it.

Examples::

    python3 scripts/demo_voice.py status demos/demo_8cores
    python3 scripts/demo_voice.py normalize demos/demo_8cores
    python3 scripts/demo_voice.py export demos/demo_8cores --lang en -o en.zip
    python3 scripts/demo_voice.py install demos/demo_8cores zh-tw.zip
    python3 scripts/demo_voice.py render demos/demo_8cores --lang zh-tw
    python3 scripts/demo_voice.py sync-xml demos/demo_8cores
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA = "btf-demo-voice"
SCHEMA_VERSION = 1
MANIFEST_NAME = "voice.json"
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aiff", ".aif", ".ogg", ".flac"}
TEXT_EXTS = {".txt"}
LANG_RE = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)?$", re.I)
LABELS = {
    "en": "English",
    "zh": "简体中文",
    "zh-tw": "中文",
    "ja": "日本語",
    "ko": "한국어",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
}
DEFAULT_SAY_VOICES = {
    "en": "Samantha",
    "zh-tw": "Meijia",
    "zh": "Tingting",
    "ja": "Kyoko",
    "ko": "Yuna",
    "de": "Anna",
    "fr": "Thomas",
    "es": "Monica",
}


def normalize_voice_lang(raw: Optional[str]) -> str:
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
    preferred: Optional[str],
    available: Sequence[str],
    fallback: str = "en",
) -> str:
    ids = [normalize_voice_lang(x) for x in available]
    ids = [x for x in ids if x]
    want = normalize_voice_lang(preferred)
    if want and want in ids:
        return want
    if want:
        prefix = want.split("-")[0]
        for item in ids:
            if item == prefix or item.startswith(f"{prefix}-"):
                return item
    fb = normalize_voice_lang(fallback) or "en"
    if fb in ids:
        return fb
    if "en" in ids:
        return "en"
    return ids[0] if ids else fb


def voice_label(lang: str, explicit: str = "") -> str:
    n = normalize_voice_lang(lang)
    return (explicit or "").strip() or LABELS.get(n, n or lang)


def voice_path_candidates(
    path: Path,
    lang: str,
    default_lang: str = "en",
) -> List[Path]:
    """``voice/<lang>/<file>``, then flat ``voice/<file>``, then ``voice/<default>/``."""
    n = path.as_posix()
    parts = n.split("/")
    try:
        voice_idx = next(i for i, p in enumerate(parts) if p.lower() == "voice")
    except StopIteration:
        return [path]
    prefix = "/".join(parts[: voice_idx + 1])
    rest = parts[voice_idx + 1 :]
    basename_parts = rest
    if len(rest) >= 2 and LANG_RE.match(rest[0] or ""):
        basename_parts = rest[1:]
    basename = "/".join(basename_parts)
    lang_n = normalize_voice_lang(lang)
    def_n = normalize_voice_lang(default_lang) or "en"
    out: List[str] = []

    def add(item: str) -> None:
        s = re.sub(r"/{2,}", "/", item)
        if s and s not in out:
            out.append(s)

    if lang_n:
        add(f"{prefix}/{lang_n}/{basename}")
    add(f"{prefix}/{basename}")
    if def_n and def_n != lang_n:
        add(f"{prefix}/{def_n}/{basename}")
    add(n)
    return [Path(s) for s in out]


def resolve_demo_dir(path: Path) -> Path:
    p = Path(path).expanduser().resolve()
    if p.is_file() and p.suffix.lower() == ".xml":
        return p.parent
    if p.is_dir():
        return p
    raise FileNotFoundError(f"demo folder not found: {path}")


def find_demo_xml(demo_dir: Path) -> Optional[Path]:
    xmls = sorted(demo_dir.glob("*.xml"))
    if not xmls:
        return None
    demoish = [p for p in xmls if "demo" in p.name.lower()]
    return (demoish or xmls)[0]


def is_audio_name(name: str) -> bool:
    return Path(name).suffix.lower() in AUDIO_EXTS


def is_text_name(name: str) -> bool:
    return Path(name).suffix.lower() in TEXT_EXTS


def posix_rel(path: Path) -> str:
    return path.as_posix().replace("\\", "/").lstrip("./")


def safe_zip_name(name: str) -> str:
    n = name.replace("\\", "/").lstrip("/")
    if not n or n.endswith("/") or ".." in Path(n).parts:
        raise ValueError(f"unsafe zip member: {name!r}")
    return n


def read_manifest(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return data


def write_manifest(
    path: Path,
    lang: str,
    label: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    n = normalize_voice_lang(lang)
    body: Dict[str, Any] = {
        "schema": SCHEMA,
        "version": SCHEMA_VERSION,
        "id": n,
        "label": voice_label(n, label),
    }
    if extra:
        for key, value in extra.items():
            if key not in body:
                body[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def manifest_lang(data: Dict[str, Any]) -> str:
    return normalize_voice_lang(
        str(data.get("id") or data.get("lang") or data.get("language") or "")
    )


def load_lang_manifest(demo_dir: Path, lang: str) -> Dict[str, Any]:
    n = normalize_voice_lang(lang)
    for cand in (
        demo_dir / "voice" / n / MANIFEST_NAME,
        demo_dir / "text" / n / MANIFEST_NAME,
    ):
        if cand.is_file():
            try:
                return read_manifest(cand)
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def iter_lang_records(demo_dir: Path, default_lang: str = "en") -> List[Dict[str, Any]]:
    """One record per language found under text/ and voice/."""
    demo_dir = Path(demo_dir)
    found: Dict[str, Dict[str, Any]] = {}

    def ensure(lang: str) -> Dict[str, Any]:
        n = normalize_voice_lang(lang)
        rec = found.setdefault(
            n,
            {"id": n, "label": voice_label(n), "scripts": [], "clips": []},
        )
        return rec

    def add_file(kind: str, lang: str, path: Path) -> None:
        rec = ensure(lang)
        key = "scripts" if kind == "text" else "clips"
        rel = posix_rel(path.relative_to(demo_dir))
        if rel not in rec[key]:
            rec[key].append(rel)

    for kind, exts in (("text", TEXT_EXTS), ("voice", AUDIO_EXTS)):
        root = demo_dir / kind
        if not root.is_dir():
            continue
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir():
                    lang = normalize_voice_lang(entry.name)
                    if not lang:
                        continue
                    for child in entry.iterdir():
                        if not child.is_file():
                            continue
                        if kind == "voice" and child.name == MANIFEST_NAME:
                            data = read_manifest(child)
                            rec = ensure(lang)
                            rec["label"] = voice_label(lang, str(data.get("label") or ""))
                            continue
                        if child.suffix.lower() in exts:
                            add_file(kind, lang, child)
                elif entry.is_file() and entry.suffix.lower() in exts:
                    add_file(kind, default_lang, entry)
            except OSError:
                continue

    for lang, rec in list(found.items()):
        data = load_lang_manifest(demo_dir, lang)
        if data:
            rec["label"] = voice_label(lang, str(data.get("label") or rec.get("label") or ""))
        rec["scripts"].sort()
        rec["clips"].sort()
    return [found[k] for k in sorted(found)]


def discover_voice_langs(demo_dir: Path, default_lang: str = "en") -> List[str]:
    return [r["id"] for r in iter_lang_records(demo_dir, default_lang)]


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
        if isinstance(item, dict):
            n = normalize_voice_lang(item.get("id"))
            label = voice_label(n, str(item.get("label") or ""))
        else:
            n = normalize_voice_lang(item)
            label = voice_label(n)
        if n and not any(x["id"] == n for x in base):
            base.append({"id": n, "label": label})
        elif n:
            for row in base:
                if row["id"] == n and label and row["label"] == n:
                    row["label"] = label
    default_id = parsed.get("defaultId") or "en"
    if not any(x["id"] == default_id for x in base):
        default_id = base[0]["id"]
    return {"defaultId": default_id, "list": base}


def _copy_file(src: Path, dest: Path, overwrite: bool) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not overwrite:
        return False
    shutil.copy2(src, dest)
    return True


def normalize_demo(
    demo_dir: Path,
    default_lang: str = "en",
    *,
    remove_flat: bool = True,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Move legacy flat text/*.txt and voice/* clips into ``<kind>/<lang>/``."""
    demo_dir = resolve_demo_dir(demo_dir)
    lang = normalize_voice_lang(default_lang) or "en"
    moved = 0
    skipped = 0
    for kind, exts in (("text", TEXT_EXTS), ("voice", AUDIO_EXTS)):
        root = demo_dir / kind
        if not root.is_dir():
            continue
        dest_dir = root / lang
        dest_dir.mkdir(parents=True, exist_ok=True)
        for entry in list(root.iterdir()):
            if not entry.is_file() or entry.suffix.lower() not in exts:
                continue
            dest = dest_dir / entry.name
            if dest.exists() and not overwrite:
                skipped += 1
            else:
                shutil.copy2(entry, dest)
                moved += 1
            if remove_flat:
                entry.unlink()
    write_manifest(
        demo_dir / "voice" / lang / MANIFEST_NAME,
        lang,
        extra={"demo": demo_dir.name},
    )
    return {"moved": moved, "skipped": skipped, "lang": lang}


def _iter_source_files(root: Path) -> List[Tuple[str, Path]]:
    out: List[Tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__"}]
        base = Path(dirpath)
        for name in filenames:
            path = base / name
            rel = posix_rel(path.relative_to(root))
            out.append((rel, path))
    return out


def detect_pack_files(
    files: Sequence[Tuple[str, Path]],
    lang_hint: str = "",
) -> Tuple[str, List[Tuple[str, str, Path]]]:
    """Return (lang, items) where items are (kind, filename, path).

    ``kind`` is ``text``, ``voice``, or ``manifest``.
    """
    hint = normalize_voice_lang(lang_hint)
    items: List[Tuple[str, str, Path]] = []
    langs: List[str] = []
    manifest_lang_id = ""

    def consider(kind: str, filename: str, path: Path, lang: str = "") -> None:
        items.append((kind, filename, path))
        n = normalize_voice_lang(lang)
        if n:
            langs.append(n)

    for rel, path in files:
        parts = [p for p in rel.split("/") if p]
        name = parts[-1] if parts else ""
        lower = [p.lower() for p in parts]
        if name.lower() in {MANIFEST_NAME, "manifest.json"}:
            try:
                data = read_manifest(path)
            except (OSError, json.JSONDecodeError):
                data = {}
            consider("manifest", MANIFEST_NAME, path, manifest_lang(data))
            manifest_lang_id = manifest_lang_id or manifest_lang(data)
            continue
        if is_text_name(name):
            kind = "text"
        elif is_audio_name(name):
            kind = "voice"
        else:
            continue
        if "text" in lower[:-1] or "voice" in lower[:-1]:
            idx = lower.index("text" if kind == "text" else "voice")
            before = parts[idx - 1] if idx > 0 else ""
            after = parts[idx + 1] if idx + 1 < len(parts) - 1 else ""
            lang = ""
            filename = name
            if after and LANG_RE.match(after):
                lang = after
                filename = Path(parts[-1]).name
            elif before and LANG_RE.match(before):
                lang = before
            consider(kind, filename, path, lang)
            continue
        if len(parts) >= 2 and LANG_RE.match(parts[0]):
            consider(kind, name, path, parts[0])
            continue
        consider(kind, name, path, "")

    lang = (
        hint
        or manifest_lang_id
        or (langs[0] if len(set(langs)) == 1 else "")
        or (langs[0] if langs else "")
    )
    if not lang:
        lang = hint
    if not lang:
        raise ValueError(
            "could not detect language id; pass --lang (en, zh-tw, ja, …)"
        )
    return normalize_voice_lang(lang), items


def install_pack(
    demo_dir: Path,
    source: Path,
    lang: str = "",
    *,
    overwrite: bool = True,
    label: str = "",
) -> Dict[str, Any]:
    demo_dir = resolve_demo_dir(demo_dir)
    source = Path(source).expanduser().resolve()
    tmp: Optional[tempfile.TemporaryDirectory] = None
    try:
        if source.is_file() and zipfile.is_zipfile(source):
            tmp = tempfile.TemporaryDirectory(prefix="btf-voice-")
            root = Path(tmp.name)
            with zipfile.ZipFile(source) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = safe_zip_name(info.filename)
                    dest = root / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, dest.open("wb") as out:
                        shutil.copyfileobj(src, out)
        elif source.is_dir():
            root = source
        else:
            raise FileNotFoundError(f"voice pack not found: {source}")
        files = _iter_source_files(root)
        lang_n, items = detect_pack_files(files, lang)
        copied = {"text": 0, "voice": 0}
        manifest_data: Dict[str, Any] = {}
        for kind, filename, path in items:
            if kind == "manifest":
                try:
                    manifest_data = read_manifest(path)
                except (OSError, json.JSONDecodeError):
                    manifest_data = {}
                continue
            dest = demo_dir / kind / lang_n / filename
            if _copy_file(path, dest, overwrite):
                copied[kind] += 1
        write_manifest(
            demo_dir / "voice" / lang_n / MANIFEST_NAME,
            lang_n,
            label=label or str(manifest_data.get("label") or ""),
            extra={"demo": demo_dir.name},
        )
        return {"lang": lang_n, "copied": copied, "label": voice_label(lang_n, label)}
    finally:
        if tmp is not None:
            tmp.cleanup()


def export_pack(
    demo_dir: Path,
    lang: str,
    dest: Path,
    *,
    include_empty: bool = False,
) -> Path:
    demo_dir = resolve_demo_dir(demo_dir)
    lang_n = normalize_voice_lang(lang)
    if not lang_n:
        raise ValueError("export requires --lang")
    dest = Path(dest).expanduser()
    if dest.is_dir() or str(dest).endswith(("/", os.sep)):
        dest = dest / f"{demo_dir.name}-{lang_n}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    recs = {r["id"]: r for r in iter_lang_records(demo_dir)}
    rec = recs.get(lang_n)
    if rec is None and not include_empty:
        raise FileNotFoundError(f"no text/ or voice/ files for language {lang_n}")
    data = load_lang_manifest(demo_dir, lang_n)
    label = voice_label(lang_n, str(data.get("label") or (rec or {}).get("label") or ""))
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "schema": SCHEMA,
            "version": SCHEMA_VERSION,
            "id": lang_n,
            "label": label,
            "demo": demo_dir.name,
        }
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        for kind, folder in (("text", demo_dir / "text" / lang_n), ("voice", demo_dir / "voice" / lang_n)):
            if not folder.is_dir():
                continue
            for path in sorted(folder.iterdir()):
                if not path.is_file():
                    continue
                if path.name == MANIFEST_NAME:
                    continue
                if kind == "text" and path.suffix.lower() not in TEXT_EXTS:
                    continue
                if kind == "voice" and path.suffix.lower() not in AUDIO_EXTS:
                    continue
                zf.write(path, f"{kind}/{path.name}")
    return dest


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def render_lang(
    demo_dir: Path,
    lang: str,
    *,
    voice: str = "",
    rate: int = 170,
    tts_cmd: str = "",
    overwrite: bool = False,
) -> Dict[str, Any]:
    demo_dir = resolve_demo_dir(demo_dir)
    lang_n = normalize_voice_lang(lang) or "en"
    text_dir = demo_dir / "text" / lang_n
    if not text_dir.is_dir():
        raise FileNotFoundError(f"missing scripts: {text_dir}")
    scripts = sorted(
        p for p in text_dir.iterdir() if p.is_file() and p.suffix.lower() in TEXT_EXTS
    )
    if not scripts:
        raise FileNotFoundError(f"no .txt scripts in {text_dir}")
    voice_dir = demo_dir / "voice" / lang_n
    voice_dir.mkdir(parents=True, exist_ok=True)
    voice_name = voice or DEFAULT_SAY_VOICES.get(lang_n, "")
    made = 0
    skipped = 0
    for src in scripts:
        dest_mp3 = voice_dir / (src.stem + ".mp3")
        dest_aiff = voice_dir / (src.stem + ".aiff")
        dest_wav = voice_dir / (src.stem + ".wav")
        existing = next((p for p in (dest_mp3, dest_aiff, dest_wav) if p.is_file()), None)
        if existing is not None and not overwrite:
            skipped += 1
            continue
        text = src.read_text(encoding="utf-8").strip()
        if not text:
            skipped += 1
            continue
        _render_one(
            text,
            dest_mp3,
            voice_name=voice_name,
            rate=rate,
            tts_cmd=tts_cmd,
            lang=lang_n,
        )
        made += 1
    write_manifest(voice_dir / MANIFEST_NAME, lang_n, extra={"demo": demo_dir.name})
    return {"lang": lang_n, "rendered": made, "skipped": skipped, "voice": voice_name}


def _render_one(
    text: str,
    dest_mp3: Path,
    *,
    lang: str,
    voice_name: str,
    rate: int,
    tts_cmd: str,
) -> None:
    dest_mp3.parent.mkdir(parents=True, exist_ok=True)
    if tts_cmd:
        subprocess.run(tts_cmd.split() + [text, str(dest_mp3)], check=True)
        return
    if sys.platform == "darwin" and _which("say"):
        aiff = dest_mp3.with_suffix(".aiff")
        cmd = ["say", "-r", str(rate), "-o", str(aiff)]
        if voice_name:
            cmd[1:1] = ["-v", voice_name]
        subprocess.run(cmd + [text], check=True)
        if _which("ffmpeg"):
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(aiff),
                    "-codec:a", "libmp3lame", "-q:a", "4", str(dest_mp3),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            aiff.unlink(missing_ok=True)
        return
    espeak = _which("espeak-ng") or _which("espeak")
    if espeak:
        wav = dest_mp3.with_suffix(".wav")
        cmd = [espeak, "-s", str(rate), "-w", str(wav), text]
        if lang.startswith("zh"):
            cmd[1:1] = ["-v", "zh"]
        subprocess.run(cmd, check=True)
        if _which("ffmpeg"):
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(wav),
                    "-codec:a", "libmp3lame", "-q:a", "4", str(dest_mp3),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            wav.unlink(missing_ok=True)
        return
    raise SystemExit("no TTS backend (macOS say, espeak, or --tts-cmd)")


def sync_xml_languages(
    demo_dir: Path,
    default_lang: str = "en",
) -> Path:
    demo_dir = resolve_demo_dir(demo_dir)
    xml_path = find_demo_xml(demo_dir)
    if xml_path is None:
        raise FileNotFoundError(f"no demo XML in {demo_dir}")
    recs = iter_lang_records(demo_dir, default_lang)
    if not recs:
        recs = [{"id": default_lang, "label": voice_label(default_lang)}]
    default_id = normalize_voice_lang(default_lang) or recs[0]["id"]
    ids = [r["id"] for r in recs]
    if default_id not in ids:
        recs.insert(0, {"id": default_id, "label": voice_label(default_id)})
    lines = [f'    <languages default="{default_id}">']
    for rec in recs:
        label = rec.get("label") or voice_label(rec["id"])
        lines.append(f'      <language id="{rec["id"]}" label="{label}"/>')
    lines.append("    </languages>")
    block = "\n".join(lines)
    text = xml_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"[ \t]*<languages\b[^>]*>.*?</languages>\s*",
        re.S,
    )
    if pattern.search(text):
        text = pattern.sub(block + "\n", text, count=1)
    else:
        meta_end = re.search(r"[ \t]*</meta>", text)
        if not meta_end:
            raise ValueError(f"{xml_path.name} has no <meta> to insert <languages>")
        text = text[: meta_end.start()] + block + "\n" + text[meta_end.start():]
    xml_path.write_text(text, encoding="utf-8")
    return xml_path


def format_status(demo_dir: Path) -> str:
    demo_dir = resolve_demo_dir(demo_dir)
    recs = iter_lang_records(demo_dir)
    xml = find_demo_xml(demo_dir)
    header = f"demo={demo_dir.name}  xml={xml.name if xml else '-'}"
    if not recs:
        return header + "\n  (no text/ or voice/ files)"
    rows = [header, f"  {'lang':<8} {'label':<10} {'scripts':>7} {'clips':>7}"]
    for rec in recs:
        rows.append(
            f"  {rec['id']:<8} {rec['label']:<10} {len(rec['scripts']):>7} {len(rec['clips']):>7}"
        )
    return "\n".join(rows)


def _add_demo_arg(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "demo",
        type=Path,
        help="demo folder or XML (e.g. demos/demo_8cores)",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Pack, install, and render demo narration languages",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="list languages and file counts")
    _add_demo_arg(p_status)

    p_norm = sub.add_parser(
        "normalize",
        help="move flat text/ and voice/ into <lang> folders",
    )
    _add_demo_arg(p_norm)
    p_norm.add_argument("--lang", default="en", help="language id for flat files (default en)")
    p_norm.add_argument("--keep-flat", action="store_true", help="copy instead of moving flat files")
    p_norm.add_argument("--overwrite", action="store_true")

    p_inst = sub.add_parser(
        "install",
        help="install a zip or folder into text/<lang>/ and voice/<lang>/",
    )
    _add_demo_arg(p_inst)
    p_inst.add_argument("source", type=Path, help="zip or directory (uniform pack or loose files)")
    p_inst.add_argument("--lang", default="", help="language id if the pack does not declare one")
    p_inst.add_argument("--label", default="", help="display label (default from voice.json)")
    p_inst.add_argument("--no-overwrite", action="store_true")

    p_exp = sub.add_parser("export", help="write a uniform zip: voice.json + text/ + voice/")
    _add_demo_arg(p_exp)
    p_exp.add_argument("--lang", required=True, help="language id to export")
    p_exp.add_argument("-o", "--output", type=Path, required=True, help="zip path")

    p_ren = sub.add_parser("render", help="TTS text/<lang>/*.txt into voice/<lang>/")
    _add_demo_arg(p_ren)
    p_ren.add_argument("--lang", default="en")
    p_ren.add_argument("--voice", default="", help="TTS voice name (macOS say -v)")
    p_ren.add_argument("--rate", type=int, default=170)
    p_ren.add_argument("--tts-cmd", default="", help="command prefix; text and output path appended")
    p_ren.add_argument("--overwrite", action="store_true")

    p_sync = sub.add_parser("sync-xml", help="rewrite <languages> from discovered folders")
    _add_demo_arg(p_sync)
    p_sync.add_argument("--default", default="en", dest="default_lang")

    args = ap.parse_args(argv)
    demo = args.demo
    if args.cmd == "status":
        print(format_status(demo))
        return 0
    if args.cmd == "normalize":
        stats = normalize_demo(
            demo,
            args.lang,
            remove_flat=not args.keep_flat,
            overwrite=args.overwrite,
        )
        print(
            f"normalize lang={stats['lang']} moved={stats['moved']} skipped={stats['skipped']}"
        )
        return 0
    if args.cmd == "install":
        info = install_pack(
            demo,
            args.source,
            args.lang,
            overwrite=not args.no_overwrite,
            label=args.label,
        )
        print(
            f"install lang={info['lang']} "
            f"text={info['copied']['text']} voice={info['copied']['voice']}"
        )
        return 0
    if args.cmd == "export":
        out = export_pack(demo, args.lang, args.output)
        print(f"export {out}")
        return 0
    if args.cmd == "render":
        info = render_lang(
            demo,
            args.lang,
            voice=args.voice,
            rate=args.rate,
            tts_cmd=args.tts_cmd,
            overwrite=args.overwrite,
        )
        print(
            f"render lang={info['lang']} rendered={info['rendered']} "
            f"skipped={info['skipped']} voice={info['voice'] or '-'}"
        )
        return 0
    if args.cmd == "sync-xml":
        path = sync_xml_languages(demo, args.default_lang)
        print(f"sync-xml {path}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
