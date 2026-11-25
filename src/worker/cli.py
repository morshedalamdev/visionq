"""Command-line entry point for VisionQ."""

import json
import platform
import sys
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path

import typer
from sqlalchemy.exc import SQLAlchemyError

from worker.backup import Directory
from worker.catalog import ingest, operation_status
from worker.catalog_backup import (
    RestoreIncomplete,
    backup_catalog,
    restore_catalog,
    verify_catalog_backup,
)
from worker.catalog_input import load_package
from worker.catalog_store import CatalogBusy
from worker.db import database
from worker.inventory import publish_inventory
from worker.reconciliation import reconcile, report_text
from worker.review import check_review, make_packet
from worker.validation import (
    audit,
    canonical_json,
    make_revision,
    write_bundle,
)

app = typer.Typer(
    help="VisionQ research application commands.",
    no_args_is_help=True,
    rich_markup_mode="rich" if sys.stderr.isatty() else None,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Run a Vision command."""


CATALOG_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    SQLAlchemyError,
    CatalogBusy,
    RestoreIncomplete,
)
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")


def describe(exc: Exception) -> str:
    # Database errors can embed connection details, so only the type is shown.
    if isinstance(exc, SQLAlchemyError):
        return f"database operation failed ({type(exc).__name__})"
    if isinstance(exc, KeyError):
        return f"missing required setting or field {exc}"
    if isinstance(exc, FileExistsError):
        return f"already exists: {exc}"
    return str(exc) or type(exc).__name__


@contextmanager
def catalog_session(command: str, database_required: bool = True, loopback=False):
    """Yield a disposable engine; map expected failures to one-line errors."""
    engine = None
    try:
        if database_required:
            engine = database()
            if loopback and engine.url.host not in LOOPBACK_HOSTS:
                raise ValueError(
                    "local catalog restore requires a loopback VISIONQ_DATABASE_URL"
                )
        yield engine
    except CATALOG_ERRORS as exc:
        typer.echo(f"{command} failed: {describe(exc)}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        if engine is not None:
            engine.dispose()


def catalog_package(
    source: Path,
    baseline: Path,
    packet: Path,
    release: Path,
    release_sha: str,
    dataset_name: str,
    version: int,
):
    return load_package(
        source=source,
        baseline=baseline,
        packet=packet,
        release=release,
        release_sha256=release_sha,
        dataset_name=dataset_name,
        version=version,
    )


@app.command()
def info() -> None:
    """Print package and interpreter information as JSON."""
    payload = {
        "application": "visionq",
        "version": version("visionq"),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command("inventory")
def inventory_command(
    root: Path = typer.Option(..., help="Existing NEU-DET source directory."),
    output: Path = typer.Option(..., help="Fresh evidence directory outside source."),
) -> None:
    """Inventory original files and report source observations."""
    try:
        report = publish_inventory(root, output)
    except (OSError, ValueError) as exc:
        typer.echo(f"Inventory failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        json.dumps(
            {
                "output": str(output.resolve()),
                "manifest_sha256": report["manifest_sha256"],
                "counts": report["counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )


@app.command("validate-dataset")
def validate_dataset(
    root: Path = typer.Option(...),
    baseline: Path = typer.Option(...),
    baseline_sha: str = typer.Option(...),
    coordinates: str = typer.Option(...),
    output: Path = typer.Option(...),
    revision: list[Path] = typer.Option([]),
    reference: Path | None = typer.Option(None),
):
    """Audit annotation candidates and retain quality findings."""
    try:
        revisions = [json.loads(path.read_bytes()) for path in revision]
        reference_data = (
            json.loads(reference.read_bytes()) if reference is not None else None
        )
        report = audit(
            root,
            baseline,
            baseline_sha,
            coordinates,
            revisions=revisions,
            reference=reference_data,
        )
        write_bundle(
            root,
            output,
            {
                "audit.json": canonical_json(report),
                "quarantine.json": canonical_json(report["quarantine"]),
            },
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"Validation failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        json.dumps(
            {
                "images": len(report["items"]),
                "quarantined": len(report["quarantine"]),
                "duplicate_groups": len(report["duplicates"]),
                "manifest_sha256": report["manifest_sha256"],
                "coordinates": coordinates,
            },
            indent=2,
        )
    )


@app.command("review-packet")
def review_packet(
    root: Path = typer.Option(...),
    audit_path: Path = typer.Option(...),
    output: Path = typer.Option(...),
):
    """Publish overlays and an incomplete human review record."""
    try:
        result = make_packet(root, audit_path, output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"Review packet failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result, indent=2))


@app.command("check-review")
def review_check(packet: Path = typer.Option(...)):
    """Verify completed human review identities and coverage."""
    try:
        result = check_review(packet)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"Review incomplete: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("revise-annotation")
def revise_annotation(
    root: Path = typer.Option(...),
    audit_path: Path = typer.Option(...),
    image: str = typer.Option(...),
    request: Path = typer.Option(...),
    output: Path = typer.Option(...),
):
    """Create a reviewed class/box correction as a new revision."""
    try:
        report = json.loads(audit_path.read_bytes())
        change = json.loads(request.read_bytes())
        revision = make_revision(
            report["items"][image],
            change["boxes"],
            change["author"],
            change["reason"],
        )
        write_bundle(
            root,
            output,
            {
                "revision.json": canonical_json(revision),
            },
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"Correction failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(revision, indent=2))


@app.command("prepare-dataset")
def prepare_dataset(
    root: Path = typer.Option(...),
    packet: Path = typer.Option(...),
    output: Path = typer.Option(...),
    official: Path | None = typer.Option(None),
    grouping_policy: str = typer.Option("pair_review"),
):
    """Create a provisional grouped split plan without training inputs."""
    from worker.preparation import prepare

    try:
        plan = prepare(root, packet, official, grouping_policy)
        data = canonical_json(plan)
        write_bundle(root, output, {"plan.json": data})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"Preparation failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        json.dumps(
            {
                "status": plan["status"],
                "stats": plan["stats"],
                "excluded": len(plan["excluded"]),
                "near_candidates": len(plan["near_candidates"]),
            },
            indent=2,
        )
    )


@app.command("export-dataset")
def export_dataset(
    root: Path = typer.Option(...),
    packet: Path = typer.Option(...),
    plan: Path = typer.Option(...),
    plan_sha: str = typer.Option(...),
    output: Path = typer.Option(...),
    near_review: Path | None = typer.Option(None),
    official: Path | None = typer.Option(None),
    component_packet: Path | None = typer.Option(None),
    component_packet_sha: str | None = typer.Option(None),
):
    """Release local training inputs only after genuine review gates pass."""
    from worker.preparation import export

    try:
        result = export(
            root,
            packet,
            plan,
            plan_sha,
            output,
            json.loads(near_review.read_bytes()) if near_review else None,
            official,
            component_packet,
            component_packet_sha,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"Export blocked: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result, indent=2))


@app.command("near-review-packet")
def near_review_packet(
    root: Path = typer.Option(...),
    packet: Path = typer.Option(...),
    plan: Path = typer.Option(...),
    plan_sha: str = typer.Option(...),
    output: Path = typer.Option(...),
    official: Path | None = typer.Option(None),
):
    """Create previews and pending decisions for near-duplicate candidates."""
    from worker.near_review import make_near_packet

    try:
        result = make_near_packet(root, packet, plan, plan_sha, output, official)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"Near review packet failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result, indent=2))


@app.command("component-review-packet")
def component_review_packet(
    root: Path = typer.Option(...),
    packet: Path = typer.Option(...),
    plan: Path = typer.Option(...),
    plan_sha: str = typer.Option(...),
    output: Path = typer.Option(...),
    official: Path | None = typer.Option(None),
):
    """Create conservative component contact sheets and pending review."""
    from worker.component_review import make_component_packet

    try:
        result = make_component_packet(root, packet, plan, plan_sha, output, official)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"Component packet failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result, indent=2))


@app.command("check-component-review")
def component_review_check(
    packet: Path = typer.Option(...),
    packet_sha: str = typer.Option(...),
):
    """Validate completed review against a separately retained packet digest."""
    from worker.component_review import check_component_review

    try:
        result = check_component_review(packet, packet_sha)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"Component review blocked: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result, indent=2))


@app.command("catalog-import")
def catalog_import(
    source: Path = typer.Option(...),
    baseline: Path = typer.Option(...),
    packet: Path = typer.Option(...),
    release: Path = typer.Option(...),
    release_sha: str = typer.Option(...),
    dataset_name: str = typer.Option(...),
    version: int = typer.Option(...),
    artifact_root: Path = typer.Option(...),
):
    """Import a synthetic T4 catalog package."""
    with catalog_session("catalog-import") as engine:
        package = catalog_package(
            source,
            baseline,
            packet,
            release,
            release_sha,
            dataset_name,
            version,
        )
        report = ingest(engine, artifact_root, package)
    typer.echo(json.dumps(report, indent=2, sort_keys=True))


@app.command("catalog-resume")
def catalog_resume(
    source: Path = typer.Option(...),
    baseline: Path = typer.Option(...),
    packet: Path = typer.Option(...),
    release: Path = typer.Option(...),
    release_sha: str = typer.Option(...),
    dataset_name: str = typer.Option(...),
    version: int = typer.Option(...),
    artifact_root: Path = typer.Option(...),
    run_id: str = typer.Option(...),
):
    """Resume only the operation matching the package run identity."""
    with catalog_session("catalog-resume") as engine:
        package = catalog_package(
            source,
            baseline,
            packet,
            release,
            release_sha,
            dataset_name,
            version,
        )
        report = ingest(
            engine,
            artifact_root,
            package,
            resume_run=run_id,
        )
    typer.echo(json.dumps(report, indent=2, sort_keys=True))


@app.command("catalog-status")
def catalog_status(run_id: str = typer.Option(...)):
    """Print persisted ingestion operation and item states."""
    with catalog_session("catalog-status") as engine:
        status = operation_status(engine, run_id)
    typer.echo(json.dumps(status, indent=2, sort_keys=True))


@app.command("catalog-reconcile")
def catalog_reconcile(
    source: Path = typer.Option(...),
    baseline: Path = typer.Option(...),
    packet: Path = typer.Option(...),
    release: Path = typer.Option(...),
    release_sha: str = typer.Option(...),
    dataset_name: str = typer.Option(...),
    version: int = typer.Option(...),
    artifact_root: Path = typer.Option(...),
):
    """Compare catalog rows and artifacts with the package specification."""
    with catalog_session("catalog-reconcile") as engine:
        package = catalog_package(
            source,
            baseline,
            packet,
            release,
            release_sha,
            dataset_name,
            version,
        )
        report = reconcile(
            engine,
            artifact_root,
            package.specification(),
        )
    typer.echo(report_text(report), nl=False)
    if not report["ok"]:
        raise typer.Exit(code=1)


@app.command("catalog-backup")
def catalog_backup(
    backup_id: str = typer.Option(...),
    artifact_root: Path = typer.Option(...),
    local_store: Path = typer.Option(..., help="Local directory used as the store."),
    source: Path = typer.Option(...),
    baseline: Path = typer.Option(...),
    packet: Path = typer.Option(...),
    release: Path = typer.Option(...),
    release_sha: str = typer.Option(...),
    dataset_name: str = typer.Option(...),
    version: int = typer.Option(...),
):
    """Back up a complete reconciled synthetic catalog snapshot."""
    with catalog_session("catalog-backup") as engine:
        package = catalog_package(
            source,
            baseline,
            packet,
            release,
            release_sha,
            dataset_name,
            version,
        )
        manifest_sha = backup_catalog(
            engine,
            artifact_root,
            Directory(local_store),
            backup_id,
            package,
        )
    typer.echo(
        json.dumps(
            {
                "backup_id": backup_id,
                "manifest_sha256": manifest_sha,
            },
            indent=2,
            sort_keys=True,
        )
    )


@app.command("catalog-verify")
def catalog_verify(
    backup_id: str = typer.Option(...),
    local_store: Path = typer.Option(..., help="Local directory used as the store."),
):
    """Verify the complete catalog backup and completion marker."""
    with catalog_session("catalog-verify", database_required=False):
        manifest_sha = verify_catalog_backup(Directory(local_store), backup_id)
    typer.echo(
        json.dumps(
            {
                "backup_id": backup_id,
                "manifest_sha256": manifest_sha,
                "verified": True,
            },
            indent=2,
            sort_keys=True,
        )
    )


@app.command("catalog-restore")
def catalog_restore(
    backup_id: str = typer.Option(...),
    destination: Path = typer.Option(...),
    local_store: Path = typer.Option(..., help="Local directory used as the store."),
):
    """Restore (or resume restoring) a synthetic catalog to local PostgreSQL."""
    with catalog_session("catalog-restore", loopback=True) as engine:
        manifest_sha = restore_catalog(
            engine,
            Directory(local_store),
            backup_id,
            destination,
        )
    typer.echo(
        json.dumps(
            {
                "backup_id": backup_id,
                "destination": str(destination.resolve()),
                "manifest_sha256": manifest_sha,
            },
            indent=2,
            sort_keys=True,
        )
    )


def _training_failure(prefix, exc):
    typer.echo(f"{prefix}: {exc}", err=True)
    raise typer.Exit(1) from exc


@app.command("train-preflight")
def train_preflight(
    export: Path = typer.Option(...),
    manifest_sha: str = typer.Option(...),
    weights: Path | None = typer.Option(None),
    weights_sha: str | None = typer.Option(None),
    device: str | None = typer.Option(None),
):
    """Verify a released export and, optionally, weights and device."""
    from worker.training import check_device, check_weights, environment, preflight

    try:
        result = {"dataset": preflight(export, manifest_sha)}
        if weights is not None:
            if not weights_sha:
                raise ValueError("--weights-sha is required with --weights")
            result["weights"] = check_weights(weights, weights_sha)
        if device is not None:
            result["device"] = check_device(device)
        result["environment"] = environment()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        _training_failure("Preflight blocked", exc)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("train-baseline")
def train_baseline_command(
    export: Path = typer.Option(...),
    manifest_sha: str = typer.Option(...),
    weights: Path = typer.Option(...),
    weights_sha: str = typer.Option(...),
    output: Path = typer.Option(...),
    device: str = typer.Option(...),
    rights_decision: str = typer.Option(...),
    label: str = typer.Option("baseline"),
    epochs: int = typer.Option(60, min=1),
    batch: int = typer.Option(16, min=1),
):
    """Train the YOLO11n baseline on verified train/validation partitions."""
    from worker.training import train_baseline

    try:
        result = train_baseline(
            export,
            manifest_sha,
            weights,
            weights_sha,
            output,
            device,
            rights_decision,
            label,
            epochs,
            batch,
        )
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        _training_failure("Training blocked", exc)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("train-verify")
def train_verify(
    run: Path = typer.Option(...),
    manifest_sha: str = typer.Option(...),
    load: bool = typer.Option(False),
    export: Path | None = typer.Option(None),
    export_sha: str | None = typer.Option(None),
):
    """Verify a sealed training run; optionally load checkpoints and re-verify the export."""
    from worker.preparation import verify_export
    from worker.training import verify_training

    try:
        result = verify_training(run, manifest_sha, load)
        if export is not None:
            if not export_sha:
                raise ValueError("--export-sha is required with --export")
            result["export"] = verify_export(export, export_sha)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        _training_failure("Verification failed", exc)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("eval-select")
def eval_select(
    export: Path = typer.Option(...),
    export_sha: str = typer.Option(...),
    run: Path = typer.Option(...),
    run_sha: str = typer.Option(...),
    output: Path = typer.Option(...),
    device: str = typer.Option(...),
    real_release_approved: bool = typer.Option(False),
):
    """Choose checkpoint and operating threshold from validation data only."""
    from worker.evaluation import select_validation

    try:
        result = select_validation(
            export,
            export_sha,
            run,
            run_sha,
            output,
            device,
            real_release_approved,
        )
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        _training_failure("Selection blocked", exc)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("eval-verify")
def eval_verify(
    selection: Path = typer.Option(...),
    selection_sha: str = typer.Option(...),
):
    """Verify a sealed validation selection and re-derive its choices."""
    from worker.evaluation import verify_selection

    try:
        result = verify_selection(selection, selection_sha)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        _training_failure("Verification failed", exc)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("eval-test")
def eval_test(
    export: Path = typer.Option(...),
    export_sha: str = typer.Option(...),
    selection: Path = typer.Option(...),
    selection_sha: str = typer.Option(...),
    output: Path = typer.Option(...),
    device: str = typer.Option(...),
    real_release_approved: bool = typer.Option(False),
):
    """Run the single frozen held-out evaluation from a sealed selection."""
    from worker.evaluation import evaluate_test

    try:
        result = evaluate_test(
            export,
            export_sha,
            selection,
            selection_sha,
            output,
            device,
            real_release_approved,
        )
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        _training_failure("Test evaluation blocked", exc)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("eval-verify-test")
def eval_verify_test(
    evaluation: Path = typer.Option(...),
    evaluation_sha: str = typer.Option(...),
    export: Path = typer.Option(...),
    export_sha: str = typer.Option(...),
):
    """Verify a sealed test evaluation against its selection and the export."""
    from worker.evaluation import verify_test_evaluation

    try:
        result = verify_test_evaluation(evaluation, evaluation_sha, export, export_sha)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        _training_failure("Verification failed", exc)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("eval-performance")
def eval_performance(
    evaluation: Path = typer.Option(...),
    evaluation_sha: str = typer.Option(...),
    export: Path = typer.Option(...),
    export_sha: str = typer.Option(...),
    output: Path = typer.Option(...),
    device: str = typer.Option(...),
):
    """Benchmark the verified frozen checkpoint without changing evaluation settings."""
    from worker.evaluation import measure_performance

    try:
        result = measure_performance(
            evaluation, evaluation_sha, export, export_sha, output, device
        )
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        _training_failure("Performance measurement blocked", exc)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("eval-verify-performance")
def eval_verify_performance(
    performance: Path = typer.Option(...),
    performance_sha: str = typer.Option(...),
    evaluation: Path = typer.Option(...),
    evaluation_sha: str = typer.Option(...),
    export: Path = typer.Option(...),
    export_sha: str = typer.Option(...),
):
    """Re-verify the benchmark and recompute its timing aggregates."""
    from worker.evaluation import verify_performance

    try:
        result = verify_performance(
            performance,
            performance_sha,
            evaluation,
            evaluation_sha,
            export,
            export_sha,
        )
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        _training_failure("Verification failed", exc)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("inference-register-batch")
def inference_register_batch(
    dataset_version_id: str = typer.Option(...),
    split: str = typer.Option(...),
    artifact_root: Path = typer.Option(...),
    asset_id: list[str] = typer.Option([]),
    kind: str = typer.Option("dataset-split"),
    real_release_approved: bool = typer.Option(False),
):
    """Register an exact immutable image membership for inference."""
    from worker.inference import register_batch

    with catalog_session("inference-register-batch") as engine:
        result = register_batch(
            engine,
            artifact_root,
            dataset_version_id,
            split,
            asset_id or None,
            kind,
            real_release_approved,
        )
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("inference-register-model")
def inference_register_model(
    dataset_version_id: str = typer.Option(...),
    selection: Path = typer.Option(...),
    selection_sha: str = typer.Option(...),
    artifact_root: Path = typer.Option(...),
    real_release_approved: bool = typer.Option(False),
):
    """Verify and register a frozen M3.T2 checkpoint."""
    from worker.inference import register_model

    with catalog_session("inference-register-model") as engine:
        result = register_model(
            engine,
            artifact_root,
            dataset_version_id,
            selection,
            selection_sha,
            real_release_approved,
        )
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("inference-run")
def inference_run(
    batch_id: str = typer.Option(...),
    model_id: str = typer.Option(...),
    artifact_root: Path = typer.Option(...),
    device: str = typer.Option(...),
    resume_run: str | None = typer.Option(None),
):
    """Run or resume a deterministic synthetic batch inference operation."""
    from worker.inference import run_inference

    with catalog_session("inference-run") as engine:
        report = run_inference(
            engine,
            artifact_root,
            batch_id,
            model_id,
            device,
            resume_run=resume_run,
        )
    typer.echo(json.dumps(report, indent=2, sort_keys=True))
    if not report["ok"]:
        raise typer.Exit(code=1)


@app.command("inference-status")
def inference_status_command(run_id: str = typer.Option(...)):
    """Print persisted inference operation and item states."""
    from worker.inference import inference_status

    with catalog_session("inference-status") as engine:
        result = inference_status(engine, run_id)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("inference-overlays")
def inference_overlays(
    run_id: str = typer.Option(...),
    artifact_root: Path = typer.Option(...),
    asset_id: list[str] = typer.Option([]),
):
    """Generate overlays solely from persisted boxes."""
    from worker.detection_overlay import generate_overlays

    with catalog_session("inference-overlays") as engine:
        result = generate_overlays(
            engine,
            artifact_root,
            run_id,
            asset_id or None,
        )
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


@app.command("inference-reconcile")
def inference_reconcile(
    run_id: str = typer.Option(...),
    artifact_root: Path = typer.Option(...),
):
    """Compare persisted inference rows, memberships and artifacts."""
    from worker.inference import inference_report_text, reconcile_run

    with catalog_session("inference-reconcile") as engine:
        report = reconcile_run(engine, artifact_root, run_id)
    typer.echo(inference_report_text(report), nl=False)
    if not report["ok"]:
        raise typer.Exit(code=1)
