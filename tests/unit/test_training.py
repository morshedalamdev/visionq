import io
import json

import pytest
from PIL import Image
from typer.testing import CliRunner

from worker import training
from worker.cli import app
from worker.inventory import canonical_json
from worker.preparation import SPLITS
from worker.validation import CLASSES, sha256


def build(tmp_path, edit=None):
    out = tmp_path / "export"
    files, records = {}, []
    stats = {}
    for s, split in enumerate(SPLITS):
        stats[split] = {"assets": 6, "boxes_per_class": {str(i): 1 for i in range(6)}}
        for cls in range(6):
            image = Image.new("RGB", (40, 30), (20 + s * 40 + cls * 5,) * 3)
            stream = io.BytesIO()
            image.save(stream, format="PNG")
            data = stream.getvalue()
            asset = sha256(data + b"asset")
            files[f"images/{split}/{asset}.png"] = data
            files[f"labels/{split}/{asset}.txt"] = f"{cls} 0.5 0.5 0.5 0.6\n".encode()
            records.append(
                {
                    "group_id": sha256(asset.encode()),
                    "asset_id": asset,
                    "pixel_sha256": sha256(image.tobytes()),
                    "lineage": [{"image_sha256": asset}],
                    "boxes": [[cls, 10.0, 6.0, 30.0, 24.0]],
                    "width": 40,
                    "height": 30,
                    "split": split,
                }
            )
    files["data.yaml"] = training._expected_yaml()
    release = {
        "schema_version": 1,
        "status": "released",
        "review_receipt": {"reviewer": "fixture"},
        "plan": {
            "classes": list(CLASSES),
            "records": records,
            "stats": stats,
            "manifest_sha256": "0" * 64,
        },
    }
    if edit:
        edit(files, release)
    files["release.json"] = canonical_json(release)
    rows = [
        {"path": p, "bytes": len(b), "sha256": sha256(b)}
        for p, b in sorted(files.items())
    ]
    manifest = canonical_json(rows)
    files["manifest.json"] = manifest
    files["manifest.sha256"] = (sha256(manifest) + "\n").encode()
    for name, data in files.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return out, sha256(manifest)


def first(files, prefix):
    return next(k for k in files if k.startswith(prefix))


def test_valid_export_and_repeatable(tmp_path, monkeypatch):
    out, digest = build(tmp_path)
    monkeypatch.chdir(tmp_path.parent)
    report = training.preflight(out, digest)
    assert report["partitions"]["train"]["assets"] == 6
    assert report == training.preflight(out, digest)


def test_wrong_external_checksum_and_changed_bytes(tmp_path):
    out, digest = build(tmp_path)
    with pytest.raises(ValueError, match="checksum"):
        training.preflight(out, "0" * 64)
    path = next((out / "labels" / "train").iterdir())
    path.write_text("0 0.5 0.5 0.4 0.4\n")
    with pytest.raises(ValueError, match="checksum"):
        training.preflight(out, digest)


def test_unreleased_release_rejected(tmp_path):
    out, digest = build(tmp_path, lambda f, r: r.update(status="provisional"))
    with pytest.raises(ValueError, match="released"):
        training.preflight(out, digest)


def test_group_and_pixel_leakage_rejected(tmp_path):
    def group(files, release):
        records = release["plan"]["records"]
        records[-1]["group_id"] = records[0]["group_id"]

    def pixels(files, release):
        records = release["plan"]["records"]
        records[-1]["pixel_sha256"] = records[0]["pixel_sha256"]

    for edit in (group, pixels):
        out, digest = build(tmp_path / edit.__name__, edit)
        with pytest.raises(ValueError, match="leakage"):
            training.preflight(out, digest)


@pytest.mark.parametrize(
    "line",
    [
        "9 0.5 0.5 0.5 0.6",
        "0 0.5 0.5 0 0.6",
        "0 0.9 0.5 0.5 0.6",
        "0 nan 0.5 0.5 0.6",
        "0 0.5 0.5 0.5",
    ],
)
def test_bad_labels_rejected(tmp_path, line):
    def edit(files, release):
        files[first(files, "labels/train/")] = (line + "\n").encode()

    out, digest = build(tmp_path, edit)
    with pytest.raises(ValueError):
        training.preflight(out, digest)


def test_label_disagreeing_with_record_rejected(tmp_path):
    def edit(files, release):
        files[first(files, "labels/train/")] = b"0 0.5 0.5 1 1\n"

    out, digest = build(tmp_path, edit)
    with pytest.raises(ValueError, match="disagrees"):
        training.preflight(out, digest)


def test_full_image_box_and_rgb_checks(tmp_path):
    assert training._label_box("0 0.5 0.5 1 1".split(), 40, 30) == (
        0,
        [0.0, 0.0, 40.0, 30.0],
    )

    def edit(files, release):
        image = Image.new("RGB", (40, 30), (10, 20, 30))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        files[first(files, "images/train/")] = stream.getvalue()

    out, digest = build(tmp_path, edit)
    with pytest.raises(ValueError, match="identical channels"):
        training.preflight(out, digest)


