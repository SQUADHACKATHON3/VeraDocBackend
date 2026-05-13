import base64
import json
import os
import uuid
from pathlib import Path

import httpx
from fastapi import UploadFile

from app.core.config import settings

_CL_PREFIX = "cl:v1:"


def _configure_cloudinary() -> None:
    import cloudinary

    if not settings.cloudinary_url:
        raise ValueError("CLOUDINARY_URL is required when FILE_STORAGE_DRIVER=cloudinary")
    cloudinary.config(cloudinary_url=settings.cloudinary_url)


def _encode_cloudinary_ref(public_id: str, resource_type: str) -> str:
    payload = json.dumps({"p": public_id, "r": resource_type}, separators=(",", ":"))
    return _CL_PREFIX + base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cloudinary_ref(storage_key: str) -> tuple[str, str] | None:
    if not storage_key.startswith(_CL_PREFIX):
        return None
    raw_b64 = storage_key[len(_CL_PREFIX) :]
    pad = "=" * (-len(raw_b64) % 4)
    data = base64.urlsafe_b64decode(raw_b64 + pad)
    d = json.loads(data.decode())
    return d["p"], d["r"]


def ensure_local_storage_dir() -> Path:
    p = Path(settings.local_storage_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_upload_locally(upload: UploadFile) -> tuple[str, int]:
    """
    Returns (storage_key, size_bytes). storage_key is an absolute filesystem path.
    """
    base = ensure_local_storage_dir()
    ext = os.path.splitext(upload.filename or "")[1].lower()
    key = f"{uuid.uuid4()}{ext}"
    dest = base / key

    size = 0
    with dest.open("wb") as f:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            f.write(chunk)

    return str(dest), size


def save_upload_cloudinary(upload: UploadFile) -> tuple[str, int]:
    import cloudinary.uploader

    _configure_cloudinary()
    upload.file.seek(0)
    result = cloudinary.uploader.upload(
        upload.file,
        folder="veradoc",
        resource_type="auto",
    )
    public_id = result["public_id"]
    resource_type = result["resource_type"]
    size = int(result.get("bytes") or 0)
    return _encode_cloudinary_ref(public_id, resource_type), size


def save_upload(upload: UploadFile) -> tuple[str, int]:
    driver = (settings.file_storage_driver or "local").lower()
    if driver == "cloudinary":
        return save_upload_cloudinary(upload)
    return save_upload_locally(upload)


def read_storage_key(storage_key: str) -> bytes:
    ref = _decode_cloudinary_ref(storage_key)
    if ref is not None:
        public_id, resource_type = ref
        _configure_cloudinary()
        from cloudinary.utils import cloudinary_url

        url, _ = cloudinary_url(public_id, resource_type=resource_type, secure=True)
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.content

    return Path(storage_key).read_bytes()
