import base64
import json
import os
import uuid
from pathlib import Path

import httpx
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile


_CL_PREFIX = "cl:v1:"


def _configure_cloudinary() -> None:
    import cloudinary

    if not settings.CLOUDINARY_URL:
        raise ValueError("CLOUDINARY_URL is required when FILE_STORAGE_DRIVER=cloudinary")
    cloudinary.config(cloudinary_url=settings.CLOUDINARY_URL)


def _encode_cloudinary_ref(
    public_id: str, resource_type: str, *, version: int | None = None, asset_format: str | None = None
) -> str:
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
    p = Path(settings.LOCAL_STORAGE_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_upload_locally(upload: UploadedFile) -> tuple[str, int]:
    base = ensure_local_storage_dir()
    ext = os.path.splitext(upload.name or "")[1].lower()
    key = f"{uuid.uuid4()}{ext}"
    dest = base / key

    size = 0
    with dest.open("wb") as f:
        for chunk in upload.chunks():
            size += len(chunk)
            f.write(chunk)

    return str(dest), size


def save_upload_cloudinary(upload: UploadedFile) -> tuple[str, int]:
    import cloudinary.uploader

    _configure_cloudinary()
    upload.seek(0)
    ct = (upload.content_type or "").split(";")[0].strip().lower()
    name = (upload.name or "").lower()
    is_pdf = ct == "application/pdf" or name.endswith(".pdf")
    resource_type = "raw" if is_pdf else "auto"
    result = cloudinary.uploader.upload(upload, folder="veradoc", resource_type=resource_type)
    public_id = result["public_id"]
    resource_type = result["resource_type"]
    size = int(result.get("bytes") or 0)
    version = result.get("version")
    ver_int = int(version) if version is not None else None
    fmt = result.get("format")
    fmt_s = str(fmt) if fmt else None
    return _encode_cloudinary_ref(public_id, resource_type, version=ver_int, asset_format=fmt_s), size


def save_upload(upload: UploadedFile) -> tuple[str, int]:
    driver = (settings.FILE_STORAGE_DRIVER or "local").lower()
    if driver == "cloudinary":
        return save_upload_cloudinary(upload)
    return save_upload_locally(upload)


def _build_cloudinary_delivery_url(public_id: str, meta: dict[str, str]) -> str:
    from cloudinary import config as cld_config

    cfg = cld_config()
    cloud_name = cfg.cloud_name
    resource_type = meta.get("r", "image")
    version = meta.get("v")
    fmt = meta.get("f")

    url = f"https://res.cloudinary.com/{cloud_name}/{resource_type}/upload"
    if version:
        url += f"/v{version}"
    url += f"/{public_id}"
    if fmt:
        url += f".{fmt}"
    return url


def _cloudinary_fetch_attempt_metas(meta: dict[str, str]) -> list[dict[str, str]]:
    attempts: list[dict[str, str]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()

    def add(m: dict[str, str]) -> None:
        key = tuple(sorted(m.items()))
        if key not in seen:
            seen.add(key)
            attempts.append(dict(m))

    add(meta)
    if meta.get("f"):
        add({k: v for k, v in meta.items() if k != "f"})
    if meta.get("r") == "image" and meta.get("f", "").lower() == "pdf":
        m = dict(meta)
        m["r"] = "raw"
        add(m)
        add({k: v for k, v in m.items() if k != "f"})
    return attempts


def read_storage_key(storage_key: str) -> bytes:
    meta = _decode_cloudinary_ref(storage_key)
    if meta is not None:
        public_id = meta["p"]
        _configure_cloudinary()

        last_status: int | None = None
        last_body: str = ""
        last_cld_err: str = ""
        for attempt in _cloudinary_fetch_attempt_metas(meta):
            url = _build_cloudinary_delivery_url(public_id, attempt)
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                r = client.get(url, headers={"User-Agent": "VeraDocBackend/1.0"})
            if r.status_code == 200:
                return r.content
            last_status = r.status_code
            last_body = (r.text or "")[:500]
            last_cld_err = (r.headers.get("x-cld-error") or r.headers.get("X-Cld-Error") or "")[:500]

        detail = f"HTTP {last_status} fetching from Cloudinary."
        if last_cld_err:
            detail += f" x-cld-error: {last_cld_err}"
        elif last_body:
            detail += f" Body: {last_body}"
        raise RuntimeError(detail)

    return Path(storage_key).read_bytes()
