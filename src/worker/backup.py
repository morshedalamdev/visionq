"""Create or restore a verified, fixture-sized backup."""

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from uuid import UUID

from worker.fixture import SHA, URI, digest, publish

IMAGE_MEMBER = f"runtime/{URI}"
MEMBERS = ("db.dump", IMAGE_MEMBER, "uv.lock", "compose.yaml", ".env.example")
MANIFEST = "manifest.json"
COMPLETE = "COMPLETE"


def validate_member(name: str, data: bytes) -> None:
    if not data:
        raise ValueError(f"empty backup member: {name}")
    if name == IMAGE_MEMBER and digest(data) != SHA:
        raise ValueError("source fixture checksum mismatch")
    if name == "db.dump" and not data.startswith(b"PGDMP"):
        raise ValueError("expected a PostgreSQL custom-format dump")


class Directory:
    def __init__(self, root: Path):
        self.root = root

    def put(self, key: str, data: bytes) -> None:
        publish(self.root / key, data)

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


class Azure:
    def __init__(self):
        from azure.identity import AzureCliCredential, ManagedIdentityCredential
        from azure.storage.blob import ContainerClient

        account = os.environ["VISIONQ_STORAGE_ACCOUNT"]
        if not re.fullmatch(r"[a-z0-9]{3,24}", account):
            raise ValueError("expected an Azure public-cloud storage account name")
        mode = os.environ.get("VISIONQ_AZURE_AUTH", "cli")
        if mode == "cli":
            credential = AzureCliCredential()
        elif mode == "managed":
            credential = ManagedIdentityCredential()
        else:
            raise ValueError("VISIONQ_AZURE_AUTH must be cli or managed")
        self.container = ContainerClient(
            f"https://{account}.blob.core.windows.net",
            os.environ["VISIONQ_STORAGE_CONTAINER"],
            credential=credential,
        )

    def put(self, key: str, data: bytes) -> None:
        self.container.upload_blob(key, data, overwrite=False)

    def get(self, key: str) -> bytes:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self.container.download_blob(key).readall()
        except ResourceNotFoundError as exc:
            if exc.error_code == "BlobNotFound":
                raise FileNotFoundError(key) from exc
            raise


def prefix(backup_id: str) -> str:
    return f"m1t2/{UUID(backup_id)}/"


def backup(store, backup_id: str, source: Path) -> str:
    base = prefix(backup_id)
    hashes = {}
    for name in MEMBERS:
        data = (source / name).read_bytes()
        validate_member(name, data)
        store.put(base + name, data)
        hashes[name] = digest(data)
        if digest(store.get(base + name)) != hashes[name]:
            raise ValueError(f"uploaded checksum mismatch: {name}")

    manifest = json.dumps(hashes, sort_keys=True).encode()
    store.put(base + MANIFEST, manifest)
    if store.get(base + MANIFEST) != manifest:
        raise ValueError("uploaded manifest differs")
    manifest_sha = digest(manifest)
    store.put(base + COMPLETE, manifest_sha.encode("ascii"))
    return manifest_sha


def restore(store, backup_id: str, destination: Path) -> str:
    base = prefix(backup_id)
    try:
        marker = store.get(base + COMPLETE)
    except FileNotFoundError:
        raise ValueError("incomplete backup: COMPLETE missing") from None

    manifest = store.get(base + MANIFEST)
    manifest_sha = digest(manifest)
    if marker != manifest_sha.encode("ascii"):
        raise ValueError("manifest checksum mismatch")
    hashes = json.loads(manifest)
    if not isinstance(hashes, dict) or set(hashes) != set(MEMBERS):
        raise ValueError("unexpected backup inventory")
    if destination.exists():
        raise FileExistsError(destination)

    with tempfile.TemporaryDirectory(dir=destination.parent) as tmpdir:
        staged = Path(tmpdir) / "bundle"
        for name in MEMBERS:
            data = store.get(base + name)
            if digest(data) != hashes[name]:
                raise ValueError(f"downloaded checksum mismatch: {name}")
            validate_member(name, data)
            publish(staged / name, data)
        publish(staged / MANIFEST, manifest)
        publish(staged / COMPLETE, marker)
        # Reserve the fresh name exclusively, including against another restore.
        destination.mkdir()
        try:
            staged.replace(destination)
        except OSError:
            destination.rmdir()
            raise
    return manifest_sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("backup_id", type=str)
    parser.add_argument("path", type=Path)
    parser.add_argument("--local-store", type=Path)
    args = parser.parse_args()
    store = Directory(args.local_store) if args.local_store else Azure()
    operation = backup if args.action == "backup" else restore
    try:
        checksum = operation(store, args.backup_id, args.path)
    except (ValueError, FileExistsError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"{args.action} {args.backup_id} manifest_sha256={checksum}")


if __name__ == "__main__":
    main()
