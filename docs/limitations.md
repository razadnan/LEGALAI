# Scope and Limitations: LegalMind AI

## 1. Document Format & OCR Scope

Current scope supports text-based PDF and DOCX ingestion. Scanned PDFs and image-based documents are not supported in this version. OCR is planned as a future enhancement.

When a scanned PDF without extractable text or an empty document is uploaded, LegalMind AI immediately reports a clean, user-friendly error instructing the user to upload a digital text document.

Extraction accuracy across all structured fields has not been measured. In deterministic fallback mode, `expiry_date` and `data_protection` are always empty, and other values rely on heuristic rules; LLM extraction truncates documents after 24,000 characters, so later content can be missed. Verify extracted values against the source document.

---

## 2. Assistance vs. Legal Advice

LegalMind AI is an assistance tool designed to accelerate human legal review and contract comprehension. It does not provide qualified legal advice and does not substitute for an attorney or legal counsel. All risk findings, missing provisions, and answers must be verified against original document text.

---

## 3. Retrieval and Embedding Boundaries

- Semantic retrieval is grounded in chunk boundaries; multi-clause provisions spanning across separate sections are aligned using internal cross-reference annotations.
- Distance threshold gating (cosine distance > 0.32) actively filters absent provisions to prevent speculative hallucination.
- Verbatim quote validation ensures every displayed citation matches the underlying page text.

---

## 4. API Throttling & Fallback Mode

On constrained API tiers (such as Google AI Studio free tier limits), the platform automatically activates deterministic rule-based analysis and pre-indexed cached responses to maintain reliable, crash-free presentation continuity.
