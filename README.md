# LegalMind AI

Agentic legal document intelligence and contract analysis. The existing Python workflow remains the
backend; `api/` exposes it through FastAPI and `frontend/` contains the Next.js App Router UI.

## Quick start

### FastAPI backend

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-api.txt
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
Python wrapper dependency is included in `requirements-api.txt`. On Windows, Tesseract can be
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

## What Developer 3 delivers

| File | Purpose |
|---|---|
| `api/main.py` | FastAPI routes wrapping the existing upload and workflow entry points |
| `frontend/` | Next.js App Router application, typed API client, and modular views |
| `app.py`, `ui/` | Existing Streamlit interface (retained) |
| `orchestration/supervisor.py` | LangGraph supervisor: intent classification, conditional routing, error isolation |
| `orchestration/workflow.py` | `run_workflow(...)` and `process_upload(...)` - the interface for the UI |
| `orchestration/adapters.py` | `Services`: calls real D1/D2 modules, falls back if absent |
| `orchestration/verification.py` | Verifies every citation and risk evidence against the document text |
| `orchestration/fallbacks.py` | Heuristic stand-ins so the app runs before D1/D2 are merged (no LLM) |
| `reports/report_generator.py` | ReportLab PDF report |
| `config/settings.py`, `config/prompts.py` | Settings from `.env`; shared untrusted-document prompt helpers |
| `core/schemas.py`, `core/state.py`, `core/exceptions.py` | Shared Pydantic contract, disk-backed document registry, errors |

## Integration contract (what D1 / D2 must expose)

`Services` imports these names; if a module or function is missing it uses the fallback and says so
on the Dashboard ("Module status").

```text
document_intelligence.document_processor.process_document(file_path, document_id) -> dict   # DocumentData
document_intelligence.document_agent.analyze_document(document_data: dict)         -> dict   # DocumentAnalysis
document_intelligence.risk_analyzer.analyze_risks(document_data: dict)             -> list[dict]
rag_engine.retrieval.index_document(document_data: dict)                           -> None
rag_engine.chat_engine.answer_question(document_id, question)                      -> dict   # {answer, sources[{page, clause, text}]}
rag_engine.comparison_agent.compare_documents(doc_a: dict, doc_b: dict)            -> dict   # {summary, changes[...]}
```

Schemas (`core/schemas.py`) are tolerant of small variations (plain strings for parties/dates, `title`
vs `clause`, `reason` vs `explanation`), but agree on the exact shapes on Day 1.
If your real function names differ, edit `_CANDIDATES` at the top of `orchestration/adapters.py` (one line each).

Merge note: `core/schemas.py` is the single shared schema file - D1/D2 should import from it rather than
define their own.

## Supervisor routing

| Request | Agents |
|---|---|
| Summarize / who are the parties? | document |
| Explain clause 8 / what is the notice period? | rag |
| Identify risks / clauses for legal review | document → risk |
| Compare two contracts | comparison |
| Generate analysis report | document → risk → (rag) → (comparison) → report |

Routing is rule-based (deterministic and testable). Free-text chat uses `task="auto"`.

## Retrieval evaluation

`tests/fixtures/rag_retrieval_benchmark.json` contains 37 manually labeled questions against a
synthetic employment agreement. By default, the benchmark uses deterministic offline hash
embeddings and a temporary in-memory vector store:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py
```

The script reports Recall@1/3/5 and MRR, validates that every gold clause exists in the fixture, and
prints each query's first relevant rank. This is a small smoke benchmark, not a representative
measure of production legal-document accuracy. Expand the labeled dataset across independently
reviewed documents before making quality claims or evaluating a reranker.

To compare a local cross-encoder against RRF, first install the optional evaluation dependency and
run the same candidate pool through both rankers. Cross-encoder loading is local-only, so the model
must already be cached:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-eval.txt
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

## Safeguards implemented

- Uploaded contracts are untrusted: `config/prompts.py` provides `wrap_untrusted()` for prompts; chat input is sanitized and instruction-like text is flagged.
- Citations and risk evidence are verified against the extracted text/page; unverifiable ones are flagged in the UI and PDF - never silently shown as fact.
- File validation: extension, size, magic bytes, path-traversal-safe names, empty/scanned PDF detection.
- Each agent runs in an error guard: one failing agent returns a friendly message instead of crashing the app.
- `.env` is git-ignored; storage contents are git-ignored.

## Known limitations (be upfront in the demo)

- Fallback modules are keyword/regex heuristics, not AI. Only the real D1/D2 modules give LLM/RAG quality.
- DOCX has no fixed pages, so the fallback uses ~3000-character "virtual pages".
- Scanned PDFs (OCR) are not supported. The API does not provide authentication; protect it with an
  authenticated gateway or equivalent access controls before exposing private contracts publicly.
- Run `pytest -q` for the Python suite and, from `frontend/`, `npm run lint` and `npm run build`.
- Passing tests show the code works, not that AI accuracy is good - measure extraction/retrieval quality on your own sample contracts before quoting percentages.
