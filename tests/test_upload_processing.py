from __future__ import annotations

import io

import pymupdf
from fastapi import HTTPException
from PIL import Image
import pytest
from pytesseract import TesseractNotFoundError

from api import upload_processing
from document_intelligence.document_processor import process_document

_OCR_TEXT = (
    "EMPLOYMENT AGREEMENT between the employer and employee. "
    "This contract sets out salary, duties, and termination provisions."
)


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (160, 90), "white").save(output, format="PNG")
    return output.getvalue()


def test_image_upload_converts_ocr_text_to_page_preserving_docx(monkeypatch):
    monkeypatch.setattr(upload_processing, "_ocr", lambda _image: _OCR_TEXT)

    filename, content, was_ocr = upload_processing.normalize_upload(
        "scan.png", _png_bytes()
    )
    document = process_document(content, filename)

    assert filename == "scan.docx"
    assert was_ocr
    assert document.page_count == 1
    assert _OCR_TEXT in document.full_text


def test_scanned_pdf_ocr_preserves_page_numbers(monkeypatch):
    image = _png_bytes()
    source = pymupdf.open()
    for _ in range(2):
        page = source.new_page()
        page.insert_image(page.rect, stream=image)
    monkeypatch.setattr(upload_processing, "_ocr", lambda _image: _OCR_TEXT)

    filename, content, was_ocr = upload_processing.normalize_upload(
        "scan.pdf", source.tobytes()
    )
    document = process_document(content, filename)

    assert was_ocr
    assert document.page_count == 2
    assert [page.page_number for page in document.pages] == [1, 2]


def test_native_pdf_is_passed_through_without_ocr():
    source = pymupdf.open()
    page = source.new_page()
    page.insert_text((50, 50), _OCR_TEXT)
    content = source.tobytes()

    filename, normalized, was_ocr = upload_processing.normalize_upload(
        "native.pdf", content
    )

    assert filename == "native.pdf"
    assert normalized == content
    assert not was_ocr


def test_image_upload_reports_missing_local_tesseract(monkeypatch):
    def missing_engine():
        raise TesseractNotFoundError()

    monkeypatch.setattr(
        upload_processing.pytesseract, "get_tesseract_version", missing_engine
    )

    with pytest.raises(HTTPException) as error:
        upload_processing.normalize_upload("scan.png", _png_bytes())
    assert error.value.status_code == 503
    assert "Install Tesseract OCR" in error.value.detail
