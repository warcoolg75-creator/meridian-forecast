import { useId, type InputHTMLAttributes } from "react";

import { cn } from "../../lib/cn";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
  /** Styleguide only: render the focus state statically. */
  forcedState?: "focus";
}

// The border is ink-400 (line-strong), not the cream hairline: a control's outline needs
// 3:1 contrast against the background to be recognisable.
const FIELD = cn(
  "h-10 w-full rounded-control border border-line-strong bg-surface px-3 text-step-0 text-fg transition-colors",
  "placeholder:text-fg-subtle hover:border-fg-muted",
  "focus-visible:border-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
  "data-force-focus:border-primary data-force-focus:outline-2 data-force-focus:outline-offset-2 data-force-focus:outline-focus",
  "aria-invalid:border-negative",
  "disabled:cursor-not-allowed disabled:border-line disabled:bg-surface-muted disabled:text-fg-subtle",
);

export function Input({ label, hint, error, forcedState, id, className, ...props }: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const noteId = `${inputId}-note`;
  const note = error ?? hint;
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <label htmlFor={inputId} className="text-step-n1 font-medium text-fg">
        {label}
      </label>
      <input
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={note ? noteId : undefined}
        data-force-focus={forcedState === "focus" || undefined}
        className={FIELD}
        {...props}
      />
      {note && (
        <p id={noteId} className={cn("text-step-n1", error ? "text-negative" : "text-fg-muted")}>
          {note}
        </p>
      )}
    </div>
  );
}
