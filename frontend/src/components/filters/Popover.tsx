import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { cn } from "../../lib/cn";
import { ChevronIcon, Spinner } from "../brand/icons";

/** A filter control's trigger: a bordered field-like button (3:1 outline, like Input). */
const TRIGGER = cn(
  "inline-flex h-10 w-full items-center gap-2 rounded-control border border-line-strong bg-surface px-3 text-left text-step-n1 text-fg transition-colors sm:w-auto",
  "hover:border-fg-muted aria-expanded:border-primary",
  "disabled:cursor-not-allowed disabled:border-line disabled:bg-surface-muted disabled:text-fg-subtle",
);

/**
 * A button that opens a panel below it: for the filter controls. Opening it moves focus
 * to the panel's first control. Escape closes it and returns focus to the button; a
 * click outside or tabbing away closes it too.
 */
export function Popover({
  trigger,
  icon,
  disabled,
  loading,
  children,
}: {
  /** The button's text, e.g. "Products: All". */
  trigger: ReactNode;
  icon?: ReactNode;
  disabled?: boolean;
  /** Shows a spinner in place of the chevron (and should come with `disabled`). */
  loading?: boolean;
  /** The panel's content; call `close` once a choice is final. */
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const panelId = useId();

  // Bumped when a choice closes the panel; the effect below then refocuses the button.
  // (Focusing from the callback would read a ref during render: the panel's content
  // receives `close` while rendering.)
  const [closedByChoice, setClosedByChoice] = useState(0);
  const close = () => {
    setOpen(false);
    setClosedByChoice((count) => count + 1);
  };

  useEffect(() => {
    if (closedByChoice) button.current?.focus();
  }, [closedByChoice]);

  useEffect(() => {
    if (!open) return;
    panel.current
      ?.querySelector<HTMLElement>("input:not([disabled]), button:not([disabled])")
      ?.focus();
    const onPointerDown = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div
      ref={root}
      className="relative w-full sm:w-auto"
      // Tabbing to something outside closes it. Pressing on a non-focusable spot inside
      // the panel (a label, its padding) moves focus to the nearest focusable ancestor:
      // <body>, or <main>, which is focusable (tabIndex -1) for focus after navigation.
      // That is not leaving, so a null relatedTarget or an ancestor must not close it;
      // clicks outside are the pointerdown listener's job.
      onBlur={(event) => {
        const next = event.relatedTarget as Node | null;
        const self = event.currentTarget;
        if (open && next && !self.contains(next) && !next.contains(self)) setOpen(false);
      }}
    >
      <button
        ref={button}
        type="button"
        disabled={disabled}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className={TRIGGER}
      >
        {icon}
        <span className="min-w-0 flex-1 truncate">{trigger}</span>
        {loading ? (
          <Spinner className="shrink-0" />
        ) : (
          <ChevronIcon direction="down" className="size-4 shrink-0 text-fg-muted" />
        )}
      </button>
      {open && (
        <div
          ref={panel}
          id={panelId}
          className="absolute top-full left-0 z-30 mt-2 w-xs max-w-full rounded-card border border-line bg-surface p-3 shadow-overlay sm:max-w-none"
        >
          {children(close)}
        </div>
      )}
    </div>
  );
}
