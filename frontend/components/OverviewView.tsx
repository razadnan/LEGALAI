"use client";

import { Fragment } from "react";
import type { DocumentAnalysis, RiskFinding, UploadResponse } from "@/lib/api";

interface OverviewViewProps {
  analysis: DocumentAnalysis;
  document: UploadResponse;
  risks: RiskFinding[];
  onAsk: () => void;
  onShowRisks: (severity: "high" | "medium" | "low") => void;
}

const counts = (risks: RiskFinding[]) => ({
  high: risks.filter((risk) => risk.severity === "high").length,
  medium: risks.filter((risk) => risk.severity === "medium").length,
  low: risks.filter((risk) => risk.severity === "low").length,
});

export function OverviewView({
  analysis,
  document,
  risks,
  onAsk,
  onShowRisks,
}: OverviewViewProps) {
  const riskCounts = counts(risks);
  const dates = analysis.important_dates;
  const terms = analysis.key_terms;
  const payments = analysis.payment_terms;
  return (
    <>
      <div className="row overview-heading">
        <div>
          <h1>{analysis.document_type}</h1>
          <p className="sub">
            {document.filename} · {document.page_count} pages · analysed
          </p>
        </div>
        <button className="btn" onClick={onAsk} type="button">
          Ask a question →
        </button>
      </div>
      <div className="devnote">
        Overview from the existing DocumentAnalysis model. Risk counts are
        calculated from RiskFinding records.
      </div>
      <div className="grid">
        <section className="card">
          <h2>Parties</h2>
          {analysis.parties.length ? (
            <dl className="kv">
              {analysis.parties.map((party, index) => {
                const match = party.match(/^(.*?) \((.*?)\)$/);
                return (
                  <Fragment key={`${party}-${index}`}>
                    <dt>{match?.[2] || `Party ${index + 1}`}</dt>
                    <dd>{match?.[1] || party}</dd>
                  </Fragment>
                );
              })}
            </dl>
          ) : (
            <p className="small">No parties were identified.</p>
          )}
        </section>
        <section className="card">
          <h2>Key dates &amp; terms</h2>
          <dl className="kv">
            {[...dates, ...terms].map((item, index) => (
              <Fragment key={`${item.label}-${index}`}>
                <dt>{item.label}</dt>
                <dd>
                  {"date" in item ? item.date : item.value}
                  {"page" in item && item.page ? (
                    <span className="small"> · p.{item.page}</span>
                  ) : null}
                </dd>
              </Fragment>
            ))}
            {payments.map((item, index) => (
              <Fragment key={`${item.kind}-${index}`}>
                <dt>{item.kind}</dt>
                <dd>
                  {item.description} {item.amounts.join(", ")}
                  {item.frequency ? <span className="small"> · {item.frequency}</span> : null}
                </dd>
              </Fragment>
            ))}
          </dl>
          {!dates.length && !terms.length && !payments.length && (
            <p className="small">No key dates or terms were identified.</p>
          )}
        </section>
        <section className="card">
          <h2>Compensation</h2>
          {payments.length ? (
            <dl className="kv">
              {payments.map((item, index) => (
                <Fragment key={`${item.kind}-comp-${index}`}>
                  <dt>{item.kind}</dt>
                  <dd>
                    {item.description} {item.amounts.join(", ")}
                  </dd>
                </Fragment>
              ))}
            </dl>
          ) : (
            <p className="small">No compensation terms were identified.</p>
          )}
        </section>
      </div>
      <section className="card">
        <h2>Obligations</h2>
        {analysis.obligations.length ? (
          <ul className="obligation-list">
            {analysis.obligations.map((obligation, index) => (
              <li key={`${obligation.description}-${index}`}>
                {obligation.party ? `${obligation.party}: ` : ""}
                {obligation.description}
                {obligation.page ? <span className="small"> · p.{obligation.page}</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="small">No obligations were identified.</p>
        )}
      </section>
      <section className="card row risk-snapshot">
        <div>
          <h2>Risk snapshot</h2>
          <span className="small">{risks.length} clauses flagged for review</span>
        </div>
        <div>
          {(["high", "medium", "low"] as const).map((severity) => (
            <button
              className="chip"
              key={severity}
              onClick={() => onShowRisks(severity)}
              type="button"
            >
              <span className={`sev ${severity}`}>{severity}</span>{" "}
              {riskCounts[severity]}
            </button>
          ))}
        </div>
      </section>
    </>
  );
}
