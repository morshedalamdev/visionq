from unittest.mock import Mock
from uuid import uuid4

import pytest

from worker.backup import (
    COMPLETE,
    IMAGE_MEMBER,
    MEMBERS,
    Azure,
    Directory,
    backup,
    restore,
)
from worker.fixture import PIXELS, SHA, URI, store_image


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    for name in MEMBERS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"public test input")
    (root / IMAGE_MEMBER).write_bytes(PIXELS)
    (root / "db.dump").write_bytes(b"PGDMP-unit-fixture")
    return root


def test_immutable_fixture(tmp_path):
    assert len(PIXELS) == 15
    assert SHA == "72da4da49413259d1c478e37535cf866b981511b8142d25ce5482f4104e45a6f"
    store_image(tmp_path)
    store_image(tmp_path)
    path = tmp_path / URI
    assert path.read_bytes() == PIXELS
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="existing artifact differs"):
        store_image(tmp_path)
    assert path.read_bytes() == b"corrupt"


def test_completed_backup_is_create_only(tmp_path, source):
    store = Directory(tmp_path / "store")
    key = str(uuid4())
    checksum = backup(store, key, source)
    with pytest.raises(FileExistsError):
        backup(store, key, source)
    target = tmp_path / "restored"
    assert restore(store, key, target) == checksum
    for name in MEMBERS:
        assert (target / name).read_bytes() == (source / name).read_bytes()
    with pytest.raises(FileExistsError):
        restore(store, key, target)


def test_interrupted_writer(tmp_path, source):
    class Interrupted(Directory):
        def put(self, key, data):
            if key.endswith(IMAGE_MEMBER):
                raise OSError("simulated interruption")
            super().put(key, data)

    store = Interrupted(tmp_path / "store")
    key = str(uuid4())
    with pytest.raises(OSError, match="simulated interruption"):
        backup(store, key, source)
    assert store.get(f"m1t2/{key}/db.dump").startswith(b"PGDMP")
    with pytest.raises(FileNotFoundError):
        store.get(f"m1t2/{key}/{COMPLETE}")
    with pytest.raises(ValueError, match="COMPLETE missing"):
        restore(store, key, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("member", [IMAGE_MEMBER, "manifest.json"])
def test_corrupt_backup_is_rejected(tmp_path, source, member):
    store = Directory(tmp_path / "store")
    key = str(uuid4())
    backup(store, key, source)
    (store.root / "m1t2" / key / member).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        restore(store, key, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_azure_adapter_writes_create_only_and_reads_same_key():
    adapter = Azure.__new__(Azure)
    adapter.container = Mock()
    key = "m1t2/test/db.dump"
    data = b"PGDMP-test"
    adapter.container.download_blob.return_value.readall.return_value = data

    adapter.put(key, data)
    assert adapter.get(key) == data

    adapter.container.upload_blob.assert_called_once_with(key, data, overwrite=False)
    adapter.container.download_blob.assert_called_once_with(key)
