# Live Demonstration Script: LegalMind AI

Follow this script step-by-step during your presentation.

---

## Step 1: Introduction
**Say:**
> "LegalMind AI is an AI-assisted contract-intelligence prototype. It extracts structured information from legal documents, answers document-specific questions with citations, identifies risks and missing safeguards, compares contract versions, and generates a downloadable report. It assists human legal review; it does not replace legal advice."

---

## Step 2: Upload
1. Navigate to the **⬆ Upload** tab.
2. Select or drag-and-drop `demo/Apex_Global_MSA_2026.pdf`.
3. Click **Process document ⚡**.
4. **Show to audience:**
   - Document ID (e.g. `DOC001`)
   - Page count (2 pages)
   - Document type (*Master Services Agreement*)
   - Parties (*Apex Cloud Solutions Inc.* and *Global Dynamics Retail LLC*)
   - Green processing completion checkmark

---

## Step 3: Overview
1. Navigate to the **▦ Overview** tab.
2. **Show to audience:**
   - Parties: Provider and Client
   - Key dates: Effective date (*January 15, 2026*)
   - Governing law: *New York*
   - Annual fee: *$240,000*
   - Payment schedule: *Quarterly in advance ($60,000)*
   - Notice period: *90 days written notice*
   - Liability cap: *Fees paid in 3 preceding months*
   - Key obligations table

---

## Step 4: Ask AI
1. Navigate to the **💬 Ask AI** tab.
2. Submit the five fixed questions in this exact order:
   - **Q1:** `"What is the annual base subscription fee?"`
     - *Expected:* $240,000 with citation to Page 1, Clause 2.1.
   - **Q2:** `"What is the notice period for convenience termination?"`
     - *Expected:* 90 days with citation to Page 1, Clause 3.1.
   - **Q3:** `"What is the liability cap under this contract?"`
     - *Expected:* 3 months fees with citation to Page 2, Clause 7.2.
   - **Q4:** `"Which law governs this agreement?"`
     - *Expected:* New York law with citation to Page 2, Clause 9.1.
   - **Q5:** `"Is there an SLA in this contract?"`
     - *Expected:* `"The uploaded document does not contain information sufficient to answer this question."` (not_found, zero hallucinated text).

---

## Step 5: Risks & Missing Safeguards
1. Navigate to the **⚠ Risks** tab.
2. **Show to audience:**
   - Three risk findings, each with quote, page, severity, affected party, and recommended action.
   - Missing-clause checklist:
     - **Four clearly absent provisions:** Insurance, Change Management, Acceptance Criteria, SLA & Uptime.
     - **Two absent-or-partial provisions:** Data Protection, Breach Remedies.
3. **Say:**
   > "These are potential review points, not legal advice."

---

## Step 6: Compare
1. Navigate to the **⇄ Compare** tab.
2. Select `Apex_Global_MSA_2026.pdf` as the original version.
3. Upload or select `demo/Apex_Global_MSA_2026_Rev2.pdf` as the revised version.
4. Click **⇄ Compare**.
5. **Show to audience:**
   - Fee change: $240,000 to $300,000 (Clause 2.1)
   - Notice change: 90 days to 120 days (Clause 3.1)
   - Liability cap change: 3 months to 12 months (Clause 7.2)
   - Red `<del>` and green `<ins>` comparison diff cards.

---

## Step 7: Report
1. Navigate to the **⬇ Report** tab.
2. Select sections to include (Summary, Key Terms, Obligations, Risks, Comparison).
3. Click **Generate PDF Report**.
4. Download and open the generated PDF.
5. **Show to audience:**
   - Executive summary
   - Key terms table
   - Risk matrix
   - Missing provisions checklist
   - Comparison results
   - Evidence citations and legal disclaimer
