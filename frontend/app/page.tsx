"use client";

import { useCallback, useEffect, useState } from "react";
import {
  askQuestion,
  compareDocuments,
  getOverview,
  getRisks,
  uploadDocument,
  type AnswerResult,
  type ComparisonResult,
  type DocumentAnalysis,
  type RiskFinding,
  type UploadResponse,
} from "@/lib/api";
import { ChatView } from "@/components/ChatView";
import { CompareView } from "@/components/CompareView";
import { OverviewView } from "@/components/OverviewView";
import { ReportView } from "@/components/ReportView";
import { RisksView } from "@/components/RisksView";
import { Sidebar, type ViewName } from "@/components/Sidebar";
import { UploadView } from "@/components/UploadView";
import type { Severity } from "@/lib/api";

export default function Home() {
  const [active, setActive] = useState<ViewName>("upload");
  const [document, setDocument] = useState<UploadResponse | null>(null);
  const [initialQuestion, setInitialQuestion] = useState("");
  const [analysis, setAnalysis] = useState<DocumentAnalysis | null>(null);
  const [risks, setRisks] = useState<RiskFinding[]>([]);
  const [riskFilter, setRiskFilter] = useState<"all" | Severity>("all");
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [revisedDocumentId, setRevisedDocumentId] = useState<string | null>(null);
  const [notes, setNotes] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const saved = window.localStorage.getItem("legalmind-theme");
    if (saved === "light" || saved === "dark") {
      window.document.documentElement.dataset.theme = saved;
    }
  }, []);

  useEffect(() => {
    window.document.body.classList.toggle("dev", notes);
  }, [notes]);

  useEffect(() => {
    if (!document || !["overview", "risks"].includes(active)) return;
    let activeRequest = true;

    const load = async () => {
      try {
        if (active === "overview") {
          const [overviewData, riskData] = await Promise.all([
            getOverview(document.document_id),
            getRisks(document.document_id),
          ]);
          if (activeRequest) {
            setAnalysis(overviewData);
            setRisks(riskData);
          }
        } else {
          const riskData = await getRisks(document.document_id);
          if (activeRequest) setRisks(riskData);
        }
      } catch (reason) {
        if (activeRequest) {
          setError(reason instanceof Error ? reason.message : "The document data could not be loaded.");
        }
      } finally {
        if (activeRequest) setLoadedFor(document.document_id);
      }
    };
    void load();
    return () => {
      activeRequest = false;
    };
  }, [active, document]);

  const handleUpload = useCallback((file: File) => uploadDocument(file), []);

  const onUploaded = useCallback((result: UploadResponse, question: string) => {
    setDocument(result);
    setInitialQuestion(question);
    setAnalysis(null);
    setRisks([]);
    setLoadedFor(null);
    setComparison(null);
    setRevisedDocumentId(null);
    setNotice(result.warnings.join(" "));
    setError(
      result.analysis_status === "completed"
        ? ""
        : "The document was uploaded and indexed, but some analysis may be incomplete.",
    );
    setActive(question ? "chat" : "overview");
  }, []);

  const onAsk = useCallback(
    (question: string): Promise<AnswerResult> => {
      if (!document) return Promise.reject(new Error("Upload a document first."));
      return askQuestion(document.document_id, question);
    },
    [document],
  );

  const onCompare = useCallback(
    async (file?: File, selectedId?: string) => {
      if (!document) throw new Error("Upload an original document first.");
      const response = await compareDocuments(
        document.document_id,
        file,
        selectedId,
      );
      setRevisedDocumentId(response.revised_document_id);
      setComparison(response.comparison);
    },
    [document],
  );

  function changeTheme() {
    const root = window.document.documentElement;
    const isDark =
      root.dataset.theme === "dark" ||
      (!root.dataset.theme &&
        window.getComputedStyle(root).getPropertyValue("--bg").trim() === "#10131c");
    const next = isDark ? "light" : "dark";
    root.dataset.theme = next;
    window.localStorage.setItem("legalmind-theme", next);
  }

  function navigate(view: ViewName) {
    setError("");
    if (view !== "chat") setInitialQuestion("");
    setActive(view);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const loading =
    Boolean(document) &&
    (active === "overview" || active === "risks") &&
    loadedFor !== document?.document_id;

  return (
    <div className="app">
      <Sidebar
        active={active}
        notes={notes}
        onNavigate={navigate}
        onNotes={setNotes}
        onTheme={changeTheme}
        ready={Boolean(document)}
      />
      <main>
        {error && <div className="error-banner" role="alert">{error}</div>}
        {notice && <div className="warning-banner" role="status">{notice}</div>}
        {loading && (
          <div className="small" role="status">Loading document analysis…</div>
        )}
        {active === "upload" && (
          <UploadView onUploaded={onUploaded} onUpload={handleUpload} />
        )}
        {active === "overview" &&
          (analysis && document ? (
            <OverviewView
              analysis={analysis}
              document={document}
              onAsk={() => navigate("chat")}
              onShowRisks={(severity) => {
                setRiskFilter(severity);
                navigate("risks");
              }}
              risks={risks}
            />
          ) : !loading ? (
            <div className="card small">No overview data is available yet.</div>
          ) : null)}
        {active === "chat" && (
          <ChatView
            initialQuestion={initialQuestion}
            onAsk={onAsk}
          />
        )}
        {active === "risks" && (
          <RisksView initialFilter={riskFilter} risks={risks} />
        )}
        {active === "compare" && document && (
          <CompareView
            onCompare={onCompare}
            onReset={() => {
              setComparison(null);
              setRevisedDocumentId(null);
            }}
            original={document}
            result={comparison}
            revisedDocumentId={revisedDocumentId}
          />
        )}
        {active === "report" && document && (
          <ReportView
            comparisonDocumentId={revisedDocumentId}
            document={document}
          />
        )}
      </main>
    </div>
  );
}
