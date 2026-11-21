import json
from types import SimpleNamespace

import pytest
from test_evaluation_select import (
    NOISE_BOX,
    metrics,
    reseal,
    select,
    setup,  # noqa: F401
)

from worker import evaluation as ev
from worker.inventory import canonical_json
from worker.validation import sha256

A = [0.0, 0.0, 10.0, 10.0]
B = [20.0, 0.0, 30.0, 10.0]
FAR = [20.0, 20.0, 30.0, 30.0]


def p(cls, conf, box):
    return {"cls": cls, "conf": conf, "box": box}


def g(cls, box):
    return {"cls": cls, "box": box}


def perfect(path, images, settings, device):
    predictions = {
        stem: [p(t["cls"], 0.9, t["box"]) for t in item["gts"]] + [p(1, 0.3, NOISE_BOX)]
        for stem, item in images.items()
    }
    return predictions, {stem: 0 for stem in images}


def empty(path, images, settings, device):
    return {stem: [] for stem in images}, {stem: 0 for stem in images}


@pytest.fixture
def frozen(setup, monkeypatch):  # noqa: F811
    result = select(setup)
    export, export_sha, run, run_sha, selection, _ = setup
    seen = {}

    def validate(path, data_yaml, project, name, settings, device):
        seen["yaml"] = data_yaml.read_text()
        seen["settings"] = settings
        return metrics(0.6)

    monkeypatch.setattr(ev, "validate_checkpoint", validate)
    monkeypatch.setattr(ev, "predict_split", perfect)
    return SimpleNamespace(
        export=export,
        export_sha=export_sha,
        selection=selection,
        selection_sha=result["selection_sha256"],
        out=selection.parent / "test-eval",
        seen=seen,
    )


def run_test(f, **kwargs):
    return ev.evaluate_test(
        f.export, f.export_sha, f.selection, f.selection_sha, f.out, "cpu", **kwargs
    )


def verify(f, sha):
    return ev.verify_test_evaluation(f.out, sha, f.export, f.export_sha)


def reseal_test(out, edit):
    saved = json.loads((out / ev.TEST_EVAL).read_bytes())
    edit(saved)
    data = canonical_json(saved)
    digest = sha256(data)
    (out / ev.TEST_EVAL).write_bytes(data)
    (out / ev.TEST_SIDECAR).write_text(digest + "\n")
    return digest


def test_frozen_roundtrip_uses_only_selection_values(frozen):
    result = run_test(frozen)
    assert result["threshold"] == 0.9
    assert result["evidence_class"] == "synthetic-development"
    saved = json.loads((frozen.out / ev.TEST_EVAL).read_bytes())
    micro = saved["operating_evaluation"]["result"]["micro"]
    assert (micro["tp"], micro["fp"], micro["fn"]) == (6, 0, 0)
    assert saved["selection"]["sha256"] == frozen.selection_sha
    assert saved["coverage"]["failed_images"] == 0
    assert verify(frozen, result["evaluation_sha256"])["test_images"] == 6
    parameters = ev.evaluate_test.__code__.co_varnames[:7]
    assert "threshold" not in parameters and "checkpoint" not in parameters


def test_only_test_partition_is_staged_and_evaluated(frozen):
    run_test(frozen)
    view = frozen.out / "dataset"
    assert sorted(path.name for path in (view / "images").iterdir()) == ["test"]
    assert {path.name for path in (view / "labels").iterdir()} <= {
        "test",
        "test.cache",
    }
    assert "images/test" in frozen.seen["yaml"]
    assert "validation" not in frozen.seen["yaml"]
    assert frozen.seen["settings"]["conf"] == ev.FLOOR


def test_ap_inputs_are_not_truncated_by_operating_threshold(frozen):
    run_test(frozen)
    rows = json.loads((frozen.out / ev.TEST_PER_IMAGE).read_bytes())
    assert {r["predictions_at_floor"] for r in rows} == {2}
    assert {r["predictions_at_threshold"] for r in rows} == {1}
    saved = json.loads((frozen.out / ev.TEST_EVAL).read_bytes())
    assert saved["ap_evaluation"]["operating_threshold_applied"] is False
    assert saved["ap_evaluation"]["map50"] == 0.5


def test_empty_predictions_are_scored_not_skipped(frozen, monkeypatch):
    monkeypatch.setattr(ev, "predict_split", empty)
    result = run_test(frozen)
    saved = json.loads((frozen.out / ev.TEST_EVAL).read_bytes())
    micro = saved["operating_evaluation"]["result"]["micro"]
    assert (micro["tp"], micro["fp"], micro["fn"]) == (0, 0, 6)
    assert micro["precision"] is None and micro["recall"] == 0
    assert saved["error_examples"]["counts"]["missed"] == 6
    verify(frozen, result["evaluation_sha256"])


def test_repeated_output_and_failed_prediction_evidence(frozen, monkeypatch):
    run_test(frozen)
    with pytest.raises(FileExistsError):
        run_test(frozen)

    def broken(path, images, settings, device):
        raise RuntimeError("prediction failed for image abc: boom")

    monkeypatch.setattr(ev, "predict_split", broken)
    frozen.out = frozen.out.parent / "second"
    with pytest.raises(RuntimeError, match="abc"):
        run_test(frozen)
    failure = json.loads((frozen.out / "failure.json").read_bytes())
    assert "abc" in failure["message"]
    assert not (frozen.out / ev.TEST_EVAL).exists()


