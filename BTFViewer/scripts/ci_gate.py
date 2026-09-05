#!/usr/bin/env python3
"""Lightweight CI gate for BTFViewer docs and generated artifacts.

Checks (no pandoc / no Qt / no npm required unless regenerating builds):

* Markdown relative links and in-document anchors
* EN ↔ zh-TW heading-count / level parity for the shipped manuals
* Stable section-ID mappings (shared ``<a id>`` + translated zh-TW titles)
* PDF freshness vs matching Markdown (git history + dirty tree)
* Statistics Reference HTML freshness vs STATISTICS.md (git history + dirty tree)
* Web HTML freshness vs web sources (git history + dirty tree)

Exit codes: 0 = pass, 1 = failures printed to stderr.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent  # FreeRTOS-BTF-Trace

MANUAL_PAIRS: Sequence[Tuple[str, str]] = (
    ("README.md", "README_zh-TW.md"),
    ("AI.md", "AI_zh-TW.md"),
    ("STATISTICS.md", "STATISTICS_zh-TW.md"),
    ("WORKFLOWS.md", "WORKFLOWS_zh-TW.md"),
)

PDF_PAIRS: Sequence[Tuple[str, str]] = (
    ("README.md", "docs/README.pdf"),
    ("STATISTICS.md", "docs/STATISTICS.pdf"),
    ("AI.md", "docs/AI.pdf"),
    ("WORKFLOWS.md", "docs/WORKFLOWS.pdf"),
    ("README_zh-TW.md", "docs/README_zh-TW.pdf"),
    ("STATISTICS_zh-TW.md", "docs/STATISTICS_zh-TW.pdf"),
    ("AI_zh-TW.md", "docs/AI_zh-TW.pdf"),
    ("WORKFLOWS_zh-TW.md", "docs/WORKFLOWS_zh-TW.pdf"),
)

LINK_SCAN_FILES: Sequence[str] = (
    "README.md",
    "README_zh-TW.md",
    "AI.md",
    "AI_zh-TW.md",
    "STATISTICS.md",
    "STATISTICS_zh-TW.md",
    "WORKFLOWS.md",
    "WORKFLOWS_zh-TW.md",
    "examples/ai/README.md",
)


class SectionMapping(NamedTuple):
    """EN/zh-TW section locked by a shared stable HTML id."""

    section_id: str
    en_file: str
    zh_file: str
    en_title: str  # exact heading text after strip_md_inline
    zh_title_must_contain: str  # CJK (or bilingual) marker required in zh heading


# Explicit cross-language section map. Extends parity beyond heading counts:
# both manuals must expose the same ``<a id>``, and the zh-TW title must be
# translated (contain the CJK marker, not copy the English title verbatim).
SECTION_MAPPINGS: Sequence[SectionMapping] = (
    SectionMapping(
        "analysis-context-strip",
        "STATISTICS.md",
        "STATISTICS_zh-TW.md",
        "Analysis Context strip",
        "分析脈絡列",
    ),
    SectionMapping(
        "symptom-shortcuts",
        "STATISTICS.md",
        "STATISTICS_zh-TW.md",
        "Symptom shortcuts",
        "症狀捷徑",
    ),
    SectionMapping(
        "trace-quality",
        "WORKFLOWS.md",
        "WORKFLOWS_zh-TW.md",
        "Trace quality banner",
        "追蹤品質橫幅",
    ),
    SectionMapping(
        "guided-first-review",
        "WORKFLOWS.md",
        "WORKFLOWS_zh-TW.md",
        "Guided first review",
        "引導式首次檢視",
    ),
)

# Shared ``<a id>`` prefixes that must appear in both EN and zh-TW of a pair
# (order-independent set equality of matching ids).
SHARED_ID_PREFIXES: Sequence[Tuple[str, str, str]] = (
    # (en_file, zh_file, id_prefix)
    ("STATISTICS.md", "STATISTICS_zh-TW.md", "statistics-"),
    ("WORKFLOWS.md", "WORKFLOWS_zh-TW.md", "workflow-step-"),
    ("README.md", "README_zh-TW.md", "ai-api-keys"),
    ("README.md", "README_zh-TW.md", "investigation-case"),
    ("README.md", "README_zh-TW.md", "investigation-planner"),
    ("README.md", "README_zh-TW.md", "btf-analysis-pages"),
    ("README.md", "README_zh-TW.md", "headless-cli-desktop-only"),
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

HTML_ARTIFACT = "builds/btf_viewer.html"
HTML_SOURCE_PATHS: Sequence[str] = (
    "web/src",
    "web/index.html",
    "web/package.json",
    "web/package-lock.json",
    "web/vite.config.js",
    "web/scripts",
    "web/example-2cores.btf.gz",
)

PY_ARTIFACT = "builds/btf_viewer.py"
PY_SOURCE_PATHS: Sequence[str] = (
    "btf_viewer_pkg",
    "scripts/bundle_viewer.py",
)

DOCS_HTML_ARTIFACTS: Sequence[str] = (
    "builds/btf_viewer.hlp",
    "web/src/generated/statistics-en.inline.html",
)
DOCS_HTML_SOURCE_PATHS: Sequence[str] = (
    "STATISTICS.md",
    "scripts/build_docs_html.py",
    "scripts/render_math.mjs",
    "scripts/package.json",
    "scripts/package-lock.json",
)

_MD_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)"
)
_HTML_ID_RE = re.compile(
    r"""<(?:a|span|div|h[1-6])\b[^>]*\b(?:id|name)\s*=\s*["']([^"']+)["']""",
    re.I,
)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _git(*args: str, cwd: Optional[Path] = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd or REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def git_commit_time(*rel_paths: str) -> int:
    """Newest commit timestamp (unix seconds) touching any of the paths."""
    if not rel_paths:
        return 0
    args = ["log", "-1", "--format=%ct", "--"]
    args.extend(f"BTFViewer/{p}" for p in rel_paths)
    out = _git(*args)
    try:
        return int(out)
    except ValueError:
        return 0


def git_dirty(rel_path: str) -> bool:
    """True when the path has unstaged/staged edits or is untracked."""
    out = _git("status", "--porcelain", "--", f"BTFViewer/{rel_path}")
    return bool(out.strip())


def any_dirty(rel_paths: Iterable[str]) -> bool:
    return any(git_dirty(p) for p in rel_paths)


def strip_md_inline(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def github_slug(heading: str) -> str:
    """Approximate GitHub / pandoc-compatible heading slug."""
    text = strip_md_inline(heading).strip().lower()
    out: List[str] = []
    for ch in text:
        if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"):
            out.append(ch)
        elif ch in " _":
            out.append("-")
        elif ch == "-":
            out.append("-")
        # drop other punctuation
    slug = re.sub(r"-{2,}", "-", "".join(out)).strip("-")
    return slug


def iter_markdown_chunks(text: str) -> Iterable[Tuple[bool, str]]:
    """Yield (is_code, chunk) so fenced code is skipped for headings/links."""
    parts = re.split(r"(```.*?```)", text, flags=re.S)
    for i, part in enumerate(parts):
        yield (i % 2 == 1, part)


def collect_anchors(path: Path) -> Set[str]:
    text = path.read_text(encoding="utf-8")
    anchors: Set[str] = set()
    seen_slugs: Dict[str, int] = defaultdict(int)
    for is_code, chunk in iter_markdown_chunks(text):
        if is_code:
            continue
        for match in _HTML_ID_RE.finditer(chunk):
            anchors.add(match.group(1))
        for match in _HEADING_RE.finditer(chunk):
            slug = github_slug(match.group(2))
            if not slug:
                continue
            n = seen_slugs[slug]
            seen_slugs[slug] = n + 1
            anchors.add(slug if n == 0 else f"{slug}-{n}")
    return anchors


def collect_headings(path: Path) -> List[Tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    out: List[Tuple[str, str]] = []
    for is_code, chunk in iter_markdown_chunks(text):
        if is_code:
            continue
        for match in _HEADING_RE.finditer(chunk):
            out.append((match.group(1), strip_md_inline(match.group(2))))
    return out


def resolve_link(source: Path, target: str) -> Tuple[Optional[Path], Optional[str]]:
    """Return (file_path, fragment) for a relative markdown link."""
    if not target or target.startswith(("#", "mailto:", "http://", "https://", "data:")):
        if target.startswith("#"):
            return source, target[1:]
        return None, None
    path_part, frag = target, None
    if "#" in target:
        path_part, frag = target.split("#", 1)
    if not path_part:
        return source, frag
    # Ignore pure query / absolute site paths
    if path_part.startswith(("/", "?")):
        return None, None
    resolved = (source.parent / path_part).resolve()
    return resolved, frag


def check_links() -> List[str]:
    errors: List[str] = []
    anchor_cache: Dict[Path, Set[str]] = {}

    def anchors_for(path: Path) -> Set[str]:
        if path not in anchor_cache:
            anchor_cache[path] = collect_anchors(path) if path.is_file() else set()
        return anchor_cache[path]

    for rel in LINK_SCAN_FILES:
        src = ROOT / rel
        if not src.is_file():
            errors.append(f"missing scan file: {rel}")
            continue
        text = src.read_text(encoding="utf-8")
        for is_code, chunk in iter_markdown_chunks(text):
            if is_code:
                continue
            for match in _MD_LINK_RE.finditer(chunk):
                href = match.group(2).strip()
                dest, frag = resolve_link(src, href)
                if dest is None and frag is None:
                    continue
                if dest is not None and not dest.exists():
                    # Allow links into sibling docs PDF/HTML that may be generated
                    if dest.suffix.lower() in {".pdf", ".html"} and dest.parent == ROOT / "docs":
                        # Still require the PDF to exist when linked from manuals
                        errors.append(f"{rel}: missing file {href}")
                    elif dest.suffix.lower() in {".pdf", ".html"}:
                        errors.append(f"{rel}: missing file {href}")
                    else:
                        try:
                            dest.relative_to(ROOT)
                            errors.append(f"{rel}: missing file {href}")
                        except ValueError:
                            # Outside the BTFViewer tree (e.g. ../images) — still check
                            if not dest.exists():
                                errors.append(f"{rel}: missing file {href}")
                    continue
                if frag and dest is not None and dest.suffix.lower() in {".md", ".markdown", ""}:
                    if dest.is_dir():
                        continue
                    if dest.suffix.lower() not in {".md", ".markdown"} and dest.name not in {
                        "README",
                    }:
                        # Non-markdown fragment targets (pdf/html) — skip anchor proof
                        if dest.suffix.lower() in {".pdf", ".html"}:
                            continue
                    ids = anchors_for(dest)
                    if frag not in ids:
                        errors.append(
                            f"{rel}: broken anchor {href} (#{frag} not in {_rel(dest)})"
                        )
    return errors


def collect_explicit_ids(path: Path) -> Set[str]:
    """HTML id/name attributes only (not heading-derived slugs)."""
    text = path.read_text(encoding="utf-8")
    ids: Set[str] = set()
    for is_code, chunk in iter_markdown_chunks(text):
        if is_code:
            continue
        for match in _HTML_ID_RE.finditer(chunk):
            ids.add(match.group(1))
    return ids


def heading_after_id(path: Path, section_id: str) -> Optional[str]:
    """Return the next markdown heading title after ``<a id=section_id>``."""
    text = path.read_text(encoding="utf-8")
    # Match explicit anchor, then the following heading (allowing blank lines).
    pattern = re.compile(
        rf"""<(?:a|span|div)\b[^>]*\bid\s*=\s*["']{re.escape(section_id)}["'][^>]*>"""
        rf""".*?\n+(#{{1,6}})\s+(.+?)\s*$""",
        re.I | re.S | re.M,
    )
    match = pattern.search(text)
    if not match:
        return None
    return strip_md_inline(match.group(2))


