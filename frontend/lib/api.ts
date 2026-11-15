export type Severity = "low" | "medium" | "high";

export interface Evidence {
  page?: number | null;
  clause?: string | null;
  text: string;
  verified?: boolean | null;
}

export interface ImportantDate {
  label: string;
  date: string;
  value?: string | null;
  iso_date?: string | null;
  page?: number | null;
  evidence?: Evidence | null;
}

export interface KeyTerm {
  label: string;
  value: string;
  evidence?: Evidence | null;
}

export interface PaymentTerm {
  kind: string;
  description: string;
  amounts: string[];
  frequency?: string | null;
  evidence?: Evidence | null;
}

export interface Obligation {
  description: string;
  party?: string | null;
  page?: number | null;
  kind: string;
  text?: string | null;
  category?: string | null;
  evidence?: Evidence | null;
}

export interface RiskFinding {
  clause: string;
  title?: string | null;
  severity: Severity;
  category: string;
  finding_type: string;
  risk_id: string;
  explanation: string;
  evidence: unknown;
  page?: number | null;
  lawyer_question: string;
  suggested_question?: string | null;
  verified?: boolean | null;
}

export interface DocumentAnalysis {
  document_id: string;
  document_type: string;
  classification_basis: string[];
  parties: string[];
  important_dates: ImportantDate[];
  key_terms: KeyTerm[];
  payment_terms: PaymentTerm[];
  obligations: Obligation[];
  key_clauses: { clause_id: string; title: string; category: string; page: number; text: string }[];
  risk_findings: RiskFinding[];
  summary: string;
  notes: string[];
}

export interface Source {
  page?: number | null;
  page_end?: number | null;
  clause?: string | null;
  text: string;
  source_id?: string | null;
  score?: number | null;
  verified?: boolean | null;
}

export interface AnswerResult {
  answer: string;
  sources: Source[];
  grounded: boolean;
  mode: string;
  warnings: string[];
  agents_invoked: string[];
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ComparisonChange {
  change_type: "added" | "removed" | "modified";
  section: string;
  old_text: string;
  new_text: string;
  summary: string;
  old_page?: number | null;
  new_page?: number | null;
}

export interface ComparisonResult {
  summary: string;
  changes: ComparisonChange[];
}

export interface UploadResponse {
  document_id: string;
  filename: string;
  page_count: number;
  status: "ready";
  analysis_status: "completed" | "partial" | "failed";
  warnings: string[];
}

export interface CompareResponse {
  revised_document_id: string;
  comparison: ComparisonResult;
}

export interface ReportPreview {
  preview_html: string;
  filename: string;
}

export type ReportSection =
  | "summary"
  | "key_terms"
  | "obligations"
  | "risks"
  | "comparison";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body: { detail?: unknown } = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((item) =>
            typeof item === "object" && item && "msg" in item
              ? String(item.msg)
              : String(item),
          )
          .join("; ");
      } else if (body.detail !== undefined) message = JSON.stringify(body.detail);
    } catch {
      // Keep the HTTP status message when the server does not return JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const body = new FormData();
  body.append("file", file);
  return request<UploadResponse>("/api/upload", { method: "POST", body });
}

export function getOverview(documentId: string): Promise<DocumentAnalysis> {
  return request<DocumentAnalysis>(
    `/api/documents/${encodeURIComponent(documentId)}/overview`,
  );
}

export function getRisks(documentId: string): Promise<RiskFinding[]> {
  return request<RiskFinding[]>(
    `/api/documents/${encodeURIComponent(documentId)}/risks`,
  );
}

export function askQuestion(
  documentId: string,
  question: string,
  history: ChatTurn[] = [],
  simpleLanguage = false,
): Promise<AnswerResult> {
  return request<AnswerResult>(
    `/api/documents/${encodeURIComponent(documentId)}/chat`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        history: history.slice(-6),
        simple_language: simpleLanguage,
      }),
    },
  );
}

export function compareDocuments(
  documentId: string,
  file?: File,
  revisedDocumentId?: string,
): Promise<CompareResponse> {
  const body = new FormData();
  if (file) body.append("file", file);
  if (revisedDocumentId) body.append("revised_document_id", revisedDocumentId);
  return request<CompareResponse>(
    `/api/documents/${encodeURIComponent(documentId)}/compare`,
    { method: "POST", body },
  );
}

export function getReportPreview(
  documentId: string,
  sections: ReportSection[],
  comparisonDocumentId?: string,
): Promise<ReportPreview> {
  return request<ReportPreview>(
    `/api/documents/${encodeURIComponent(documentId)}/report`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sections,
        comparison_document_id: comparisonDocumentId || null,
      }),
    },
  );
}

export async function downloadReport(
  documentId: string,
  sections: ReportSection[],
  comparisonDocumentId?: string,
): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(
    `${API_URL}/api/documents/${encodeURIComponent(documentId)}/report?download=true`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sections,
        comparison_document_id: comparisonDocumentId || null,
      }),
    },
  );
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body: { detail?: unknown } = await response.json();
      if (body.detail !== undefined) message = String(body.detail);
    } catch {
      // Keep the HTTP status message when the server does not return JSON.
    }
    throw new Error(message);
  }
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] || "legalmind_report.pdf";
  return { blob: await response.blob(), filename };
}
