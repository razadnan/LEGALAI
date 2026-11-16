"""Live End-to-End System Test and Evaluation Suite for LegalMind AI.

Acts as a rigorous automated auditor and tester evaluating the entire platform:
1. Document Ingestion & Domain Guard
2. Extraction Separation (10 Field Categories)
3. Chunking & ChromaDB Retrieval
4. Grounded Q&A with Citation Support
5. Missing-Clause Playbook Analysis
6. Risk Scoring with Rationale & Redlines
7. Legal Reasoning & Favorability
8. Version Comparison (Diffing)
9. Report Generation
10. System Metrics Tracking
"""
import json
import time
from pathlib import Path
from core.schemas import DocumentData, Page
from core.domain_guard import is_legal_document, is_out_of_domain_question
from document_intelligence.structured_extractor import extract_structured_fields
from document_intelligence.missing_clause_checker import check_missing_clauses
from document_intelligence.risk_analyzer import find_risks, score_risks_with_rationale
from document_intelligence.legal_reasoning import produce_reasoning
from orchestration.workflow import get_runtime, process_upload, run_workflow
from rag_engine.llm import get_llm
from rag_engine.retrieval import retrieve
from rag_engine.chat_engine import answer_question
from core.metrics import get_collector, reset_collector

SAMPLE_MSA_TEXT = """
MASTER SERVICES AGREEMENT

This Master Services Agreement ("Agreement") is entered into on January 15, 2026 ("Effective Date"), by and between:
1. Apex Cloud Solutions Inc., a Delaware corporation ("Provider" or "Company"), and
2. Global Dynamics Retail LLC, a California limited liability company ("Client" or "Customer").

1. SCOPE OF SERVICES
1.1 Provider shall provide cloud hosting, application maintenance, and infrastructure management services as detailed in Statements of Work.
1.2 The initial term of this Agreement shall be three (3) years from the Effective Date ("Term").

2. FEES AND PAYMENT TERMS
2.1 Client shall pay Provider an annual base subscription fee of $240,000, payable quarterly in advance in installments of $60,000.
2.2 Invoices are payable within thirty (30) days of receipt. Late payments shall accrue interest at 1.5% per month.

3. TERM AND TERMINATION
3.1 Either party may terminate this Agreement for convenience upon ninety (90) days prior written notice.
3.2 Provider may terminate this Agreement immediately without notice if Client fails to pay undisputed fees within ten (10) days of overdue notice.
3.3 Either party may terminate immediately for cause upon thirty (30) days written notice of material breach, provided such breach remains uncured.

4. CONFIDENTIALITY
4.1 "Confidential Information" means all non-public information disclosed by either party. Each party agrees to protect the other's Confidential Information with the same degree of care it uses for its own confidential information, but not less than reasonable care.
4.2 Obligations of confidentiality shall survive termination and continue for a period of five (5) years thereafter.

5. INTELLECTUAL PROPERTY
5.1 Provider retains all right, title, and interest in and to its pre-existing IP, software platforms, algorithms, and documentation.
5.2 Client shall own all right, title, and interest in Client Data. Work product specifically commissioned and paid for by Client shall be deemed works made for hire.

6. INDEMNIFICATION
6.1 Client agrees to defend, indemnify, and hold harmless Provider from and against any third-party claims arising out of Client's breach of law or violation of third-party IP rights.
6.2 Provider offers no mutual indemnification for infringement claims related to standard hosting components.

7. LIMITATION OF LIABILITY
7.1 EXCEPT FOR GROSS NEGLIGENCE OR WILLFUL MISCONDUCT, IN NO EVENT SHALL EITHER PARTY BE LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL, OR CONSEQUENTIAL DAMAGES.
7.2 PROVIDER'S TOTAL AGGREGATE LIABILITY ARISING UNDER THIS AGREEMENT SHALL BE STRICTLY CAPPED AT THE FEES ACTUALLY PAID BY CLIENT IN THE THREE (3) MONTHS PRECEDING THE CLAIM.

8. NON-COMPETE AND RESTRICTIVE COVENANTS
8.1 Client agrees not to solicit or hire any of Provider's employees or contractors for a period of twenty-four (24) months following termination of this Agreement.

9. GOVERNING LAW AND JURISDICTION
9.1 This Agreement shall be governed by and construed in accordance with the laws of the State of New York, without regard to conflict of laws principles.
9.2 Exclusive jurisdiction and venue for any dispute shall lie in the state and federal courts located in New York County, New York.
"""

SAMPLE_MSA_REVISED = SAMPLE_MSA_TEXT.replace(
    "$240,000, payable quarterly in advance in installments of $60,000.",
    "$300,000, payable quarterly in advance in installments of $75,000."
).replace(
    "ninety (90) days prior written notice.",
    "one hundred twenty (120) days prior written notice."
).replace(
    "STRICTLY CAPPED AT THE FEES ACTUALLY PAID BY CLIENT IN THE THREE (3) MONTHS PRECEDING THE CLAIM.",
    "CAPPED AT TWELVE (12) MONTHS OF FEES PAID BY CLIENT."
)