def check_heading_parity() -> List[str]:
    errors: List[str] = []
    for en_rel, zh_rel in MANUAL_PAIRS:
        en = ROOT / en_rel
        zh = ROOT / zh_rel
        if not en.is_file() or not zh.is_file():
            errors.append(f"parity: missing {en_rel} or {zh_rel}")
            continue
        he = collect_headings(en)
        hz = collect_headings(zh)
        if len(he) != len(hz):
            errors.append(
                f"parity: {en_rel} has {len(he)} headings, {zh_rel} has {len(hz)}"
            )
            continue
        for i, ((le, _), (lz, _)) in enumerate(zip(he, hz)):
            if le != lz:
                errors.append(
                    f"parity: heading level mismatch at index {i}: "
                    f"{en_rel} {le} vs {zh_rel} {lz}"
                )
                break
    return errors


def check_section_mappings() -> List[str]:
    """Stable section IDs + translated zh-TW titles (not English copies)."""
    errors: List[str] = []

    for mapping in SECTION_MAPPINGS:
        en = ROOT / mapping.en_file
        zh = ROOT / mapping.zh_file
        if not en.is_file() or not zh.is_file():
            errors.append(
                f"section: missing {mapping.en_file} or {mapping.zh_file} "
                f"for #{mapping.section_id}"
            )
            continue
        en_ids = collect_explicit_ids(en)
        zh_ids = collect_explicit_ids(zh)
        if mapping.section_id not in en_ids:
            errors.append(
                f"section: {mapping.en_file} missing <a id=\"{mapping.section_id}\">"
            )
        if mapping.section_id not in zh_ids:
            errors.append(
                f"section: {mapping.zh_file} missing <a id=\"{mapping.section_id}\">"
            )
        en_title = heading_after_id(en, mapping.section_id)
        zh_title = heading_after_id(zh, mapping.section_id)
        if en_title is None:
            errors.append(
                f"section: {mapping.en_file}#{mapping.section_id} has no following heading"
            )
        elif en_title != mapping.en_title:
            errors.append(
                f"section: {mapping.en_file}#{mapping.section_id} title "
                f"{en_title!r} != {mapping.en_title!r}"
            )
        if zh_title is None:
            errors.append(
                f"section: {mapping.zh_file}#{mapping.section_id} has no following heading"
            )
        else:
            if zh_title == mapping.en_title:
                errors.append(
                    f"section: {mapping.zh_file}#{mapping.section_id} still uses "
                    f"English title {zh_title!r}"
                )
            if mapping.zh_title_must_contain not in zh_title:
                errors.append(
                    f"section: {mapping.zh_file}#{mapping.section_id} title "
                    f"{zh_title!r} missing {mapping.zh_title_must_contain!r}"
                )
            if not _CJK_RE.search(zh_title):
                errors.append(
                    f"section: {mapping.zh_file}#{mapping.section_id} title "
                    f"has no CJK characters: {zh_title!r}"
                )

    # Shared id-prefix sets (Help links / workflow steps) must match EN ↔ zh-TW.
    grouped: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for en_rel, zh_rel, prefix in SHARED_ID_PREFIXES:
        grouped[(en_rel, zh_rel)].append(prefix)

    for (en_rel, zh_rel), prefixes in grouped.items():
        en = ROOT / en_rel
        zh = ROOT / zh_rel
        if not en.is_file() or not zh.is_file():
            continue
        en_ids = collect_explicit_ids(en)
        zh_ids = collect_explicit_ids(zh)
        for prefix in prefixes:
            en_set = {i for i in en_ids if i.startswith(prefix) or i == prefix}
            zh_set = {i for i in zh_ids if i.startswith(prefix) or i == prefix}
            if not en_set and not zh_set:
                # Exact README anchors: require presence in both.
                if prefix in {
                    "ai-api-keys",
                    "investigation-case",
                    "investigation-planner",
                    "btf-analysis-pages",
                    "headless-cli-desktop-only",
                }:
                    errors.append(
                        f"section: shared id {prefix!r} missing from both "
                        f"{en_rel} and {zh_rel}"
                    )
                continue
            only_en = sorted(en_set - zh_set)
            only_zh = sorted(zh_set - en_set)
            if only_en or only_zh:
                errors.append(
                    f"section: id prefix {prefix!r} mismatch "
                    f"{en_rel}↔{zh_rel}: only_en={only_en} only_zh={only_zh}"
                )
    return errors


