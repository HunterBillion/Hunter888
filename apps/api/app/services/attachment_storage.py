"""Storage helpers for CRM/client attachments."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
ATTACHMENTS_DIR = Path(__file__).resolve().parents[2] / "uploads" / "attachments"
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredAttachment:
    filename: str
    sha256: str
    file_size: int
    storage_path: str
    public_url: str


def safe_filename(filename: str | None) -> str:
    raw = (filename or "attachment").strip().replace("\\", "/").split("/")[-1]
    suffix = Path(raw).suffix.lower()
    stem = raw[: -len(suffix)] if suffix else raw
    cleaned_stem = _SAFE_FILENAME_RE.sub("_", stem)[:160].strip("._")
    cleaned_suffix = _SAFE_FILENAME_RE.sub("", suffix)[:20]
    if not cleaned_stem:
        cleaned_stem = "attachment"
    return f"{cleaned_stem}{cleaned_suffix}" or "attachment"


def attachment_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def infer_document_type(filename: str, content_type: str | None) -> str:
    lower = filename.lower()
    mime = (content_type or "").lower()
    if "pdf" in mime or lower.endswith(".pdf"):
        return "pdf"
    if mime.startswith("image/") or lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic", ".tiff")):
        return "image"
    if lower.endswith((".doc", ".docx", ".rtf", ".odt")):
        return "document"
    if lower.endswith((".xls", ".xlsx", ".csv")):
        return "spreadsheet"
    return "unknown"


def ocr_status_for(document_type: str) -> str:
    return "pending" if document_type in {"pdf", "image"} else "not_required"


def store_attachment_bytes(*, client_id: str, filename: str | None, data: bytes) -> StoredAttachment:
    cleaned = safe_filename(filename)
    digest = attachment_sha256(data)
    client_dir = ATTACHMENTS_DIR / str(client_id)
    client_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{digest[:16]}_{cleaned}"
    path = client_dir / stored_name
    if not path.exists():
        path.write_bytes(data)

    relative = f"{client_id}/{stored_name}"
    return StoredAttachment(
        filename=cleaned,
        sha256=digest,
        file_size=len(data),
        storage_path=str(path),
        public_url=f"/api/uploads/attachments/{relative}",
    )
