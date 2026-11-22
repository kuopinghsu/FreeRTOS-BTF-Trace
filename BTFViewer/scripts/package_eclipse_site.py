"""Build an offline Eclipse p2 update site from the packaged BTFViewer JAR."""

import argparse
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo


FEATURE = "com.btfviewer.eclipse.feature"
PLUGIN = "com.btfviewer.eclipse"
LICENSE = Path(__file__).resolve().parents[2] / "LICENSE"


def bundle_version(bundle: Path) -> str:
    with ZipFile(bundle) as jar:
        manifest = jar.read("META-INF/MANIFEST.MF").decode("utf-8").splitlines()
    headers = dict(line.split(": ", 1) for line in manifest if ": " in line)
    if headers.get("Bundle-SymbolicName", "").split(";")[0] != PLUGIN:
        raise ValueError(f"Expected the {PLUGIN} bundle in {bundle}")
    version = headers.get("Bundle-Version", "")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:\.[A-Za-z0-9_-]+)?", version):
        raise ValueError(f"Invalid Eclipse bundle version in {bundle}: {version!r}")
    if bundle.name != f"{PLUGIN}_{version}.jar":
        raise ValueError(f"Bundle filename must match its manifest version: {bundle}")
    return version


def write_zip_entry(archive: ZipFile, name: str, contents: bytes) -> None:
    entry = ZipInfo(name)
    entry.create_system = 3
    entry.external_attr = 0o100644 << 16
    archive.writestr(entry, contents, compress_type=ZIP_DEFLATED)


def eclipse_command(home: Path, configuration: Path) -> list[str]:
    launchers = list((home / "plugins").glob("org.eclipse.equinox.launcher_*.jar"))
    if len(launchers) != 1:
        raise ValueError(f"Expected one Equinox launcher in {home / 'plugins'}")
    java_exe = "java.exe" if os.name == "nt" else "java"
    java_home = os.environ.get("JAVA_HOME", "").strip('"')
    java = Path(java_home) / "bin" / java_exe if java_home else shutil.which("java")
    if not java:
        raise ValueError("Set JAVA_HOME to a Java installation supported by Eclipse or add java to PATH")
    original = home / "configuration"
    configuration.mkdir()
    config = (original / "config.ini").read_bytes()
    config = re.sub(rb"(?m)^eclipse\.p2\.(?:data\.area|profile)=.*\r?\n", b"", config)
    (configuration / "config.ini").write_bytes(config)
    shutil.copytree(
        original / "org.eclipse.equinox.simpleconfigurator",
        configuration / "org.eclipse.equinox.simpleconfigurator",
    )
    return [str(java), f"-Declipse.p2.data.area={(configuration / 'p2').as_uri()}",
            "-jar", str(launchers[0]), "-install", str(home),
            "-configuration", configuration.as_uri(), "-nosplash", "-data", "@none", "-consoleLog"]


def publish_site(home: Path, bundle: Path, output: Path) -> Path:
    version = bundle_version(bundle)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".btfviewer-p2-", dir=output) as work:
        root = Path(work)
        source = root / "source"
        plugins = source / "plugins"
        features = source / "features"
        plugins.mkdir(parents=True)
        features.mkdir()
        shutil.copyfile(bundle, plugins / bundle.name)

        feature_name = f"{FEATURE}_{version}.jar"
        feature = ET.Element("feature", id=FEATURE, label="BTFViewer", version=version,
                             attrib={"provider-name": "BTFViewer"})
        ET.SubElement(feature, "description").text = "Open BTF traces in the Eclipse workbench."
        ET.SubElement(feature, "license").text = LICENSE.read_text(encoding="utf-8")
        ET.SubElement(feature, "plugin", id=PLUGIN, version=version, unpack="false")
        with ZipFile(features / feature_name, "w") as jar:
            write_zip_entry(jar, "feature.xml", ET.tostring(feature, encoding="utf-8"))

        category = ET.Element("site")
        category_feature = ET.SubElement(category, "feature", id=FEATURE, version=version,
                                         url=f"features/{feature_name}")
        ET.SubElement(category_feature, "category", name="btfviewer")
        ET.SubElement(category, "category-def", name="btfviewer", label="BTFViewer")
        category_file = root / "category.xml"
        ET.ElementTree(category).write(category_file, encoding="utf-8", xml_declaration=True)

        eclipse = eclipse_command(home, root / "configuration")
        site = root / "repository"
        # Eclipse's publisher arguments escape filesystem paths when parsing file URIs.
        repository = unquote(site.as_uri())
        subprocess.run(eclipse + [
            "-application", "org.eclipse.equinox.p2.publisher.FeaturesAndBundlesPublisher",
            "-metadataRepository", repository, "-artifactRepository", repository,
            "-metadataRepositoryName", "BTFViewer", "-artifactRepositoryName", "BTFViewer",
            "-source", str(source), "-publishArtifacts",
        ], check=True)
        subprocess.run(eclipse + [
            "-application", "org.eclipse.equinox.p2.publisher.CategoryPublisher",
            "-metadataRepository", repository, "-categoryDefinition", unquote(category_file.as_uri()),
            "-categoryQualifier", "btfviewer",
        ], check=True)

        archive_name = f"{PLUGIN}_{version}-p2.zip"
        required = ("artifacts.xml", "content.xml", f"features/{feature_name}", f"plugins/{bundle.name}")
        for path in required:
            if not (site / path).is_file():
                raise ValueError(f"Eclipse p2 publisher did not produce {path}")
        # CategoryPublisher can return success without publishing an installable feature.
        units = ET.parse(site / "content.xml")
        if (units.find(f".//unit[@id='{FEATURE}.feature.group']") is None
                or units.find(".//unit[@id='btfviewer.btfviewer']") is None):
            raise ValueError("The Eclipse p2 repository is missing the BTFViewer feature or category")
        with ZipFile(root / archive_name, "w") as archive:
            for path in sorted(site.rglob("*")):
                if path.is_file():
                    contents = path.read_bytes()
                    if path.name in ("artifacts.xml", "content.xml"):
                        # The publisher writes wall-clock timestamps into otherwise stable metadata.
                        contents = re.sub(rb"(name=['\"]p2\.timestamp['\"] value=['\"])[0-9]+",
                                          rb"\g<1>0", contents.replace(b"\r\n", b"\n"))
                    write_zip_entry(archive, path.relative_to(site).as_posix(), contents)
        (root / archive_name).replace(output / archive_name)
    return output / archive_name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eclipse-home", type=Path, required=True,
                        help="Eclipse SDK directory containing plugins and configuration")
    parser.add_argument("--bundle", type=Path, required=True, help="Built BTFViewer Eclipse JAR")
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    args = parser.parse_args()
    try:
        archive = publish_site(args.eclipse_home.resolve(), args.bundle.resolve(), args.output)
    except (OSError, ValueError, KeyError, BadZipFile, ET.ParseError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"Built {archive}")


if __name__ == "__main__":
    main()