def check_pdf_freshness() -> List[str]:
    errors: List[str] = []
    for md_rel, pdf_rel in PDF_PAIRS:
        md = ROOT / md_rel
        pdf = ROOT / pdf_rel
        if not md.is_file():
            errors.append(f"pdf: missing markdown {md_rel}")
            continue
        if not pdf.is_file():
            errors.append(f"pdf: missing {pdf_rel} (run: make -C BTFViewer doc)")
            continue
        md_t = git_commit_time(md_rel)
        pdf_t = git_commit_time(pdf_rel)
        if md_t and pdf_t and md_t > pdf_t:
            errors.append(
                f"pdf: {pdf_rel} is older than {md_rel} "
                f"(md commit {md_t} > pdf commit {pdf_t}); run: make -C BTFViewer doc"
            )
        if git_dirty(md_rel) and not git_dirty(pdf_rel):
            errors.append(
                f"pdf: {md_rel} has local edits but {pdf_rel} does not; "
                f"run: make -C BTFViewer doc"
            )
    return errors


def check_html_freshness() -> List[str]:
    errors: List[str] = []
    html = ROOT / HTML_ARTIFACT
    if not html.is_file():
        errors.append(f"html: missing {HTML_ARTIFACT} (run: make -C BTFViewer web)")
        return errors
    src_t = git_commit_time(*HTML_SOURCE_PATHS)
    art_t = git_commit_time(HTML_ARTIFACT)
    if src_t and art_t and src_t > art_t:
        errors.append(
            f"html: {HTML_ARTIFACT} is older than web sources "
            f"(sources {src_t} > html {art_t}); run: make -C BTFViewer web"
        )
    if any_dirty(HTML_SOURCE_PATHS) and not git_dirty(HTML_ARTIFACT):
        errors.append(
            f"html: web sources have local edits but {HTML_ARTIFACT} does not; "
            f"run: make -C BTFViewer web"
        )
    return errors


