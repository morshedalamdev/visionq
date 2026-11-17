"""Write or verify one small synthetic inspection."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from worker.db import database

PIXELS = b"P5\n2 2\n255\n" + bytes([0, 64, 128, 255])
INSPECTION = UUID("6a8eddee-0cdb-42ac-b9ea-bcfaac112001")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


SHA = digest(PIXELS)
URI = f"objects/{SHA}.pgm"


def publish(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent) as staged:
        staged.write(data)
        staged.flush()
        os.fsync(staged.fileno())
        if digest(Path(staged.name).read_bytes()) != digest(data):
            raise ValueError("staged bytes failed verification")
        os.link(staged.name, path)


def store_image(root: Path) -> None:
    path = root / URI
    try:
        publish(path, PIXELS)
    except FileExistsError:
        if path.read_bytes() != PIXELS:
            raise ValueError("existing artifact differs from fixture") from None


def inspect(root: Path, *, seed: bool = False) -> dict:
    expected = {
        "inspection_id": str(INSPECTION),
        "version": 1,
        "artifact_uri": URI,
        "byte_count": len(PIXELS),
        "sha256": SHA,
    }
    with database().begin() as connection:
        if seed:
            store_image(root)
            connection.execute(
                text("""
                INSERT INTO inspection_fixture
                (inspection_id, version, artifact_uri, byte_count, sha256)
                VALUES (:inspection_id, :version, :artifact_uri, :byte_count, :sha256)
                ON CONFLICT (inspection_id, version) DO NOTHING
                """),
                expected,
            )
        row = (
            connection.execute(
                text("""
            SELECT inspection_id::text AS inspection_id, version, artifact_uri, byte_count, sha256
            FROM inspection_fixture    
        """)
            )
            .mappings()
            .one()
        )
        if dict(row) != expected:
            raise ValueError("fixture row differs from expected identity or version")
        data = (root / row["artifact_uri"]).read_bytes()
        if len(data) != row["byte_count"] or digest(data) != row["sha256"]:
            raise ValueError("stored artifact differs from database record")
        return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "verify"))
    args = parser.parse_args()
    result = inspect(Path(os.environ["ARTIFACT_ROOT"]), seed=args.action == "seed")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
