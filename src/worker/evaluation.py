"""Operating-point metrics and validation-only selection (M3.T2).

Matching and selection rules are pure Python and testable without a model;
Ultralytics is imported lazily inside the adapter functions only.
Predictions are dicts {"cls": int, "conf": float, "box": [x1, y1, x2, y2]};
ground truth omits "conf". Adapters must convert numpy values to Python types.
"""

import json
import math
import statistics
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


def stage_split(export, release, dest, split):
    """Copy only one released split, re-hashed against the manifest."""
    export, dest = Path(export).resolve(), Path(dest)
    rows = {
        r["path"]: r["sha256"]
        for r in json.loads((export / "manifest.json").read_bytes())
    }
    count = 0
    for record in release["plan"]["records"]:
        if record["split"] != split:
            continue
        for kind, suffix in (("images", "png"), ("labels", "txt")):
            rel = f"{kind}/{split}/{record['asset_id']}.{suffix}"
            data = (export / rel).read_bytes()
            if sha256(data) != rows[rel]:
                raise ValueError("export changed during staging")
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        count += 1
    if not count:
        raise ValueError(f"release has no {split} assets")
    # Ultralytics requires a train key even for evaluation; it is never trained.
    config = (
        f"path: {json.dumps(str(dest.resolve()))}\n"
        f"train: images/{split}\nval: images/{split}\nnames:\n"
        + "".join(f"  {i}: {name}\n" for i, name in enumerate(CLASSES))
    )
    (dest / "data.yaml").write_text(config)
    return {
        "root": str(dest.resolve()),
        "data_yaml_sha256": sha256(config.encode()),
        "split": split,
        "assets": count,
    }


def stage_validation(export, release, dest):
    view = stage_split(export, release, dest, "validation")
    return {
        "root": view["root"],
        "data_yaml_sha256": view["data_yaml_sha256"],
        "validation_assets": view["assets"],
        "test_partition_staged": False,
    }


def load_split(root, split):
    root = Path(root)
    items = {}
    for image in sorted((root / "images" / split).glob("*.png")):
        with Image.open(image) as handle:
            width, height = handle.size
        label = root / "labels" / split / f"{image.stem}.txt"
        gts = []
        for line in label.read_text().splitlines():
            cls, box = _label_box(line.split(), width, height)
            gts.append({"cls": cls, "box": box})
        items[image.stem] = {"image": image, "gts": gts}
    if not items:
        raise ValueError(f"no {split} images staged")
    return items


def load_validation(root):
    return load_split(root, "validation")


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
        predictions[stem], count = _predict_one(model, item["image"], settings, device)
        dropped += count
    return predictions, dropped


def _predict_one(model, image, settings, device):
    boxes = model.predict(str(image), device=device, verbose=False, **settings)[0].boxes
    kept, dropped = [], 0
    for box, conf, cls in zip(
        boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist(), strict=True
    ):
        box = [float(v) for v in box]
        if box[2] <= box[0] or box[3] <= box[1]:
            dropped += 1
            continue
        kept.append({"cls": int(cls), "conf": float(conf), "box": box})
    return kept, dropped


def predict_split(path, images, settings, device):
    """Per-image predictions and degenerate-box counts; any failure is fatal."""
    from ultralytics import YOLO

    model = YOLO(str(path))
    predictions, dropped = {}, {}
    for stem, item in images.items():
        try:
            predictions[stem], dropped[stem] = _predict_one(
                model, item["image"], settings, device
            )
        except Exception as exc:
            raise RuntimeError(f"prediction failed for image {stem}: {exc}") from exc
    return predictions, dropped


def _pairs(images, predictions):
    if set(predictions) != set(images):
        raise ValueError("predictions do not cover the staged images")
    return [(predictions[stem], images[stem]["gts"]) for stem in sorted(images)]


