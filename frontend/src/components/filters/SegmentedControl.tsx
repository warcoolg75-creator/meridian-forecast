import { useId } from "react";

import { cn } from "../../lib/cn";

/**
 * One choice from a few, side by side: native radio buttons, so arrow keys move between
 * them. The chosen segment is filled maroon (a primary selection, not a status).
 */
export function SegmentedControl<Value extends string>({
  label,
  options,
  value,
  onChange,
  className,
}: {
  /** Names the group for screen readers, e.g. "Granularity". */
  label: string;
  options: Array<{ value: Value; label: string }>;
  value: Value;
  onChange: (value: Value) => void;
  className?: string;
}) {
  const name = useId();
  return (
    <fieldset
      className={cn(
        "flex h-10 items-stretch gap-1 rounded-control border border-line-strong bg-surface p-1",
        className,
      )}
    >
      <legend className="sr-only">{label}</legend>
      {options.map((option) => (
        <label key={option.value} className="flex flex-1 sm:flex-none">
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            className="peer sr-only"
          />
          <span className="flex flex-1 cursor-pointer items-center justify-center rounded-control px-3 text-step-n1 font-medium text-fg-muted transition-colors peer-checked:bg-primary peer-checked:text-on-primary peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus hover:text-fg peer-checked:hover:text-on-primary">
            {option.label}
          </span>
        </label>
      ))}
    </fieldset>
  );
}
