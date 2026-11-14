"use client";

import { useRef, useState } from "react";
import type { UploadResponse } from "@/lib/api";

const steps = [
  "Extracting text and page numbers",
  "Detecting document type and parties",
  "Splitting into clauses",
  "Creating embeddings and indexing",
  "Preparing risk review",
];

interface UploadViewProps {
  onUploaded: (result: UploadResponse, question: string) => void;
  onUpload: (file: File) => Promise<UploadResponse>;
}

export function UploadView({ onUploaded, onUpload }: UploadViewProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(-1);
  const [filename, setFilename] = useState("");
  const [error, setError] = useState("");
  const [question, setQuestion] = useState("");

  async function submit(file: File) {
    setError("");
    if (!/\.(pdf|docx|jpe?g|png|tiff?)$/i.test(file.name)) {
      setError("Upload a PDF, DOCX, JPG, PNG, or TIFF file.");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      setError("This file is larger than 20 MB.");
      return;
    }
    setFilename(file.name);
    setBusy(true);
    setStep(0);
    const timer = window.setInterval(
      () => setStep((current) => Math.min(current + 1, steps.length - 1)),
      900,
    );
    try {
      const result = await onUpload(file);
      window.clearInterval(timer);
      setStep(steps.length);
      onUploaded(result, question.trim());
    } catch (reason) {
      window.clearInterval(timer);
      setBusy(false);
      setStep(-1);
      setError(reason instanceof Error ? reason.message : "The upload failed.");
    }
  }

  const progress = step < 0 ? 0 : Math.min(100, Math.round((step / steps.length) * 100));

  return (
    <>
      <h1>Upload a contract</h1>
      <p className="sub">
        PDF or DOCX documents, scanned PDFs, or JPG, PNG, and TIFF scans. Use
        synthetic or anonymised contracts for demos.
      </p>
      <div className="devnote">
        Local Tesseract OCR is used for scanned PDFs and images before the
        existing document processing and indexing workflow.
      </div>
      <div
        className={`drop${dragging ? " over" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          setDragging(false);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file) void submit(file);
        }}
      >
        <div className="upload-icon" aria-hidden="true">
          📄
        </div>
        <p>
          <b>Drag &amp; drop your contract here</b>
          <br />
          <span className="small">
            PDF · DOCX · JPG/JPEG · PNG · TIFF · up to 20 MB
          </span>
        </p>
        <input
          accept=".pdf,.docx,.jpg,.jpeg,.png,.tif,.tiff"
          className="visually-hidden"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void submit(file);
            event.currentTarget.value = "";
          }}
          ref={inputRef}
          type="file"
        />
        <button
          className="btn"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
          type="button"
        >
          Choose file
        </button>
        <label className="upload-question-label" htmlFor="upload-question">
          Ask a question after upload (optional)
        </label>
        <textarea
          id="upload-question"
          maxLength={1000}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="For example: What is the termination notice period?"
          value={question}
        />
        <div aria-live="polite" className="warn upload-error">
          {error}
        </div>
      </div>
      {(busy || step === steps.length) && (
        <div className="card">
          <div className="row">
            <b>{filename}</b>
            <span className="small">{step === steps.length ? "100%" : `${progress}%`}</span>
          </div>
          <div
            aria-label="Upload progress"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={step === steps.length ? 100 : progress}
            className="bar"
            role="progressbar"
          >
            <b style={{ width: `${step === steps.length ? 100 : progress}%` }} />
          </div>
          <ul className="steps">
            {steps.map((label, index) => {
              const done = step === steps.length || index < step;
              const running = step < steps.length && index === step;
              return (
                <li
                  className={done ? "done" : running ? "run" : ""}
                  key={label}
                >
                  {done ? "✓" : running ? "◔" : "○"} {label}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </>
  );
}