def _rows(out, skip=(SELECTION, SIDECAR)):
    rows = []
    for path in sorted(Path(out).rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink inside evaluation directory")
        rel = path.relative_to(out).as_posix()
        if not path.is_file() or rel in skip:
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


TEST_EVAL = "test-evaluation.json"
TEST_SIDECAR = "test-evaluation.sha256"
TEST_PREDICTIONS = "test-predictions.json"
TEST_PER_IMAGE = "test-per-image.json"
ERROR_CATEGORIES = (
    "false_alarm",
    "localization",
    "class_confusion",
    "duplicate",
    "missed",
)
ERROR_RULE = (
    "Unmatched predictions at the frozen threshold are classified in order: "
    "same-class IoU >= 0.5 -> duplicate; different-class IoU >= 0.5 -> "
    "class_confusion; same-class IoU in [0.1, 0.5) -> localization; otherwise "
    "false_alarm. Unmatched ground truth is missed. Per category, examples are "
    "ordered by descending confidence (missed: none), image ID, then index, and "
    "the first `limit` are kept. No outcome-dependent choice is made."
)
TEST_LIMITATIONS = [
    *LIMITATIONS[:-2],
    "This held-out evaluation must be run once per frozen selection. The code "
    "cannot prevent a second output directory; repeating it to improve results "
    "is a protocol violation and must be disclosed.",
    "Acquisition independence beyond exact identities is not proven.",
    "No healthy-image false-positive rate or production yield is estimable "
    "from this dataset.",
]
PERFORMANCE = "performance.json"
PERFORMANCE_SIDECAR = "performance.sha256"
OBSERVATIONS = "performance-observations.json"
WARMUPS = 10
OBSERVATION_COUNT = 100
TIMING_METHOD = (
    "Batch=1. Warmed sorted test assets in a deterministic cycle. Decode is "
    "cv2.imread; preprocess is Ultralytics predictor.pre_transform/preprocess; "
    "inference is predictor.inference; postprocess is predictor.postprocess "
    "including NMS and result construction. MPS is synchronized before/after "
    "accelerator-dependent stages. Full-pipeline latency is wall time from "
    "decode start through synchronized postprocess completion."
)
PERFORMANCE_LIMITATIONS = [
    "Synthetic-development measurements are software evidence only.",
    "Repeated observations of the same image are not independent images.",
    "Throughput is sequential batch-size-1 throughput, not concurrent capacity.",
    "The 100-observation sample is too small for production or hardware claims.",
    "The MPS runtime can be nondeterministic and is not bit-exact.",
    "No precision conversion or quantization is performed by this command.",
]


def _best_iou(box, gts, same_class, cls):
    best, other = 0.0, None
    for truth in gts:
        if (truth["cls"] == cls) != same_class:
            continue
        value = iou(box, truth["box"])
        if value > best:
            best, other = value, truth["cls"]
    return best, other


def _classify_unmatched(pred, gts):
    same, _ = _best_iou(pred["box"], gts, True, pred["cls"])
    other, other_cls = _best_iou(pred["box"], gts, False, pred["cls"])
    if same >= MATCH_IOU:
        return "duplicate", same, None
    if other >= MATCH_IOU:
        return "class_confusion", other, other_cls
    if same >= 0.1:
        return "localization", same, None
    return "false_alarm", max(same, other), None


def error_examples(images, predictions, threshold, limit=3):
    found = {category: [] for category in ERROR_CATEGORIES}
    for stem in sorted(images):
        gts, preds = images[stem]["gts"], predictions[stem]
        result = match_image(preds, gts, threshold)
        for index in result["false_positives"]:
            pred = preds[index]
            category, best, other = _classify_unmatched(pred, gts)
            found[category].append(
                {
                    "image": stem,
                    "index": index,
                    "class_id": pred["cls"],
                    "conf": pred["conf"],
                    "box": pred["box"],
                    "best_iou": best,
                    "other_class_id": other,
                }
            )
        for index in result["missed"]:
            truth = gts[index]
            found["missed"].append(
                {
                    "image": stem,
                    "index": index,
                    "class_id": truth["cls"],
                    "conf": None,
                    "box": truth["box"],
                    "best_iou": None,
                    "other_class_id": None,
                }
            )

    def order(item):
        conf = -item["conf"] if item["conf"] is not None else 0.0
        return (conf, item["image"], item["index"])

    return {
        "rule": ERROR_RULE,
        "limit": limit,
        "counts": {c: len(v) for c, v in found.items()},
        "examples": {c: sorted(v, key=order)[:limit] for c, v in found.items()},
    }


def per_image_rows(images, predictions, dropped, threshold):
    rows = []
    for stem in sorted(images):
        gts, preds = images[stem]["gts"], predictions[stem]
        result = match_image(preds, gts, threshold)
        rows.append(
            {
                "image": stem,
                "ground_truth": len(gts),
                "predictions_at_floor": len(preds),
                "predictions_at_threshold": sum(p["conf"] >= threshold for p in preds),
                "tp": sum(result["tp"]),
                "fp": sum(result["fp"]),
                "fn": sum(result["fn"]),
                "dropped_degenerate_boxes": dropped[stem],
            }
        )
    return rows


def _reports(images, predictions, dropped, threshold):
    """Everything derived from saved evidence; used by evaluate and verify."""
    return {
        "operating": evaluate_at(_pairs(images, predictions), threshold),
        "per_image": per_image_rows(images, predictions, dropped, threshold),
        "errors": error_examples(images, predictions, threshold),
    }


def _frozen(selection, selection_sha):
    verify_selection(selection, selection_sha)
    saved = json.loads((Path(selection) / SELECTION).read_bytes())
    return {
        "saved": saved,
        "threshold": saved["operating_evaluation"]["selected"]["threshold"],
        "checkpoint": saved["selected_checkpoint"],
        "ap_settings": saved["ap_evaluation"]["settings"],
        "predict_settings": saved["operating_evaluation"]["settings"],
    }


def _check_identity(saved, report, export_sha):
    if saved["dataset"]["manifest_sha256"] != export_sha:
        raise ValueError("selection belongs to a different dataset release")
    if saved["dataset"]["release_sha256"] != report["release_sha256"]:
        raise ValueError("release identity differs from the selection")
    if saved["dataset"]["partitions"] != report["partitions"]:
        raise ValueError("split membership differs from the selection")
    if saved["classes"] != list(CLASSES) or report["classes"] != list(CLASSES):
        raise ValueError("class vocabulary mismatch")


def evaluate_test(
    export,
    export_sha,
    selection,
    selection_sha,
    output,
    device,
    real_release_approved=False,
):
    """Stage B: one frozen held-out evaluation. Settings come from the selection."""
    require_ml()
    frozen = _frozen(selection, selection_sha)
    saved = frozen["saved"]
    run = saved["training_run"]
    verify_training(run["path"], run["manifest_sha256"], load=True)
    report, release = load_release(export, export_sha)
    _check_identity(saved, report, export_sha)
    synthetic = saved["evidence_class"] == "synthetic-development"
    if not synthetic and not real_release_approved:
        raise ValueError(
            "non-synthetic selection: held-out evaluation needs "
            "--real-release-approved after the M2 and M3.T1 gates are accepted"
        )
    checkpoint = frozen["checkpoint"]
    if file_sha256(checkpoint["path"]) != checkpoint["sha256"]:
        raise ValueError("selected checkpoint checksum mismatch")
    device_info = check_device(device)
    out = safe_output(export, output)
    for protected in (Path(selection).resolve(), Path(run["path"]).resolve()):
        if out.is_relative_to(protected) or protected.is_relative_to(out):
            raise ValueError("evaluation directory must be separate from inputs")
    out.mkdir(parents=True)
    started = datetime.now(UTC)
    clock = time.monotonic()
    threshold = frozen["threshold"]
    try:
        view = stage_split(export, release, out / "dataset", "test")
        images = load_split(view["root"], "test")
        truth = support_counts(images)
        metrics = validate_checkpoint(
            checkpoint["path"],
            Path(view["root"]) / "data.yaml",
            out / "ultralytics-val",
            "test",
            frozen["ap_settings"],
            device,
        )
        for key in ("map50", "map50_95"):
            _finite(metrics[key], key)
        for row in metrics["per_class"]:
            for key in ("ap50", "ap50_95"):
                if row[key] is not None:
                    _finite(row[key], f"class AP {key}")
        if metrics["support"] != truth:
            raise ValueError("Ultralytics support differs from staged labels")
        predictions, dropped = predict_split(
            checkpoint["path"], images, frozen["predict_settings"], device
        )
        if set(predictions) != set(images) or set(dropped) != set(images):
            raise ValueError("prediction coverage is incomplete")
        write_new(
            out / TEST_PREDICTIONS,
            canonical_json(
                {
                    "checkpoint_sha256": checkpoint["sha256"],
                    "settings": frozen["predict_settings"],
                    "dropped_degenerate_boxes": dropped,
                    "images": predictions,
                }
            ),
        )
        reports = _reports(images, predictions, dropped, threshold)
        write_new(out / TEST_PER_IMAGE, canonical_json(reports["per_image"]))
        micro = reports["operating"]["micro"]
        (out / "summary.md").write_text(
            f"# VisionQ M3.T2 frozen test evaluation "
            f"({'synthetic-development' if synthetic else 'real-test'})\n\n"
            f"- Dataset manifest: {export_sha}\n"
            f"- Selection: {selection_sha}\n"
            f"- Checkpoint: {checkpoint['name']} ({checkpoint['sha256']})\n"
            f"- Frozen threshold: {threshold}\n"
            f"- Test images: {len(images)}\n"
            f"- mAP50: {metrics['map50']:.6f}, mAP50-95: {metrics['map50_95']:.6f}\n"
            f"- Operating TP/FP/FN: {micro['tp']}/{micro['fp']}/{micro['fn']}\n\n"
            "Nothing here may change the checkpoint, threshold or settings.\n"
        )
        payload = {
            "tool_version": EVAL_VERSION,
            "stage": "frozen-test-evaluation",
            "evidence_class": "synthetic-development" if synthetic else "real-test",
            "classes": list(CLASSES),
            "selection": {
                "path": str(Path(selection).resolve()),
                "sha256": selection_sha,
                "checkpoint": checkpoint["name"],
                "checkpoint_sha256": checkpoint["sha256"],
                "threshold": threshold,
            },
            "dataset": report,
            "dataset_view": view,
            "training_run": run,
            "ap_evaluation": {
                "source": "Ultralytics val(split='val') on the test view",
                "settings": frozen["ap_settings"],
                "operating_threshold_applied": False,
                "map50": metrics["map50"],
                "map50_95": metrics["map50_95"],
                "support": metrics["support"],
                "per_class": metrics["per_class"],
            },
            "operating_evaluation": {
                "source": "VisionQ one-to-one class-aware matching",
                "settings": frozen["predict_settings"],
                "match_iou": MATCH_IOU,
                "threshold": threshold,
                "predictions_file": TEST_PREDICTIONS,
                "per_image_file": TEST_PER_IMAGE,
                "result": reports["operating"],
            },
            "coverage": {
                "test_images": len(images),
                "evaluated_images": len(predictions),
                "failed_images": 0,
                "dropped_degenerate_boxes": sum(dropped.values()),
            },
            "error_examples": reports["errors"],
            "device": device_info,
            "environment": environment(),
            "code": code_identity(),
            "started_utc": started.isoformat(),
            "finished_utc": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(time.monotonic() - clock, 3),
            "limitations": TEST_LIMITATIONS,
            "artifacts": _rows(out, (TEST_EVAL, TEST_SIDECAR)),
        }
        data = canonical_json(payload)
        digest = sha256(data)
        write_new(out / TEST_EVAL, data)
        write_new(out / TEST_SIDECAR, (digest + "\n").encode())
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
        "evaluation": str(out),
        "evaluation_sha256": digest,
        "map50": metrics["map50"],
        "map50_95": metrics["map50_95"],
        "threshold": threshold,
        "evidence_class": payload["evidence_class"],
    }


