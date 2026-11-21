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
