"use client";

export type ViewName =
  | "upload"
  | "overview"
  | "chat"
  | "risks"
  | "compare"
  | "report";

const items: { id: ViewName; icon: string; label: string }[] = [
  { id: "upload", icon: "⬆", label: "Upload" },
  { id: "overview", icon: "▦", label: "Overview" },
  { id: "chat", icon: "💬", label: "Ask AI" },
  { id: "risks", icon: "⚠", label: "Risks" },
  { id: "compare", icon: "⇄", label: "Compare" },
  { id: "report", icon: "⬇", label: "Report" },
];

interface SidebarProps {
  active: ViewName;
  ready: boolean;
  notes: boolean;
  onNavigate: (view: ViewName) => void;
  onTheme: () => void;
  onNotes: (enabled: boolean) => void;
}

export function Sidebar({
  active,
  ready,
  notes,
  onNavigate,
  onTheme,
  onNotes,
}: SidebarProps) {
  return (
    <aside aria-label="Main navigation">
      <div className="logo">
        <i>⚖</i> LegalMind AI
      </div>
      {items.map((item) => {
        const locked = item.id !== "upload" && !ready;
        return (
          <button
            aria-current={active === item.id ? "page" : undefined}
            className={`nav${active === item.id ? " on" : ""}`}
            disabled={locked}
            key={item.id}
            onClick={() => onNavigate(item.id)}
            title={locked ? "Upload and index a document to unlock" : item.label}
            type="button"
          >
            <span aria-hidden="true">{item.icon}</span>
            {item.label}
          </button>
        );
      })}
      <div className="spacer" />
      <label className="chip hide-m team-toggle">
        <input
          checked={notes}
          onChange={(event) => onNotes(event.target.checked)}
          type="checkbox"
        />
        Team notes
      </label>
      <button className="chip hide-m theme-button" onClick={onTheme} type="button">
        ◐ Theme
      </button>
      <div className="small hide-m disclaimer">
        AI-assisted analysis.
        <br />
        Not legal advice.
        <br />
        Use anonymised contracts for demos.
      </div>
    </aside>
  );
}