def verify_test_evaluation(directory, expected_sha, export, export_sha):
    """Independent check against the sealed selection and the released export."""
    directory = Path(directory).resolve()
    data = (directory / TEST_EVAL).read_bytes()
    if sha256(data) != expected_sha:
        raise ValueError("test evaluation checksum mismatch")
    if (directory / TEST_SIDECAR).read_text().strip() != expected_sha:
        raise ValueError("test evaluation sidecar mismatch")
    saved = json.loads(data)
    if saved.get("tool_version") != EVAL_VERSION or (
        saved.get("stage") != "frozen-test-evaluation"
    ):
        raise ValueError("not a frozen test evaluation artifact")
    have = {r["path"]: r for r in _rows(directory, (TEST_EVAL, TEST_SIDECAR))}
    want = {r["path"]: r for r in saved["artifacts"]}
    if have != want:
        bad = sorted(
            (set(have) ^ set(want))
            | {p for p in have if p in want and have[p] != want[p]}
        )
        raise ValueError(f"artifact mismatch: {bad}")
    for kind in ("images", "labels"):
        for split in ("train", "validation"):
            if (directory / "dataset" / kind / split).exists():
                raise ValueError("non-test partition present in the evaluation view")
    ref = saved["selection"]
    frozen = _frozen(ref["path"], ref["sha256"])
    sel = frozen["saved"]
    if saved["classes"] != list(CLASSES) or sel["classes"] != list(CLASSES):
        raise ValueError("class vocabulary mismatch")
    if (
        ref["threshold"] != frozen["threshold"]
        or ref["checkpoint_sha256"] != frozen["checkpoint"]["sha256"]
        or ref["checkpoint"] != frozen["checkpoint"]["name"]
    ):
        raise ValueError("evaluation differs from the frozen selection")
    ap, op = saved["ap_evaluation"], saved["operating_evaluation"]
    if (
        ap["settings"] != frozen["ap_settings"]
        or op["settings"] != frozen["predict_settings"]
        or op["threshold"] != frozen["threshold"]
        or op["match_iou"] != MATCH_IOU
    ):
        raise ValueError("evaluator settings differ from the frozen selection")
    if ap["operating_threshold_applied"] or ap["settings"]["conf"] != FLOOR:
        raise ValueError("AP evaluation was truncated by an operating threshold")
    if saved["training_run"] != sel["training_run"]:
        raise ValueError("training run differs from the frozen selection")
    report, release = load_release(export, export_sha)
    _check_identity(sel, report, export_sha)
    if saved["dataset"] != report:
        raise ValueError("dataset identity differs from the released export")
    expected = {
        r["asset_id"] for r in release["plan"]["records"] if r["split"] == "test"
    }
    images = load_split(directory / "dataset", "test")
    if set(images) != expected:
        raise ValueError("staged test membership differs from the release")
    manifest = {
        r["path"]: r["sha256"]
        for r in json.loads((Path(export) / "manifest.json").read_bytes())
    }
    for stem in images:
        for kind, suffix in (("images", "png"), ("labels", "txt")):
            rel = f"{kind}/test/{stem}.{suffix}"
            if file_sha256(directory / "dataset" / rel) != manifest[rel]:
                raise ValueError("staged test file differs from the export")
    cov = saved["coverage"]
    if (
        cov["failed_images"] != 0
        or cov["test_images"] != len(expected)
        or cov["evaluated_images"] != len(expected)
    ):
        raise ValueError("incomplete test coverage")
    for key in ("map50", "map50_95"):
        _finite(ap[key], key)
    if ap["support"] != support_counts(images):
        raise ValueError("support differs from the staged labels")
    stored = json.loads((directory / TEST_PREDICTIONS).read_bytes())
    if stored["checkpoint_sha256"] != frozen["checkpoint"]["sha256"]:
        raise ValueError("predictions belong to a different checkpoint")
    predictions, dropped = stored["images"], stored["dropped_degenerate_boxes"]
    if set(predictions) != set(images) or set(dropped) != set(images):
        raise ValueError("incomplete test coverage")
    if cov["dropped_degenerate_boxes"] != sum(dropped.values()):
        raise ValueError("dropped prediction count differs from the evidence")
    again = _reports(images, predictions, dropped, frozen["threshold"])
    if canonical_json(again["operating"]) != canonical_json(op["result"]):
        raise ValueError("operating metrics are not reproducible from evidence")
    if canonical_json(again["errors"]) != canonical_json(saved["error_examples"]):
        raise ValueError("error examples are not reproducible from evidence")
    if (directory / TEST_PER_IMAGE).read_bytes() != canonical_json(again["per_image"]):
        raise ValueError("per-image results are not reproducible from evidence")
    return {
        "verified_artifacts": len(have),
        "evaluation_sha256": expected_sha,
        "test_images": len(images),
        "map50": ap["map50"],
        "map50_95": ap["map50_95"],
        "threshold": frozen["threshold"],
        "evidence_class": saved["evidence_class"],
    }