def check_py_freshness() -> List[str]:
    """History/dirty freshness for the desktop bundle (regenerate via check-bundle)."""
    errors: List[str] = []
    py = ROOT / PY_ARTIFACT
    if not py.is_file():
        errors.append(f"bundle: missing {PY_ARTIFACT} (run: make -C BTFViewer bundle)")
        return errors
    src_t = git_commit_time(*PY_SOURCE_PATHS)
    art_t = git_commit_time(PY_ARTIFACT)
    if src_t and art_t and src_t > art_t:
        errors.append(
            f"bundle: {PY_ARTIFACT} is older than package sources "
            f"(sources {src_t} > py {art_t}); run: make -C BTFViewer bundle"
        )
    if any_dirty(PY_SOURCE_PATHS) and not git_dirty(PY_ARTIFACT):
        errors.append(
            f"bundle: package sources have local edits but {PY_ARTIFACT} does not; "
            f"run: make -C BTFViewer check-bundle"
        )
    return errors


def check_docs_html_freshness() -> List[str]:
    """History/dirty freshness for the pre-rendered Statistics Reference HTML
    (btf_viewer.hlp + statistics-en.inline.html) vs STATISTICS.md and the
    build script. Same git-timestamp/dirty-tree approach as PDF freshness —
    no pandoc/npm/mathjax rebuild needed in CI to catch a forgotten
    ``python3 scripts/build_docs_html.py`` after editing STATISTICS.md."""
    errors: List[str] = []
    src_t = git_commit_time(*DOCS_HTML_SOURCE_PATHS)
    src_dirty = any_dirty(DOCS_HTML_SOURCE_PATHS)
    for artifact_rel in DOCS_HTML_ARTIFACTS:
        artifact = ROOT / artifact_rel
        if not artifact.is_file():
            errors.append(
                f"docs-html: missing {artifact_rel} "
                f"(run: python3 scripts/build_docs_html.py)"
            )
            continue
        art_t = git_commit_time(artifact_rel)
        if src_t and art_t and src_t > art_t:
            errors.append(
                f"docs-html: {artifact_rel} is older than STATISTICS.md/build script "
                f"(sources {src_t} > artifact {art_t}); "
                f"run: python3 scripts/build_docs_html.py"
            )
        if src_dirty and not git_dirty(artifact_rel):
            errors.append(
                f"docs-html: STATISTICS.md or the build script has local edits but "
                f"{artifact_rel} does not; run: python3 scripts/build_docs_html.py"
            )
    return errors


