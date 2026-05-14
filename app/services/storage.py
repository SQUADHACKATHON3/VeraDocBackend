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


def _encode_cloudinary_ref(public_id: str, resource_type: str, *, version: int | None = None, asset_format: str | None = None) -> str:
    d: dict[str, str] = {"p": public_id, "r": resource_type}
    if version is not None:
        d["v"] = str(int(version))
    if asset_format:
        d["f"] = asset_format
    payload = json.dumps(d, separators=(",", ":"))
    return _CL_PREFIX + base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _decode_cloudinary_ref(storage_key: str) -> dict[str, str] | None:
    if not storage_key.startswith(_CL_PREFIX):
        return None
    raw_b64 = storage_key[len(_CL_PREFIX) :]
    pad = "=" * (-len(raw_b64) % 4)
    data = base64.urlsafe_b64decode(raw_b64 + pad)
    d = json.loads(data.decode())
    if "p" not in d or "r" not in d:
        return None
    return {str(k): str(v) for k, v in d.items()}


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
    version = result.get("version")
    ver_int = int(version) if version is not None else None
    fmt = result.get("format")
    fmt_s = str(fmt) if fmt else None
    return _encode_cloudinary_ref(public_id, resource_type, version=ver_int, asset_format=fmt_s), size


def save_upload(upload: UploadFile) -> tuple[str, int]:
    driver = (settings.file_storage_driver or "local").lower()
    if driver == "cloudinary":
        return save_upload_cloudinary(upload)
    return save_upload_locally(upload)


def read_storage_key(storage_key: str) -> bytes:
    meta = _decode_cloudinary_ref(storage_key)
    if meta is not None:
        public_id = meta["p"]
        resource_type = meta["r"]
        _configure_cloudinary()
        from cloudinary.utils import cloudinary_url

        kwargs: dict = {
            "resource_type": resource_type,
            "secure": True,
            # Accounts with strict transformations / private delivery return 401 on unsigned URLs.
            "sign_url": True,
        }
        if meta.get("v"):
            kwargs["version"] = int(meta["v"])
        if meta.get("f"):
            kwargs["format"] = meta["f"]

        url, _ = cloudinary_url(public_id, **kwargs)
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.content

    return Path(storage_key).read_bytes()