def summarize_timing(values):
    if not values:
        raise ValueError("no timing observations")
    values = [float(value) for value in values]
    if not all(math.isfinite(value) and value >= 0 for value in values):
        raise ValueError("timings must be finite and non-negative")
    ordered = sorted(values)
    p95_index = math.ceil(0.95 * len(ordered)) - 1
    return {
        "count": len(ordered),
        "median_ms": statistics.median(ordered),
        "p95_ms": ordered[p95_index],
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
    }


def aggregate_observations(records, expected_count, failures):
    if failures:
        raise ValueError(f"{len(failures)} benchmark sample(s) failed")
    if len(records) != expected_count:
        raise ValueError(
            f"incomplete benchmark: {len(records)} of {expected_count} observations"
        )
    required = (
        "decode_ms",
        "preprocess_ms",
        "inference_ms",
        "postprocess_ms",
        "full_pipeline_ms",
    )
    stages = {}
    for name in required:
        stages[name.removesuffix("_ms")] = summarize_timing(
            [record[name] for record in records]
        )
    total_seconds = sum(record["full_pipeline_ms"] for record in records) / 1000
    if total_seconds <= 0:
        raise ValueError("benchmark elapsed time must be positive")
    return {
        "observation_count": len(records),
        "stages": stages,
        "throughput_images_per_second": len(records) / total_seconds,
    }


