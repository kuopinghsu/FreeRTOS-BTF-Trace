"""Package the viewer release and extract its notes from ChangeLog.md."""

import argparse
import json
from pathlib import Path
from shutil import copyfileobj
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
VIEWER_FILES = ("btf_viewer.hlp", "btf_viewer.html", "btf_viewer.py", "demo_8cores.btfw")
PDF_FILES = ("WORKFLOWS.pdf", "STATISTICS.pdf", "README.pdf", "AI.pdf")


def package_release(tag: str, output: Path) -> None:
    version = json.loads((ROOT / "web/package.json").read_text(encoding="utf-8"))["version"]
    if tag != f"v{version}":
        raise ValueError(f"Release tag {tag!r} does not match viewer version v{version}")

    changelog = (ROOT / "ChangeLog.md").read_text(encoding="utf-8")
    heading = f"## {tag}"
    sections = changelog.splitlines()
    try:
        start = sections.index(heading) + 1
    except ValueError as exc:
        raise ValueError(f"Missing {heading!r} in ChangeLog.md") from exc
    end = next((i for i in range(start, len(sections)) if sections[i].startswith("## ")), len(sections))
    notes = "\n".join(sections[start:end]).strip()
    if not notes:
        raise ValueError(f"Empty release notes for {tag} in ChangeLog.md")

    viewer_files = [(ROOT / "builds" / name, name) for name in VIEWER_FILES]
    pdf_files = [(ROOT / "docs" / name, f"docs/{name}") for name in PDF_FILES]
    for source, _ in viewer_files + pdf_files:
        if not source.is_file():
            raise FileNotFoundError(f"Missing release file: {source.relative_to(ROOT)}")

    output.mkdir(parents=True, exist_ok=True)
    with ZipFile(output / f"btf_viewer_{tag}.zip", mode="w") as archive:
        for source, entry in viewer_files:
            write_release_file(archive, source, entry)
        directory = ZipInfo("docs/")
        directory.create_system = 3
        directory.external_attr = (0o40775 << 16) | 0x10
        archive.writestr(directory, b"")
        for source, entry in pdf_files:
            write_release_file(archive, source, entry)
    (output / "release-notes.md").write_text(
        f"# BTFViewer {tag}\n\n{notes}\n", encoding="utf-8", newline="\n",
    )


def write_release_file(archive: ZipFile, source: Path, entry: str) -> None:
    # Fixed ZIP metadata makes the archive independent of checkout timestamps.
    info = ZipInfo(entry)
    info.create_system = 3  # Unix file attributes on every build host.
    info.external_attr = 0o100644 << 16
    info.compress_type = ZIP_DEFLATED
    info.file_size = source.stat().st_size
    with source.open("rb") as contents, archive.open(info, "w") as target:
        copyfileobj(contents, target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Published GitHub release tag")
    parser.add_argument("output", type=Path, help="Directory for the ZIP and release notes")
    args = parser.parse_args()
    try:
        package_release(args.tag, args.output)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"error: {exc}\n")


if __name__ == "__main__":
    main()
