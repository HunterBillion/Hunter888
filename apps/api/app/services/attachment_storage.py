"""Storage helpers for CRM/client attachments."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
# TZ-5 §5 — ROP/admin uploads of training materials run through a separate
# size budget (50 MB) because .pptx/.pdf course material is bulkier than
# typical CRM scans. The training_material code path explicitly opts in to
# this limit; the regular client-attachment limit stays at 25 MB.
MAX_TRAINING_MATERIAL_BYTES = 50 * 1024 * 1024
ATTACHMENTS_DIR = Path(__file__).resolve().parents[2] / "uploads" / "attachments"
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

# Whitelist of accepted upload extensions. Anything outside this set is
# rejected — content_type from the browser is spoofable, but the on-disk
# extension drives how StaticFiles serves the file later, so blocking
# .html/.svg/.exe here closes the XSS / drive-by surface even with
# nginx X-Content-Type-Options: nosniff.
#
# TZ-5 §5 added .md and .pptx to the set so ROP can upload memos written
# in markdown and product pitch decks. Both are handled by the scenario
# extractor (markdown trivially, pptx via python-pptx in scenario_extractor).
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf",
    ".jpg", ".jpeg", ".png", ".webp", ".heic", ".tiff",
    ".doc", ".docx", ".rtf", ".odt",
    ".xls", ".xlsx", ".csv",
    ".txt", ".md",
    ".pptx",
})


# TZ-5 §3.1 — formats accepted by the scenario_extractor input funnel.
# Strict subset of ALLOWED_EXTENSIONS: image/spreadsheet uploads make no
# sense as training material, so the import endpoint rejects them with a
# clearer error than "unsupported attachment".
TRAINING_MATERIAL_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".pptx",
})


class UnsupportedAttachmentType(ValueError):
    """Raised when an upload uses an extension outside ALLOWED_EXTENSIONS."""


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


def infer_document_type(
    filename: str,
    content_type: str | None,
    *,
    is_training_material: bool = False,
) -> str:
    """Map (filename, content_type) to a canonical document_type token.

    TZ-5 §3 introduces ``training_material`` as a first-class document_type
    that gates the scenario_extractor pipeline branch. The caller signals
    intent via ``is_training_material`` -- we don't infer this from the
    extension because the same .pdf may be a client-uploaded passport scan
    OR a ROP-uploaded memo, and the two go through completely different
    pipelines. The intent comes from the API endpoint, not the bytes.
    """
    if is_training_material:
        return "training_material"
    lower = filename.lower()
    mime = (content_type or "").lower()
    if "pdf" in mime or lower.endswith(".pdf"):
        return "pdf"
    if mime.startswith("image/") or lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic", ".tiff")):
        return "image"
    if lower.endswith((".doc", ".docx", ".rtf", ".odt", ".md", ".pptx")):
        return "document"
    if lower.endswith((".xls", ".xlsx", ".csv")):
        return "spreadsheet"
    return "unknown"


def ocr_status_for(document_type: str) -> str:
    """B1 — return spec §7.1.1-canonical ``ocr_pending`` instead of the
    legacy ``pending`` (which was ambiguous with ``classification_pending``
    when readers looked at both columns). Existing rows are migrated by
    alembic ``20260427_004``."""
    return "ocr_pending" if document_type in {"pdf", "image"} else "not_required"


def reject_disallowed_extension(
    filename: str | None,
    *,
    allowed: frozenset[str] = ALLOWED_EXTENSIONS,
) -> str:
    """Validate the upload's extension against ``allowed`` and return the
    cleaned filename. Raises UnsupportedAttachmentType on mismatch so the
    API layer can map it to a 415 — ``content_type`` from the browser is
    intentionally not used here (spoofable).

    TZ-5 §5 — the ``allowed`` kwarg lets the training-material endpoint
    pass ``TRAINING_MATERIAL_EXTENSIONS`` so the error message points at
    the narrower set instead of the full client-upload set.
    """
    cleaned = safe_filename(filename)
    suffix = Path(cleaned).suffix.lower()
    if not suffix or suffix not in allowed:
        raise UnsupportedAttachmentType(
            f"Unsupported attachment extension: {suffix or '<none>'}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
    return cleaned


def store_attachment_bytes(
    *,
    client_id: str,
    filename: str | None,
    data: bytes,
    allowed_extensions: frozenset[str] = ALLOWED_EXTENSIONS,
) -> StoredAttachment:
    cleaned = reject_disallowed_extension(filename, allowed=allowed_extensions)
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
