"""Verified, create-only YOLO11n baseline training (M3.T1)."""

import csv
import hashlib
import importlib.util
import json
import logging
import math
import os
import platform
import resource
import subprocess
import time
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from PIL import Image, ImageChops

from worker.inventory import canonical_json
from worker.preparation import SPLITS, verify_export
from worker.validation import CLASSES, sha256

TOOL_VERSION = "m3t1-v1"
TRAIN_SPLITS = ("train", "validation")
DEVICES = ("cpu", "mps")
PACKAGES = ("ultralytics", "torch", "torchvision", "numpy", "opencv-python", "pillow")
MANIFEST = "training-manifest.json"
SIDECAR = "training-manifest.sha256"
EPS = 1e-9
REPO = Path(__file__).resolve().parents[2]
# Library defaults not listed here (augmentation, warmup, momentum) are recorded
# from the trainer after the run; they are not asserted in advance.
BASE_ARGS = {
    "seed": 42,
    "deterministic": True,
    "imgsz": 320,
    "optimizer": "AdamW",
    "lr0": 0.001,
    "cos_lr": True,
    "patience": 20,
    "workers": 0,
    "cache": False,
    "plots": False,
    "amp": False,
    "val": True,
    "save": True,
    "save_period": -1,
    "pretrained": True,
}
PREPROCESSING = (
    "Exports are original-size lossless RGB PNG. Ultralytics letterboxes to "
    "imgsz and applies its train-only augmentation; no other transform is added. "
    "Effective arguments are recorded from the trainer."
)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_new(path, data):
    """Atomic create-only write: hard link fails if the target exists."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink()


def _git(*args):
    try:
        done = subprocess.run(
            ["git", "-C", str(REPO), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout


def code_identity():
    revision = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    lock, project = REPO / "uv.lock", REPO / "pyproject.toml"
    return {
        "git_revision": revision.strip() if revision else None,
        "working_tree_dirty": None if status is None else bool(status.strip()),
        "dirty_paths": status.splitlines() if status else [],
        "uv_lock_sha256": file_sha256(lock) if lock.is_file() else None,
        "pyproject_sha256": file_sha256(project) if project.is_file() else None,
    }


def environment():
    packages = {}
    for name in PACKAGES:
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "memory_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
        "packages": packages,
    }


def require_ml():
    missing = [
        m for m in ("torch", "ultralytics") if importlib.util.find_spec(m) is None
    ]
    if missing:
        raise RuntimeError(
            f"ML dependencies missing: {', '.join(missing)}; "
            "use 'uv run --locked --group train ...'"
        )


def check_device(device):
    if device not in DEVICES:
        raise ValueError(f"device must be one of {DEVICES}")
    require_ml()
    import torch

    info = {
        "requested": device,
        "torch": torch.__version__,
        "mps_built": torch.backends.mps.is_built(),
        "mps_available": torch.backends.mps.is_available(),
    }
    if device == "mps":
        if not info["mps_available"]:
            raise RuntimeError("MPS unavailable; choose --device cpu explicitly")
        if (torch.ones(4, device="mps") * 2).sum().item() != 8.0:
            raise RuntimeError("MPS arithmetic probe failed")
        info["mps_probe"] = "passed"
    return info


def check_weights(path, expected_sha):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("pretrained weights file not found")
    digest = file_sha256(path)
    if digest != expected_sha:
        raise ValueError("pretrained weights checksum mismatch")
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": digest,
    }


def safe_output(export, output):
    export = Path(export).resolve()
    output = Path(output)
    target = output.parent.resolve() / output.name
    if output.is_symlink() or target.exists():
        raise FileExistsError(target)
    if target.is_relative_to(export) or export.is_relative_to(target):
        raise ValueError("run directory must be separate from the export")
    return target


def stage_view(export, release, dest):
    export, dest = Path(export).resolve(), Path(dest)
    rows = {r["path"]: r for r in json.loads((export / "manifest.json").read_bytes())}
    dest.mkdir(parents=True)
    staged = {split: 0 for split in TRAIN_SPLITS}
    for record in release["plan"]["records"]:
        split = record["split"]
        if split not in TRAIN_SPLITS:
            continue
        for kind, suffix in (("images", "png"), ("labels", "txt")):
            rel = f"{kind}/{split}/{record['asset_id']}.{suffix}"
            data = (export / rel).read_bytes()
            if sha256(data) != rows[rel]["sha256"]:
                raise ValueError("export changed during staging")
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        staged[split] += 1
    config = (
        f"path: {json.dumps(str(dest.resolve()))}\n"
        "train: images/train\nval: images/validation\nnames:\n"
        + "".join(f"  {i}: {name}\n" for i, name in enumerate(CLASSES))
    )
    (dest / "data.yaml").write_text(config)
    return {
        "root": str(dest.resolve()),
        "data_yaml_sha256": sha256(config.encode()),
        "staged_assets": staged,
        "test_partition_staged": False,
    }


REQUIRED_COLUMNS = ("epoch", "metrics/mAP50(B)", "metrics/mAP50-95(B)")


def read_curves(path, max_epochs):
    with Path(path).open(newline="") as handle:
        rows = [
            {k.strip(): v.strip() for k, v in row.items() if k}
            for row in csv.DictReader(handle)
        ]
    if not rows:
        raise ValueError("empty learning curve")
    columns = list(rows[0])
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if (
        missing
        or not any(c.startswith("train/") for c in columns)
        or not any(c.startswith("val/") for c in columns)
    ):
        raise ValueError(f"results.csv lacks expected columns {missing}; inspect it")
    parsed = []
    for row in rows:
        values = {k: float(v) for k, v in row.items()}
        if not all(math.isfinite(v) for v in values.values()):
            raise ValueError("non-finite value in learning curve")
        parsed.append(values)
    if len(parsed) > max_epochs:
        raise ValueError("more curve rows than requested epochs")
    best = max(parsed, key=lambda r: r["metrics/mAP50-95(B)"])
    return {
        "columns": columns,
        "epochs_recorded": len(parsed),
        "first": parsed[0],
        "last": parsed[-1],
        "best_validation_map50_95_epoch": best["epoch"],
        "best_validation_map50_95": best["metrics/mAP50-95(B)"],
    }


def artifact_rows(run):
    rows = []
    for path in sorted(run.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink inside run directory")
        rel = path.relative_to(run).as_posix()
        if (
            not path.is_file()
            or rel.startswith("dataset/")
            or rel in (MANIFEST, SIDECAR)
        ):
            continue
        rows.append(
            {"path": rel, "bytes": path.stat().st_size, "sha256": file_sha256(path)}
        )
    return rows


def seal_run(out, save_dir, context):
    out, save_dir = Path(out).resolve(), Path(save_dir).resolve()
    if not save_dir.is_relative_to(out):
        raise ValueError("trainer wrote outside the run directory")
    checkpoints = {}
    for name in ("best", "last"):
        path = save_dir / "weights" / f"{name}.pt"
        if not path.is_file():
            raise ValueError(f"missing checkpoint {name}.pt; run incomplete")
        checkpoints[name] = path.relative_to(out).as_posix()
    curves = read_curves(save_dir / "results.csv", context["requested"]["epochs"])
    summary = (
        f"# VisionQ M3.T1 run ({context['label']})\n\n"
        f"- Dataset manifest: {context['dataset']['manifest_sha256']}\n"
        f"- Weights: {context['weights']['sha256']}\n"
        f"- Device: {context['device']['requested']}\n"
        f"- Epochs recorded: {curves['epochs_recorded']}\n"
        f"- Best validation mAP50-95 {curves['best_validation_map50_95']} at epoch "
        f"{curves['best_validation_map50_95_epoch']} (validation only)\n"
        f"- Elapsed seconds: {context.get('elapsed_seconds')}\n\n"
        "Validation-selected candidate only. No held-out test evaluation was run.\n"
    )
    (out / "summary.md").write_text(summary)
    payload = {
        **context,
        "status": "complete",
        "curves": curves,
        "checkpoints": checkpoints,
        "artifacts": artifact_rows(out),
    }
    data = canonical_json(payload)
    digest = sha256(data)
    write_new(out / MANIFEST, data)
    write_new(out / SIDECAR, (digest + "\n").encode())
    return digest


def verify_training(run, expected_sha, load=False):
    run = Path(run).resolve()
    data = (run / MANIFEST).read_bytes()
    if sha256(data) != expected_sha:
        raise ValueError("training manifest checksum mismatch")
    if (run / SIDECAR).read_text().strip() != expected_sha:
        raise ValueError("training manifest sidecar mismatch")
    manifest = json.loads(data)
    have = {r["path"]: r for r in artifact_rows(run)}
    want = {r["path"]: r for r in manifest["artifacts"]}
    if have != want:
        bad = sorted(
            (set(have) ^ set(want))
            | {p for p in have if p in want and have[p] != want[p]}
        )
        raise ValueError(f"artifact mismatch: {bad}")
    for split in ("images", "labels"):
        if (run / "dataset" / split / "test").exists():
            raise ValueError("test partition present in the training view")
    if load:
        require_ml()
        from ultralytics import YOLO

        for rel in manifest["checkpoints"].values():
            names = YOLO(str(run / rel)).names
            if [names[i] for i in range(len(names))] != list(CLASSES):
                raise ValueError("checkpoint class names differ from the vocabulary")
    return {
        "verified_artifacts": len(have),
        "manifest_sha256": expected_sha,
        "checkpoints": manifest["checkpoints"],
        "loaded": load,
    }


def train_baseline(
    export,
    expected_sha,
    weights,
    weights_sha,
    output,
    device,
    rights_decision,
    label="baseline",
    epochs=60,
    batch=16,
):
    if not rights_decision.strip():
        raise ValueError("a recorded rights decision is required")
    if label not in ("smoke", "baseline", "corrective"):
        raise ValueError("label must be smoke, baseline or corrective")
    require_ml()
    report, release = load_release(export, expected_sha)
    weights_info = check_weights(weights, weights_sha)
    device_info = check_device(device)
    out = safe_output(export, output)
    out.mkdir(parents=True)
    started = datetime.now(UTC)
    clock = time.monotonic()
    view = stage_view(export, release, out / "dataset")
    requested = {"epochs": epochs, "batch": batch, **BASE_ARGS}
    context = {
        "tool_version": TOOL_VERSION,
        "label": label,
        "dataset": report,
        "dataset_view": view,
        "weights": weights_info,
        "device": device_info,
        "environment": environment(),
        "code": code_identity(),
        "rights_decision_owner_supplied": rights_decision,
        "requested": requested,
        "preprocessing": PREPROCESSING,
        "started_utc": started.isoformat(),
    }
    write_new(out / "run-intent.json", canonical_json({**context, "status": "started"}))
    logger = logging.getLogger("ultralytics")
    handler = logging.FileHandler(out / "train.log")
    logger.addHandler(handler)
    try:
        try:
            from ultralytics import YOLO, settings

            settings.update({"sync": False})
            model = YOLO(weights_info["path"])
            model.train(
                data=str(Path(view["root"]) / "data.yaml"),
                project=str(out),
                name="ultralytics",
                exist_ok=False,
                device=device,
                **requested,
            )
        finally:
            logger.removeHandler(handler)
            handler.close()
        context["finished_utc"] = datetime.now(UTC).isoformat()
        context["elapsed_seconds"] = round(time.monotonic() - clock, 3)
        context["peak_rss_bytes_macos"] = resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss
        context["effective_args"] = json.loads(
            json.dumps(vars(model.trainer.args), default=str)
        )
        digest = seal_run(out, model.trainer.save_dir, context)
    except BaseException as exc:
        failure = {
            "status": "failed",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "elapsed_seconds": round(time.monotonic() - clock, 3),
        }
        if not (out / "failure.json").exists():
            write_new(out / "failure.json", canonical_json(failure))
        raise
    return {"run": str(out), "manifest_sha256": digest, "label": label}
