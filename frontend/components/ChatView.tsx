"use client";

import { useState } from "react";
import type { AnswerResult, ChatTurn, Source } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  text: string;
  question?: string;
  answer?: AnswerResult;
}

interface ChatViewProps {
  onAsk: (
    question: string,
    history: ChatTurn[],
    simpleLanguage: boolean,
  ) => Promise<AnswerResult>;
  initialQuestion?: string;
}

const AGENT_LABELS: Record<string, string> = {
  document_agent: "Document",
  risk_agent: "Risk",
  rag_agent: "RAG",
  comparison_agent: "Compare",
  report_generator: "Report",
};

const HIGHLIGHT_STOP_WORDS = new Set([
  "about", "after", "again", "also", "and", "are", "can", "does", "for", "from",
  "have", "how", "into", "its", "may", "not", "our", "that", "the", "their",
  "them", "there", "this", "what", "when", "where", "which", "who", "with",
  "would", "you",
]);

function EvidenceText({ text, question }: { text: string; question: string }) {
  const trimmed = text.trim();
  const sentences = trimmed.split(/(?<=[.!?])\s+|\n+/).filter(Boolean);
  const queryTerms = new Set(
    (question.toLowerCase().match(/[a-z0-9]+/g) ?? [])
      .filter((term) => term.length > 2 && !HIGHLIGHT_STOP_WORDS.has(term)),
  );
  if (!sentences.length || !queryTerms.size) return <>{trimmed}</>;

  let bestIndex = -1;
  let bestScore = 0;
  sentences.forEach((sentence, index) => {
    const terms = new Set(sentence.toLowerCase().match(/[a-z0-9]+/g) ?? []);
    const score = [...queryTerms].filter((term) => terms.has(term)).length;
    if (score > bestScore) {
      bestIndex = index;
      bestScore = score;
    }
  });
  if (bestIndex < 0) return <>{trimmed}</>;

  return (
    <>
      {sentences.map((sentence, index) => (
        <span key={index}>
          {index === bestIndex ? <mark>{sentence}</mark> : sentence}
          {index < sentences.length - 1 ? " " : ""}
        </span>
      ))}
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
  const [simpleLanguage, setSimpleLanguage] = useState(false);

  async function send(value = question) {
    const text = value.trim();
    if (!text || busy) return;
    const history = messages
      .slice(-6)
      .map(({ role, text: content }) => ({ role, content: content.slice(-2000) }));
    setQuestion("");
    setError("");
    setMessages((current) => [...current, { role: "user", text }]);
    setBusy(true);
    try {
      const answer = await onAsk(text, history, simpleLanguage);
      setMessages((current) => [
        ...current,
        { role: "assistant", text: answer.answer, question: text, answer },
      ]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The question could not be answered.");
    } finally {
      setBusy(false);
    }
  }

  const suggestions = [
    "Who are the parties?",
    "What is the notice period?",
    "What are the payment terms?",
    "How can the agreement be terminated?",
  ];

  function agentTrace(agents: string[]) {
    const steps = ["Router", ...agents.map((agent) => AGENT_LABELS[agent] ?? agent)];
    if (agents.includes("rag_agent") || agents.includes("risk_agent")) {
      steps.push("Verifier");
    }
    return steps.join(" → ");
  }

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
                  {message.answer.agents_invoked.length > 0 && (
                    <div className="agent-trace" aria-label="Agent trace">
                      {agentTrace(message.answer.agents_invoked)}
                    </div>
                  )}
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
                            <EvidenceText
                              question={message.question ?? ""}
                              text={source.text}
                            />
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
        {messages.length === 0 && (
          <div className="suggestions" aria-label="Suggested questions">
            <div className="small">Try asking:</div>
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
        )}
        <label className="simple-language">
          <input
            checked={simpleLanguage}
            onChange={(event) => setSimpleLanguage(event.target.checked)}
            type="checkbox"
          />
          Explain simply
        </label>
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