def _sync_device(torch, device):
    if device.type == "mps":
        torch.mps.synchronize()
    elif device.type == "cuda":
        torch.cuda.synchronize(device)


def timed_prediction(path, model, predictor, device):
    """One batch=1 observation with explicit synchronized stage boundaries."""
    import cv2
    import torch

    _sync_device(torch, device)
    started = time.perf_counter()
    decoded = cv2.imread(str(path), cv2.IMREAD_COLOR)
    decoded_at = time.perf_counter()
    if decoded is None:
        raise ValueError(f"failed to decode {path.name}")

    _sync_device(torch, device)
    prepared_at = time.perf_counter()
    tensor = predictor.preprocess([decoded])
    _sync_device(torch, device)
    preprocessed_at = time.perf_counter()

    predictions = predictor.inference(tensor)
    _sync_device(torch, device)
    inferred_at = time.perf_counter()

    predictor.postprocess(predictions, tensor, [decoded])
    _sync_device(torch, device)
    finished = time.perf_counter()

    return {
        "image": path.stem,
        "decode_ms": (decoded_at - started) * 1000,
        "preprocess_ms": (preprocessed_at - prepared_at) * 1000,
        "inference_ms": (inferred_at - preprocessed_at) * 1000,
        "postprocess_ms": (finished - inferred_at) * 1000,
        "full_pipeline_ms": (finished - started) * 1000,
    }


