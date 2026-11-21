"""Operating-point metrics and validation-only selection (M3.T2).

Matching and selection rules are pure Python and testable without a model;
Ultralytics is imported lazily inside the adapter functions only.
Predictions are dicts {"cls": int, "conf": float, "box": [x1, y1, x2, y2]};
ground truth omits "conf". Adapters must convert numpy values to Python types.
"""

import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from worker.inventory import canonical_json
from worker.training import (
    MANIFEST,
    _label_box,
    check_device,
    code_identity,
    environment,
    file_sha256,
    load_release,
    require_ml,
    safe_output,
    verify_training,
    write_new,
)
from worker.validation import CLASSES, sha256

EVAL_VERSION = "m3t2-v1"
SELECTION = "selection.json"
SIDECAR = "selection.sha256"
PREDICTIONS = "validation-predictions.json"
# One low floor serves both AP and the operating sweep; the selected operating
# threshold is applied only afterwards, offline, and never truncates AP inputs.
FLOOR = 0.001
NMS_IOU = 0.7
MAX_DET = 300
LIMITATIONS = [
    "Synthetic fixtures are software evidence only, not research evidence.",
    "MPS/torch kernels are not guaranteed bit-exact across runs or hosts; "
    "exact numerical reproducibility is not claimed. The threshold selection "
    "is deterministic given the saved predictions and is recomputed by verify.",
    "AP comes from Ultralytics' matcher; operating precision/recall/F1 use "
    "VisionQ one-to-one matching at IoU 0.5. The two are not reconciled.",
    "Operating predictions come from predict() (letterbox) while AP comes from "
    "val() (rect batching); small differences are possible.",
    "Checkpoint and threshold were chosen on the same validation partition, so "
    "validation scores are optimistic; held-out data is untouched.",
    "Acquisition independence beyond exact identities is not proven.",
]

CLASS_COUNT = 6
MATCH_IOU = 0.5
THRESHOLDS = tuple(k / 100 for k in range(1, 100))
CHECKPOINT_ORDER = ("best", "last")
SELECTION_RULE = {
    "checkpoint": "highest validation mAP50-95 rounded to 6 places; tie -> best",
    "threshold": (
        "highest validation macro-F1 over supported classes; tie -> fewer "
        "total FP+FN; tie -> higher threshold"
    ),
    "matching": (
        "per image and class; predictions by descending confidence, input order "
        "on ties; each takes the unmatched ground truth with highest IoU >= "
        "match_iou, lowest index on ties; one-to-one"
    ),
    "undefined": (
        "precision is null when no predictions; classes without validation "
        "support have null F1 and are excluded from the macro average"
    ),
    "match_iou": MATCH_IOU,
    "thresholds": "k/100 for k in 1..99",
}


def _check(item, scored, classes):
    cls = item["cls"]
    if type(cls) is not int or cls not in range(classes):
        raise ValueError("class ID outside the vocabulary")
    box = item["box"]
    if len(box) != 4 or not all(math.isfinite(v) for v in box):
        raise ValueError("box needs four finite coordinates")
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError("box must have positive width and height")
    if scored:
        conf = item["conf"]
        if not math.isfinite(conf) or not 0 <= conf <= 1:
            raise ValueError("confidence must lie in [0, 1]")


def iou(a, b):
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = width * height
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match_image(preds, gts, threshold, classes=CLASS_COUNT, match_iou=MATCH_IOU):
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must lie in [0, 1]")
    for pred in preds:
        _check(pred, True, classes)
    for truth in gts:
        _check(truth, False, classes)
    kept = sorted(
        ((i, p) for i, p in enumerate(preds) if p["conf"] >= threshold),
        key=lambda item: (-item[1]["conf"], item[0]),
    )
    taken, matches, false_positives = set(), [], []
    tp, fp, fn = [0] * classes, [0] * classes, [0] * classes
    for index, pred in kept:
        best, best_iou = None, 0.0
        for j, truth in enumerate(gts):
            if j in taken or truth["cls"] != pred["cls"]:
                continue
            value = iou(pred["box"], truth["box"])
            # Strict > keeps the lowest ground-truth index on equal IoU.
            if value >= match_iou and value > best_iou:
                best, best_iou = j, value
        if best is None:
            fp[pred["cls"]] += 1
            false_positives.append(index)
        else:
            taken.add(best)
            tp[pred["cls"]] += 1
            matches.append((index, best, best_iou))
    missed = [j for j in range(len(gts)) if j not in taken]
    for j in missed:
        fn[gts[j]["cls"]] += 1
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "matches": matches,
        "false_positives": false_positives,
        "missed": missed,
    }


