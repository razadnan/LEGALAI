"""Public interface of Developer 3's layer.

    run_workflow(task, document_ids, question=None) -> WorkflowResult
    process_upload(filename, data)                  -> DocumentData
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from config.settings import Settings, get_settings
from core.exceptions import (
    EmptyDocumentError,
    FileTooLargeError,
    LegalMindError,
    NonLegalDocumentError,
    UnsupportedFileError,
)
from core.domain_guard import is_legal_document
from core.schemas import DocumentData, WorkflowResult
from core.state import DocumentRegistry
from orchestration.adapters import Services
from orchestration.supervisor import AgentState, SupervisorGraph

_MIN_CHARS = 30  # fewer extractable characters than this => treat as scanned / empty


class _Runtime:
    """Lazily-created shared objects (one per Streamlit server process)."""
    settings: Optional[Settings] = None
    registry: Optional[DocumentRegistry] = None
    services: Optional[Services] = None
    graph: Optional[SupervisorGraph] = None


_rt = _Runtime()


def get_runtime(settings: Optional[Settings] = None, registry: Optional[DocumentRegistry] = None,
                services: Optional[Services] = None) -> _Runtime:
    if settings or registry or services or _rt.graph is None:
        _rt.settings = settings or _rt.settings or get_settings()
        _rt.registry = registry or _rt.registry or DocumentRegistry(_rt.settings.processed_dir)
        _rt.services = services or _rt.services or Services()
        _rt.graph = SupervisorGraph(_rt.services, _rt.registry, _rt.settings)
    return _rt


def _safe_name(filename: str) -> str:
    name = Path(filename or "").name  # drop any path components
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return name or "document"


def process_upload(filename: str, data: bytes, *, runtime: Optional[_Runtime] = None) -> DocumentData:
    """Validate, store, extract and index an uploaded file."""
    rt = runtime or get_runtime()
    s = rt.settings
    name = _safe_name(filename)
    ext = Path(name).suffix.lower()
    if ext not in s.allowed_extensions:
        raise UnsupportedFileError(f"Rejected extension {ext!r}")
    if not data:
        raise EmptyDocumentError("Empty upload", user_message="The uploaded file is empty.")
    if len(data) > s.max_upload_bytes:
        raise FileTooLargeError(f"{len(data)} bytes", user_message=f"The file is larger than {s.max_upload_mb} MB.")
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        raise UnsupportedFileError("Bad PDF header", user_message="This file is not a valid PDF.")
    if ext == ".docx" and not data.startswith(b"PK"):
        raise UnsupportedFileError("Bad DOCX header", user_message="This file is not a valid DOCX.")

    doc_id = rt.registry.next_id()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    path = Path(s.upload_dir) / f"{doc_id}_{name}"
    path.write_bytes(data)
    try:
        doc = rt.services.process_document(path, doc_id)
        doc.filename = name  # keep the clean name (without the id prefix)
        if sum(len(p.text.strip()) for p in doc.pages) < _MIN_CHARS:
            raise EmptyDocumentError("No text extracted")

        if not is_legal_document(doc.full_text):
            raise NonLegalDocumentError("Document failed legal-domain validation")

        rt.registry.save(doc)
        rt.services.index_document(doc)
        return doc
    except LegalMindError:
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise LegalMindError(f"Processing failed: {exc}",
                             user_message="The document could not be processed. Please try another file.") from exc


def run_workflow(task: str, document_ids: list[str], question: Optional[str] = None, *,
                 runtime: Optional[_Runtime] = None) -> WorkflowResult:
    """Run the supervisor. ``task`` is a TaskType value ("auto" classifies the question) or a free-text request."""
    rt = runtime or get_runtime()
    state: AgentState = {"task": task, "document_ids": list(document_ids or []), "question": question,
                         "errors": [], "warnings": []}
    try:
        return rt.graph.invoke(state)["result"]
    except LegalMindError as exc:
        return WorkflowResult(task=task, errors=[exc.user_message])
    except Exception as exc:  # last line of defence: the UI always gets a result object
        return WorkflowResult(task=task, errors=[f"Unexpected error ({type(exc).__name__}). Please try again."])
