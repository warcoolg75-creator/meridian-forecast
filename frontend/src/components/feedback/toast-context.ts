import { createContext, useContext } from "react";

export type ToastTone = "neutral" | "positive" | "warning" | "negative";

export interface ToastOptions {
  title: string;
  description?: string;
  /** Colour and icon. Negative toasts are announced at once (role="alert"); the rest politely. */
  tone?: ToastTone;
  /** Milliseconds before it dismisses itself; paused while hovered or focused. */
  duration?: number;
}

export interface ToastApi {
  /** Shows a transient message and returns its id. */
  show: (options: ToastOptions) => string;
  dismiss: (id: string) => void;
}

export const ToastContext = createContext<ToastApi | null>(null);

/** Transient messages: "Plan saved", "Import failed". For lasting problems use ErrorState. */
export function useToast(): ToastApi {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside <ToastProvider>");
  return value;
}
