import type { ReactNode } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useSearchParams } from "react-router-dom";

// One look for every area: simple cards (title, a line on what it is, its number); a card opens its details, with
// "Back to all" above them. The open card is kept in the address (?open=...), so the browser's Back returns here.

export interface HubCard {
  key: string;
  title: string;
  about: string;
  stat?: ReactNode;                     // the number that matters (count, status)
  statLabel?: string;
  tone?: "good" | "bad" | "warn" | "info";
  icon?: LucideIcon;
  disabled?: string;                    // why it cannot open yet
  onOpen?: () => void;                  // a card that goes elsewhere instead of opening details here
  body?: () => ReactNode;               // its details
}

export function useOpenCard(): [string | null, (key: string | null) => void] {
  const [params, setParams] = useSearchParams();
  const open = params.get("open");
  const set = (key: string | null) => {
    const next = new URLSearchParams(params);
    if (key) next.set("open", key);
    else next.delete("open");
    setParams(next);
    window.scrollTo({ top: 0 });
  };
  return [open, set];
}

export function CardHub({ cards, label = "All" }: { cards: HubCard[]; label?: string }) {
  const [open, setOpen] = useOpenCard();
  const current = cards.find((c) => c.key === open && c.body && !c.disabled);
  if (current) {
    return (
      <div className="hub-detail">
        <div className="hub-back">
          <button type="button" className="btn btn-outline btn-sm" onClick={() => setOpen(null)}>
            <ArrowLeft size={15} aria-hidden="true" /> Back to {label.toLowerCase()}
          </button>
          <h3 className="hub-detail-title">{current.title}</h3>
        </div>
        {current.body!()}
      </div>
    );
  }
  return (
    <div className="hub-grid">
      {cards.map(({ key, title, about, stat, statLabel, tone, icon: Icon, disabled, onOpen, body }) => (
        <button key={key} type="button" className={`hub-card ${tone ? `tone-${tone}` : ""}`} disabled={!!disabled}
                onClick={() => (onOpen ? onOpen() : body && setOpen(key))} title={disabled}>
          <span className="hub-top">
            {Icon && <span className="hub-icon" aria-hidden="true"><Icon size={18} /></span>}
            <b className="hub-title">{title}</b>
          </span>
          {stat !== undefined && <span className="hub-stat"><b>{stat}</b>{statLabel && <small>{statLabel}</small>}</span>}
          <small className="hub-about">{disabled || about}</small>
          <span className="hub-open">Open <ArrowRight size={14} aria-hidden="true" /></span>
        </button>
      ))}
    </div>
  );
}
