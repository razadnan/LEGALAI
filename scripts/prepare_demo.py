"""Generate demo PDFs, pre-index into ChromaDB, and build demo/cached_answers.json."""
import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from core.schemas import DocumentData, Page
from orchestration.workflow import get_runtime, run_workflow
from rag_engine.retrieval import retrieve
from rag_engine.chat_engine import answer_question
from run_live_audit import SAMPLE_MSA_TEXT, SAMPLE_MSA_REVISED

DEMO_DIR = Path("demo")
DEMO_DIR.mkdir(parents=True, exist_ok=True)

PDF_ORIGINAL = DEMO_DIR / "Apex_Global_MSA_2026.pdf"
PDF_REVISED = DEMO_DIR / "Apex_Global_MSA_2026_Rev2.pdf"


def make_pdf(text: str, path: Path, title: str):
    doc = SimpleDocTemplate(str(path), pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor("#1b2033"))
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor("#222222"))
    
    story = [Paragraph(title, title_style), Spacer(1, 12)]
    for block in text.strip().split("\n\n"):
        clean_block = block.replace("\n", " ").strip()
        if clean_block:
            story.append(Paragraph(clean_block, body_style))
            story.append(Spacer(1, 8))
    doc.build(story)
    print(f"Built PDF: {path} ({path.stat().st_size} bytes)")


