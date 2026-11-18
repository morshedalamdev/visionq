"""Command-line entry point for VisionQ."""

import json
import typer
import platform

from pathlib import Path
from importlib.metadata import version

from worker.inventory import publish_inventory

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
