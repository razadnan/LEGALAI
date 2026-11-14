"""Application-level exceptions.

Every exception carries a ``user_message`` that is safe to show in the UI
(no stack traces, no secrets).
"""
from __future__ import annotations


class LegalMindError(Exception):
    user_message = "Something went wrong. Please try again."

    def __init__(self, message: str | None = None, *, user_message: str | None = None):
        super().__init__(message or user_message or self.user_message)
        if user_message:
            self.user_message = user_message


class UnsupportedFileError(LegalMindError):
    user_message = "Unsupported file type. Please upload a text-based PDF or a DOCX file."


class FileTooLargeError(LegalMindError):
    user_message = "The file is too large."


class EmptyDocumentError(LegalMindError):
    user_message = (
        "No extractable text was found. Scanned PDFs (images) are not supported yet - "
        "please upload a text-based PDF or DOCX."
    )


class DocumentNotFoundError(LegalMindError):
    user_message = "The requested document could not be found. Please upload it again."


class InvalidRequestError(LegalMindError):
    user_message = "The request is incomplete or invalid."


class ModuleUnavailableError(LegalMindError):
    user_message = "A required component is not available in this environment."


class AgentError(LegalMindError):
    user_message = "An AI component failed to complete the request."


class ReportGenerationError(LegalMindError):
    user_message = "The PDF report could not be generated."


class NonLegalDocumentError(LegalMindError):
    user_message = (
        "This document does not appear to belong to LegalMind AI's domain. "
        "LegalMind AI is designed exclusively for legal document analysis. "
        "Please upload a legal document to continue."
    )


class CorruptDocumentError(LegalMindError):
    user_message = "The document file is corrupted or could not be parsed."


class EncryptedDocumentError(LegalMindError):
    user_message = "The document is password-protected or encrypted. Please upload an unencrypted file."


class ScannedPDFError(LegalMindError):
    user_message = (
        "This document appears to be a scanned image with little or no extractable text. "
        "OCR is not supported yet; please upload a text-based PDF or DOCX."
    )


class InvalidDocumentError(LegalMindError):
    user_message = "The document contains no extractable text or is formatted invalidly."


class DocumentNotIndexedError(LegalMindError):
    user_message = "The requested document is not indexed for search. Please re-index or upload again."


class LLMError(LegalMindError):
    user_message = "The AI model service encountered an error. Please verify your API key and network connection."