def prf(tp, fp, fn):
    return {
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
    }


def evaluate_at(images, threshold, classes=CLASS_COUNT, match_iou=MATCH_IOU):
    """images is a sequence of (predictions, ground_truth) pairs."""
    tp, fp, fn = [0] * classes, [0] * classes, [0] * classes
    for preds, gts in images:
        result = match_image(preds, gts, threshold, classes, match_iou)
        for c in range(classes):
            tp[c] += result["tp"][c]
            fp[c] += result["fp"][c]
            fn[c] += result["fn"][c]
    per_class = []
    for c in range(classes):
        support = tp[c] + fn[c]
        metrics = prf(tp[c], fp[c], fn[c])
        if support == 0:
            metrics["f1"] = None

        per_class.append(
            {
                "class_id": c,
                "support": support,
                "tp": tp[c],
                "fp": fp[c],
                "fn": fn[c],
                **metrics,
            }
        )
    supported = [row["f1"] for row in per_class if row["support"] > 0]
    return {
        "threshold": threshold,
        "per_class": per_class,
        "macro_f1": sum(supported) / len(supported) if supported else None,
        "micro": {
            "tp": sum(tp),
            "fp": sum(fp),
            "fn": sum(fn),
            **prf(sum(tp), sum(fp), sum(fn)),
        },
        "unsupported_classes": [r["class_id"] for r in per_class if not r["support"]],
    }


def select_checkpoint(candidates):
    """candidates maps 'best'/'last' to {'map50_95': float} from validation only."""
    scored = []
    for rank, name in enumerate(CHECKPOINT_ORDER):
        if name not in candidates:
            continue
        value = candidates[name]["map50_95"]
        if not math.isfinite(value):
            raise ValueError("validation mAP50-95 must be finite")
        scored.append((round(value, 6), -rank, name))
    if not scored:
        raise ValueError("no candidate checkpoints")
    return max(scored)[2]


def select_threshold(images, thresholds=THRESHOLDS, classes=CLASS_COUNT):
    if not thresholds or list(thresholds) != sorted(set(thresholds)):
        raise ValueError("thresholds must be non-empty and strictly increasing")
    if thresholds[0] <= 0 or thresholds[-1] > 1:
        raise ValueError("thresholds must lie in (0, 1]")
    results = [evaluate_at(images, t, classes) for t in thresholds]
    if results[0]["macro_f1"] is None:
        raise ValueError("validation has no supported classes")
    best = max(
        results,
        key=lambda r: (
            round(r["macro_f1"], 12),
            -(r["micro"]["fp"] + r["micro"]["fn"]),
            r["threshold"],
        ),
    )
    return {
        "rule": SELECTION_RULE,
        "selected": best,
        "search": [
            {
                "threshold": r["threshold"],
                "macro_f1": r["macro_f1"],
                "fp": r["micro"]["fp"],
                "fn": r["micro"]["fn"],
            }
            for r in results
        ],
    }


def _finite(value, what):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"invalid {what}: not finite")
    return value


def stage_validation(export, release, dest):
    """Copy only released validation files, re-hashed against the manifest."""
    export, dest = Path(export).resolve(), Path(dest)
    rows = {
        r["path"]: r["sha256"]
        for r in json.loads((export / "manifest.json").read_bytes())
    }
    count = 0
    for record in release["plan"]["records"]:
        if record["split"] != "validation":
            continue
        for kind, suffix in (("images", "png"), ("labels", "txt")):
            rel = f"{kind}/validation/{record['asset_id']}.{suffix}"
            data = (export / rel).read_bytes()
            if sha256(data) != rows[rel]:
                raise ValueError("export changed during staging")
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        count += 1
    if not count:
        raise ValueError("release has no validation assets")
    # Ultralytics requires a train key even for validation; it is never trained.
    config = (
        f"path: {json.dumps(str(dest.resolve()))}\n"
        "train: images/validation\nval: images/validation\nnames:\n"
        + "".join(f"  {i}: {name}\n" for i, name in enumerate(CLASSES))
    )
    (dest / "data.yaml").write_text(config)
    return {
        "root": str(dest.resolve()),
        "data_yaml_sha256": sha256(config.encode()),
        "validation_assets": count,
        "test_partition_staged": False,
    }