def test_unsealed_or_changed_selection_blocks_evaluation(frozen):
    predictions = frozen.selection / ev.PREDICTIONS
    predictions.write_bytes(predictions.read_bytes() + b" ")
    with pytest.raises(ValueError, match="artifact mismatch"):
        run_test(frozen)
    assert not frozen.out.exists()


def test_wrong_selection_checksum_and_missing_selection(frozen):
    frozen.selection_sha = "0" * 64
    with pytest.raises(ValueError, match="selection checksum"):
        run_test(frozen)
    (frozen.selection / ev.SELECTION).unlink()
    with pytest.raises(FileNotFoundError):
        run_test(frozen)
    assert not frozen.out.exists()


def test_selection_for_other_release_rejected(frozen):
    def different(saved):
        saved["dataset"]["release_sha256"] = "0" * 64

    frozen.selection_sha = reseal(frozen.selection, different)
    with pytest.raises(ValueError, match="release identity"):
        run_test(frozen)
    assert not frozen.out.exists()


def test_real_data_selection_requires_explicit_approval(frozen):
    def real(saved):
        saved["evidence_class"] = "real-validation"

    frozen.selection_sha = reseal(frozen.selection, real)
    with pytest.raises(ValueError, match="real-release-approved"):
        run_test(frozen)
    assert not frozen.out.exists()


def edit_settings(saved):
    saved["ap_evaluation"]["settings"]["conf"] = 0.5


def edit_threshold(saved):
    saved["operating_evaluation"]["threshold"] = 0.5


def edit_checkpoint(saved):
    saved["selection"]["checkpoint_sha256"] = "0" * 64


def edit_coverage(saved):
    saved["coverage"]["evaluated_images"] = 5


def edit_dataset(saved):
    saved["dataset"]["release_sha256"] = "0" * 64


def edit_metrics(saved):
    saved["operating_evaluation"]["result"]["micro"]["tp"] = 0


def edit_errors(saved):
    saved["error_examples"]["counts"]["missed"] = 99


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (edit_settings, "evaluator settings"),
        (edit_threshold, "evaluator settings"),
        (edit_checkpoint, "frozen selection"),
        (edit_coverage, "incomplete test coverage"),
        (edit_dataset, "release identity|dataset identity"),
        (edit_metrics, "operating metrics"),
        (edit_errors, "error examples"),
    ],
)
def test_resealed_edits_are_rejected(frozen, edit, message):
    run_test(frozen)
    with pytest.raises(ValueError, match=message):
        verify(frozen, reseal_test(frozen.out, edit))


def test_artifact_tampering_detected(frozen):
    digest = run_test(frozen)["evaluation_sha256"]
    for name in (ev.TEST_PREDICTIONS, ev.TEST_PER_IMAGE):
        path = frozen.out / name
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with pytest.raises(ValueError, match="artifact mismatch"):
            verify(frozen, digest)
        path.write_bytes(original)
    (frozen.out / ev.TEST_PER_IMAGE).unlink()
    with pytest.raises(ValueError, match="artifact mismatch"):
        verify(frozen, digest)
    with pytest.raises(ValueError, match="checksum"):
        verify(frozen, "0" * 64)


def test_extra_partition_or_changed_selection_detected(frozen):
    digest = run_test(frozen)["evaluation_sha256"]
    (frozen.out / "dataset" / "images" / "validation").mkdir()
    with pytest.raises(ValueError, match="non-test"):
        verify(frozen, digest)
    (frozen.out / "dataset" / "images" / "validation").rmdir()
    predictions = frozen.selection / ev.PREDICTIONS
    predictions.write_bytes(predictions.read_bytes() + b" ")
    with pytest.raises(ValueError, match="artifact mismatch"):
        verify(frozen, digest)


def test_error_examples_are_class_aware_and_deterministic():
    images = {
        "a": {"gts": [g(0, A), g(1, B)]},
        "b": {"gts": [g(2, A)]},
    }
    predictions = {
        "a": [
            p(1, 0.9, A),  # overlaps a class-0 truth: class confusion
            p(0, 0.8, [0, 0, 10, 4]),  # IoU 0.4 with the same class: localization
            p(1, 0.95, B),  # true positive
            p(1, 0.6, B),  # second box on a matched truth: duplicate
            p(2, 0.7, FAR),  # no overlap: false alarm
        ],
        "b": [p(2, 0.99, A), p(0, 0.5, FAR), p(0, 0.6, FAR), p(3, 0.55, FAR)],
    }
    found = ev.error_examples(images, predictions, 0.5, limit=2)
    assert found["counts"] == {
        "false_alarm": 4,
        "localization": 1,
        "class_confusion": 1,
        "duplicate": 1,
        "missed": 1,
    }
    assert found["examples"]["class_confusion"][0]["other_class_id"] == 0
    # Highest confidence first, truncated to the limit.
    assert [e["conf"] for e in found["examples"]["false_alarm"]] == [0.7, 0.6]
    assert found["examples"]["missed"][0]["image"] == "a"
    assert found == ev.error_examples(images, predictions, 0.5, limit=2)
