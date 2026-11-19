"""Command-line entry point for VisionQ."""

import json
import platform
from importlib.metadata import version
from pathlib import Path

import typer

from worker.backup import Directory
from worker.catalog import ingest, operation_status
from worker.catalog_backup import (
    backup_catalog,
    restore_catalog,
    verify_catalog_backup,
)
from worker.catalog_input import load_package
from worker.catalog_store import CatalogBusy, CatalogConflict
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
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Run a Vision command."""


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


def catalog_store(local_store: Path | None):
    if local_store is None:
        raise ValueError(
            "M2.T4 requires --local-store; remote catalog backup is not authorized"
        )
    return Directory(local_store)


def catalog_engine(require_loopback: bool = False):
    engine = database()
    if require_loopback:
        if engine.url.host not in ("127.0.0.1", "localhost"):
            engine.dispose()
            raise ValueError(
                "local catalog restore requires an explicit loopback database URL"
            )
    return engine


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
):
    """Create a provisional grouped split plan without training inputs."""
    from worker.preparation import prepare

    try:
        plan = prepare(root, packet, official)
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
    engine = catalog_engine()
    try:
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
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        CatalogConflict,
        CatalogBusy,
    ) as exc:
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
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
    engine = catalog_engine()
    try:
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
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        CatalogConflict,
        CatalogBusy,
    ) as exc:
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    typer.echo(json.dumps(report, indent=2, sort_keys=True))


@app.command("catalog-status")
def catalog_status(run_id: str = typer.Option(...)):
    """Print persisted ingestion operation and item states."""
    engine = catalog_engine()
    try:
        status = operation_status(engine, run_id)
    except (OSError, ValueError, CatalogConflict) as exc:
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
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
    engine = catalog_engine()
    try:
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
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        CatalogConflict,
    ) as exc:
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
    typer.echo(report_text(report), nl=False)


@app.command("catalog-backup")
def catalog_backup(
    backup_id: str = typer.Option(...),
    artifact_root: Path = typer.Option(...),
    local_store: Path | None = typer.Option(None),
    source: Path = typer.Option(...),
    baseline: Path = typer.Option(...),
    packet: Path = typer.Option(...),
    release: Path = typer.Option(...),
    release_sha: str = typer.Option(...),
    dataset_name: str = typer.Option(...),
    version: int = typer.Option(...),
):
    """Back up a complete reconciled synthetic catalog snapshot."""
    engine = catalog_engine()
    try:
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
            catalog_store(local_store),
            backup_id,
            package,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        CatalogConflict,
        CatalogBusy,
    ) as exc:
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
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
    local_store: Path | None = typer.Option(None),
):
    """Verify the complete catalog backup and completion marker."""
    try:
        manifest_sha = verify_catalog_backup(
            catalog_store(local_store),
            backup_id,
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        typer.echo(f"catalog-verify failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
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
    local_store: Path | None = typer.Option(None),
):
    """Restore a synthetic catalog to fresh local artifacts and PostgreSQL."""
    engine = catalog_engine(require_loopback=True)
    try:
        manifest_sha = restore_catalog(
            engine,
            catalog_store(local_store),
            backup_id,
            destination,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        CatalogConflict,
        CatalogBusy,
    ) as exc:
        raise typer.Exit(code=1) from exc
    finally:
        engine.dispose()
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
