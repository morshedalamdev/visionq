"""Research registration isolation and database immutability."""

import copy
import hashlib

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_inference_schema import registered

from worker.catalog_store import CatalogConflict
from worker.evaluation_registry import scoped_evidence, validate_model


def test_evidence_constraints_and_scope(postgres_engine, tmp_path):
    _, batch, model = registered(postgres_engine, tmp_path)
    with postgres_engine.begin() as c:
        args = dict(
            sha=hashlib.sha256(model["id"].encode()).hexdigest(),
            model=model["id"],
            dataset=model["dataset_version_id"],
        )
        c.execute(
            text("""INSERT INTO detector_evidence
            (sha256,kind,model_id,dataset_version_id,payload,manifest_bytes)
            VALUES (:sha,'evaluation',CAST(:model AS uuid),CAST(:dataset AS uuid),'{}','x')"""),
            args,
        )
        for sql in [
            "UPDATE detector_evidence SET payload='{}' WHERE sha256=:sha",
            "DELETE FROM detector_evidence WHERE sha256=:sha",
        ]:
            with pytest.raises(IntegrityError), c.begin_nested():
                c.execute(text(sql), args)
        with pytest.raises(IntegrityError), c.begin_nested():
            c.execute(
                text("""INSERT INTO detector_evidence
                (sha256,kind,model_id,dataset_version_id,payload,manifest_bytes)
                VALUES (:other,'evaluation',CAST(:model AS uuid),CAST(:dataset AS uuid),'{}','x')"""),
                {
                    **args,
                    "other": hashlib.sha256(
                        (model["id"] + "other").encode()
                    ).hexdigest(),
                },
            )
        assert (
            scoped_evidence(
                c, model["dataset_version_id"], "00000000-0000-0000-0000-000000000000"
            )["items"]
            == []
        )


def test_provenance_checks_each_identity():
    # Pure contract test with representative structure, no model execution.
    ev = {
        "selection": {"checkpoint_sha256": "a", "sha256": "b", "threshold": 0.31},
        "training_run": {"manifest_sha256": "c"},
        "dataset": {"manifest_sha256": "d"},
        "operating_evaluation": {"settings": {"imgsz": 320}},
        "classes": ["x"],
        "evidence_class": "real-test",
    }
    perf = {"selection": ev["selection"], "evidence_class": "real-test"}
    model = {
        "checkpoint_sha256": "a",
        "selection_manifest_sha256": "b",
        "training_manifest_sha256": "c",
        "release_manifest_sha256": "d",
        "inference_config": {"settings": {"imgsz": 320}, "confidence_threshold": 0.31},
        "classes": ["x"],
        "evidence_kind": "released",
    }
    validate_model(model, ev, perf)
    for key in [
        "checkpoint_sha256",
        "selection_manifest_sha256",
        "training_manifest_sha256",
        "release_manifest_sha256",
        "classes",
        "evidence_kind",
    ]:
        bad = copy.deepcopy(model)
        bad[key] = "wrong"
        with pytest.raises(CatalogConflict):
            validate_model(bad, ev, perf)
    for key in ["settings", "confidence_threshold"]:
        bad = copy.deepcopy(model)
        bad["inference_config"][key] = None
        with pytest.raises(CatalogConflict):
            validate_model(bad, ev, perf)
