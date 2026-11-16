# LegalMind AI

LegalMind AI is an AI-assisted contract-intelligence prototype that extracts structured information from legal documents, answers document-specific questions using page and clause citations, identifies potential risks and missing safeguards, compares contract versions, and generates a downloadable analysis report. It is designed to assist human legal review, not replace legal advice.

In a controlled benchmark using one Master Services Agreement and a revised version, LegalMind AI correctly answered four targeted factual questions, returned not_found for one absent provision, identified four clearly absent MSA safeguards and two absent-or-partial provisions, detected three known contract modifications, and generated a downloadable evidence-based report. Further validation across multiple contract types and jurisdictions is required before production use.

---

## 🏛️ Architecture Flow

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

---

## 📂 Repository Structure

```
LegalMind-AI/
├── api/                   # FastAPI REST API endpoints
├── config/                # Central settings and prompt definitions
├── core/                  # Shared Pydantic schemas, domain guard, exceptions
├── document_intelligence/ # Text extraction, 10-field structured schema, risk rules
├── rag_engine/            # Hybrid vector + BM25 retrieval, Gemini embeddings, chat
├── orchestration/         # LangGraph supervisor workflow, deterministic verification
├── reports/               # ReportLab PDF report generation
├── ui/                    # Streamlit prototype UI
├── frontend/              # Next.js web application
├── docs/                  # Architecture, testing report, and limitations documentation
├── demo/                  # Pre-indexed MSA PDFs, test script, and cached results
│   ├── Apex_Global_MSA_2026.pdf
│   ├── Apex_Global_MSA_2026_Rev2.pdf
│   ├── demo_script.md
│   ├── expected_results.md
│   ├── cached_answers.json
│   └── backup_demo.mp4
├── tests/                 # Automated pytest test suite (78 tests)
├── requirements.txt       # Production dependencies
└── README.md
```

---

## 🚀 Quick Start

### 1. Python Environment Setup
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Streamlit Web Application (Default Demo UI)
```powershell
streamlit run app.py
```
Open `http://localhost:8501` to access the interactive web interface.

### 3. FastAPI REST API
```powershell
uvicorn api.main:app --reload --port 8000
```
Interactive Swagger API documentation is available at `http://localhost:8000/docs`.

### 4. Next.js Frontend (Optional)
```powershell
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000`.

---

## 🎯 Live Demonstration Scope

- **Demo Questions:** The live demonstration uses five fixed questions: four factual questions and one absent-provision question.
- **Retrieval Result:** The system correctly answered four targeted factual questions and returned not_found for one absent provision.
- **Missing Provisions:** The MSA playbook identified four clearly absent provisions and two provisions that were absent or only partially addressed.
- **Document Ingestion:** Current scope supports text-based PDF and DOCX ingestion. Scanned PDFs and image-based documents are not supported in this version. OCR is planned as a future enhancement.

---

## 🧪 Testing & Validation

Run the complete automated test suite (78 unit, integration, and security tests):
```powershell
pytest -v
```
To run the end-to-end live demo verification:
```powershell
python run_live_audit.py
```
