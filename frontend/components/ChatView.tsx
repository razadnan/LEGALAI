"use client";

import { useState } from "react";
import type { AnswerResult, Source } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  text: string;
  answer?: AnswerResult;
}

interface ChatViewProps {
  onAsk: (question: string) => Promise<AnswerResult>;
  initialQuestion?: string;
}

function EvidenceText({ text }: { text: string }) {
  const trimmed = text.trim();
  const end = trimmed.search(/[.!?](?:\s|$)/);
  const splitAt = end >= 0 ? end + 1 : Math.min(trimmed.length, 180);
  return (
    <>
      <mark>{trimmed.slice(0, splitAt)}</mark>
      {trimmed.slice(splitAt)}
    </>
  );
}

function sourceLabel(source: Source) {
  const clause = source.clause ? `Clause ${source.clause}` : "Clause";
  return `${clause} · p.${source.page ?? "—"}`;
}

export function ChatView({ onAsk, initialQuestion = "" }: ChatViewProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState(initialQuestion);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [openSources, setOpenSources] = useState<Record<string, boolean>>({});

  async function send(value = question) {
    const text = value.trim();
    if (!text || busy) return;
    setQuestion("");
    setError("");
    setMessages((current) => [...current, { role: "user", text }]);
    setBusy(true);
    try {
      const answer = await onAsk(text);
      setMessages((current) => [...current, { role: "assistant", text: answer.answer, answer }]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The question could not be answered.");
    } finally {
      setBusy(false);
    }
  }

  const suggestions = [
    "What is my notice period?",
    "How much is the salary?",
    "Can I work for a competitor?",
    "What is confidential?",
    "Does it cover vacation leave?",
  ];

  return (
    <>
      <h1>Ask the document</h1>
      <p className="sub">
        Answers come only from your contract and always show the supporting
        clause and page.
      </p>
      <div className="devnote">
        Supervisor → RAG answer_question(document_id, question) → verified sources
      </div>
      <section className="card">
        <div aria-live="polite" className="chat">
          {messages.map((message, index) => (
            <div className={`msg ${message.role === "user" ? "u" : "a"}`} key={`${index}-${message.role}`}>
              {message.text}
              {message.answer && (
                <>
                  {(!message.answer.grounded || message.answer.warnings.length > 0) && (
                    <div className="warn">
                      {!message.answer.grounded
                        ? "No supporting clause found, so this answer should not be relied on."
                        : message.answer.warnings.join(" ")}
                    </div>
                  )}
                  {message.answer.sources.length > 0 && (
                    <div className="source-chips">
                      {message.answer.sources.map((source, sourceIndex) => {
                        const key = `${index}-${sourceIndex}`;
                        return (
                          <button
                            aria-expanded={Boolean(openSources[key])}
                            className="chip"
                            key={key}
                            onClick={() =>
                              setOpenSources((current) => ({ ...current, [key]: !current[key] }))
                            }
                            type="button"
                          >
                            📎 {sourceLabel(source)}
                          </button>
                        );
                      })}
                      {message.answer.sources.map((source, sourceIndex) => {
                        const key = `${index}-${sourceIndex}`;
                        return openSources[key] ? (
                          <div className="ev" key={`evidence-${key}`}>
                            <b>
                              {source.clause ? `Clause ${source.clause}` : "Supporting text"}
                              {source.page ? ` · page ${source.page}` : ""}
                            </b>
                            <br />
                            <EvidenceText text={source.text} />
                          </div>
                        ) : null;
                      })}
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
          {busy && <div className="msg a small">Searching clauses…</div>}
        </div>
        <div className="suggestions">
          {suggestions.map((suggestion) => (
            <button
              className="chip"
              disabled={busy}
              key={suggestion}
              onClick={() => void send(suggestion)}
              type="button"
            >
              {suggestion}
            </button>
          ))}
        </div>
        <form
          className="inp"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <input
            aria-label="Ask about any clause"
            autoComplete="off"
            maxLength={1000}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about any clause…"
            value={question}
          />
          <button className="btn" disabled={busy || !question.trim()} type="submit">
            Send
          </button>
        </form>
        {error && <div className="warn">{error}</div>}
      </section>
    </>
  );
}
