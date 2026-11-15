# LegalMind AI

Agentic legal document intelligence and contract analysis. The existing Python workflow remains the
backend; `api/` exposes it through FastAPI and `frontend/` contains the Next.js App Router UI.

## Quick start

### FastAPI backend

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # configure an LLM key if needed
uvicorn api.main:app --reload
```

The API is available at `http://localhost:8000`; interactive API documentation is at
`http://localhost:8000/docs`. It writes uploads, processed documents, reports, and vector data under
the existing `storage/` directories.

Scanned PDFs and JPG/JPEG, PNG, or TIFF uploads are OCR-processed locally before entering the
existing document workflow. Install the Tesseract OCR executable with English language data and make
`tesseract --version` available in `PATH`; if it is installed elsewhere, set `TESSERACT_CMD` to its
full executable path (for example, `C:\Program Files\Tesseract-OCR\tesseract.exe` on Windows). The
Python wrapper dependency is included in `requirements.txt`. On Windows, Tesseract can be
installed with `winget install --id UB-Mannheim.TesseractOCR -e`. Set `TESSERACT_LANG` if using
additional installed language data. OCR extracts text only; verify quotations and page references
against the original scan.

### Next.js frontend

In another terminal:

```powershell
Set-Location frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

The app runs at `http://localhost:3000`. Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` to the
FastAPI base URL. The API allows localhost and `*.vercel.app` origins; set `CORS_ORIGINS` on the API
for any custom frontend domain.

### Vercel deployment

Import the repository into Vercel and set the project **Root Directory** to `frontend`. Configure
`NEXT_PUBLIC_API_URL` as the public URL of the separately deployed FastAPI service, then deploy.
Deploy the Python API on a host that supports persistent disk and mount durable storage for
`storage/processed/`, `storage/vector_db/`, `storage/uploads/`, and `storage/reports/`; Vercel's
serverless filesystem is not suitable for this backend data. Set `CORS_ORIGINS` to the deployed
frontend origin (and configure the existing model credentials in the backend environment).

## Project structure

| File | Purpose |
|---|---|
| `api/` | FastAPI upload, chat, comparison, and report endpoints |
| `frontend/` | Next.js interface with document views and evidence-backed chat |
| `app.py`, `ui/` | Legacy Streamlit interface |
| `orchestration/` | Supervisor routing, workflow execution, service adapters, and evidence verification |
| `rag_engine/` | Clause-aware chunking, hybrid retrieval, and citation-grounded answers |
| `document_intelligence/` | Document extraction, analysis, risk findings, and DOCX editing |
| `core/` | Shared Pydantic schemas, document registry, and application errors |
| `scripts/evaluate_retrieval.py` | Offline retrieval benchmark runner |

## How it works

Uploads are extracted locally; scanned PDFs and supported image files use OCR when Tesseract is
installed. The workflow analyzes document structure and risks, chunks text by clause, and indexes it
for hybrid vector and keyword retrieval. For questions, the configured LLM classifies intent (with
rule-based fallback), uses recent chat turns to clarify follow-ups, and answers from retrieved
passages. Source citations are checked against the extracted document before display. If no LLM is
configured, the application uses its heuristic/extractive fallback.

## Supervisor routing

| Request | Agents |
|---|---|
| Summarize / who are the parties? | document |
| Explain clause 8 / what is the notice period? | rag |
| Identify risks / clauses for legal review | document → risk |
| Compare two contracts | comparison |
| Generate analysis report | document → risk → (rag) → (comparison) → report |

Automatic requests use the configured LLM to classify intent; if no LLM is configured or
classification fails, the supervisor falls back to deterministic regex rules. Explicit task
selections still take precedence. Chat requests include up to the last six messages, which the
RAG engine can use to rewrite follow-ups before retrieval.

## Retrieval evaluation

The retrieval benchmark contains 66 manually labeled questions across four synthetic agreements
(employment, NDA, commercial lease, and professional services). By default, it uses deterministic
offline hash embeddings and a temporary in-memory vector store:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py
```

The latest offline run reported overall Recall@1/3/5 of **0.833 / 0.955 / 0.970** and MRR **0.894**.
The per-contract macro averages were **0.873 / 0.964 / 0.971** and MRR **0.915**. The script reports
overall and macro-average Recall@1/3/5 and MRR, per-contract metrics, validates
that every gold clause exists in its fixture, and prints each query's first relevant rank. These
synthetic fixtures are a smoke benchmark, not a representative measure of production legal-document
accuracy; do not use the scores as proof of accuracy.

The chat UI offers suggested questions, an optional plain-language answer instruction, and an
agent trace per response. Plain-language mode changes only the LLM answer instruction; retrieval
and source verification remain the same.

To compare a local cross-encoder against RRF, first install the optional evaluation dependency and
run the same candidate pool through both rankers. Cross-encoder loading is local-only, so the model
must already be cached:

```powershell
.\.venv\Scripts\python.exe -m pip install sentence-transformers==5.7.0
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py --top-k 15 --cross-encoder BAAI/bge-reranker-base
```

To run the same benchmark with the application's configured production embedding provider and model
(loaded by the existing `config.settings` and `rag_engine.embeddings.get_embedder()`), use:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py --embedding-mode production --top-k 15 --cross-encoder BAAI/bge-reranker-base
```

Production mode fails clearly if no production provider/key is configured; it never silently falls
back to hash embeddings. The script prints the resolved provider/model and embedding, retrieval,
reranking, and total elapsed times. Chunk embeddings are generated once, query embeddings use the
same configured embedder, and RRF and BGE compare the exact same candidate lists. The vector store
uses a temporary isolated backend that is removed when the command exits; it does not open or write
the app's persistent ChromaDB collection. The script uses the synthetic fixture only, and the
cross-encoder is not part of the production retrieval path.

## DOCX editing foundation

`document_intelligence/docx_editing.py` provides clause-tree extraction and deterministic
proposal application for DOCX drafts. Clause paragraph indexes are zero-based indexes into
`python-docx`'s top-level `Document.paragraphs`; ranges are inclusive and stop before the next
numbered heading. A proposal must name an existing clause and exact old text that occurs exactly
once there. Applying a proposal writes a separate `.docx` draft, never overwrites the source, and
does not call an LLM. PDFs remain read-only. This is a foundation utility only; approval state,
audit persistence, and UI/API integration are not implemented yet.

## Safeguards implemented

- Uploaded contracts are untrusted: `config/prompts.py` provides `wrap_untrusted()` for prompts; chat input is sanitized and instruction-like text is flagged.
- Citations and risk evidence are verified against the extracted text/page; unverifiable ones are flagged in the UI and PDF - never silently shown as fact.
- File validation: extension, size, magic bytes, path-traversal-safe names, empty/scanned PDF detection.
- Each agent runs in an error guard: one failing agent returns a friendly message instead of crashing the app.
- `.env` is git-ignored; storage contents are git-ignored.

## Known limitations

- The retrieval scores above use four synthetic contracts and offline hash embeddings; no real-contract
  accuracy study has been run. Validate extraction and retrieval on appropriately reviewed documents
  before relying on or quoting accuracy.
- Fallback analysis is heuristic and chat is extractive when no LLM is configured. DOCX has no fixed
  pages; the fallback assigns approximate virtual pages.
- OCR extracts text, not images or layout; verify quotations and page references against the original.
- The API has no built-in authentication. Put it behind appropriate access controls before handling
  private contracts. LegalMind provides information, not legal advice.
- Run `pip install -r requirements-dev.txt` and `pytest -q` for Python tests; from `frontend/`, run
  `npm run lint` and `npm run build`.
