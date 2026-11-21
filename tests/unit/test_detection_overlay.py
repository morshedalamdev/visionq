import io

import pytest
from PIL import Image

from worker.detection_overlay import RENDERER_VERSION, render_overlay
from worker.validation import CLASSES, sha256


def image_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 20, 30)).save(stream, format="PNG")
    return stream.getvalue()


def test_overlay_uses_original_pixels_without_mutating_source():
    source = image_bytes()
    source_sha = sha256(source)
    detections = [
        {
            "class_id": 2,
            "confidence": 0.875,
            "box_xmin": 5.2,
            "box_ymin": 4.1,
            "box_xmax": 20.4,
            "box_ymax": 16.8,
        }
    ]

    output = render_overlay(source, detections, CLASSES)

    assert sha256(source) == source_sha
    with Image.open(io.BytesIO(output)) as image:
        assert image.size == (40, 30)
        assert image.getpixel((5, 4)) == (255, 0, 0)
        assert image.getpixel((39, 29)) == (10, 20, 30)


def test_zero_detection_overlay_preserves_image_pixels():
    source = image_bytes()
    output = render_overlay(source, [])
    with Image.open(io.BytesIO(output)) as image:
        assert image.convert("RGB").getpixel((20, 15)) == (10, 20, 30)


@pytest.mark.parametrize(
    "edit",
    [
        {"class_id": 6},
        {"confidence": float("nan")},
        {"box_xmin": -1},
        {"box_xmax": 41},
        {"box_ymin": 5, "box_ymax": 5},
    ],
)
def test_persisted_overlay_values_are_strictly_validated(edit):
    detection = {
        "class_id": 0,
        "confidence": 0.5,
        "box_xmin": 1,
        "box_ymin": 1,
        "box_xmax": 10,
        "box_ymax": 10,
    }
    with pytest.raises(ValueError):
        render_overlay(image_bytes(), [detection | edit], CLASSES)


def test_renderer_has_an_explicit_revision():
    assert RENDERER_VERSION == "m3t3-overlay-v1"
