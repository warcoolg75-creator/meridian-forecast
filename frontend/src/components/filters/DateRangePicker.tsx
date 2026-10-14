import { useId, useState } from "react";

import { formatRange, isIsoDate, type IsoDate } from "../../lib/dates";
import { CalendarIcon } from "../brand/icons";
import { Button } from "../ui/Button";
import { PRESET_LABELS, presetRange, type DatePreset, type DateRange } from "./filters";
import { Popover } from "./Popover";

const PRESETS = Object.keys(PRESET_LABELS) as DatePreset[];

/**
 * A date range from presets that end on `asOf`, or a custom from-to. A preset applies
 * as soon as it is picked; a custom range applies on "Apply", once it is valid.
 */
export function DateRangePicker({
  value,
  onChange,
  asOf,
}: {
  value: DateRange;
  onChange: (range: DateRange) => void;
  /** The last day with data: presets count back from it. */
  asOf: IsoDate;
}) {
  return (
    <Popover
      icon={<CalendarIcon className="size-4 shrink-0 text-fg-muted" />}
      trigger={
        <>
          {PRESET_LABELS[value.preset]}
          <span className="text-fg-muted">
            {" · "}
            <span className="figure">{formatRange(value.from, value.to)}</span>
          </span>
        </>
      }
    >
      {(close) => <Panel value={value} asOf={asOf} onChange={onChange} close={close} />}
    </Popover>
  );
}

function Panel({
  value,
  asOf,
  onChange,
  close,
}: {
  value: DateRange;
  asOf: IsoDate;
  onChange: (range: DateRange) => void;
  close: () => void;
}) {
  const [preset, setPreset] = useState<DatePreset>(value.preset);
  const [from, setFrom] = useState(value.from);
  const [to, setTo] = useState(value.to);
  const id = useId();

  const invalid =
    !isIsoDate(from) || !isIsoDate(to)
      ? "Enter both dates."
      : from > to
        ? "The start date must be on or before the end date."
        : null;

  const pick = (next: DatePreset) => {
    setPreset(next);
    if (next !== "custom") {
      onChange(presetRange(next, asOf));
      close();
    }
  };

  return (
    <div className="space-y-3">
      <fieldset className="space-y-1">
        <legend className="sr-only">Date range</legend>
        {PRESETS.map((option) => (
          <label
            key={option}
            className="flex cursor-pointer items-center gap-2 rounded-control px-2 py-2 text-step-n1 text-fg hover:bg-surface-muted"
          >
            <input
              type="radio"
              name={`${id}-preset`}
              checked={preset === option}
              onChange={() => pick(option)}
              className="size-4 shrink-0 accent-primary"
            />
            {PRESET_LABELS[option]}
          </label>
        ))}
      </fieldset>
      {preset === "custom" && (
        <form
          className="space-y-3 border-t border-line pt-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (invalid) return;
            onChange({ preset: "custom", from, to });
            close();
          }}
        >
          <div className="grid grid-cols-2 gap-3">
            <DateField label="From" value={from} onChange={setFrom} invalid={Boolean(invalid)} />
            <DateField label="To" value={to} onChange={setTo} invalid={Boolean(invalid)} />
          </div>
          {invalid && <p className="text-step-n2 text-negative">{invalid}</p>}
          <Button type="submit" size="sm" disabled={Boolean(invalid)} className="w-full">
            Apply
          </Button>
        </form>
      )}
    </div>
  );
}

function DateField({
  label,
  value,
  onChange,
  invalid,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  invalid: boolean;
}) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-step-n2 font-medium text-fg">
        {label}
      </label>
      <input
        id={id}
        type="date"
        value={value}
        aria-invalid={invalid || undefined}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 w-full rounded-control border border-line-strong bg-surface px-2 text-step-n1 text-fg focus-visible:border-primary aria-invalid:border-negative"
      />
    </div>
  );
}
