import json

import pytest

from worker import evaluation as ev
from worker.inventory import canonical_json
from worker.validation import sha256


def record(index, value):
    return {
        "index": index,
        "image": str(index % 2),
        "decode_ms": value / 10,
        "preprocess_ms": value / 5,
        "inference_ms": value,
        "postprocess_ms": value / 4,
        "full_pipeline_ms": value * 1.55,
    }


def test_nearest_rank_p95():
    result = ev.summarize_timing(list(range(1, 101)))
    assert result["median_ms"] == 50.5
    assert result["p95_ms"] == 95
    assert result["count"] == 100


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_non_finite_or_negative_timing_rejected(value):
    with pytest.raises(ValueError, match="finite|non-negative"):
        ev.summarize_timing([1, value])


def test_empty_or_incomplete_samples_rejected():
    with pytest.raises(ValueError, match="no timing"):
        ev.aggregate_observations([], 100, [])
    with pytest.raises(ValueError, match="incomplete"):
        ev.aggregate_observations([record(0, 1)], 100, [])
    with pytest.raises(ValueError, match="failed"):
        ev.aggregate_observations([], 100, [{"index": 1, "error": "boom"}])


def test_aggregate_and_throughput():
    result = ev.aggregate_observations([record(i, i + 1) for i in range(100)], 100, [])
    assert result["observation_count"] == 100
    assert result["stages"]["inference"]["p95_ms"] == 95
    assert result["throughput_images_per_second"] > 0
    assert result["stages"]["full_pipeline"]["median_ms"] == pytest.approx(78.275)


def test_sampling_preserves_unique_and_repeated_counts():
    images = {str(i): {"image": i} for i in range(3)}
    plan = ev.benchmark_plan(images)
    assert plan["unique_image_count"] == 3
    assert plan["observation_count"] == 100
    assert plan["repeated_observation_count"] == 97
    assert plan["sequence"][:6] == ["0", "1", "2", "0", "1", "2"]


def test_sampling_rejects_empty_and_bad_count():
    with pytest.raises(ValueError, match="no unique"):
        ev.benchmark_plan({})
    with pytest.raises(ValueError, match="positive"):
        ev.benchmark_plan({"0": {}}, 0)


def test_observation_evidence_roundtrips():
    records = [record(i, i + 1) for i in range(100)]
    evidence = canonical_json(
        {
            "records": records,
            "failed_samples": [],
            "settings": {"batch": 1},
        }
    )
    loaded = json.loads(evidence)
    assert canonical_json(
        ev.aggregate_observations(loaded["records"], 100, loaded["failed_samples"])
    ) == canonical_json(ev.aggregate_observations(records, 100, []))
    assert sha256(evidence) == sha256(canonical_json(loaded))


def test_empty_timing_total_rejected():
    records = [record(i, 0) for i in range(100)]
    with pytest.raises(ValueError, match="elapsed time"):
        ev.aggregate_observations(records, 100, [])


def test_performance_configuration_is_locked():
    assert ev.WARMUPS == 10
    assert ev.OBSERVATION_COUNT == 100
    assert "synchron" in ev.TIMING_METHOD.lower()
    assert "decode" in ev.TIMING_METHOD and "NMS" in ev.TIMING_METHOD


def test_complete_performance_artifact_verifies(tmp_path, monkeypatch):
    from pathlib import Path

    from worker import evaluation as evaluation

    export = tmp_path / "export"
    evaluation_dir = tmp_path / "evaluation"
    (export / "placeholder").mkdir(parents=True)
    (evaluation_dir / "dataset").mkdir(parents=True)
    checkpoint = tmp_path / "best.pt"
    checkpoint.write_bytes(b"checkpoint")
    images = {str(i): {"image": Path(f"{i}.png")} for i in range(3)}
    prediction_settings = {
        "imgsz": 320,
        "conf": 0.001,
        "iou": 0.7,
        "max_det": 300,
    }
    frozen = {
        "checkpoint": {
            "name": "best",
            "path": str(checkpoint),
            "sha256": "checkpoint-sha",
        },
        "predict_settings": prediction_settings,
        "threshold": 0.07,
    }
    evidence = {
        "stage": "frozen-test-evaluation",
        "evidence_class": "synthetic-development",
        "selection": {
            "path": str(tmp_path / "selection"),
            "sha256": "selection-sha",
        },
        "dataset": {"manifest_sha256": "dataset-sha"},
    }
    (evaluation_dir / evaluation.TEST_EVAL).write_bytes(canonical_json(evidence))
    monkeypatch.setattr(evaluation, "require_ml", lambda: None)
    monkeypatch.setattr(
        evaluation,
        "performance_inputs",
        lambda *args: (evidence, frozen, images, {"evaluation_sha256": args[1]}),
    )
    monkeypatch.setattr(
        evaluation, "check_device", lambda device: {"requested": device}
    )
    monkeypatch.setattr(evaluation, "environment", lambda: {"python": "test"})
    monkeypatch.setattr(evaluation, "code_identity", lambda: {"revision": "test"})

    def benchmark(*args, **kwargs):
        plan = evaluation.benchmark_plan(images)
        records = []
        for index in range(100):
            row = record(index, index + 1)
            row["image"] = plan["sequence"][index]
            records.append(row)
        return records, [], plan, "float32"

    monkeypatch.setattr(evaluation, "benchmark_checkpoint", benchmark)

    performance = tmp_path / "performance"
    result = evaluation.measure_performance(
        evaluation_dir, "evaluation-sha", export, "dataset-sha", performance, "cpu"
    )

    monkeypatch.setattr(
        evaluation,
        "verify_test_evaluation",
        lambda *args: {"evaluation_sha256": args[1]},
    )
    monkeypatch.setattr(evaluation, "_frozen", lambda *args: frozen)
    monkeypatch.setattr(evaluation, "load_split", lambda *args: images)
    verified = evaluation.verify_performance(
        performance,
        result["performance_sha256"],
        evaluation_dir,
        "evaluation-sha",
        export,
        "dataset-sha",
    )
    assert verified["unique_images"] == 3
    assert verified["observations"] == 100

    observations = json.loads((performance / evaluation.OBSERVATIONS).read_bytes())
    manifest = json.loads((performance / evaluation.PERFORMANCE).read_bytes())
    assert observations["settings"] == manifest["settings"]
    assert manifest["settings"]["batch"] == 1
    assert manifest["settings"]["warmups"] == 10

    with pytest.raises(ValueError, match="performance checksum"):
        evaluation.verify_performance(
            performance,
            "0" * 64,
            evaluation_dir,
            "evaluation-sha",
            export,
            "dataset-sha",
        )

    observation_path = performance / evaluation.OBSERVATIONS
    observation_path.write_bytes(observation_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="artifact mismatch"):
        # Restore the observations file to its original state for the next test
        observation_path.write_bytes(observation_path.read_bytes()[:-1])
        evaluation.verify_performance(
            performance,
            result["performance_sha256"],
            evaluation_dir,
            "evaluation-sha",
            export,
            "dataset-sha",
        )
