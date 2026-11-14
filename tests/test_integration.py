"""End-to-end tests with the fallback services (no API key, no Streamlit needed)."""
import pytest

from core.exceptions import DocumentNotFoundError
from core.schemas import TaskType
from orchestration.workflow import process_upload, run_workflow


def _upload(rt, docx_bytes):
    a = process_upload("employment_v1.docx", docx_bytes[0], runtime=rt)
    b = process_upload("employment_v2.docx", docx_bytes[1], runtime=rt)
    return a, b


def test_upload_assigns_ids_and_extracts_text(runtime, docx_bytes):
    a, b = _upload(runtime, docx_bytes)
    assert (a.document_id, b.document_id) == ("DOC001", "DOC002")
    assert "Termination" in a.full_text and a.page_count >= 1
    assert runtime.registry.exists("DOC001")


def test_summarize_extracts_parties_dates_obligations(runtime, docx_bytes):
    a, _ = _upload(runtime, docx_bytes)
    r = run_workflow("summarize", [a.document_id], runtime=runtime)
    assert r.ok and r.agents_invoked == ["document_agent"]
    assert r.analysis.document_type == "Employment Agreement"
    assert any("Acme" in p for p in r.analysis.parties) and any("Jane" in p for p in r.analysis.parties)
    assert any("2026" in d.date for d in r.analysis.important_dates)
    assert r.analysis.obligations


def test_qa_returns_verified_sources_with_page_and_clause(runtime, docx_bytes):
    a, _ = _upload(runtime, docx_bytes)
    r = run_workflow("auto", [a.document_id], "What is the notice period?", runtime=runtime)
    assert r.intent == TaskType.QA.value and r.agents_invoked == ["rag_agent"]
    assert r.answer.sources and all(s.verified for s in r.answer.sources)
    assert r.answer.sources[0].clause == "8" and "30 days" in r.answer.sources[0].text


def test_clause_reference_question(runtime, docx_bytes):
    a, _ = _upload(runtime, docx_bytes)
    r = run_workflow("auto", [a.document_id], "Explain clause 10", runtime=runtime)
    assert r.answer.sources[0].clause == "10"


def test_unanswerable_question_does_not_invent_sources(runtime, docx_bytes):
    a, _ = _upload(runtime, docx_bytes)
    r = run_workflow("qa", [a.document_id], "zzzz qqqq", runtime=runtime)
    assert r.answer.sources == [] and not r.errors


def test_risk_findings_have_verified_evidence(runtime, docx_bytes):
    a, _ = _upload(runtime, docx_bytes)
    r = run_workflow("auto", [a.document_id], "Identify clauses that deserve additional legal review.", runtime=runtime)
    assert r.agents_invoked == ["document_agent", "risk_agent"]
    assert r.risks and all(x.evidence and x.verified for x in r.risks)
    assert any("Non-compete" in x.clause for x in r.risks)


def test_comparison_finds_modified_and_added(runtime, docx_bytes):
    a, b = _upload(runtime, docx_bytes)
    r = run_workflow("compare", [a.document_id, b.document_id], runtime=runtime)
    kinds = {c.change_type for c in r.comparison.changes}
    assert {"modified", "added"} <= kinds
    modified = " ".join(c.new_text for c in r.comparison.changes if c.change_type == "modified")
    assert "5,500" in modified and "60 days" in modified


def test_compare_with_one_document_is_a_friendly_error(runtime, docx_bytes):
    a, _ = _upload(runtime, docx_bytes)
    r = run_workflow("compare", [a.document_id], runtime=runtime)
    assert r.errors and "two documents" in r.errors[0].lower()


def test_report_pdf_is_generated(runtime, docx_bytes):
    a, b = _upload(runtime, docx_bytes)
    r = run_workflow("report", [a.document_id, b.document_id], "What is the notice period?", runtime=runtime)
    assert r.ok and r.report_path
    data = open(r.report_path, "rb").read()
    assert data.startswith(b"%PDF") and len(data) > 2000
    assert r.agents_invoked == ["document_agent", "risk_agent", "rag_agent", "comparison_agent", "report_generator"]


def test_report_text_contains_analysis(runtime, docx_bytes):
    pypdf = pytest.importorskip("pypdf")
    import io
    a, _ = _upload(runtime, docx_bytes)
    r = run_workflow("report", [a.document_id], runtime=runtime)
    text = "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(open(r.report_path, "rb").read())).pages)
    assert "Employment Agreement" in text and "Non-Compete" in text and "not legal" in text.lower()


def test_missing_document_and_empty_selection_are_handled(runtime):
    assert run_workflow("summarize", ["DOC999"], runtime=runtime).errors
    assert run_workflow("summarize", [], runtime=runtime).errors
    with pytest.raises(DocumentNotFoundError):
        runtime.registry.get("../etc/passwd")


def test_question_required_for_qa(runtime, docx_bytes):
    a, _ = _upload(runtime, docx_bytes)
    assert run_workflow("qa", [a.document_id], "  ", runtime=runtime).errors


def test_unsupported_and_invalid_files_rejected(runtime):
    from core.exceptions import EmptyDocumentError, FileTooLargeError, UnsupportedFileError
    with pytest.raises(UnsupportedFileError):
        process_upload("notes.txt", b"hello", runtime=runtime)
    with pytest.raises(UnsupportedFileError):
        process_upload("fake.pdf", b"not a pdf", runtime=runtime)
    with pytest.raises(FileTooLargeError):
        process_upload("big.pdf", b"%PDF" + b"0" * (2 * 1024 * 1024), runtime=runtime)
    with pytest.raises(EmptyDocumentError):
        process_upload("empty.pdf", b"", runtime=runtime)


