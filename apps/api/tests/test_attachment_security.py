"""Upload extension whitelist (SEC-1).

content_type from the browser is spoofable, so the whitelist is keyed on
the on-disk filename suffix. Anything outside ALLOWED_EXTENSIONS must
raise UnsupportedAttachmentType so the API layer can map it to 415 —
otherwise nginx serves the saved file with the wrong Content-Type and
the X-Content-Type-Options: nosniff guard becomes the only defence.
"""

from __future__ import annotations

import pytest

from app.services.attachment_storage import (
    ALLOWED_EXTENSIONS,
    UnsupportedAttachmentType,
    reject_disallowed_extension,
)


@pytest.mark.parametrize(
    "name",
    [
        "report.pdf",
        "passport.JPG",
        "scan.png",
        "contract.docx",
        "ledger.xlsx",
        "notes.txt",
    ],
)
def test_whitelisted_extensions_accepted(name):
    cleaned = reject_disallowed_extension(name)
    # Cleaned filename keeps the original suffix (lowercased by safe_filename).
    assert cleaned.lower().endswith(name.split(".")[-1].lower())


@pytest.mark.parametrize(
    "name",
    [
        "exploit.html",
        "exploit.svg",
        "trojan.exe",
        "trojan.sh",
        "page.htm",
        "vector.js",
        "config.yaml",
        "binary.dll",
    ],
)
def test_blocked_extensions_rejected(name):
    with pytest.raises(UnsupportedAttachmentType):
        reject_disallowed_extension(name)


def test_no_extension_rejected():
    with pytest.raises(UnsupportedAttachmentType):
        reject_disallowed_extension("README")


def test_double_extension_keeps_only_last_suffix():
    """Path traversal attempt: foo.pdf.html — the actual on-disk extension
    is .html, so it must be rejected even though .pdf appears in the name."""
    with pytest.raises(UnsupportedAttachmentType):
        reject_disallowed_extension("foo.pdf.html")


def test_allow_set_is_documented_lowercase():
    """Sanity: the whitelist is canonical lowercase so the suffix check
    (which lowercases) never silently misses a match."""
    for ext in ALLOWED_EXTENSIONS:
        assert ext == ext.lower()
        assert ext.startswith(".")
