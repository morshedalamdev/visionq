"""Observe a local NEU-DET copy while preserving its source files."""

import hashlib
import html
import json
import os
import stat
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".pgm", ".png", ".ppm", ".tif", ".tiff"}
XML_LIMIT = 2 * 1024 * 1024


def canonical_json(value: object) -> bytes:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return (text + "\n").encode("utf-8")


def _fingerprint(details: os.stat_result) -> tuple:
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


def _file_paths(root: Path) -> list[str]:
    result = []

    def fail(error: OSError) -> None:
        raise error

    for parent, directories, files in os.walk(root, onerror=fail):
        for name in directories + files:
            path = Path(parent) / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError(f"source symlink requires review: {path}")
            if stat.S_ISREG(mode):
                result.append(path.relative_to(root).as_posix())
            elif not stat.S_ISDIR(mode):
                raise ValueError(f"unsupported source entry: {path}")

    return sorted(result)


class _WithoutDTO(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise ValueError("DTD is unsupported in inventory XML")


def _xml_observation(data: bytes) -> dict:
    if len(data) > XML_LIMIT:
        raise ValueError("XML exceeds inventory inspection limit")

    parser = ET.XMLParser(target=_WithoutDTO())
    root = ET.fromstring(data, parser=parser)
    if root.tag != "annotation":
        raise ValueError(f"unexpected XML root: {root.tag}")

    source_fields = []
    for source in root.findall("source"):
        for node in source.iter():
            if node is not source and len(node) == 0:
                source_fields.append({"tag": node.tag, "text": node.text})

    return {
        "filename": root.findtext("filename"),
        "folder": root.findtext("folder"),
        "source_fields": source_fields,
        "size": [
            root.findtext("size/width"),
            root.findtext("size/height"),
            root.findtext("size/depth"),
        ],
        "object_names": [node.findtext("name") for node in root.findall("object")],
        "bndbox_elements": len(root.findall("object/bndbox")),
        "leaf_tags": sorted({node.tag for node in root.iter() if len(node) == 0}),
    }


def inventory(root: Path) -> tuple[list[dict], dict]:
    root = root.resolve(strict=True)
    for directory in ("IMAGES", "ANNOTATIONS"):
        if not (root / directory).is_dir():
            raise ValueError(f"expected source directory: {directory}")

    paths = _file_paths(root)
    manifest = []
    observations = {}
    errors = []
    fingerprints = {}

    for relative in paths:
        path = root / relative
        is_xml = (
            Path(relative).parts[0] == "ANNOTATIONS" and path.suffix.lower() == ".xml"
        )

        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            data = b""
            if is_xml:
                stream.seek(0)
                data = stream.read(XML_LIMIT + 1)
            after = os.fstat(stream.fileno())

        if _fingerprint(before) != _fingerprint(after):
            raise ValueError(f"source changed during read: {relative}")

        fingerprints[relative] = _fingerprint(before)
        manifest.append(
            {
                "path": relative,
                "bytes": before.st_size,
                "sha256": checksum,
            }
        )

        if is_xml:
            try:
                observations[relative] = _xml_observation(data)
            except (ET.ParseError, ValueError) as exc:
                errors.append({"path": relative, "error": str(exc)})

    if _file_paths(root) != paths:
        raise ValueError("source membership changed during inventory")

    for relative, expected in fingerprints.items():
        if _fingerprint((root / relative).lstat()) != expected:
            raise ValueError(f"source changed during inventory: {relative}")

    return manifest, _summarize(manifest, observations, errors)


def _summarize(manifest: list[dict], observations: dict, errors: list[dict]) -> dict:
    groups = defaultdict(lambda: {"images": [], "xml": []})
    other_files = []

    for row in manifest:
        relative = Path(row["path"])
        if relative.parts[0] == "IMAGES" and relative.suffix.lower() in IMAGE_SUFFIXES:
            kind = "images"
        elif relative.parts[0] == "ANNOTATIONS" and relative.suffix.lower() == ".xml":
            kind = "xml"
        else:
            other_files.append(row["path"])
            continue

    pairs = []
    images_only = []
    xml_only = []
    ambiguous = []

    for stem, members in sorted(groups.items()):
        images = members["images"]
        xml_files = members["xml"]
        if not xml_files:
            images_only.extend(images)
        if not images:
            xml_only.extend(xml_files)
        if len(images) > 1 or len(xml_files) > 1:
            ambiguous.append({"stem": images[0], "xml": xml_files[0]})

    filename_mismatches = []
    for pair in pairs:
        observed = observations.get(pair["xml"])
        if observed is not None and observed["filename"] != Path(pair["image"]).name:
            filename_mismatches.append(
                {
                    "xml": pair["xml"],
                    "declared": observed["filename"],
                    "paired_image": pair["image"],
                }
            )

    object_names = []
    xml_files_per_label = Counter()
    mixed_label_xmls = 0

    for observed in observations.values():
        names = observed["object_names"]
        object_names.extend(names)
        distinct = {name for name in names if name not in (None, "")}
        xml_files_per_label.update(distinct)
        if len(distinct) > 1:
            mixed_label_xmls += 1

    named_objects = [name for name in object_names if name not in (None, "")]
    object_name_counts = Counter(named_objects)
    counts = {
        "regular_files": len(manifest),
        "total_bytes": sum(row["bytes"] for row in manifest),
        "image_candidates": sum(len(group["images"]) for group in groups.values()),
        "xml_files": sum(len(group["xml"]) for group in groups.values()),
        "other_files": len(other_files),
        "stem_pairs": len(pairs),
        "images_without_xml": len(images_only),
        "xml_without_images": len(xml_only),
        "ambiguous_stems": len(ambiguous),
        "xml_inspection_errors": len(errors),
        "xml_filename_mismatches": len(filename_mismatches),
        "xml_objects": len(object_names),
        "xml_bndbox_elements": sum(
            observed["bndbox_elements"] for observed in observations.values()
        ),
        "objects_without_names": len(object_names) - len(named_objects),
        "xmls_with_multiple_labels": mixed_label_xmls,
    }

    return {
        "schema_version": 1,
        "manifest_sha256": hashlib.sha256(canonical_json(manifest)).hexdigest(),
        "counts": counts,
        "object_name_counts": dict(object_name_counts),
        "xml_files_per_label": dict(xml_files_per_label),
        "pairs": pairs,
        "images_without_xml": images_only,
        "xml_without_images": xml_only,
        "ambiguous_stems": ambiguous,
        "filename_mismatches": filename_mismatches,
        "xml_errors": errors,
        "xml_metadata": observations,
        "other_files": other_files,
    }


def factsheet(report: dict) -> str:
    lines = [
        "<!-- M2.T1 inventory:start -->",
        "### Measured extracted-copy inventory",
        "",
        f"Manifest SHA-256 `{report['manifest_sha256']}`.",
        "",
        "| Measurement | Observed |",
        "|---|---:|",
    ]

    for name, value in sorted(report["counts"].items()):
        lines.append(f"| {name.replace('_', ' ')} | {value} |")

    lines.extend(
        [
            "",
            "| Raw XML label | Object elements | XML files containing label |",
            "|---|---:|---:|",
        ]
    )
    for name in sorted(report["object_name_counts"]):
        label = (
            html.escape(name)
            .replace("|", "&#124;")
            .replace("\r", "&#13;")
            .replace("\n", "&#10;")
        )
        objects = report["object_name_counts"][name]
        xml_files = report["xml_files_per_label"][name]
        lines.append(f"| {label} | {objects} | {xml_files} |")

    lines.extend(["", "<!-- M2.T1 inventory:end -->", ""])
    return "\n".join(lines)


def publish_inventory(root: Path, destination: Path) -> dict:
    root = root.resolve(strict=True)
    destination = destination.resolve()

    if destination.is_relative_to(root):
        raise ValueError("inventory output must be outside the source root")
    if destination.exists():
        raise FileExistsError(f"output already exists: {destination}")

    manifest, report = inventory(root)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".m2t1", dir=destination.parent
    ) as temporary:
        staged = Path(temporary) / "inventory"
        staged.mkdir()
        (staged / "manifest.json").write_bytes(canonical_json(manifest))
        (staged / "report.json").write_bytes(canonical_json(report))
        (staged / "facts.md").write_text(
            factsheet(report), encoding="utf-8", newline="\n"
        )

        destination.mkdir()
        try:
            staged.replace(destination)
        except OSError:
            destination.rmdir()
            raise

    return report
