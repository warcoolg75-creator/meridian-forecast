import { useId, useState } from "react";

import { SearchIcon } from "../brand/icons";
import { ErrorState } from "../feedback/ErrorState";
import { Button } from "../ui/Button";
import type { FilterOption } from "./filters";
import { Popover } from "./Popover";

/** Long lists get a search box. */
const SEARCH_FROM = 8;

/**
 * Pick any number of options. Nothing picked means all of them (the filter is off), so
 * the button reads "Products: All". "Select all" picks every option the search shows.
 */
export function MultiSelect({
  label,
  options,
  value,
  onChange,
  isLoading,
  error,
  onRetry,
}: {
  /** Plural noun: "Products", "Regions". */
  label: string;
  options: FilterOption[];
  value: string[];
  onChange: (value: string[]) => void;
  /** The options are still loading: the control is disabled. */
  isLoading?: boolean;
  /** The options failed to load: the panel says so and offers `onRetry`. */
  error?: string | null;
  onRetry?: () => void;
}) {
  const [query, setQuery] = useState("");
  const searchId = useId();
  const noun = label.toLowerCase();
  const selected = new Set(value);
  const visible = query
    ? options.filter((o) => o.label.toLowerCase().includes(query.trim().toLowerCase()))
    : options;

  // Emitted in the options' order, so the same choice always yields the same filter.
  const emit = (next: Set<string>) =>
    onChange(options.map((o) => o.value).filter((v) => next.has(v)));
  const toggle = (option: string) => {
    const next = new Set(selected);
    if (next.has(option)) next.delete(option);
    else next.add(option);
    emit(next);
  };

  const summary = isLoading
    ? "loading…"
    : error
      ? "unavailable"
      : value.length === 0
        ? "All"
        : value.length === 1
          ? (options.find((o) => o.value === value[0])?.label ?? "1 selected")
          : `${value.length} selected`;

  return (
    <Popover
      trigger={
        <>
          <span className="text-fg-muted">{label}:</span> {summary}
        </>
      }
      disabled={isLoading}
      loading={isLoading}
    >
      {() =>
        error ? (
          <ErrorState title={`Couldn’t load ${noun}`} message={error} onRetry={onRetry} />
        ) : options.length === 0 ? (
          <p className="px-1 py-4 text-center text-step-n1 text-fg-muted">
            No {noun} to choose from.
          </p>
        ) : (
          <fieldset className="space-y-3">
            <legend className="sr-only">{label}</legend>
            {options.length >= SEARCH_FROM && (
              <div className="relative">
                <label htmlFor={searchId} className="sr-only">
                  Search {noun}
                </label>
                <SearchIcon className="pointer-events-none absolute top-2 left-2 size-4 text-fg-subtle" />
                <input
                  id={searchId}
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={`Search ${noun}`}
                  className="h-8 w-full rounded-control border border-line-strong bg-surface pr-2 pl-8 text-step-n1 text-fg focus-visible:border-primary"
                />
              </div>
            )}
            <div className="flex items-center justify-between gap-2">
              <Button
                variant="ghost"
                size="sm"
                disabled={visible.length === 0}
                onClick={() => emit(new Set([...value, ...visible.map((o) => o.value)]))}
              >
                Select all{query ? " shown" : ""}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={value.length === 0}
                onClick={() => onChange([])}
              >
                Clear
              </Button>
            </div>
            <ul role="list" className="max-h-scroll-list space-y-1 overflow-y-auto">
              {visible.map((option) => (
                <li key={option.value}>
                  <label className="flex cursor-pointer items-center gap-2 rounded-control px-2 py-2 text-step-n1 text-fg hover:bg-surface-muted">
                    <input
                      type="checkbox"
                      checked={selected.has(option.value)}
                      onChange={() => toggle(option.value)}
                      className="size-4 shrink-0 accent-primary"
                    />
                    {option.label}
                  </label>
                </li>
              ))}
              {visible.length === 0 && (
                <li className="px-2 py-2 text-step-n1 text-fg-muted">No {noun} match.</li>
              )}
            </ul>
            <p className="text-step-n2 text-fg-muted">None selected shows all {noun}.</p>
          </fieldset>
        )
      }
    </Popover>
  );
}
