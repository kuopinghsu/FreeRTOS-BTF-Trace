"""Package the viewer release and extract its notes from ChangeLog.md."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


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
    with ZipFile(output / f"btf_viewer_{tag}.zip", mode="w", compression=ZIP_DEFLATED) as archive:
        for source, entry in viewer_files:
            archive.write(source, entry)
        archive.mkdir("docs")
        for source, entry in pdf_files:
            archive.write(source, entry)
    (output / "release-notes.md").write_text(
        f"# BTFViewer {tag}\n\n{notes}\n", encoding="utf-8", newline="\n",
    )


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
