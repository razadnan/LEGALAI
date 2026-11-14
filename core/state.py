"""Document registry (disk-backed) and Streamlit session helpers."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, MutableMapping, Optional

from core.exceptions import DocumentNotFoundError
from core.schemas import DocumentAnalysis, DocumentData

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class DocumentRegistry:
    """Stores processed documents and cached analyses as JSON files.

    Disk persistence lets the same documents survive Streamlit reruns and
    restarts, and lets the supervisor load documents by ID only.
    """

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._docs: dict[str, DocumentData] = {}
        self._analyses: dict[str, DocumentAnalysis] = {}

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _check(doc_id: str) -> str:
        if not _ID_RE.match(doc_id or ""):
            raise DocumentNotFoundError(f"Invalid document id: {doc_id!r}")
        return doc_id

    def _doc_path(self, doc_id: str) -> Path:
        return self.directory / f"{self._check(doc_id)}.json"

    def _analysis_path(self, doc_id: str) -> Path:
        return self.directory / f"{self._check(doc_id)}.analysis.json"

    # -- documents ----------------------------------------------------------
    def list_ids(self) -> list[str]:
        ids = {p.stem for p in self.directory.glob("*.json") if not p.name.endswith(".analysis.json")}
        return sorted(ids | set(self._docs))

    def next_id(self) -> str:
        nums = [int(m.group(1)) for i in self.list_ids() if (m := re.fullmatch(r"DOC(\d+)", i))]
        return f"DOC{(max(nums) + 1) if nums else 1:03d}"

    def save(self, doc: DocumentData) -> None:
        self._docs[doc.document_id] = doc
        self._doc_path(doc.document_id).write_text(doc.model_dump_json(indent=2), encoding="utf-8")

    def get(self, doc_id: str) -> DocumentData:
        if doc_id in self._docs:
            return self._docs[doc_id]
        path = self._doc_path(doc_id)
        if not path.exists():
            raise DocumentNotFoundError(f"Document {doc_id} not found")
        doc = DocumentData.model_validate_json(path.read_text(encoding="utf-8"))
        self._docs[doc_id] = doc
        return doc

    def exists(self, doc_id: str) -> bool:
        try:
            self.get(doc_id)
            return True
        except DocumentNotFoundError:
            return False

    def delete(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)
        self._analyses.pop(doc_id, None)
        for p in (self._doc_path(doc_id), self._analysis_path(doc_id)):
            p.unlink(missing_ok=True)

    # -- analyses -----------------------------------------------------------
    def save_analysis(self, doc_id: str, analysis: DocumentAnalysis) -> None:
        self._analyses[doc_id] = analysis
        self._analysis_path(doc_id).write_text(analysis.model_dump_json(indent=2), encoding="utf-8")

    def get_analysis(self, doc_id: str) -> Optional[DocumentAnalysis]:
        if doc_id in self._analyses:
            return self._analyses[doc_id]
        path = self._analysis_path(doc_id)
        if path.exists():
            a = DocumentAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
            self._analyses[doc_id] = a
            return a
        return None


# --------------------------------------------------------------------------- #
# Streamlit session helpers (work with any MutableMapping, so they are testable)
# --------------------------------------------------------------------------- #
_DEFAULTS: dict[str, Any] = {
    "active_document_id": None,
    "chat_history": {},       # document_id -> list[{"role", "content", "result"}]
    "results": {},            # (kind, key) -> WorkflowResult
    "last_report": None,      # {"name": str, "bytes": bytes}
}


def init_session(store: MutableMapping[str, Any]) -> None:
    for key, default in _DEFAULTS.items():
        if key not in store:
            store[key] = type(default)() if isinstance(default, (dict, list)) else default
