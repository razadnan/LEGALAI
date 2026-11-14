from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional

import pymupdf
import pytesseract
from docx import Document
from fastapi import HTTPException
from PIL import Image, ImageSequence, UnidentifiedImageError
from pytesseract import TesseractError, TesseractNotFoundError

from config.settings import get_settings


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
_SUPPORTED_EXTENSIONS = {".pdf", ".docx", *_IMAGE_EXTENSIONS}
_MIN_NATIVE_PAGE_CHARS = 40


def _ensure_tesseract() -> None:
    command = os.getenv("TESSERACT_CMD")
    if command:
        pytesseract.pytesseract.tesseract_cmd = command
    try:
        pytesseract.get_tesseract_version()
    except (TesseractNotFoundError, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Local OCR is unavailable. Install Tesseract OCR and add it to "
                "PATH, or set TESSERACT_CMD to its executable."
            ),
        ) from exc


def _ocr(image: Image.Image) -> str:
    _ensure_tesseract()
    try:
        return pytesseract.image_to_string(
            image,
            lang=os.getenv("TESSERACT_LANG", "eng"),
            timeout=90,
        ).strip()
    except (TesseractError, RuntimeError) as exc:
        raise HTTPException(
            status_code=422,
            detail="OCR could not read this page. Try a clearer image or PDF.",
        ) from exc


def _docx_from_pages(pages: list[str]) -> bytes:
    document = Document()
    for index, text in enumerate(pages):
        if index:
            document.add_page_break()
        for line in text.splitlines() or [""]:
            document.add_paragraph(line)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _pdf_ocr_pages(data: bytes) -> Optional[list[str]]:
    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError):
        return None
    with pdf:
        if pdf.needs_pass:
            return None
        pages = []
        needs_ocr = False
        for page in pdf:
            text = page.get_text("text").strip()
            if len(text) < _MIN_NATIVE_PAGE_CHARS:
                needs_ocr = True
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False)
                with Image.open(io.BytesIO(pixmap.tobytes("png"))) as image:
                    text = _ocr(image.convert("RGB"))
            pages.append(text)
    return pages if needs_ocr else None


def _image_ocr_pages(data: bytes) -> list[str]:
    try:
        image = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            status_code=400,
            detail="The image is invalid, damaged, or too large to process.",
        ) from exc
    with image:
        pages = []
        for index in range(getattr(image, "n_frames", 1)):
            try:
                image.seek(index)
                frame = image.convert("RGB")
            except (OSError, Image.DecompressionBombError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail="The image is invalid, damaged, or too large to process.",
                ) from exc
            pages.append(_ocr(frame))
    return pages


def normalize_upload(filename: str, data: bytes) -> tuple[str, bytes, bool]:
    """Convert scanned PDFs and raster images into page-preserving DOCX text."""
    extension = Path(filename).suffix.lower()
    if extension not in _SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Upload a PDF, DOCX, JPG/JPEG, PNG, or TIFF file.",
        )
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"The file is larger than {get_settings().max_upload_mb} MB.",
        )
    if extension == ".pdf":
        pages = _pdf_ocr_pages(data)
    elif extension in _IMAGE_EXTENSIONS:
        pages = _image_ocr_pages(data)
    else:
        return filename, data, False

    if pages is None:
        return filename, data, False
    if not any(page.strip() for page in pages):
        raise HTTPException(
            status_code=422,
            detail="OCR found no readable text. Try a clearer scan.",
        )
    converted_name = f"{Path(filename).stem}.docx"
    return converted_name, _docx_from_pages(pages), True
