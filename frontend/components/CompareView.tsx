"use client";

import { useState } from "react";
import type { ComparisonResult, UploadResponse } from "@/lib/api";

interface CompareViewProps {
  original: UploadResponse;
  revisedDocumentId: string | null;
  result: ComparisonResult | null;
  onCompare: (file?: File, revisedDocumentId?: string) => Promise<void>;
  onReset: () => void;
}

type CompareFilter = "all" | "modified" | "added" | "removed";

export function CompareView({
  original,
  revisedDocumentId,
  result,
  onCompare,
  onReset,
}: CompareViewProps) {
  const [filter, setFilter] = useState<CompareFilter>("all");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function compare() {
    if (!selectedFile && !selectedId.trim()) {
      setError("Choose a revised PDF or DOCX, or enter its document ID.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onCompare(selectedFile || undefined, selectedId.trim() || undefined);
      setSelectedFile(null);
      setSelectedId("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The documents could not be compared.");
    } finally {
      setBusy(false);
    }
  }

  if (!result) {
    return (
      <>
        <h1>Compare two versions</h1>
        <p className="sub">
          Upload the revised agreement or select an already indexed document to
          see what changed, clause by clause.
        </p>
        <div className="devnote">
          Existing comparison workflow aligns clauses and reports added,
          removed, and modified text.
        </div>
        <div className="grid">
          <section className="card">
            <h2>Original</h2>
            <p>📄 {original.filename}</p>
            <span className="chip">✓ Indexed · {original.document_id}</span>
          </section>
          <section className="card">
            <h2>Revised version</h2>
            <p className="small">Upload a second contract or provide an indexed document ID.</p>
            <label className="field-label" htmlFor="revised-file">Revised file</label>
            <input
              accept=".pdf,.docx"
              id="revised-file"
              onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
              type="file"
            />
            <label className="field-label" htmlFor="revised-id">Or document ID</label>
            <input
              id="revised-id"
              onChange={(event) => setSelectedId(event.target.value)}
              placeholder="DOC002"
              value={selectedId}
            />
            <button className="btn compare-button" disabled={busy} onClick={() => void compare()} type="button">
              {busy ? "Comparing…" : "Compare versions"}
            </button>
            {error && <div className="warn">{error}</div>}
          </section>
        </div>
        {revisedDocumentId && (
          <p className="small">Last compared against document {revisedDocumentId}.</p>
        )}
      </>
    );
  }

  const changes = result.changes.filter(
    (change) => filter === "all" || change.change_type === filter,
  );
  const count = (type: CompareFilter) =>
    type === "all"
      ? result.changes.length
      : result.changes.filter((change) => change.change_type === type).length;

  return (
    <>
      <h1>What changed</h1>
      <p className="sub">
        {original.filename} → {revisedDocumentId || "revised document"}
      </p>
      <div className="devnote">
        {result.summary || `${result.changes.length} detected change(s)`}
      </div>
      <div className="tabs" role="group" aria-label="Filter comparison changes">
        {(["all", "modified", "added", "removed"] as const).map((item) => (
          <button
            aria-pressed={filter === item}
            className={`chip${filter === item ? " selected" : ""}`}
            key={item}
            onClick={() => setFilter(item)}
            type="button"
          >
            {item[0].toUpperCase() + item.slice(1)} {count(item)}
          </button>
        ))}
        <button className="chip" onClick={onReset} type="button">
          Compare another
        </button>
      </div>
      {changes.map((change, index) => (
        <article className="card" key={`${change.section}-${index}`}>
          <div className="row">
            <b>
              {change.section || "Contract text"}{" "}
              <span className="small">· {change.change_type}</span>
            </b>
            <span className={`sev ${change.change_type === "removed" ? "high" : "low"}`}>
              {change.change_type}
            </span>
          </div>
          {change.summary && <p className="change-summary">{change.summary}</p>}
          <div className="cmp">
            <div className="pane">
              <h4>Original{change.old_page ? ` · p.${change.old_page}` : ""}</h4>
              {change.old_text ? <del>{change.old_text}</del> : "— not present —"}
            </div>
            <div className="pane">
              <h4>Revised{change.new_page ? ` · p.${change.new_page}` : ""}</h4>
              {change.new_text ? <ins>{change.new_text}</ins> : "— not present —"}
            </div>
          </div>
        </article>
      ))}
      {!changes.length && <div className="card small">No changes match this filter.</div>}
    </>
  );
}
