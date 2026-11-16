# Expected Results Reference Card: LegalMind AI

Keep this card handy during your live demo rehearsal and presentation.

---

## 1. Document Extraction Targets (`Apex_Global_MSA_2026.pdf`)

| Field | Expected Ground Truth | Source Reference |
|---|---|---|
| Document Type | Master Services Agreement | Title |
| Provider | Apex Cloud Solutions Inc. (Delaware) | Preamble |
| Client | Global Dynamics Retail LLC (California) | Preamble |
| Effective Date | January 15, 2026 | Preamble |
| Initial Term | 3 years | Clause 1.2 |
| Annual Base Fee | $240,000 | Clause 2.1 |
| Payment Installments | $60,000 quarterly in advance | Clause 2.1 |
| Payment Terms | 30 days from receipt | Clause 2.2 |
| Convenience Notice | 90 days prior written notice | Clause 3.1 |
| Immediate Termination | 10 days overdue notice (unilateral by Provider) | Clause 3.2 |
| Confidentiality Period | 5 years surviving termination | Clause 4.2 |
| Liability Cap | Capped at 3 months of fees paid | Clause 7.2 |
| Non-Solicitation | 24 months post-termination | Clause 8.1 |
| Governing Law | State of New York | Clause 9.1 |
| Jurisdiction | State and federal courts in New York County | Clause 9.2 |

---

## 2. Five Demo Questions & Verdicts

1. **What is the annual base subscription fee?**
   - *Verdict:* Supported
   - *Answer:* The annual base subscription fee is $240,000.
   - *Citation:* Page 1, Clause 2.1
   - *Quote:* "Client shall pay Provider an annual base subscription fee of $240,000, payable quarterly in advance in installments of $60,000."

2. **What is the notice period for convenience termination?**
   - *Verdict:* Supported
   - *Answer:* 90 days prior written notice.
   - *Citation:* Page 1, Clause 3.1
   - *Quote:* "Either party may terminate this Agreement for convenience upon ninety (90) days prior written notice."

3. **What is the liability cap under this contract?**
   - *Verdict:* Supported
   - *Answer:* Strictly capped at the fees actually paid in the 3 months preceding the claim.
   - *Citation:* Page 2, Clause 7.2
   - *Quote:* "PROVIDER'S TOTAL AGGREGATE LIABILITY ARISING UNDER THIS AGREEMENT SHALL BE STRICTLY CAPPED AT THE FEES ACTUALLY PAID BY CLIENT IN THE THREE (3) MONTHS PRECEDING THE CLAIM."

4. **Which law governs this agreement?**
   - *Verdict:* Supported
   - *Answer:* Laws of the State of New York (exclusive venue New York County).
   - *Citation:* Page 2, Clause 9.1
   - *Quote:* "This Agreement shall be governed by and construed in accordance with the laws of the State of New York, without regard to conflict of laws principles."

5. **Is there an SLA in this contract?**
   - *Verdict:* not_found
   - *Answer:* "The uploaded document does not contain information sufficient to answer this question."
   - *Citation:* None (sources empty)
   - No unsupported citations or invented numeric values were detected in the tested benchmark.

---

## 3. Comparison Diff Targets

| Item | Version A (Original) | Version B (Revised) | Change Type |
|---|---|---|---|
| Annual Fee | $240,000 | $300,000 | Modified |
| Notice Period | 90 days | 120 days | Modified |
| Liability Cap | 3 months fees | 12 months fees | Modified |
