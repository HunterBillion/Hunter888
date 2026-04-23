from app.services.attachment_storage import (
    attachment_sha256,
    infer_document_type,
    ocr_status_for,
    safe_filename,
)


def test_safe_filename_strips_path_and_unsafe_chars():
    assert safe_filename("../passport scan.pdf") == "passport_scan.pdf"
    assert safe_filename("folder/My File (1).png") == "My_File_1.png"
    assert safe_filename("../паспорт скан.pdf") == "attachment.pdf"
    assert safe_filename("") == "attachment"


def test_document_type_and_ocr_status():
    assert infer_document_type("scan.pdf", "application/pdf") == "pdf"
    assert infer_document_type("photo.jpg", "image/jpeg") == "image"
    assert infer_document_type("creditors.xlsx", None) == "spreadsheet"
    assert ocr_status_for("pdf") == "pending"
    assert ocr_status_for("spreadsheet") == "not_required"


def test_attachment_sha256_is_stable():
    assert attachment_sha256(b"client-doc") == attachment_sha256(b"client-doc")
    assert attachment_sha256(b"client-doc") != attachment_sha256(b"other-doc")
