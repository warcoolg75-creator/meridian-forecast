import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { cn } from "../../lib/cn";
import { AlertIcon, CheckCircleIcon, CloseIcon, InfoIcon, WarningIcon } from "../brand/icons";
import { ToastContext, type ToastApi, type ToastOptions, type ToastTone } from "./toast-context";

interface Toast extends Required<Omit<ToastOptions, "description">> {
  id: string;
  description?: string;
}

/** Older toasts give way beyond this many. */
const MAX_VISIBLE = 3;
const DEFAULT_DURATION: Record<ToastTone, number> = {
  neutral: 5000,
  positive: 5000,
  warning: 8000,
  negative: 8000,
};

const ICONS: Record<ToastTone, (props: { className?: string }) => ReactNode> = {
  neutral: InfoIcon,
  positive: CheckCircleIcon,
  warning: WarningIcon,
  negative: AlertIcon,
};

// The icon carries the tone; text stays in text colours (amber-600 never as text).
const ICON_TONE: Record<ToastTone, string> = {
  neutral: cn("text-fg-muted"),
  positive: cn("text-positive"),
  warning: cn("text-warning"),
  negative: cn("text-negative"),
};

/**
 * Hosts transient messages for the whole app (mounted in main.tsx). Both live regions
 * exist before any toast does, which is what makes screen readers announce new ones.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback((options: ToastOptions) => {
    const tone = options.tone ?? "neutral";
    const id = `toast-${++nextId.current}`;
    const toast: Toast = {
      id,
      tone,
      title: options.title,
      description: options.description,
      duration: options.duration ?? DEFAULT_DURATION[tone],
    };
    setToasts((current) => [...current, toast].slice(-MAX_VISIBLE));
    return id;
  }, []);

  const api = useMemo<ToastApi>(() => ({ show, dismiss }), [show, dismiss]);
  const urgent = toasts.filter((toast) => toast.tone === "negative");
  const polite = toasts.filter((toast) => toast.tone !== "negative");

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col gap-2 sm:right-6 sm:bottom-6 sm:left-auto sm:w-sm">
        <div role="alert" className="flex flex-col gap-2">
          {urgent.map((toast) => (
            <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
          ))}
        </div>
        <div role="status" className="flex flex-col gap-2">
          {polite.map((toast) => (
            <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
          ))}
        </div>
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: string) => void }) {
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    const timer = window.setTimeout(() => onDismiss(toast.id), toast.duration);
    return () => window.clearTimeout(timer);
  }, [paused, toast.id, toast.duration, onDismiss]);

  const Icon = ICONS[toast.tone];
  return (
    <div
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      className="pointer-events-auto flex items-start gap-3 rounded-card border border-line bg-surface p-4 shadow-overlay fade-in"
    >
      <Icon className={cn("size-5 shrink-0", ICON_TONE[toast.tone])} />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-step-n1 font-medium text-fg">{toast.title}</p>
        {toast.description && <p className="text-step-n1 text-fg-muted">{toast.description}</p>}
      </div>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => onDismiss(toast.id)}
        className="-m-1 inline-flex size-8 shrink-0 items-center justify-center rounded-control text-fg-muted hover:bg-surface-muted hover:text-fg"
      >
        <CloseIcon className="size-4" />
      </button>
    </div>
  );
}