def performance_inputs(evaluation, evaluation_sha, export, export_sha):
    verification = verify_test_evaluation(
        evaluation, evaluation_sha, export, export_sha
    )
    saved = json.loads((Path(evaluation) / TEST_EVAL).read_bytes())
    selection_path = Path(saved["selection"]["path"]).resolve()
    frozen = _frozen(selection_path, saved["selection"]["sha256"])
    checkpoint = frozen["checkpoint"]
    if checkpoint["sha256"] != saved["selection"]["checkpoint_sha256"]:
        raise ValueError("performance checkpoint differs from frozen selection")
    settings = frozen["predict_settings"]
    if (
        settings != saved["operating_evaluation"]["settings"]
        or saved["operating_evaluation"]["threshold"] != saved["selection"]["threshold"]
    ):
        raise ValueError("performance settings differ from frozen evaluation")
    images = load_split(Path(evaluation) / "dataset", "test")
    return saved, frozen, images, verification


def measure_performance(
    evaluation,
    evaluation_sha,
    export,
    export_sha,
    output,
    device,
):
    require_ml()
    saved, frozen, images, verification = performance_inputs(
        evaluation, evaluation_sha, export, export_sha
    )
    device_info = check_device(device)
    checkpoint = frozen["checkpoint"]
    out = safe_output(export, output)
    protected = (Path(evaluation).resolve(), Path(export).resolve())
    if any(out.is_relative_to(path) or path.is_relative_to(out) for path in protected):
        raise ValueError("performance directory must be separate from inputs")
    out.mkdir(parents=True)
    started = datetime.now(UTC)
    clock = time.monotonic()
    records, failures = [], []
    try:
        records, failures, plan, precision = benchmark_checkpoint(
            checkpoint["path"], images, frozen["predict_settings"], device
        )
        summary = aggregate_observations(records, OBSERVATION_COUNT, failures)
        write_new(
            out / OBSERVATIONS,
            canonical_json(
                {
                    "method": TIMING_METHOD,
                    "settings": {
                        "device": device,
                        "precision": precision,
                        "batch": 1,
                        **frozen["predict_settings"],
                    },
                    "warmup_count": WARMUPS,
                    "plan": plan,
                    "records": records,
                    "failed_samples": failures,
                }
            ),
        )
        result = {
            "tool_version": EVAL_VERSION,
            "stage": "performance",
            "evidence_class": saved["evidence_class"],
            "evaluation": {
                "path": str(Path(evaluation).resolve()),
                "sha256": evaluation_sha,
            },
            "selection": {
                "path": saved["selection"]["path"],
                "sha256": saved["selection"]["sha256"],
                "checkpoint": checkpoint["name"],
                "checkpoint_sha256": checkpoint["sha256"],
                "threshold": frozen["threshold"],
            },
            "dataset": {
                "manifest_sha256": export_sha,
                "split_sha_evidence": saved["dataset"]["manifest_sha256"],
            },
            "device": device_info,
            "environment": environment(),
            "code": code_identity(),
            "method": TIMING_METHOD,
            "settings": {
                "device": device,
                "precision": precision,
                "batch": 1,
                **frozen["predict_settings"],
                "warmups": WARMUPS,
            },
            "measurements": summary,
            "sampling": {
                "unique_image_count": plan["unique_image_count"],
                "timed_observation_count": summary["observation_count"],
                "repeated_observation_count": plan["repeated_observation_count"],
                "failed_samples": len(failures),
                "evaluation_verification": verification,
            },
            "started_utc": started.isoformat(),
            "finished_utc": datetime.now(UTC).isoformat(),
            "elapsed_seconds": round(time.monotonic() - clock, 3),
            "limitations": PERFORMANCE_LIMITATIONS,
            "artifacts": _rows(out, (PERFORMANCE, PERFORMANCE_SIDECAR)),
        }
        (out / "summary.md").write_text(
            f"# VisionQ M3.T2 performance ({saved['evidence_class']})\n\n"
            f"- Device/precision: {device} / {precision}\n"
            f"- Unique images: {plan['unique_image_count']}\n"
            f"- Timed observations: {summary['observation_count']}\n"
            f"- Repeated observations: {plan['repeated_observation_count']}\n"
            f"- Model inference median: "
            f"{summary['stages']['inference']['median_ms']:.3f} ms\n"
            f"- Model inference p95: "
            f"{summary['stages']['inference']['p95_ms']:.3f} ms\n"
            f"- Full pipeline median: "
            f"{summary['stages']['full_pipeline']['median_ms']:.3f} ms\n"
            f"- Throughput: "
            f"{summary['throughput_images_per_second']:.3f} images/s\n\n"
            "This synthetic result is development evidence only.\n"
        )
        result["artifacts"] = _rows(out, (PERFORMANCE, PERFORMANCE_SIDECAR))
        data = canonical_json(result)
        digest = sha256(data)
        write_new(out / PERFORMANCE, data)
        write_new(out / PERFORMANCE_SIDECAR, (digest + "\n").encode())
    except BaseException as exc:
        if not (out / "failure.json").exists():
            write_new(
                out / "failure.json",
                canonical_json(
                    {
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "completed_observations": len(records),
                        "failed_samples": failures,
                    }
                ),
            )
        raise
    return {
        "performance": str(out),
        "performance_sha256": digest,
        "evidence_class": saved["evidence_class"],
        "device": device,
        "precision": precision,
        "unique_images": plan["unique_image_count"],
        "observations": summary["observation_count"],
        "inference_median_ms": summary["stages"]["inference"]["median_ms"],
        "inference_p95_ms": summary["stages"]["inference"]["p95_ms"],
        "throughput_images_per_second": summary["throughput_images_per_second"],
    }