def test_stage_excludes_test_and_detects_drift(tmp_path):
    out, digest = build(tmp_path)
    _, release = training.load_release(out, digest)
    view = training.stage_view(out, release, tmp_path / "run" / "dataset")
    root = tmp_path / "run" / "dataset"
    assert view["staged_assets"] == {"train": 6, "validation": 6}
    assert not (root / "images" / "test").exists()
    text = (root / "data.yaml").read_text()
    assert "test:" not in text and str(root.resolve()) in text
    next((out / "images" / "train").iterdir()).write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        training.stage_view(out, release, tmp_path / "run2")


def test_weights_and_output_guards(tmp_path):
    weights = tmp_path / "w.pt"
    weights.write_bytes(b"weights")
    assert training.check_weights(weights, sha256(b"weights"))["bytes"] == 7
    with pytest.raises(ValueError, match="checksum"):
        training.check_weights(weights, "0" * 64)
    with pytest.raises(ValueError, match="not found"):
        training.check_weights(tmp_path / "missing.pt", "0" * 64)
    export = tmp_path / "export"
    export.mkdir()
    (tmp_path / "taken").mkdir()
    with pytest.raises(FileExistsError):
        training.safe_output(export, tmp_path / "taken")
    with pytest.raises(ValueError, match="separate"):
        training.safe_output(export, export / "run")


def test_missing_ml_dependencies_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(training.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(RuntimeError, match="ML dependencies missing"):
        training.require_ml()
    out, digest = build(tmp_path)
    result = CliRunner().invoke(
        app, ["train-preflight", "--export", str(out), "--manifest-sha", digest]
    )
    assert result.exit_code == 0
    result = CliRunner().invoke(
        app,
        [
            "train-preflight",
            "--export",
            str(out),
            "--manifest-sha",
            digest,
            "--device",
            "cpu",
        ],
    )
    assert result.exit_code == 1


CSV = (
    "epoch,train/box_loss,val/box_loss,metrics/mAP50(B),metrics/mAP50-95(B)\n"
    "1,1.0,1.1,0.1,0.05\n2,0.9,1.0,0.2,0.1\n"
)


def fake_run(tmp_path, csv_text=CSV, last=True):
    run = tmp_path / "run"
    weights = run / "ultralytics" / "weights"
    weights.mkdir(parents=True)
    (weights / "best.pt").write_bytes(b"best")
    if last:
        (weights / "last.pt").write_bytes(b"last")
    (run / "ultralytics" / "results.csv").write_text(csv_text)
    return run


def context():
    return {
        "label": "smoke",
        "requested": {"epochs": 2},
        "dataset": {"manifest_sha256": "a"},
        "weights": {"sha256": "b"},
        "device": {"requested": "cpu"},
    }


def test_seal_verify_and_tamper(tmp_path):
    run = fake_run(tmp_path)
    digest = training.seal_run(run, run / "ultralytics", context())
    assert training.verify_training(run, digest)["verified_artifacts"] >= 3
    with pytest.raises(FileExistsError):
        training.write_new(run / training.MANIFEST, b"x")
    (run / "ultralytics" / "weights" / "best.pt").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="artifact mismatch"):
        training.verify_training(run, digest)
    manifest = run / training.MANIFEST
    manifest.write_bytes(manifest.read_bytes() + b" ")
    with pytest.raises(ValueError, match="manifest checksum"):
        training.verify_training(run, digest)


def test_incomplete_run_and_bad_curves(tmp_path):
    run = fake_run(tmp_path, last=False)
    with pytest.raises(ValueError, match="missing checkpoint"):
        training.seal_run(run, run / "ultralytics", context())
    for text in (CSV.replace("0.05", "nan"), "epoch,x\n1,2\n", ""):
        path = tmp_path / "bad.csv"
        path.write_text(text)
        with pytest.raises(ValueError):
            training.read_curves(path, 2)
    path = tmp_path / "many.csv"
    path.write_text(CSV)
    with pytest.raises(ValueError, match="more curve rows"):
        training.read_curves(path, 1)


def test_manifest_records_are_json(tmp_path):
    run = fake_run(tmp_path)
    training.seal_run(run, run / "ultralytics", context())
    assert json.loads((run / training.MANIFEST).read_bytes())["status"] == "complete"


def test_staged_data_tamper_and_test_partition_detected(tmp_path):
    run = fake_run(tmp_path)
    staged = run / "dataset" / "images" / "train"
    staged.mkdir(parents=True)
    (staged / "a.png").write_bytes(b"image")
    digest = training.seal_run(run, run / "ultralytics", context())
    (staged / "a.png").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="artifact mismatch"):
        training.verify_training(run, digest)
    (staged / "a.png").write_bytes(b"image")
    (run / "dataset" / "labels" / "test").mkdir(parents=True)
    with pytest.raises(ValueError):
        training.verify_training(run, digest)


def test_create_only_record_preserves_neighboring_file(tmp_path):
    neighbor = tmp_path / "intent.json.tmp"
    neighbor.write_bytes(b"independent work")
    training.write_new(tmp_path / "intent.json", b"record")
    assert neighbor.read_bytes() == b"independent work"
    assert (tmp_path / "intent.json").read_bytes() == b"record"