def load_validation(root):
    root = Path(root)
    items = {}
    for image in sorted((root / "images" / "validation").glob("*.png")):
        with Image.open(image) as handle:
            width, height = handle.size
        label = root / "labels" / "validation" / f"{image.stem}.txt"
        gts = []
        for line in label.read_text().splitlines():
            cls, box = _label_box(line.split(), width, height)
            gts.append({"cls": cls, "box": box})
        items[image.stem] = {"image": image, "gts": gts}
    if not items:
        raise ValueError("no validation images staged")
    return items


def support_counts(images):
    counts = [0] * CLASS_COUNT
    for item in images.values():
        for truth in item["gts"]:
            counts[truth["cls"]] += 1
    return counts


def validate_checkpoint(path, data_yaml, project, name, settings, device):
    """AP metrics from Ultralytics val() on the validation split only."""
    from ultralytics import YOLO

    result = YOLO(str(path)).val(
        data=str(data_yaml),
        split="val",
        device=device,
        plots=False,
        save_json=False,
        verbose=False,
        project=str(project),
        name=name,
        exist_ok=False,
        workers=0,
        **settings,
    )
    box = result.box
    index = [int(c) for c in box.ap_class_index]
    ap50 = {c: float(v) for c, v in zip(index, box.ap50, strict=True)}
    # Ultralytics fills maps[] for absent classes with the overall mAP, so
    # per-class AP is reported only where the class has ground truth.
    ap50_95 = {c: float(box.maps[c]) for c in index}
    return {
        "map50": float(box.map50),
        "map50_95": float(box.map),
        "support": [int(n) for n in result.nt_per_class],
        "per_class": [
            {"class_id": c, "ap50": ap50.get(c), "ap50_95": ap50_95.get(c)}
            for c in range(CLASS_COUNT)
        ],
    }


def collect_predictions(path, images, settings, device):
    """Raw predictions at the score floor, converted to the VisionQ schema."""
    from ultralytics import YOLO

    model = YOLO(str(path))
    predictions, dropped = {}, 0
    for stem, item in images.items():
        boxes = model.predict(
            str(item["image"]), device=device, verbose=False, **settings
        )[0].boxes
        kept = []
        for box, conf, cls in zip(
            boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist(), strict=True
        ):
            box = [float(v) for v in box]
            if box[2] <= box[0] or box[3] <= box[1]:
                dropped += 1
                continue
            kept.append({"cls": int(cls), "conf": float(conf), "box": box})
        predictions[stem] = kept
    return predictions, dropped


def _pairs(images, predictions):
    if set(predictions) != set(images):
        raise ValueError("predictions do not cover the staged validation images")
    return [(predictions[stem], images[stem]["gts"]) for stem in sorted(images)]


