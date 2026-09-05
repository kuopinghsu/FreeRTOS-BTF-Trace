#!/usr/bin/env python3
"""Pack a demo folder into a shareable ``.xtf`` archive (zip).

An ``.xtf`` is a zip of the demo script, frozen BTF, and selected voice packs
so apps can Open / drag-drop it and play the guided demo.

By default voice ``.mp3`` clips are transcoded to ``.aac`` (24 kHz mono 32 kb/s)
and ``<audio file=…>`` paths in the packed XML are rewritten to ``.aac``.

Example (from ``BTFViewer/``)::

    python3 scripts/demo_pack.py demos/demo_8cores \\
        -o builds/demo_8cores.xtf
    # default voices: en, zh-tw  (override with --voice / --all-voices)

Equivalent layout inside the archive (flat, no folder prefix)::

    demo_8cores.xml          # <languages> filtered; audio → .aac
    demo_8cores.btf.gz
    voice/en/*.aac + voice.json
    voice/zh-tw/*.aac + voice.json
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
BTF_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from demo_voice import (  # noqa: E402
    find_demo_xml,
    iter_lang_records,
    normalize_voice_lang,
    resolve_demo_dir,
    voice_label,
)

DEFAULT_LANGS = ("en", "zh-tw")
BTF_GLOBS = ("*.btf", "*.btf.gz", "*.btf.bz2", "*.btf.zip")
FFMPEG_AAC_ARGS = ("-c:a", "aac", "-ar", "32000", "-ac", "1", "-b:a", "48k")


def list_voice_packs(demo_dir: Path, voice_root: str = "voice") -> List[dict]:
    """Available voice packs under ``<voice_root>/<lang>/`` (with clip counts).

    ``voice_root`` lets a pack be built from an alternate rendered take —
    ``voice-male``/``voice-female`` (see demo_voice.py render --gender) —
    instead of the live ``voice/`` tree, without first running ``use-voice``.
    """
    demo_dir = resolve_demo_dir(demo_dir)
    recs = iter_lang_records(demo_dir, voice_root=voice_root)
    # Prefer packs that actually have clips under voice_root/, not text-only.
    out = []
    for rec in recs:
        voice_dir = demo_dir / voice_root / rec["id"]
        if not voice_dir.is_dir():
            continue
        out.append({
            "id": rec["id"],
            "label": rec.get("label") or voice_label(rec["id"]),
            "clips": len(rec.get("clips") or []),
            "path": str(voice_dir),
        })
    return out


def format_voice_packs(demo_dir: Path, voice_root: str = "voice") -> str:
    packs = list_voice_packs(demo_dir, voice_root=voice_root)
    demo_dir = resolve_demo_dir(demo_dir)
    if not packs:
        return f"demo={demo_dir.name}\n  (no {voice_root}/<lang>/ packs)"
    rows = [
        f"demo={demo_dir.name}  available {voice_root}/ packs:",
        f"  {'id':<10} {'label':<12} {'clips':>5}",
    ]
    for p in packs:
        rows.append(f"  {p['id']:<10} {p['label']:<12} {p['clips']:>5}")
    rows.append("")
    rows.append("Examples:")
    demo_arg = "demos/demo_8cores"
    try:
        demo_arg = str(demo_dir.relative_to(BTF_ROOT))
    except ValueError:
        demo_arg = str(demo_dir)
    rows.append(f"  python3 scripts/demo_pack.py {demo_arg} --voice en")
    rows.append(f"  python3 scripts/demo_pack.py {demo_arg} --voice en --voice zh-tw")
    rows.append(f"  python3 scripts/demo_pack.py {demo_arg} --voice en,zh-tw,ja")
    rows.append(f"  python3 scripts/demo_pack.py {demo_arg} --all-voices")
    rows.append(f"  python3 scripts/demo_pack.py {demo_arg} --gender male   # pack from voice-male/")
    return "\n".join(rows)


def resolve_voice_selection(
    demo_dir: Path,
    *,
    voice_args: Sequence[str],
    all_voices: bool = False,
    voice_root: str = "voice",
) -> List[str]:
    """Resolve CLI voice selection to language ids present on disk."""
    available = [p["id"] for p in list_voice_packs(demo_dir, voice_root=voice_root)]
    if not available:
        raise FileNotFoundError(f"no {voice_root}/<lang>/ packs under {resolve_demo_dir(demo_dir)}")

    if all_voices:
        return list(available)

    selected: List[str] = []
    for raw in voice_args:
        for part in re.split(r"[,;\s]+", str(raw or "").strip()):
            n = normalize_voice_lang(part)
            if n and n not in selected:
                selected.append(n)

    if not selected:
        # Default: English when present, else every available pack.
        for lid in DEFAULT_LANGS:
            if lid in available and lid not in selected:
                selected.append(lid)
        if not selected:
            selected = list(available)

    missing = [lid for lid in selected if lid not in available]
    if missing:
        avail = ", ".join(available)
        raise FileNotFoundError(
            f"unknown voice pack(s): {', '.join(missing)}  "
            f"(available: {avail})"
        )
    return selected


def filter_xml_languages(
    xml_text: str,
    langs: Sequence[str],
    *,
    default_lang: str = "en",
) -> str:
    """Rewrite ``<languages>`` so only *langs* remain (labels preserved when known)."""
    ids = [normalize_voice_lang(x) for x in langs if normalize_voice_lang(x)]
    if not ids:
        ids = list(DEFAULT_LANGS)
    default_id = normalize_voice_lang(default_lang) or ids[0]
    if default_id not in ids:
        default_id = ids[0]

    labels = {n: voice_label(n) for n in ids}
    # Prefer labels already declared in the source XML.
    for m in re.finditer(
        r'<language\b[^>]*\bid=["\']([^"\']+)["\'][^>]*(?:\blabel=["\']([^"\']*)["\'])?',
        xml_text,
        re.I,
    ):
        lid = normalize_voice_lang(m.group(1))
        if lid in labels and (m.group(2) or "").strip():
            labels[lid] = m.group(2).strip()

    lines = [f'    <languages default="{default_id}">']
    for lid in ids:
        lines.append(f'      <language id="{lid}" label="{labels[lid]}"/>')
    lines.append("    </languages>")
    block = "\n".join(lines)

    pattern = re.compile(r"[ \t]*<languages\b[^>]*>.*?</languages>\s*", re.S)
    if pattern.search(xml_text):
        return pattern.sub(block + "\n", xml_text, count=1)
    meta_end = re.search(r"[ \t]*</meta>", xml_text)
    if not meta_end:
        raise ValueError("demo XML has no <meta> to insert <languages>")
    return xml_text[: meta_end.start()] + block + "\n" + xml_text[meta_end.start() :]


def rewrite_xml_audio_ext(xml_text: str, from_ext: str = ".mp3", to_ext: str = ".aac") -> str:
    """Rewrite ``file="…voice/….mp3"`` (and bare ``….mp3``) audio paths to *to_ext*."""
    src = from_ext if from_ext.startswith(".") else f".{from_ext}"
    dst = to_ext if to_ext.startswith(".") else f".{to_ext}"
    src_re = re.escape(src)

    def _swap(m: re.Match) -> str:
        return m.group(1) + dst + m.group(2)

    # file="…foo.mp3" / file='…foo.mp3'
    pattern = re.compile(
        rf'(file\s*=\s*["\'][^"\']*){src_re}(["\'])',
        re.I,
    )
    return pattern.sub(_swap, xml_text)


def _which_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def mp3_to_aac(src: Path, dest: Path, *, ffmpeg: Optional[str] = None) -> None:
    """``ffmpeg -i input.mp3 -c:a aac -ar 32000 -ac 1 -b:a 48k output.aac``."""
    exe = ffmpeg or _which_ffmpeg()
    if not exe:
        raise SystemExit("ffmpeg not found on PATH (needed to convert .mp3 → .aac)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        exe, "-y", "-i", str(src),
        *FFMPEG_AAC_ARGS,
        str(dest),
    ]
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def prepare_voice_dir(
    src_dir: Path,
    dest_dir: Path,
    *,
    to_aac: bool = True,
    ffmpeg: Optional[str] = None,
) -> int:
    """Copy *src_dir* into *dest_dir*, converting ``.mp3`` → ``.aac`` when *to_aac*."""
    n = 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src_dir)
        if to_aac and path.suffix.lower() == ".mp3":
            out = dest_dir / rel.with_suffix(".aac")
            mp3_to_aac(path, out, ffmpeg=ffmpeg)
            n += 1
            continue
        out = dest_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
        n += 1
    return n


def _iter_btf_files(demo_dir: Path) -> List[Path]:
    found: List[Path] = []
    seen = set()
    for pat in BTF_GLOBS:
        for p in sorted(demo_dir.glob(pat)):
            if not p.is_file():
                continue
            key = p.name.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(p)
    return found


def _add_tree(zf: zipfile.ZipFile, src: Path, arc_prefix: str) -> int:
    """Add a file or directory under *arc_prefix*. Returns member count."""
    n = 0
    if src.is_file():
        zf.write(src, arc_prefix.replace("\\", "/"))
        return 1
    if not src.is_dir():
        return 0
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src).as_posix()
        arc = f"{arc_prefix.rstrip('/')}/{rel}"
        zf.write(path, arc)
        n += 1
    return n


def pack_demo_xtf(
    demo: Path,
    output: Path,
    langs: Sequence[str],
    *,
    default_lang: str = "en",
    to_aac: bool = True,
    ffmpeg: Optional[str] = None,
    voice_src_root: str = "voice",
) -> Path:
    """``voice_src_root`` is the folder on disk to pack clips FROM (default
    the live ``voice/`` tree; pass ``voice-male``/``voice-female`` to pack
    straight from a rendered-but-not-yet-live take). The archive always
    stores clips under ``voice/<lang>/`` internally regardless — that is
    the path the packed demo XML references at playback time."""
    demo_dir = resolve_demo_dir(demo)
    xml_src = find_demo_xml(demo_dir)
    if xml_src is None:
        raise FileNotFoundError(f"no demo XML in {demo_dir}")
    lang_ids: List[str] = []
    for x in langs:
        n = normalize_voice_lang(x)
        if n and n not in lang_ids:
            lang_ids.append(n)
    if not lang_ids:
        lang_ids = list(DEFAULT_LANGS)

    missing_voice = [lid for lid in lang_ids if not (demo_dir / voice_src_root / lid).is_dir()]
    if missing_voice:
        raise FileNotFoundError(
            f"missing {voice_src_root} folders: {', '.join(missing_voice)} "
            f"under {demo_dir / voice_src_root}"
        )

    btfs = _iter_btf_files(demo_dir)
    if not btfs:
        raise FileNotFoundError(f"no .btf / .btf.gz in {demo_dir}")

    if to_aac and not (ffmpeg or _which_ffmpeg()):
        raise SystemExit("ffmpeg not found on PATH (needed to convert .mp3 → .aac)")

    xml_text = filter_xml_languages(
        xml_src.read_text(encoding="utf-8"),
        lang_ids,
        default_lang=default_lang,
    )
    if to_aac:
        xml_text = rewrite_xml_audio_ext(xml_text, ".mp3", ".aac")

    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    members = 0
    with tempfile.TemporaryDirectory(prefix="btf_xtf_voice_") as td:
        staging_root = Path(td)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(xml_src.name, xml_text.encode("utf-8"))
            members += 1
            for btf in btfs:
                zf.write(btf, btf.name)
                members += 1
            for lid in lang_ids:
                staged = staging_root / lid
                prepare_voice_dir(
                    demo_dir / voice_src_root / lid,
                    staged,
                    to_aac=to_aac,
                    ffmpeg=ffmpeg,
                )
                members += _add_tree(zf, staged, f"voice/{lid}")

    return output


def is_xtf_path(path: Path | str) -> bool:
    return str(path or "").lower().endswith(".xtf")


def extract_xtf(path: Path, dest: Optional[Path] = None) -> Path:
    """Extract an ``.xtf`` zip into *dest* (or a new temp dir). Returns the folder."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if not zipfile.is_zipfile(path):
        raise ValueError(f"not a zip/.xtf archive: {path}")
    out = Path(dest) if dest else Path(tempfile.mkdtemp(prefix="btf_xtf_"))
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "r") as zf:
        zf.extractall(out)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Pack a demo folder into a shareable .xtf (zip) archive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Voice packs (choose one or more):\n"
            "  --voice en                 English only\n"
            "  --voice en --voice zh-tw   English + 中文\n"
            "  --voice en,zh-tw,ja        comma list\n"
            "  --lang en,zh-tw            alias for --voice\n"
            "  --all-voices               every voice/<lang>/ on disk\n"
            "  --list-voices              list available packs and exit\n"
            "  (default voice packs: en, zh-tw)\n"
            "\n"
            "Source folder (pack from a rendered take, not just voice/):\n"
            "  --gender male              pack from voice-male/ instead of voice/\n"
            "  --voice-folder voice-male  same, by exact folder name\n"
            "  (the archive always stores clips under voice/<lang>/ internally —\n"
            "   this only picks which folder on disk to read them FROM)\n"
        ),
    )
    ap.add_argument(
        "demo",
        type=Path,
        nargs="?",
        default=BTF_ROOT / "demos" / "demo_8cores",
        help="demo folder or XML (default: demos/demo_8cores)",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="output .xtf path (default: builds/<demo>.xtf)",
    )
    ap.add_argument(
        "--voice",
        "-V",
        action="append",
        default=[],
        metavar="LANG",
        help="voice pack id to include (repeatable or comma-separated; "
             "default: en when present)",
    )
    ap.add_argument(
        "--lang",
        action="append",
        default=[],
        metavar="LANG",
        help="alias for --voice",
    )
    ap.add_argument(
        "--all-voices",
        action="store_true",
        help="include every voice/<lang>/ pack found in the demo folder",
    )
    ap.add_argument(
        "--list-voices",
        action="store_true",
        help="list available voice packs and exit",
    )
    ap.add_argument(
        "--voice-folder",
        default="",
        metavar="NAME",
        help="pack from <NAME>/<lang>/ instead of voice/ "
             "(e.g. voice-male, voice-female); overrides --gender",
    )
    ap.add_argument(
        "--gender", default="", choices=("", "male", "female"),
        help="shorthand for --voice-folder voice-<gender>",
    )
    ap.add_argument(
        "--default-lang",
        default="",
        help="XML <languages default> (default: first selected pack)",
    )
    ap.add_argument(
        "--keep-mp3",
        action="store_true",
        help="pack original .mp3 clips (skip ffmpeg AAC convert)",
    )
    ap.add_argument(
        "--ffmpeg",
        default="",
        help="ffmpeg binary (default: ffmpeg on PATH)",
    )
    args = ap.parse_args(argv)

    voice_src_root = args.voice_folder.strip() or (f"voice-{args.gender}" if args.gender else "voice")

    demo_dir = resolve_demo_dir(args.demo)
    if args.list_voices:
        print(format_voice_packs(demo_dir, voice_root=voice_src_root))
        return 0

    voice_args = list(args.voice) + list(args.lang)
    try:
        langs = resolve_voice_selection(
            demo_dir,
            voice_args=voice_args,
            all_voices=args.all_voices,
            voice_root=voice_src_root,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(format_voice_packs(demo_dir, voice_root=voice_src_root), file=sys.stderr)
        return 2

    out = args.output
    if out is None:
        out = BTF_ROOT / "builds" / f"{demo_dir.name}.xtf"
    default_lang = args.default_lang or (langs[0] if langs else "en")
    to_aac = not args.keep_mp3
    path = pack_demo_xtf(
        demo_dir,
        out,
        langs,
        default_lang=default_lang,
        to_aac=to_aac,
        ffmpeg=(args.ffmpeg or None),
        voice_src_root=voice_src_root,
    )
    size = path.stat().st_size
    audio = "aac" if to_aac else "mp3"
    print(
        f"packed {path} ({size:,} bytes) voices={','.join(langs)} "
        f"audio={audio} from={voice_src_root}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
