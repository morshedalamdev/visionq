"""Operating-point metrics and validation-only selection rules (M3.T2).

Pure Python with no ML imports, so every rule is testable without a model.
Predictions are dicts {"cls": int, "conf": float, "box": [x1, y1, x2, y2]};
ground truth omits "conf". Adapters must convert numpy values to Python types.
"""

import math

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
