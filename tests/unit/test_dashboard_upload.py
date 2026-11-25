from __future__ import annotations

import io

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from api import dashboard
from api.main import create_app


def test_upload_checks_pixel_limit_before_decoding(monkeypatch, tmp_path):
    stream = io.BytesIO()
    Image.new("RGB", (3, 3)).save(stream, "PNG")
    monkeypatch.setattr(dashboard, "PIXEL_LIMIT", 8)
    monkeypatch.setattr(
        "PIL.PngImagePlugin.PngImageFile.load",
        lambda self: pytest.fail("decoded before limit check"),
    )
    app = create_app(
        engine=object(), analytics_api_token="secret", artifact_root=tmp_path
    )
    with TestClient(app) as client:
        response = client.post(
            "/app/uploads",
            headers={"Authorization": "Bearer secret"},
            files={"file": ("image.png", stream.getvalue(), "image/png")},
        )
    assert response.status_code == 422
    assert "megapixel" in response.json()["detail"]


def test_upload_storage_rejects_symlinked_parent(tmp_path):
    root = tmp_path / "storage"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (root / "uploads").symlink_to(external, target_is_directory=True)
    with pytest.raises(HTTPException, match="symlink"):
        dashboard.upload_path(root, "a" * 64)
    assert list(external.iterdir()) == []


@pytest.mark.parametrize("declare_length", [False, True])
def test_upload_limits_multipart_before_form_parsing(
    tmp_path, monkeypatch, declare_length
):
    from api import main

    monkeypatch.setattr(main, "UPLOAD_BODY_LIMIT", 64)
    app = create_app(
        engine=object(), analytics_api_token="secret", artifact_root=tmp_path
    )
    headers = {"Content-Type": "multipart/form-data; boundary=test"}
    content = (
        b'--test\r\nContent-Disposition: form-data; name="file"; filename="x"\r\n\r\n'
        + b"a" * 128
    )
    if declare_length:
        headers["Content-Length"] = str(len(content))
    with TestClient(app) as client:
        response = client.post(
            "/app/uploads", content=iter([content[:75], content[75:]]), headers=headers
        )
    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []
