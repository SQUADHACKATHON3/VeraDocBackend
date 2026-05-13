import os
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings


def ensure_local_storage_dir() -> Path:
    p = Path(settings.local_storage_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_upload_locally(upload: UploadFile) -> tuple[str, int]:
    """
    Returns (storage_key, size_bytes).
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


def read_storage_key(storage_key: str) -> bytes:
    return Path(storage_key).read_bytes()

