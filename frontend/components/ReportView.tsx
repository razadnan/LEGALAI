"use client";

import { useEffect, useState } from "react";
import {
  downloadReport,
  getReportPreview,
  type ReportPreview as ReportPreviewData,
  type ReportSection,
  type UploadResponse,
} from "@/lib/api";

const sectionOptions: { id: ReportSection; label: string }[] = [
  { id: "summary", label: "Summary & parties" },
  { id: "key_terms", label: "Key dates and compensation" },
  { id: "obligations", label: "Obligations" },
  { id: "risks", label: "Risk findings with evidence" },
  { id: "comparison", label: "Version comparison" },
];

interface ReportViewProps {
  document: UploadResponse;
  comparisonDocumentId: string | null;
}

export function ReportView({ document, comparisonDocumentId }: ReportViewProps) {
  const [selected, setSelected] = useState<ReportSection[]>([
    "summary",
    "key_terms",
    "obligations",
    "risks",
    ...(comparisonDocumentId ? (["comparison"] as const) : []),
  ]);
  const [preview, setPreview] = useState<{
    signature: string;
    data: ReportPreviewData;
  } | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");
  const signature = JSON.stringify([selected, comparisonDocumentId]);

  useEffect(() => {
    let active = true;
    getReportPreview(document.document_id, selected, comparisonDocumentId || undefined)
      .then((data) => {
        if (active) setPreview({ signature, data });
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Preview could not be generated.");
      });
    return () => {
      active = false;
    };
  }, [document.document_id, comparisonDocumentId, selected, signature]);

  async function generate() {
    setDownloading(true);
    setError("");
    try {
      const { blob, filename } = await downloadReport(
        document.document_id,
        selected,
        comparisonDocumentId || undefined,
      );
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The PDF could not be generated.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <>
      <h1>Generate report</h1>
      <p className="sub">Choose what to include, preview it, then download.</p>
      <div className="devnote">
        ReportLab generates the downloadable PDF from the selected existing analysis results.
      </div>
      <div className="grid report-grid">
        <section className="card">
          <h2>Sections</h2>
          {sectionOptions.map((option) => (
            <label className="check" key={option.id}>
              <input
                checked={selected.includes(option.id)}
                disabled={option.id === "comparison" && !comparisonDocumentId}
                onChange={(event) => {
                  setError("");
                  setSelected((current) =>
                    event.target.checked
                      ? [...current, option.id]
                      : current.filter((value) => value !== option.id),
                  );
                }}
                type="checkbox"
              />
              {option.label}
              {option.id === "comparison" && !comparisonDocumentId ? (
                <span className="small"> (compare documents first)</span>
              ) : null}
            </label>
          ))}
          <p>
            <button className="btn" disabled={downloading} onClick={() => void generate()} type="button">
              {downloading ? "Generating…" : "Generate PDF"}
            </button>
          </p>
          {error && <div className="warn">{error}</div>}
          {downloading && <div className="small">Generating your PDF…</div>}
        </section>
        <section className="card">
          <h2>Preview</h2>
          {preview?.signature !== signature && !error && (
            <p className="small">Updating preview…</p>
          )}
          <div
            className="paper"
            dangerouslySetInnerHTML={{
              __html: preview?.signature === signature ? preview.data.preview_html : "",
            }}
          />
        </section>
      </div>
    </>
  );
}
