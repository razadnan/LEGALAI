"use client";

import { useState } from "react";
import type { RiskFinding, Severity } from "@/lib/api";

type RiskFilter = "all" | Severity;

interface RisksViewProps {
  risks: RiskFinding[];
  initialFilter?: RiskFilter;
}

function evidenceItems(value: unknown): { page?: number | null; clause?: string | null; text: string }[] {
  if (typeof value === "string") return value ? [{ text: value }] : [];
  if (Array.isArray(value)) {
    return value.flatMap((item) => evidenceItems(item));
  }
  if (value && typeof value === "object") {
    const item = value as { page?: number | null; clause?: string | null; text?: unknown };
    return typeof item.text === "string"
      ? [{ page: item.page, clause: item.clause, text: item.text }]
      : [];
  }
  return [];
}

export function RisksView({ risks, initialFilter = "all" }: RisksViewProps) {
  const [filter, setFilter] = useState<RiskFilter>(initialFilter);
  const visible = risks.filter((risk) => filter === "all" || risk.severity === filter);
  return (
    <>
      <h1>Clauses worth a closer look</h1>
      <p className="sub">
        Every flag shows its evidence. These are prompts for discussion with a
        lawyer, not legal advice.
      </p>
      <div className="devnote">
        RiskFinding records with evidence verification from the existing workflow.
      </div>
      <div className="tabs" role="group" aria-label="Filter risks">
        {(["all", "high", "medium", "low"] as const).map((item) => (
          <button
            aria-pressed={filter === item}
            className={`chip${filter === item ? " selected" : ""}`}
            key={item}
            onClick={() => setFilter(item)}
            type="button"
          >
            {item[0].toUpperCase() + item.slice(1)}
          </button>
        ))}
      </div>
      {visible.length ? (
        visible.map((risk, index) => {
          const evidence = evidenceItems(risk.evidence);
          return (
            <article className={`card risk ${risk.severity}`} key={`${risk.risk_id}-${index}`}>
              <div className="row">
                <b>{risk.title || risk.clause || "Flagged clause"}</b>
                <span className={`sev ${risk.severity}`}>{risk.severity}</span>
              </div>
              <p className="risk-explanation">{risk.explanation}</p>
              {evidence.map((item, evidenceIndex) => (
                <div className="ev" key={`${item.clause}-${evidenceIndex}`}>
                  <b>
                    {item.clause || risk.clause
                      ? `Clause ${item.clause || risk.clause}`
                      : "Evidence"}
                    {item.page || risk.page ? ` · p.${item.page || risk.page}` : ""}
                  </b>
                  <br />
                  <mark>{item.text}</mark>
                </div>
              ))}
              {risk.verified === false && (
                <div className="warn">
                  This evidence could not be verified against the uploaded document.
                </div>
              )}
              {(risk.lawyer_question || risk.suggested_question) && (
                <p className="small lawyer-question">
                  💡 Ask a lawyer: {risk.lawyer_question || risk.suggested_question}
                </p>
              )}
            </article>
          );
        })
      ) : (
        <div className="card small">
          {risks.length ? "No risks match this filter." : "No risk findings were returned."}
        </div>
      )}
    </>
  );
}
