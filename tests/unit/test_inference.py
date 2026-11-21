import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from worker import inference
from worker.inventory import canonical_json
from worker.validation import sha256


def test_zero_detections_are_a_successful_valid_output():
    result = inference.validate_predictions([], 20, 10, 6, 0.07)

    assert result["raw_prediction_count"] == 0
    assert result["detections"] == []
    assert result["detection_count"] == 0
    assert result["prediction_sha256"] == sha256(canonical_json([]))


def test_threshold_and_original_coordinates_are_preserved():
    raw = [
        {"cls": 2, "conf": 0.95, "box": [1, 2, 8, 9]},
        {"cls": 4, "conf": 0.05, "box": [0, 0, 20, 10]},
    ]

    result = inference.validate_predictions(raw, 20, 10, 6, 0.07)

    assert result["raw_prediction_count"] == 2
    assert result["detection_count"] == 1
    assert result["detections"] == [
        {"cls": 2, "conf": 0.95, "box": [1.0, 2.0, 8.0, 9.0]}
    ]
    assert result["prediction_sha256"] == sha256(canonical_json(raw))


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({}, "list"),
        ([{"cls": True, "conf": 0.5, "box": [0, 0, 1, 1]}], "class ID"),
        ([{"cls": 6, "conf": 0.5, "box": [0, 0, 1, 1]}], "class ID"),
        ([{"cls": 0, "conf": float("nan"), "box": [0, 0, 1, 1]}], "confidence"),
        ([{"cls": 0, "conf": 1.1, "box": [0, 0, 1, 1]}], "confidence"),
        ([{"cls": 0, "conf": 0.5, "box": [1, 1, 1, 2]}], "coordinates"),
        ([{"cls": 0, "conf": 0.5, "box": [-1, 0, 1, 1]}], "coordinates"),
        ([{"cls": 0, "conf": 0.5, "box": [0, 0, 21, 1]}], "dimensions"),
        ([{"cls": 0, "conf": 0.5, "box": [0, 0, float("inf"), 1]}], "finite"),
    ],
)
def test_malformed_predictions_fail_closed(raw, message):
    with pytest.raises(ValueError, match=message):
        inference.validate_predictions(raw, 20, 10, 6, 0.07)


def test_membership_and_run_identities_are_deterministic():
    members = [
        {"asset_id": "00000000-0000-0000-0000-000000000001", "image_sha256": "a" * 64},
        {"asset_id": "00000000-0000-0000-0000-000000000002", "image_sha256": "b" * 64},
    ]
    config = {"device": "mps", "batch_size": 1}
    version = "00000000-0000-0000-0000-000000000003"

    digest = inference.membership_sha256(version, members)
    assert digest == inference.membership_sha256(version, members)
    assert inference.run_identity("batch", "model", config) == inference.run_identity(
        "batch", "model", config
    )
    assert inference.run_identity("batch", "model", config) != inference.run_identity(
        "batch", "model", {**config, "device": "cpu"}
    )


def test_selected_model_rejects_changed_checkpoint(tmp_path, monkeypatch):
    checkpoint = tmp_path / "best.pt"
    checkpoint.write_bytes(b"original")
    saved = {
        "evidence_class": "synthetic-development",
        "classes": ["a"] * 6,
        "selected_checkpoint": {
            "path": str(checkpoint),
            "name": "best",
            "sha256": sha256(b"expected"),
        },
        "training_run": {"manifest_sha256": "b" * 64},
        "dataset": {"manifest_sha256": "c" * 64},
        "operating_evaluation": {
            "settings": {"conf": 0.001},
            "selected": {"threshold": 0.07},
            "match_iou": 0.5,
        },
    }
    (tmp_path / inference.SELECTION).write_bytes(canonical_json(saved))
    monkeypatch.setattr(inference, "verify_selection", lambda *args: None)

    with pytest.raises(ValueError, match="checkpoint checksum"):
        inference.selected_model(tmp_path, "d" * 64)


def test_selected_model_preserves_frozen_runtime_settings(tmp_path, monkeypatch):
    checkpoint = tmp_path / "best.pt"
    checkpoint.write_bytes(b"checkpoint")
    saved = {
        "evidence_class": "synthetic-development",
        "classes": list(inference.CLASSES),
        "selected_checkpoint": {
            "path": str(checkpoint),
            "name": "best",
            "sha256": sha256(checkpoint.read_bytes()),
        },
        "training_run": {"manifest_sha256": "b" * 64},
        "dataset": {"manifest_sha256": "c" * 64},
        "operating_evaluation": {
            "settings": {"imgsz": 320, "conf": 0.001, "iou": 0.7, "max_det": 300},
            "selected": {"threshold": 0.07},
            "match_iou": 0.5,
        },
    }
    (tmp_path / inference.SELECTION).write_bytes(canonical_json(saved))
    monkeypatch.setattr(inference, "verify_selection", lambda *args: None)

    contract = inference.selected_model(tmp_path, "d" * 64)
    assert (
        json.loads(canonical_json(contract["inference_config"]))["confidence_threshold"]
        == 0.07
    )
    assert contract["inference_config"]["settings"]["imgsz"] == 320
    assert contract["evidence_kind"] == "synthetic"


def test_ultralytics_predictor_decodes_extensionless_content_addressed_image(
    tmp_path,
):
    image = tmp_path / ("f" * 64)
    stream = io.BytesIO()
    Image.new("L", (8, 6), 7).save(stream, format="PNG")
    image.write_bytes(stream.getvalue())

    class Boxes:
        xyxy = [[1, 2, 3, 4]]
        conf = [0.8]
        cls = [2]

        def tolist(self):
            return list(self)

    class BoxList:
        def __init__(self):
            self.xyxy = self._values(Boxes.xyxy)
            self.conf = self._values(Boxes.conf)
            self.cls = self._values(Boxes.cls)

        class _values(list):
            def tolist(self):
                return list(self)

    class Model:
        def predict(self, source, **kwargs):
            assert isinstance(source, Image.Image)
            assert source.mode == "RGB"
            return [type("Result", (), {"boxes": BoxList()})()]

    predictor = inference.UltralyticsPredictor.__new__(inference.UltralyticsPredictor)
    predictor.model = Model()

    assert predictor(image, {"imgsz": 320}, "mps") == [
        {"cls": 2, "conf": 0.8, "box": [1.0, 2.0, 3.0, 4.0]}
    ]


def test_ultralytics_predictor_stages_extensionless_checkpoint(tmp_path, monkeypatch):
    checkpoint = tmp_path / ("a" * 64)
    checkpoint.write_bytes(b"verified-checkpoint")
    loaded = {}

    def fake_yolo(path):
        loaded["path"] = Path(path)
        loaded["data"] = loaded["path"].read_bytes()
        return object()

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=fake_yolo))
    predictor = inference.UltralyticsPredictor(checkpoint)

    assert predictor.model is not None
    assert loaded["path"].suffix == ".pt"
    assert loaded["data"] == checkpoint.read_bytes()