def print_html_build_date() -> int:
    html = ROOT / HTML_ARTIFACT
    if not html.is_file():
        print(os.environ.get("BTF_BUILD_DATE") or "", end="")
        return 0
    text = html.read_text(encoding="utf-8", errors="ignore")
    # Prefer the About-panel build date embedding.
    match = re.search(r"Build Date.{0,80}?(\d{4}-\d{2}-\d{2})", text, re.S)
    if not match:
        match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    print(match.group(1) if match else "", end="")
    return 0


def run_selected(args: argparse.Namespace) -> int:
    if args.print_html_build_date:
        return print_html_build_date()

    selected = []
    if args.all or args.links:
        selected.append(("documentation links", check_links))
    if args.all or args.parity:
        selected.append(("heading parity", check_heading_parity))
        selected.append(("section mappings", check_section_mappings))
    if args.all or args.pdf:
        selected.append(("PDF freshness", check_pdf_freshness))
    if args.all or args.docs_html:
        selected.append(("docs-html freshness", check_docs_html_freshness))
    if args.all or args.html:
        selected.append(("HTML freshness", check_html_freshness))
    if args.all or args.bundle:
        selected.append(("bundle freshness", check_py_freshness))

    if not selected:
        selected = [
            ("documentation links", check_links),
            ("heading parity", check_heading_parity),
            ("section mappings", check_section_mappings),
            ("PDF freshness", check_pdf_freshness),
            ("docs-html freshness", check_docs_html_freshness),
            ("HTML freshness", check_html_freshness),
            ("bundle freshness", check_py_freshness),
        ]

    all_errors: List[str] = []
    for label, fn in selected:
        errs = fn()
        if errs:
            print(f"FAIL: {label} ({len(errs)})", file=sys.stderr)
            for err in errs:
                print(f"  - {err}", file=sys.stderr)
            all_errors.extend(errs)
        else:
            print(f"OK: {label}")
    if all_errors:
        print(f"\n{len(all_errors)} issue(s) in CI gate.", file=sys.stderr)
        return 1
    print("CI gate passed.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Run every check (default)")
    parser.add_argument("--links", action="store_true", help="Markdown link/anchor check")
    parser.add_argument(
        "--parity",
        action="store_true",
        help="EN/zh-TW heading parity + stable section-ID mappings",
    )
    parser.add_argument("--pdf", action="store_true", help="PDF freshness vs Markdown")
    parser.add_argument(
        "--docs-html", dest="docs_html", action="store_true",
        help="Statistics Reference HTML (btf_viewer.hlp / statistics-en.inline.html) freshness",
    )
    parser.add_argument("--html", action="store_true", help="Web HTML freshness")
    parser.add_argument("--bundle", action="store_true", help="Desktop bundle freshness")
    parser.add_argument(
        "--print-html-build-date",
        action="store_true",
        help="Print builds/btf_viewer.html About build date (for reproducible rebuilds)",
    )
    args = parser.parse_args(argv)
    return run_selected(args)


if __name__ == "__main__":
    sys.exit(main())