def _rows(out):
    rows = []
    for path in sorted(Path(out).rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink inside evaluation directory")
        rel = path.relative_to(out).as_posix()
        if not path.is_file() or rel in (SELECTION, SIDECAR):
            continue
        rows.append(
            {"path": rel, "bytes": path.stat().st_size, "sha256": file_sha256(path)}
        )
    return rows


def verified_inputs(run, run_sha, export, export_sha):
    run = Path(run).resolve()
    verify_training(run, run_sha, load=True)
    manifest = json.loads((run / MANIFEST).read_bytes())
    if (
        manifest.get("status") != "complete"
        or manifest["dataset"]["manifest_sha256"] != export_sha
    ):
        raise ValueError("training run does not belong to this dataset release")
    report, release = load_release(export, export_sha)
    if report["release_sha256"] != manifest["dataset"]["release_sha256"]:
        raise ValueError("release identity differs from the training run")
    expected = report["partitions"]["validation"]["assets"]
    if manifest["dataset_view"]["staged_assets"]["validation"] != expected:
        raise ValueError("training view validation membership differs")
    rows = {r["path"]: r for r in manifest["artifacts"]}
    candidates = {}
    for name in CHECKPOINT_ORDER:
        rel = manifest["checkpoints"].get(name)
        if rel is None or rel not in rows:
            raise ValueError(f"missing checkpoint {name}")
        candidates[name] = {
            "path": str(run / rel),
            "relative": rel,
            "bytes": rows[rel]["bytes"],
            "sha256": rows[rel]["sha256"],
        }
    return manifest, report, release, candidates


def select_validation(
    export,
    export_sha,
    run,
    run_sha,
    output,
    device,
    real_release_approved=False,
):
    """Stage A: choose checkpoint and threshold from validation data only."""
    require_ml()
    manifest, report, release, candidates = verified_inputs(
        run, run_sha, export, export_sha
    )
    synthetic = all(
        r.get("categories") == ["synthetic"] for r in release["plan"]["records"]
    )
    if not synthetic and not real_release_approved:
        raise ValueError(
            "non-synthetic release: selection needs --real-release-approved "
            "after the M2 release gates are accepted"
        )
    device_info = check_device(device)
    run_dir = Path(run).resolve()
    out = safe_output(export, output)
    if out.is_relative_to(run_dir) or run_dir.is_relative_to(out):
        raise ValueError("evaluation directory must be separate from the run")
    out.mkdir(parents=True)
    started = datetime.now(UTC)
    clock = time.monotonic()
    try:
        view = stage_validation(export, release, out / "dataset")
        images = load_validation(view["root"])
        truth = support_counts(images)
        imgsz = manifest["requested"]["imgsz"]
        predict_settings = {
            "imgsz": imgsz,
            "conf": FLOOR,
            "iou": NMS_IOU,
            "max_det": MAX_DET,
        }
        val_settings = {**predict_settings, "batch": 1}
        metrics = {}
        for name, info in candidates.items():
            result = validate_checkpoint(
                info["path"],
                Path(view["root"]) / "data.yaml",
                out / "ultralytics-val",
                name,
                val_settings,
                device,
            )
            _finite(result["map50"], "mAP50")
            _finite(result["map50_95"], "mAP50-95")
            for row in result["per_class"]:
                for key in ("ap50", "ap50_95"):
                    if row[key] is not None:
                        _finite(row[key], f"class AP {key}")
            if result["support"] != truth:
                raise ValueError("Ultralytics support differs from staged labels")
            metrics[name] = result
        chosen = select_checkpoint(
            {n: {"map50_95": m["map50_95"]} for n, m in metrics.items()}
        )
        predictions, dropped = collect_predictions(
            candidates[chosen]["path"], images, predict_settings, device
        )
        write_new(
            out / PREDICTIONS,
            canonical_json(
                {
                    "checkpoint": chosen,
                    "settings": predict_settings,
                    "dropped_degenerate_boxes": dropped,
                    "images": predictions,
                }
            ),
        )
        threshold = select_threshold(_pairs(images, predictions))
        selected = threshold["selected"]
        summary = (
            f"# VisionQ M3.T2 validation selection "
            f"({'synthetic-development' if synthetic else 'real-validation'})\n\n"
            f"- Dataset manifest: {export_sha}\n"
            f"- Training manifest: {run_sha}\n"
            f"- Selected checkpoint: {chosen} "
            f"(validation mAP50-95 {metrics[chosen]['map50_95']:.6f})\n"
            f"- Operating threshold: {selected['threshold']} "
            f"(validation macro-F1 {selected['macro_f1']:.6f}, IoU 0.5)\n"
            f"- Validation images: {len(images)}\n\n"
            "Validation only. No held-out test data was used or staged.\n"
        )
        (out / "summary.md").write_text(summary)
        payload = {
            "tool_version": EVAL_VERSION,
            "stage": "validation-selection",
            "evidence_class": (
                "synthetic-development" if synthetic else "real-validation"
            ),
            "selection_rule": SELECTION_RULE,
            "classes": list(CLASSES),
            "dataset": report,
            "dataset_view": view,
            "training_run": {
                "path": str(run_dir),
                "manifest_sha256": run_sha,
                "label": manifest["label"],
            },
            "candidates": {
                name: {**info, "validation": metrics[name]}
                for name, info in candidates.items()
            },
            "selected_checkpoint": {"name": chosen, **candidates[chosen]},
            "ap_evaluation": {
                "source": "Ultralytics val(split='val') on validation only",
                "settings": val_settings,
                "operating_threshold_applied": False,
            },
            "operating_evaluation": {
                "source": "VisionQ one-to-one class-aware matching",
                "settings": predict_settings,
                "match_iou": MATCH_IOU,
                "predictions_file": PREDICTIONS,
                **threshold,
            },
            "device": device_info,
            "environment": environment(),
            "code": code_identity(),
            "started_utc": started.isoformat(),
            "finished_utc": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(time.monotonic() - clock, 3),
            "limitations": LIMITATIONS,
            "artifacts": _rows(out),
        }
        data = canonical_json(payload)
        digest = sha256(data)
        write_new(out / SELECTION, data)
        write_new(out / SIDECAR, (digest + "\n").encode())
    except BaseException as exc:
        if not (out / "failure.json").exists():
            write_new(
                out / "failure.json",
                canonical_json(
                    {
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                ),
            )
        raise
    return {
        "selection": str(out),
        "selection_sha256": digest,
        "checkpoint": chosen,
        "threshold": selected["threshold"],
        "evidence_class": payload["evidence_class"],
    }


def verify_selection(directory, expected_sha):
    """Independent check: bytes, identities, and a full re-derivation."""
    directory = Path(directory).resolve()
    data = (directory / SELECTION).read_bytes()
    if sha256(data) != expected_sha:
        raise ValueError("selection checksum mismatch")
    if (directory / SIDECAR).read_text().strip() != expected_sha:
        raise ValueError("selection sidecar mismatch")
    saved = json.loads(data)
    if saved.get("tool_version") != EVAL_VERSION or (
        saved.get("stage") != "validation-selection"
    ):
        raise ValueError("not a validation selection artifact")
    if saved["classes"] != list(CLASSES):
        raise ValueError("class vocabulary mismatch")
    have = {r["path"]: r for r in _rows(directory)}
    want = {r["path"]: r for r in saved["artifacts"]}
    if have != want:
        bad = sorted(
            (set(have) ^ set(want))
            | {p for p in have if p in want and have[p] != want[p]}
        )
        raise ValueError(f"artifact mismatch: {bad}")
    for kind in ("images", "labels"):
        if (directory / "dataset" / kind / "test").exists():
            raise ValueError("test partition present in the evaluation view")
    run = Path(saved["training_run"]["path"])
    if (
        sha256((run / MANIFEST).read_bytes())
        != saved["training_run"]["manifest_sha256"]
    ):
        raise ValueError("training manifest changed since selection")
    for info in saved["candidates"].values():
        if file_sha256(info["path"]) != info["sha256"]:
            raise ValueError("checkpoint checksum mismatch")
    ap = saved["ap_evaluation"]
    if ap["operating_threshold_applied"] or ap["settings"]["conf"] != FLOOR:
        raise ValueError("AP evaluation was truncated by an operating threshold")
    for name, info in saved["candidates"].items():
        _finite(info["validation"]["map50"], "mAP50")
        _finite(info["validation"]["map50_95"], "mAP50-95")
    chosen = select_checkpoint(
        {
            n: {"map50_95": c["validation"]["map50_95"]}
            for n, c in saved["candidates"].items()
        }
    )
    if (
        chosen != saved["selected_checkpoint"]["name"]
        or saved["selected_checkpoint"]["sha256"]
        != saved["candidates"][chosen]["sha256"]
    ):
        raise ValueError("checkpoint selection is not reproducible")
    images = load_validation(directory / "dataset")
    predictions = json.loads((directory / PREDICTIONS).read_bytes())["images"]
    again = select_threshold(_pairs(images, predictions))
    op = saved["operating_evaluation"]
    if canonical_json(again["selected"]) != canonical_json(op["selected"]) or (
        canonical_json(again["search"]) != canonical_json(op["search"])
    ):
        raise ValueError("threshold selection is not reproducible")
    return {
        "verified_artifacts": len(have),
        "selection_sha256": expected_sha,
        "checkpoint": chosen,
        "threshold": op["selected"]["threshold"],
        "evidence_class": saved["evidence_class"],
    }
