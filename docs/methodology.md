# Methodology (Developer 3)

**Testing.** `tests/test_agents.py` verifies the routing table from the project plan, plan building, input sanitising,
schema tolerance and citation/evidence verification. `tests/test_integration.py` runs the whole pipeline (upload → extract →
analyze → ask → risk → compare → PDF) on synthetic DOCX/PDF contracts using the fallback services.

**What the tests do not prove.** They validate orchestration and traceability, not LLM answer quality. Retrieval relevance,
extraction accuracy and risk-finding quality must be measured by Developers 1 and 2 on their own labelled samples; report only
measured numbers.

**Security.** Contracts are untrusted data (prompt-injection risk); secrets stay in `.env`; agents cannot take actions beyond
returning analysis; no external network calls are made by the orchestration layer.