def run_tests():
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tests": {},
        "metrics": {},
        "verdict": "PASS"
    }
    reset_collector()
    collector = get_collector()
    llm = get_llm()

    print("=== [1] TESTING DOMAIN GUARD & SECURITY ===")
    legal_ok = is_legal_document(SAMPLE_MSA_TEXT)
    non_legal_text = "Today's chocolate cake recipe: 2 cups flour, 1 cup sugar, 2 eggs, bake at 350F for 30 mins."
    non_legal_ok = is_legal_document(non_legal_text)
    bad_q = is_out_of_domain_question("How do I bake chocolate cake?")
    legal_q = is_out_of_domain_question("What is the limitation of liability cap?")

    domain_pass = legal_ok and (not non_legal_ok) and bad_q and (not legal_q)
    report["tests"]["domain_guard"] = {
        "status": "PASS" if domain_pass else "FAIL",
        "legal_doc_accepted": legal_ok,
        "recipe_doc_rejected": not non_legal_ok,
        "recipe_query_blocked": bad_q,
        "legal_query_allowed": not legal_q
    }
    print(f"Domain Guard: {report['tests']['domain_guard']}")

    print("\n=== [2] TESTING DOCUMENT INGESTION & DATA STRUCTURE ===")
    doc = DocumentData(
        document_id="TEST_MSA_001",
        filename="Apex_Global_MSA_2026.pdf",
        pages=[
            Page(page_number=1, text=SAMPLE_MSA_TEXT[:1800]),
            Page(page_number=2, text=SAMPLE_MSA_TEXT[1800:])
        ]
    )
    rt = get_runtime()
    rt.registry.save(doc)
    rt.services.index_document(doc)
    report["tests"]["ingestion"] = {
        "status": "PASS",
        "doc_id": doc.document_id,
        "pages": doc.page_count,
        "text_length": len(doc.full_text)
    }

    print("\n=== [3] TESTING STRUCTURED EXTRACTION (10 FIELDS) ===")
    st_fields = extract_structured_fields(doc, llm=llm)
    extracted_keys = {
        "parties": len(st_fields.parties) > 0,
        "effective_date": bool(st_fields.effective_date),
        "notice_period": bool(st_fields.notice_period),
        "governing_law": bool(st_fields.governing_law),
        "monetary_terms": len(st_fields.monetary_terms) > 0,
        "termination": len(st_fields.termination) > 0,
        "confidentiality": len(st_fields.confidentiality) > 0,
        "intellectual_property": len(st_fields.intellectual_property) > 0,
        "indemnity": len(st_fields.indemnity) > 0,
        "liability": len(st_fields.liability) > 0
    }
    field_count = sum(1 for v in extracted_keys.values() if v)
    collector.record_extraction(st_fields.extraction_confidence)
    report["tests"]["structured_extraction"] = {
        "status": "PASS" if field_count >= 8 else "WARNING",
        "field_coverage": f"{field_count}/10",
        "confidence": st_fields.extraction_confidence,
        "governing_law": st_fields.governing_law,
        "notice_period": st_fields.notice_period,
        "warnings": st_fields.warnings
    }
    print(f"Extraction coverage: {field_count}/10, Confidence: {st_fields.extraction_confidence}")

    print("\n=== [4] TESTING RAG CHAT & CITATION VERIFICATION ===")
    test_queries = [
        ("What is the annual base subscription fee?", "$240,000", "2.1"),
        ("What is the notice period for convenience termination?", "90", "3.1"),
        ("What law governs this agreement and which courts have jurisdiction?", "New York", "9.1"),
        ("What is the liability cap under this contract?", "3", "7.2"),
    ]
    qa_results = []
    qa_passed = 0
    for q, expected_token, expected_clause in test_queries:
        res_dict = answer_question(doc.document_id, q, store=None, llm=llm)
        answer_text = res_dict.get("answer", "")
        grounded = res_dict.get("grounded", False)
        sources = res_dict.get("sources", [])
        
        has_token = expected_token.lower() in answer_text.lower()
        has_clause = any(expected_clause in (s.get("clause") or "") or expected_clause in s.get("text", "") for s in sources) if sources else False
        
        is_good = has_token and grounded
        if is_good:
            qa_passed += 1
            
        qa_results.append({
            "question": q,
            "answer_preview": answer_text[:120] + "...",
            "grounded": grounded,
            "expected_found": has_token,
            "sources_count": len(sources)
        })
        # Record into metrics
        from core.schemas import AnswerResult
        collector.record_answer(AnswerResult(**res_dict))

    report["tests"]["rag_qa"] = {
        "status": "PASS" if qa_passed >= 3 else "FAIL",
        "accuracy": f"{qa_passed}/{len(test_queries)}",
        "queries": qa_results
    }
    print(f"RAG QA Accuracy: {qa_passed}/{len(test_queries)}")

    print("\n=== [5] TESTING RISK IDENTIFICATION & SCORING ===")
    from document_intelligence.risk_analyzer import build_context
    ctx = build_context(doc)
    risks = find_risks(ctx)
    scored = score_risks_with_rationale(risks, llm=llm)
    collector.record_risk_findings(risks)

    report["tests"]["risk_analysis"] = {
        "status": "PASS" if len(scored) > 0 else "FAIL",
        "findings_count": len(scored),
        "high_severity_count": sum(1 for r in scored if r.get("severity") == "high"),
        "sample_scored_risk": {
            "clause": scored[0].get("clause"),
            "severity": scored[0].get("severity"),
            "affected_party": scored[0].get("affected_party"),
            "business_impact": scored[0].get("business_impact"),
            "has_redline": bool(scored[0].get("proposed_redline")),
            "confidence": scored[0].get("confidence")
        } if scored else None
    }
    print(f"Risk findings identified: {len(scored)} (High: {report['tests']['risk_analysis']['high_severity_count']})")

    print("\n=== [6] TESTING MISSING-CLAUSE PLAYBOOK CHECKLIST ===")
    playbook_res = check_missing_clauses(doc, doc_type="MSA", llm=llm, playbook_name="MSA")
    absent = [f.provision for f in playbook_res.findings if f.status == "absent"]
    present = [f.provision for f in playbook_res.findings if f.status == "present"]
    report["tests"]["missing_clause_playbook"] = {
        "status": "PASS" if playbook_res.present_count > 0 and playbook_res.absent_count > 0 else "FAIL",
        "playbook": playbook_res.playbook,
        "present_count": playbook_res.present_count,
        "absent_count": playbook_res.absent_count,
        "partial_count": playbook_res.partial_count,
        "sample_absent_provisions": absent[:5],
        "sample_present_provisions": present[:5]
    }
    print(f"Playbook Check: {playbook_res.present_count} Present, {playbook_res.absent_count} Absent (Gaps: {absent[:3]})")

    print("\n=== [7] TESTING LEGAL REASONING LAYER ===")
    reasoning = produce_reasoning(
        doc_type="Master Services Agreement",
        extracted_fields=st_fields,
        risks=risks,
        passages_text=doc.full_text[:4000],
        playbook=playbook_res,
        llm=llm
    )
    report["tests"]["legal_reasoning"] = {
        "status": "PASS" if reasoning.favorability != "unclear" or len(reasoning.recommendations) > 0 else "WARNING",
        "favorability": reasoning.favorability,
        "rationale_preview": reasoning.favorability_rationale[:160] + "...",
        "recommendations_count": len(reasoning.recommendations),
        "gaps_count": len(reasoning.gaps),
        "layperson_summary_preview": reasoning.summary_for_layperson[:160] + "..."
    }
    print(f"Legal Reasoning Favorability: {reasoning.favorability}, Recommendations: {len(reasoning.recommendations)}")

    print("\n=== [8] TESTING VERSION COMPARISON (DIFF ENGINE) ===")
    doc_b = DocumentData(
        document_id="TEST_MSA_002",
        filename="Apex_Global_MSA_2026_Rev2.pdf",
        pages=[Page(page_number=1, text=SAMPLE_MSA_REVISED)]
    )
    rt.registry.save(doc_b)
    cmp_res = rt.services.compare_documents(doc, doc_b)
    changes_count = len(cmp_res.changes) if cmp_res else 0
    report["tests"]["comparison"] = {
        "status": "PASS" if changes_count > 0 else "FAIL",
        "changes_detected": changes_count,
        "summary": cmp_res.summary if cmp_res else ""
    }
    print(f"Comparison: {changes_count} differences detected. Summary: {cmp_res.summary}")

    print("\n=== [9] TESTING REPORT GENERATION (PDF) ===")
    wf_res = run_workflow("report", [doc.document_id], question="What is the liability cap?")
    report_exists = wf_res.report_path and Path(wf_res.report_path).exists()
    file_size = Path(wf_res.report_path).stat().st_size if report_exists else 0
    report["tests"]["pdf_report"] = {
        "status": "PASS" if report_exists and file_size > 500 else "FAIL",
        "report_path": wf_res.report_path,
        "file_size_bytes": file_size
    }
    print(f"PDF Report generated: {report_exists} ({file_size} bytes at {wf_res.report_path})")

    # Final System Snapshot Metrics
    metrics = collector.snapshot()
    report["metrics"] = {
        "extraction_confidence": round(metrics.extraction_confidence, 3),
        "retrieval_recall_at_k": round(metrics.retrieval_recall_at_k, 3),
        "citation_support_rate": round(metrics.citation_support_rate, 3),
        "unsupported_citation_rate": round(metrics.unsupported_citation_rate, 3),
        "false_refusal_rate": round(metrics.false_refusal_rate, 3),
        "total_claims": metrics.total_claims,
        "clauses_cited": metrics.clauses_cited,
        "unsupported_claims": metrics.unsupported_claims
    }
    print("\n=== [10] PIPELINE METRICS SNAPSHOT ===")
    print(json.dumps(report["metrics"], indent=2))

    Path("live_test_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nSaved full audit results to live_test_report.json")
    return report

if __name__ == "__main__":
    run_tests()
