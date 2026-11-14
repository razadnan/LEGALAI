from __future__ import annotations

import html
import os
import re
from pathlib import Path
from threading import Lock
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from core.exceptions import LegalMindError
from core.schemas import (
    AnswerResult,
    ComparisonResult,
    DocumentAnalysis,
    DocumentInfo,
    RiskFinding,
    WorkflowResult,
)
from orchestration.workflow import get_runtime, process_upload, run_workflow
from reports.report_generator import generate_report
from api.upload_processing import normalize_upload


Section = Literal["summary", "key_terms", "obligations", "risks", "comparison"]
_upload_lock = Lock()

app = FastAPI(title="LegalMind AI API", version="1.0.0")

_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        *_origins,
    ],
    allow_origin_regex=r"https://[a-zA-Z0-9-]+\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    page_count: int
    status: Literal["ready"]
    analysis_status: Literal["completed", "partial", "failed"]
    warnings: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class CompareResponse(BaseModel):
    revised_document_id: str
    comparison: ComparisonResult


class ReportRequest(BaseModel):
    sections: list[Section]
    comparison_document_id: Optional[str] = None


class ReportPreview(BaseModel):
    preview_html: str
    filename: str


@app.exception_handler(LegalMindError)
async def legalmind_error_handler(_request: Request, exc: LegalMindError) -> Response:
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=400, content={"detail": exc.user_message})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> Response:
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=422, content={"detail": exc.errors()})


def _workflow(task: str, document_ids: list[str], question: Optional[str] = None) -> WorkflowResult:
    result = run_workflow(task, document_ids, question)
    if result.errors:
        raise HTTPException(status_code=422, detail=result.errors)
    return result


def _get_document(document_id: str):
    try:
        return get_runtime().registry.get(document_id)
    except LegalMindError as exc:
        raise HTTPException(status_code=404, detail=exc.user_message) from exc


def _upload_and_analyze(filename: str, data: bytes) -> UploadResponse:
    with _upload_lock:
        processed_filename, processed_data, ocr_applied = normalize_upload(
            filename, data
        )
        document = process_upload(processed_filename, processed_data)
        if ocr_applied:
            document.filename = Path(filename).name
            document.file_type = Path(filename).suffix.lower().lstrip(".")
            document.page_source = "ocr"
            document.warnings.append(
                "Text was extracted locally with OCR; verify quoted passages against the original scan."
            )
            original_name = re.sub(
                r"[^A-Za-z0-9._ -]", "_", Path(filename).name
            ).strip(" .") or "upload"
            original_path = (
                get_runtime().settings.upload_dir
                / f"{document.document_id}_original_{original_name}"
            )
            try:
                original_path.write_bytes(data)
            except OSError:
                document.warnings.append(
                    "The original upload could not be retained in storage."
                )
            get_runtime().registry.save(document)
        result = run_workflow("risk", [document.document_id])
    if result.errors:
        analysis_status: Literal["completed", "partial", "failed"] = (
            "partial" if result.analysis else "failed"
        )
    else:
        analysis_status = "completed"
    return UploadResponse(
        document_id=document.document_id,
        filename=document.filename,
        page_count=document.page_count,
        status="ready",
        analysis_status=analysis_status,
        warnings=[*document.warnings, *result.warnings, *result.errors],
    )


def _report_result(
    document_id: str, request: ReportRequest
) -> tuple[WorkflowResult, str]:
    document = _get_document(document_id)
    overview = _workflow("summarize", [document_id])
    analysis = overview.analysis
    selected = set(request.sections)
    if analysis is not None:
        analysis = analysis.model_copy(
            update={
                "summary": analysis.summary if "summary" in selected else "",
                "parties": analysis.parties if "summary" in selected else [],
                "important_dates": analysis.important_dates if "key_terms" in selected else [],
                "key_terms": analysis.key_terms if "key_terms" in selected else [],
                "payment_terms": analysis.payment_terms if "key_terms" in selected else [],
                "obligations": analysis.obligations if "obligations" in selected else [],
            }
        )
        if not selected.intersection({"summary", "key_terms", "obligations"}):
            analysis = None

    risks_result = (
        _workflow("risk", [document_id])
        if "risks" in selected
        else None
    )

    comparison: Optional[ComparisonResult] = None
    documents: list[DocumentInfo] = list(overview.documents)
    if request.comparison_document_id and "comparison" in request.sections:
        _get_document(request.comparison_document_id)
        compare_result = _workflow(
            "compare", [document_id, request.comparison_document_id]
        )
        comparison = compare_result.comparison
        documents = compare_result.documents

    result = WorkflowResult(
        task="report",
        intent="report",
        documents=documents,
        analysis=analysis,
        risks=risks_result.risks if risks_result else [],
        comparison=comparison,
        warnings=[
            *overview.warnings,
            *(risks_result.warnings if risks_result else []),
        ],
    )
    return result, document.filename


