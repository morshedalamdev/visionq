"""Command-line entry point for VisionQ."""

import json
import platform
from importlib.metadata import version

import typer

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