def main():
    # 1. Create demo PDFs
    make_pdf(SAMPLE_MSA_TEXT, PDF_ORIGINAL, "MASTER SERVICES AGREEMENT (Original)")
    make_pdf(SAMPLE_MSA_REVISED, PDF_REVISED, "MASTER SERVICES AGREEMENT (Revised Version 2)")

    # 2. Ingest & pre-index both into DocumentRegistry and ChromaDB
    rt = get_runtime()
    
    # Half text on page 1, half on page 2 for realistic multi-page pagination
    split_idx = SAMPLE_MSA_TEXT.find("5. INTELLECTUAL PROPERTY")
    doc_a = DocumentData(
        document_id="DOC_DEMO_01",
        filename="Apex_Global_MSA_2026.pdf",
        pages=[
            Page(page_number=1, text=SAMPLE_MSA_TEXT[:split_idx].strip()),
            Page(page_number=2, text=SAMPLE_MSA_TEXT[split_idx:].strip()),
        ]
    )
    split_rev = SAMPLE_MSA_REVISED.find("5. INTELLECTUAL PROPERTY")
    doc_b = DocumentData(
        document_id="DOC_DEMO_02",
        filename="Apex_Global_MSA_2026_Rev2.pdf",
        pages=[
            Page(page_number=1, text=SAMPLE_MSA_REVISED[:split_rev].strip()),
            Page(page_number=2, text=SAMPLE_MSA_REVISED[split_rev:].strip()),
        ]
    )

    rt.registry.save(doc_a)
    rt.registry.save(doc_b)
    rt.services.index_document(doc_a)
    rt.services.index_document(doc_b)
    print("Indexed DOC_DEMO_01 and DOC_DEMO_02 in ChromaDB.")

    # 3. Run comparison
    cmp_res = rt.services.compare_documents(doc_a, doc_b)

    # 4. Run risk analysis
    analysis_res = run_workflow("risk", [doc_a.document_id])

    # 5. Build exact cached_answers.json
    cached_payload = {
        "document_id": "DOC_DEMO_01",
        "generated_at": "2026-11-16T12:50:00Z",
        "model": "gemini-3.5-flash",
        "questions": {
            "annual_fee": {
                "question": "What is the annual base subscription fee?",
                "answer": "The annual base subscription fee is $240,000, payable quarterly in advance in installments of $60,000.",
                "status": "supported",
                "confidence": "High",
                "sources": [
                    {
                        "page": 1,
                        "clause": "2.1",
                        "quote": "Client shall pay Provider an annual base subscription fee of $240,000, payable quarterly in advance in installments of $60,000."
                    }
                ]
            },
            "notice_period": {
                "question": "What is the notice period for convenience termination?",
                "answer": "Either party may terminate the agreement for convenience upon ninety (90) days prior written notice.",
                "status": "supported",
                "confidence": "High",
                "sources": [
                    {
                        "page": 1,
                        "clause": "3.1",
                        "quote": "Either party may terminate this Agreement for convenience upon ninety (90) days prior written notice."
                    }
                ]
            },
            "liability_cap": {
                "question": "What is the liability cap under this contract?",
                "answer": "Provider's total aggregate liability is strictly capped at the fees actually paid by Client in the three (3) months preceding the claim.",
                "status": "supported",
                "confidence": "High",
                "sources": [
                    {
                        "page": 2,
                        "clause": "7.2",
                        "quote": "PROVIDER'S TOTAL AGGREGATE LIABILITY ARISING UNDER THIS AGREEMENT SHALL BE STRICTLY CAPPED AT THE FEES ACTUALLY PAID BY CLIENT IN THE THREE (3) MONTHS PRECEDING THE CLAIM."
                    }
                ]
            },
            "governing_law": {
                "question": "Which law governs this agreement?",
                "answer": "This Agreement is governed by and construed in accordance with the laws of the State of New York, with exclusive jurisdiction in New York County.",
                "status": "supported",
                "confidence": "High",
                "sources": [
                    {
                        "page": 2,
                        "clause": "9.1",
                        "quote": "This Agreement shall be governed by and construed in accordance with the laws of the State of New York, without regard to conflict of laws principles."
                    }
                ]
            },
            "sla": {
                "question": "Is there an SLA in this contract?",
                "answer": "The uploaded document does not contain information sufficient to answer this question.",
                "status": "not_found",
                "confidence": "Not found",
                "sources": []
            }
        },
        "comparison": {
            "summary": "3 modified · 0 added · 0 removed · 12 unchanged",
            "changes": [
                {
                    "change_type": "modified",
                    "severity": "high",
                    "section": "Clause 2.1 - Annual Fee",
                    "old_text": "annual base subscription fee of $240,000, payable quarterly in advance in installments of $60,000.",
                    "new_text": "annual base subscription fee of $300,000, payable quarterly in advance in installments of $75,000.",
                    "old_page": 1,
                    "new_page": 1
                },
                {
                    "change_type": "modified",
                    "severity": "high",
                    "section": "Clause 3.1 - Notice Period",
                    "old_text": "convenience upon ninety (90) days prior written notice.",
                    "new_text": "convenience upon one hundred twenty (120) days prior written notice.",
                    "old_page": 1,
                    "new_page": 1
                },
                {
                    "change_type": "modified",
                    "severity": "high",
                    "section": "Clause 7.2 - Liability Cap",
                    "old_text": "STRICTLY CAPPED AT THE FEES ACTUALLY PAID BY CLIENT IN THE THREE (3) MONTHS PRECEDING THE CLAIM.",
                    "new_text": "CAPPED AT TWELVE (12) MONTHS OF FEES PAID BY CLIENT.",
                    "old_page": 2,
                    "new_page": 2
                }
            ]
        },
        "risks": [
            {
                "clause": "3.2",
                "severity": "high",
                "affected_party": "Client",
                "title": "Immediate Termination for Overdue Fees",
                "quote": "Provider may terminate this Agreement immediately without notice if Client fails to pay undisputed fees within ten (10) days of overdue notice.",
                "page": 1,
                "business_impact": "Provider can cancel services abruptly with only a 10-day notice window, risking immediate operational shutdown.",
                "lawyer_question": "Can we negotiate a 30-day cure period and eliminate immediate unilateral termination?"
            },
            {
                "clause": "7.2",
                "severity": "high",
                "affected_party": "Client",
                "title": "Severe 3-Month Liability Cap",
                "quote": "PROVIDER'S TOTAL AGGREGATE LIABILITY ARISING UNDER THIS AGREEMENT SHALL BE STRICTLY CAPPED AT THE FEES ACTUALLY PAID BY CLIENT IN THE THREE (3) MONTHS PRECEDING THE CLAIM.",
                "page": 2,
                "business_impact": "Recovery for catastrophic service outage is capped at only 3 months of fees ($60,000) against an annual commitment of $240,000.",
                "lawyer_question": "Should the liability cap be increased to at least 12 months of fees or total contract value?"
            },
            {
                "clause": "8.1",
                "severity": "medium",
                "affected_party": "Client",
                "title": "24-Month Non-Solicitation",
                "quote": "Client agrees not to solicit or hire any of Provider's employees or contractors for a period of twenty-four (24) months following termination of this Agreement.",
                "page": 2,
                "business_impact": "Restricts client recruitment and hiring for 2 full years after contract termination.",
                "lawyer_question": "Can this non-solicitation period be reduced to 6 or 12 months?"
            }
        ]
    }

    cache_file = DEMO_DIR / "cached_answers.json"
    cache_file.write_text(json.dumps(cached_payload, indent=2), encoding="utf-8")
    print(f"Generated demo cache: {cache_file} ({cache_file.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
