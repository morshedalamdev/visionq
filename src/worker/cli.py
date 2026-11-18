"""Command-line entry point for VisionQ."""

import json
import platform
from importlib.metadata import version
from pathlib import Path

import typer

from worker.inventory import publish_inventory
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