def verify_performance(
    directory, expected_sha, evaluation, evaluation_sha, export, export_sha
):
    directory = Path(directory).resolve()
    data = (directory / PERFORMANCE).read_bytes()
    if sha256(data) != expected_sha:
        raise ValueError("performance checksum mismatch")
    if (directory / PERFORMANCE_SIDECAR).read_text().strip() != expected_sha:
        raise ValueError("performance sidecar mismatch")
    saved = json.loads(data)
    if saved.get("stage") != "performance" or saved.get("tool_version") != EVAL_VERSION:
        raise ValueError("not an M3.T2 performance artifact")
    have = {r["path"]: r for r in _rows(directory, (PERFORMANCE, PERFORMANCE_SIDECAR))}
    want = {r["path"]: r for r in saved["artifacts"]}
    if have != want:
        raise ValueError("performance artifact mismatch")
    expected_evaluation = verify_test_evaluation(
        evaluation, evaluation_sha, export, export_sha
    )
    if saved["evaluation"]["sha256"] != evaluation_sha:
        raise ValueError("performance references a different evaluation")
    evidence = json.loads((Path(evaluation) / TEST_EVAL).read_bytes())
    frozen = _frozen(
        Path(evidence["selection"]["path"]), evidence["selection"]["sha256"]
    )
    if (
        saved["selection"]["checkpoint_sha256"] != frozen["checkpoint"]["sha256"]
        or saved["selection"]["threshold"] != frozen["threshold"]
        or saved["settings"]["imgsz"] != frozen["predict_settings"]["imgsz"]
        or saved["settings"]["conf"] != frozen["predict_settings"]["conf"]
    ):
        raise ValueError("performance settings differ from the frozen selection")
    observations = json.loads((directory / OBSERVATIONS).read_bytes())
    records = observations["records"]
    failures = observations["failed_samples"]
    plan = observations["plan"]
    if observations["settings"] != saved["settings"]:
        raise ValueError("observation settings differ from the manifest")
    again = aggregate_observations(records, OBSERVATION_COUNT, failures)
    if canonical_json(again) != canonical_json(saved["measurements"]):
        raise ValueError("performance aggregates are not reproducible")
    if (
        plan["sequence"]
        != benchmark_plan(load_split(Path(evaluation) / "dataset", "test"))["sequence"]
    ):
        raise ValueError("benchmark sampling order is not reproducible")
    if plan["unique_image_count"] != saved["sampling"]["unique_image_count"]:
        raise ValueError("unique-image count mismatch")
    if (
        plan["repeated_observation_count"]
        != saved["sampling"]["repeated_observation_count"]
    ):
        raise ValueError("repeated-observation count mismatch")
    if saved["sampling"]["failed_samples"] != 0:
        raise ValueError("failed benchmark samples recorded as complete")
    return {
        "verified_artifacts": len(have),
        "performance_sha256": expected_sha,
        "evaluation_sha256": expected_evaluation["evaluation_sha256"],
        "unique_images": plan["unique_image_count"],
        "observations": again["observation_count"],
        "inference_median_ms": again["stages"]["inference"]["median_ms"],
        "inference_p95_ms": again["stages"]["inference"]["p95_ms"],
        "throughput_images_per_second": again["throughput_images_per_second"],
    }
