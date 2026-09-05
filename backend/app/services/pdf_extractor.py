"""Bounded, in-memory PDF text extraction for question generation."""

from io import BytesIO

from fastapi import UploadFile
from pypdf import PdfReader

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 30
MAX_EXTRACTED_CHARACTERS = 20_000
MIN_EXTRACTED_CHARACTERS = 80


class PdfExtractionError(ValueError):
    pass


async def extract_pdf_text(file: UploadFile) -> str:
    if file.content_type not in {"application/pdf", "application/x-pdf"} and not (file.filename or "").lower().endswith(".pdf"):
        raise PdfExtractionError("Please upload a PDF file.")
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise PdfExtractionError("PDFs must be 10 MB or smaller.")
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        raise PdfExtractionError("This PDF could not be read. Upload an unencrypted text PDF.") from exc
    if reader.is_encrypted:
        raise PdfExtractionError("Password-protected PDFs are not supported.")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise PdfExtractionError("PDFs are limited to 30 pages.")
    try:
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:
        raise PdfExtractionError("Text could not be extracted from this PDF.") from exc
    if len(text) < MIN_EXTRACTED_CHARACTERS:
        raise PdfExtractionError("No usable text was found. Scanned/image-only PDFs are not supported.")
    if len(text) > MAX_EXTRACTED_CHARACTERS:
        raise PdfExtractionError("The PDF contains too much text; use 20,000 extracted characters or fewer.")
    return text
