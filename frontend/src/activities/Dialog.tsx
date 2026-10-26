import { useEffect, useId, useLayoutEffect, useRef } from "react";
import type { ReactNode } from "react";
import { X } from "lucide-react";

// Accessible modal: focus moves in and is kept inside, Escape asks to close, focus returns on close.

const openStack: object[] = [];       // only the dialog on top reacts to keys
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Modal({ title, subtitle, onClose, children, footer, wide, role = "dialog" }: {
  title: string;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
  role?: "dialog" | "alertdialog";
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const onCloseRef = useRef(onClose);
  useLayoutEffect(() => { onCloseRef.current = onClose; });

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    const box = ref.current;
    const me = {};
    openStack.push(me);
    const first = box?.querySelector<HTMLElement>("[data-autofocus]") || box?.querySelector<HTMLElement>(FOCUSABLE);
    (first || box)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (!box || openStack[openStack.length - 1] !== me) return;
      if (e.key === "Escape") {
        e.stopPropagation();
        onCloseRef.current();
      } else if (e.key === "Tab") {
        const items = Array.from(box.querySelectorAll<HTMLElement>(FOCUSABLE));
        if (items.length === 0) return;
        const [a, z] = [items[0], items[items.length - 1]];
        if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
        else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      openStack.splice(openStack.indexOf(me), 1);
      before?.focus?.();
    };
  }, []);

  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={ref} className={`modal-dialog lib-dialog ${wide ? "wide" : ""}`} role={role} aria-modal="true"
           aria-labelledby={titleId} tabIndex={-1}>
        <div className="modal-header lib-dialog-header">
          <div style={{ minWidth: 0 }}>
            <h2 id={titleId} className="modal-title">{title}</h2>
            {subtitle && <div className="lib-dialog-sub">{subtitle}</div>}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="modal-body lib-dialog-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}