def _report_preview(result: WorkflowResult, filename: str) -> str:
    parts = [
        "<h3>LegalMind AI – Contract Analysis</h3>",
        f'<span style="color:#777">{html.escape(filename)}</span>',
        "<hr>",
    ]
    analysis = result.analysis
    if analysis and (analysis.summary or analysis.parties):
        parts.append("<b>Summary &amp; parties</b><br>")
        parts.append(html.escape(analysis.summary or analysis.document_type))
        if analysis.parties:
            parts.append("<br>" + html.escape("; ".join(analysis.parties)))
        parts.append("<br><br>")
    if analysis and (analysis.important_dates or analysis.payment_terms or analysis.key_terms):
        parts.append("<b>Key dates and compensation</b><br>")
        parts.extend(
            f"{html.escape(item.label)}: {html.escape(item.date)}<br>"
            for item in analysis.important_dates
        )
        parts.extend(
            f"{html.escape(item.kind)}: {html.escape(item.description)} "
            f"{html.escape(', '.join(item.amounts))}<br>"
            for item in analysis.payment_terms
        )
        parts.extend(
            f"{html.escape(item.label)}: {html.escape(item.value)}<br>"
            for item in analysis.key_terms
        )
        parts.append("<br>")
    if analysis and analysis.obligations:
        parts.append("<b>Obligations</b><br>")
        parts.extend(
            f"• {html.escape(item.description)}<br>"
            for item in analysis.obligations
        )
        parts.append("<br>")
    if result.risks:
        parts.append("<b>Risk findings</b><br>")
        parts.extend(
            f"• [{html.escape(risk.severity.upper())}] "
            f"{html.escape(risk.title or risk.clause)}"
            f" (cl. {html.escape(risk.clause)}, p.{risk.page or '–'})<br>"
            for risk in result.risks
        )
        parts.append("<br>")
    if result.comparison:
        parts.extend(
            [
                "<b>Version comparison</b><br>",
                html.escape(result.comparison.summary),
                "<br><br>",
            ]
        )
    parts.append(
        '<span style="color:#999;font-size:11px">'
        "Generated by AI from the uploaded document. Not legal advice.</span>"
    )
    return "".join(parts)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    filename = Path(file.filename or "document").name
    data = await file.read()
    return await run_in_threadpool(_upload_and_analyze, filename, data)


@app.get(
    "/api/documents/{document_id}/overview",
    response_model=DocumentAnalysis,
)
async def overview(document_id: str) -> DocumentAnalysis:
    _get_document(document_id)
    result = await run_in_threadpool(_workflow, "summarize", [document_id])
    if result.analysis is None:
        raise HTTPException(status_code=422, detail="Document analysis is not available.")
    return result.analysis


@app.post(
    "/api/documents/{document_id}/chat",
    response_model=AnswerResult,
)
async def chat(document_id: str, body: ChatRequest) -> AnswerResult:
    _get_document(document_id)
    result = await run_in_threadpool(
        _workflow, "qa", [document_id], body.question
    )
    if result.answer is None:
        raise HTTPException(status_code=422, detail="No answer was produced.")
    return result.answer


@app.get(
    "/api/documents/{document_id}/risks",
    response_model=list[RiskFinding],
)
async def risks(document_id: str) -> list[RiskFinding]:
    _get_document(document_id)
    result = await run_in_threadpool(_workflow, "risk", [document_id])
    return result.risks


@app.post(
    "/api/documents/{document_id}/compare",
    response_model=CompareResponse,
)
async def compare(
    document_id: str,
    file: Optional[UploadFile] = File(default=None),
    revised_document_id: Optional[str] = Form(default=None),
) -> CompareResponse:
    _get_document(document_id)
    if file is not None:
        revised = await run_in_threadpool(
            _upload_and_analyze,
            Path(file.filename or "revised").name,
            await file.read(),
        )
        revised_id = revised.document_id
    elif revised_document_id:
        _get_document(revised_document_id)
        revised_id = revised_document_id
    else:
        raise HTTPException(
            status_code=422,
            detail="Upload a revised document or provide its document ID.",
        )
    result = await run_in_threadpool(
        _workflow, "compare", [document_id, revised_id]
    )
    if result.comparison is None:
        raise HTTPException(status_code=422, detail="No comparison was produced.")
    return CompareResponse(
        revised_document_id=revised_id,
        comparison=result.comparison,
    )


@app.post("/api/documents/{document_id}/report")
async def report(
    document_id: str,
    body: ReportRequest,
    download: bool = False,
):
    result, filename = await run_in_threadpool(
        _report_result, document_id, body
    )
    report_name = f"legalmind_report_{re.sub(r'[^A-Za-z0-9_-]', '_', document_id)}.pdf"
    if download:
        pdf_result = result
        if result.analysis and "key_terms" in body.sections:
            terms = [
                f"{item.kind}: {item.description} {', '.join(item.amounts)}".strip()
                for item in result.analysis.payment_terms
            ]
            terms.extend(
                f"{item.label}: {item.value}"
                for item in result.analysis.key_terms
            )
            if terms:
                pdf_analysis = result.analysis.model_copy(
                    update={
                        "summary": "\n".join(
                            part
                            for part in (result.analysis.summary, *terms)
                            if part
                        )
                    }
                )
                pdf_result = result.model_copy(update={"analysis": pdf_analysis})
        pdf = await run_in_threadpool(generate_report, pdf_result)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{report_name}"'},
        )
    return ReportPreview(
        preview_html=_report_preview(result, filename),
        filename=report_name,
    )
