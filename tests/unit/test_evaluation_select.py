import json
import math

import pytest
from test_training import build, fake_run

from worker import evaluation as ev
from worker import training
from worker.inventory import canonical_json
from worker.validation import CLASSES, sha256

NOISE_BOX = [0.0, 0.0, 5.0, 5.0]


def synthetic(files, release):
    for record in release["plan"]["records"]:
        record["categories"] = ["synthetic"]


def metrics(value):
    return {
        "map50": 0.5,
        "map50_95": value,
        "support": [1] * 6,
        "per_class": [{"class_id": c, "ap50": 0.5, "ap50_95": value} for c in range(6)],
    }


def predictions(path, images, settings, device):
    # Perfect boxes at 0.9 plus one low-confidence false positive per image.
    result = {}
    for stem, item in images.items():
        found = [{"cls": g["cls"], "conf": 0.9, "box": g["box"]} for g in item["gts"]]
        found.append({"cls": 1, "conf": 0.3, "box": NOISE_BOX})
        result[stem] = found
    return result, 0


@pytest.fixture
def setup(tmp_path, monkeypatch):
    export, export_sha = build(tmp_path, synthetic)
    run = fake_run(tmp_path)
    report, _ = training.load_release(export, export_sha)
    context = {
        "label": "smoke",
        "requested": {"epochs": 2, "imgsz": 320},
        "dataset": report,
        "dataset_view": {"staged_assets": {"train": 6, "validation": 6}},
        "weights": {"sha256": "b"},
        "device": {"requested": "cpu"},
    }
    run_sha = training.seal_run(run, run / "ultralytics", context)
    values = {"best": 0.6, "last": 0.5}
    monkeypatch.setattr(ev, "require_ml", lambda: None)
    monkeypatch.setattr(ev, "check_device", lambda device: {"requested": device})
    monkeypatch.setattr(
        ev, "verify_training", lambda r, s, load=False: training.verify_training(r, s)
    )
    monkeypatch.setattr(
        ev, "validate_checkpoint", lambda p, d, pr, name, st, dev: metrics(values[name])
    )
    monkeypatch.setattr(ev, "collect_predictions", predictions)
    return export, export_sha, run, run_sha, tmp_path / "eval", values


def select(setup, **kwargs):
    export, export_sha, run, run_sha, out, _ = setup
    return ev.select_validation(export, export_sha, run, run_sha, out, "cpu", **kwargs)


def reseal(out, edit):
    saved = json.loads((out / ev.SELECTION).read_bytes())
    edit(saved)
    data = canonical_json(saved)
    digest = sha256(data)
    (out / ev.SELECTION).write_bytes(data)
    (out / ev.SIDECAR).write_text(digest + "\n")
    return digest


def test_selection_roundtrip_and_frozen_choices(setup):
    result = select(setup)
    out = setup[4]
    assert result["checkpoint"] == "best"
    # Noise at 0.3 is dropped from 0.31 upward; the highest tied threshold wins.
    assert result["threshold"] == 0.9
    assert result["evidence_class"] == "synthetic-development"
    assert not (out / "dataset" / "images" / "test").exists()
    verified = ev.verify_selection(out, result["selection_sha256"])
    assert verified["threshold"] == 0.9
    saved = json.loads((out / ev.SELECTION).read_bytes())
    assert saved["ap_evaluation"]["operating_threshold_applied"] is False
    assert saved["ap_evaluation"]["settings"]["conf"] == ev.FLOOR
    assert saved["classes"] == list(CLASSES)


def test_last_checkpoint_chosen_when_better_on_validation(setup):
    setup[5]["last"] = 0.7
    assert select(setup)["checkpoint"] == "last"


def test_existing_output_rejected_and_run_untouched(setup):
    before = sha256((setup[2] / training.MANIFEST).read_bytes())
    select(setup)
    with pytest.raises(FileExistsError):
        select(setup)
    assert sha256((setup[2] / training.MANIFEST).read_bytes()) == before


def test_tampering_detected(setup):
    result = select(setup)
    out, digest = setup[4], result["selection_sha256"]
    predictions_file = out / ev.PREDICTIONS
    original = predictions_file.read_bytes()
    predictions_file.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="artifact mismatch"):
        ev.verify_selection(out, digest)
    predictions_file.write_bytes(original)
    with pytest.raises(ValueError, match="selection checksum"):
        ev.verify_selection(out, "0" * 64)
    (out / ev.SELECTION).write_bytes((out / ev.SELECTION).read_bytes() + b" ")
    with pytest.raises(ValueError, match="selection checksum"):
        ev.verify_selection(out, digest)


def test_checkpoint_tamper_detected_before_and_after_selection(setup):
    result = select(setup)
    best = setup[2] / "ultralytics" / "weights" / "best.pt"
    best.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checkpoint checksum"):
        ev.verify_selection(setup[4], result["selection_sha256"])
    with pytest.raises(ValueError, match="artifact mismatch"):
        ev.select_validation(
            setup[0], setup[1], setup[2], setup[3], setup[4].parent / "other", "cpu"
        )


def _threshold(saved):
    saved["operating_evaluation"]["selected"]["threshold"] = 0.5


def _classes(saved):
    saved["classes"] = list(reversed(saved["classes"]))


def _truncated(saved):
    saved["ap_evaluation"]["operating_threshold_applied"] = True


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (_threshold, "threshold selection"),
        (_classes, "class vocabulary"),
        (_truncated, "truncated"),
    ],
)
def test_resealed_edits_are_rejected_by_rederivation(setup, edit, message):
    select(setup)
    out = setup[4]
    with pytest.raises(ValueError, match=message):
        ev.verify_selection(out, reseal(out, edit))


def test_invalid_metric_fails_closed_and_records_failure(setup):
    setup[5]["best"] = math.nan
    with pytest.raises(ValueError, match="invalid"):
        select(setup)
    assert (setup[4] / "failure.json").is_file()


def test_support_mismatch_rejected(setup, monkeypatch):
    bad = metrics(0.6) | {"support": [9] * 6}
    monkeypatch.setattr(ev, "validate_checkpoint", lambda *a: bad)
    with pytest.raises(ValueError, match="support differs"):
        select(setup)


def test_real_release_requires_explicit_approval(tmp_path, monkeypatch):
    export, export_sha = build(tmp_path)
    run = fake_run(tmp_path)
    report, _ = training.load_release(export, export_sha)
    context = {
        "label": "baseline",
        "requested": {"epochs": 2, "imgsz": 320},
        "dataset": report,
        "dataset_view": {"staged_assets": {"train": 6, "validation": 6}},
        "weights": {"sha256": "b"},
        "device": {"requested": "cpu"},
    }
    run_sha = training.seal_run(run, run / "ultralytics", context)
    monkeypatch.setattr(ev, "require_ml", lambda: None)
    monkeypatch.setattr(
        ev, "verify_training", lambda r, s, load=False: training.verify_training(r, s)
    )
    with pytest.raises(ValueError, match="real-release-approved"):
        ev.select_validation(export, export_sha, run, run_sha, tmp_path / "e", "cpu")
    assert not (tmp_path / "e").exists()


def test_run_for_a_different_dataset_rejected(setup):
    export, export_sha, run, run_sha, out, _ = setup

    def different(files, release):
        synthetic(files, release)
        release["review_receipt"] = {"reviewer": "someone else"}

    other, other_sha = build(export.parent / "other", different)
    with pytest.raises(ValueError):
        ev.select_validation(other, other_sha, run, run_sha, out, "cpu")
