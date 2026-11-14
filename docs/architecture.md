# Architecture (Developer 3 layer)

```
Streamlit (app.py, ui/*)
   │  run_workflow(task, document_ids, question)      process_upload(filename, bytes)
   ▼
orchestration/workflow.py ──► DocumentRegistry (storage/processed/*.json)
   │
   ▼
SupervisorGraph (LangGraph StateGraph, built-in runner if langgraph missing)

   classify ─► [conditional edge: next unfinished step in plan] ─► finalize
                 ├─ document_agent      (D1 analyze_document, cached per document)
                 ├─ risk_agent          (D1 risk findings + evidence verification)
                 ├─ rag_agent           (D2 answer_question + citation verification)
                 ├─ comparison_agent    (D2 compare_documents)
                 └─ report_generator    (ReportLab PDF)

Services (adapters.py): real D1/D2 modules if importable, else fallbacks.py
```

## Design decisions

- **One conditional edge function (`next_node`)** is shared by every node. A plan (list of steps) is built once in `classify`; each node marks itself complete, so the graph always terminates (each step runs at most once).
- **Error isolation:** each agent node is wrapped; failures become user-safe messages in `result.errors` and the workflow still reaches `finalize`.
- **Verification layer:** `verification.py` compares citations / evidence to the extracted text so invented clauses or pages are flagged.
- **Rule-based intent classification:** deterministic, free, unit-tested. It can be replaced by an LLM classifier inside `classify_intent` without touching the graph.
- **Disk-backed registry:** documents and analyses survive Streamlit reruns; the supervisor only needs document IDs.
- **State shared via one `WorkflowResult` schema:** UI and PDF generator render the same object.