def test_path_traversal_filename_is_neutralised(runtime, docx_bytes):
    doc = process_upload("../../evil.docx", docx_bytes[0], runtime=runtime)
    assert doc.filename == "evil.docx"
    assert all(runtime.settings.upload_dir in p.parents for p in runtime.settings.upload_dir.glob("*"))


def test_pdf_upload_roundtrip(runtime, tmp_path):
    pytest.importorskip("pypdf")
    from reportlab.pdfgen import canvas
    p = tmp_path / "c.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(72, 750, "1. Termination")
    c.drawString(72, 730, "Either party may terminate this agreement with 30 days written notice.")
    c.showPage()
    c.drawString(72, 750, "2. Governing law")
    c.drawString(72, 730, "This agreement is governed by the laws of India.")
    c.save()
    doc = process_upload("c.pdf", p.read_bytes(), runtime=runtime)
    assert doc.page_count == 2
    r = run_workflow("qa", [doc.document_id], "Which law governs?", runtime=runtime)
    assert r.answer.sources[0].page == 2 and r.answer.sources[0].verified

def test_unrelated_question_is_rejected(runtime, docx_bytes):
    a, _ = _upload(runtime, docx_bytes)

    r = run_workflow(
        "qa", [a.document_id],
        "What is the weather forecast for tomorrow?",
        runtime=runtime,
    )

    assert r.errors
    assert "outside legalmind ai's domain" in r.errors[0].lower()
    assert "rag_agent" not in r.agents_invoked


def test_recipe_question_is_rejected(runtime, docx_bytes):
    a, _ = _upload(runtime, docx_bytes)

    r = run_workflow(
        "qa", [a.document_id],
        "Give me a recipe for chocolate cake.",
        runtime=runtime,
    )

    assert r.errors
    assert "rag_agent" not in r.agents_invoked


def test_legal_document_question_is_allowed(runtime, docx_bytes):
    a, _ = _upload(runtime, docx_bytes)

    r = run_workflow(
        "qa", [a.document_id],
        "What is the notice period?",
        runtime=runtime,
    )

    assert not r.errors
    assert r.agents_invoked == ["rag_agent"]
    assert r.answer.sources


def test_real_services_resolution_and_pipeline(tmp_path, docx_bytes):
    from config.settings import Settings
    from core.state import DocumentRegistry
    from orchestration.adapters import Services
    from orchestration.supervisor import SupervisorGraph
    from orchestration.workflow import _Runtime

    services = Services(prefer_real=True)
    assert not services.uses_fallback
    assert all(not status.startswith("fallback") for status in services.status.values())

    settings = Settings(
        upload_dir=tmp_path / "uploads",
        processed_dir=tmp_path / "processed",
        vector_db_dir=tmp_path / "vdb",
        reports_dir=tmp_path / "reports",
        max_upload_mb=5,
    )
    settings.ensure_dirs()
    registry = DocumentRegistry(settings.processed_dir)
    rt = _Runtime()
    rt.settings, rt.registry, rt.services = settings, registry, services
    rt.graph = SupervisorGraph(services, registry, settings)

    a, b = _upload(rt, docx_bytes)
    assert a.document_id and b.document_id

    # Summarize with real document intelligence module
    r_sum = run_workflow("summarize", [a.document_id], runtime=rt)
    assert r_sum.ok and r_sum.analysis.document_type == "Employment Agreement"

    # Risk analysis with real 15 risk rules
    r_risk = run_workflow("risk", [a.document_id], runtime=rt)
    assert r_risk.ok and len(r_risk.risks) >= 1

    # Comparison with real comparison agent
    r_cmp = run_workflow("compare", [a.document_id, b.document_id], runtime=rt)
    assert r_cmp.ok and len(r_cmp.comparison.changes) >= 1

    # Report with real modules
    r_rep = run_workflow("report", [a.document_id, b.document_id], "What is the notice period?", runtime=rt)
    assert r_rep.ok and r_rep.report_path


def test_reconciled_schemas_and_exceptions():
    import core.exceptions as exc
    import core.schemas as sch

    for err in [
        exc.CorruptDocumentError,
        exc.EncryptedDocumentError,
        exc.ScannedPDFError,
        exc.InvalidDocumentError,
        exc.DocumentNotIndexedError,
        exc.LLMError,
    ]:
        e = err()
        assert e.user_message

    evidence = sch.Evidence(page=1, clause="8", text="Notice period 30 days", verified=True)
    party = sch.Party(name="Acme Corp", role="Employer", evidence=evidence)
    date = sch.ImportantDate(label="Effective date", date="2026-01-01", value="1 Jan 2026", evidence=evidence)
    term = sch.KeyTerm(label="Notice period", value="30 days", evidence=evidence)
    pay = sch.PaymentTerm(kind="salary", description="5,000 USD", amounts=["5,000 USD"], evidence=evidence)
    obl = sch.Obligation(description="Employee shall report to CTO", party="Employee", evidence=evidence)
    chunk = sch.Chunk(
        chunk_id="c1", document_id="DOC001", chunk_index=0,
        text="text", page_start=1, page_end=1, clause="1", clause_ids=["1"]
    )
    ans = sch.Answer(answer="30 days", sources=[sch.Source(page=1, text="30 days")])

    assert party.name == "Acme Corp"
    assert date.label == "Effective date"
    assert term.value == "30 days"
    assert pay.amounts == ["5,000 USD"]
    assert obl.party == "Employee"
    assert chunk.chunk_id == "c1"
    assert ans.answer == "30 days"
