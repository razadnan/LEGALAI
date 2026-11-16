# Architecture Specification: LegalMind AI

## 1. System Overview

LegalMind AI is an AI-assisted contract-intelligence prototype that extracts structured information from legal documents, answers document-specific questions using page and clause citations, identifies potential risks and missing safeguards, compares contract versions, and generates a downloadable analysis report. It is designed to assist human legal review, not replace legal advice.

In a controlled benchmark using one Master Services Agreement and a revised version, LegalMind AI correctly answered four targeted factual questions, returned not_found for one absent provision, identified four clearly absent MSA safeguards and two absent-or-partial provisions, detected three known contract modifications, and generated a downloadable evidence-based report. Further validation across multiple contract types and jurisdictions is required before production use.

---

## 2. Execution Pipeline & Data Flow

```
Next.js UI / Streamlit UI
       │
       ▼
FastAPI API / LangGraph workflow
       │
       ▼
Document Agent ──► RAG Agent ──► Risk Agent ──► Comparison Agent
       │
       ▼
Deterministic evidence verifier
       │
       ▼
PDF report / UI response
```

### Flow Breakdown:
1. **Document Agent:** Extracts text from PDF/DOCX using PyMuPDF and python-docx, validates against the legal-domain guard, and extracts key entities (parties, dates, obligations).
2. **RAG Agent:** Chunks documents with clause-aware boundaries and cross-reference preserving metadata, generates 3072-dimensional vector embeddings, indexes into ChromaDB, and performs hybrid semantic + BM25 keyword retrieval.
3. **Risk Agent:** Executes 15 predefined legal risk rules, scores risks with rationale, affected party, and proposed redlines.
4. **Comparison Agent:** Computes clause-by-clause version alignment with `<del>` and `<ins>` change tagging.
5. **Deterministic Evidence Verifier:** Checks exact quotes against page text; drops unverified citations or marks answers `not_found`.
6. **Delivery:** Outputs reactive Streamlit / Next.js views and compiles downloadable PDF reports via ReportLab.

---

## 3. Key Technical Safeguards

- **Retrieval Threshold:** Computes Chroma cosine distance; questions whose closest chunk exceeds distance `0.32` (or similarity `< 0.68`) return `not_found` immediately to prevent hallucinations and conserve API quota.
- **Deterministic Quote Verification:** Exact normalized substring matching and windowed fragment checking verify quotes page-by-page.
- **Visible Fallback Mode:** Recovers gracefully from rate limits with one retry (2s sleep), returning clear fallback indicators without exposing stack traces.
- **Legal Domain Guard:** Intercepts non-legal documents and out-of-domain questions before execution.
