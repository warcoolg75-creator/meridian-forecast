import { useMemo } from "react";

import {
  COMPARISON_LABELS,
  useCatalog,
  type ComparisonMode,
  type MovingEvent,
} from "../../../api/analytics";
import { FilterBar } from "../../../components/filters/FilterBar";
import type { Filters } from "../../../components/filters/filters";
import { SegmentedControl } from "../../../components/filters/SegmentedControl";
import { Skeleton } from "../../../components/feedback/Skeleton";
import { formatDate, type IsoDate } from "../../../lib/dates";
import { errorMessage } from "../../../lib/format";
import { filterOptions } from "./present";

/** The FilterBar, fed with every product, state and city from the catalogue. */
export function ViewFilters({
  filters,
  onChange,
  asOf,
  hideProducts,
}: {
  filters: Filters | null;
  onChange: (filters: Filters) => void;
  asOf: IsoDate | null | undefined;
  hideProducts?: boolean;
}) {
  const catalog = useCatalog();
  const options = useMemo(
    () =>
      catalog.data
        ? filterOptions(catalog.data.products, catalog.data.regions)
        : { products: [], regions: [], channels: [] },
    [catalog.data],
  );
  if (!filters || !asOf) return <Skeleton className="h-10 w-full" />;
  return (
    <FilterBar
      value={filters}
      onChange={onChange}
      options={options}
      asOf={asOf}
      optionsLoading={catalog.isPending}
      optionsError={catalog.error ? errorMessage(catalog.error) : null}
      onRetryOptions={() => void catalog.refetch()}
      show={{ products: !hideProducts }}
    />
  );
}

// Short labels: "Same period last year" does not fit a 360px toggle. The page subtitle and
// the chart legends spell the comparison out.
const MODES: Array<{ value: ComparisonMode; label: string }> = [
  { value: "same_period_last_year", label: "Last year" },
  { value: "previous_period", label: COMPARISON_LABELS.previous_period },
];

/** Same period last year (52 weeks back) or the previous period of equal length. */
export function ComparisonToggle({
  value,
  onChange,
}: {
  value: ComparisonMode;
  onChange: (mode: ComparisonMode) => void;
}) {
  return (
    <SegmentedControl
      label="Compare with"
      options={MODES}
      value={value}
      onChange={onChange}
      className="w-full sm:w-auto"
    />
  );
}

const NAMED = 4;

function describe(event: MovingEvent): string {
  if (event.current_date && event.comparison_date) {
    // days_apart = this year's date minus last year's date moved 52 weeks on.
    const apart = event.days_apart ?? 0;
    return `${formatDate(event.current_date)}, ${Math.abs(apart)} days ${apart < 0 ? "earlier" : "later"} than last year (${formatDate(event.comparison_date)})`;
  }
  if (event.current_date) return `${formatDate(event.current_date)}; not in the comparison period`;
  return `only in the comparison period (${formatDate(event.comparison_date!)})`;
}

/**
 * Under a year-over-year chart: festivals that fall on different dates in the two periods,
 * so a swing around them is read as the calendar, not as demand.
 */
export function MovingFestivalsNote({ events }: { events: MovingEvent[] }) {
  if (events.length === 0) return null;
  const names = [...new Set(events.map((e) => e.name))];
  const named = names.slice(0, NAMED);
  const rest = names.length - named.length;
  return (
    <div className="space-y-2 rounded-control border border-line bg-surface-muted p-3 text-step-n1">
      <p className="text-fg">
        <span className="font-medium">Moving festivals.</span> {named.join(", ")}
        {rest > 0 ? ` and ${rest} more` : ""} fall on different dates than in the comparison period,
        so a swing around them reflects the calendar, not a change in demand.
      </p>
      <details className="text-fg-muted">
        <summary className="cursor-pointer text-primary">Show the dates</summary>
        <ul className="mt-2 space-y-1">
          {events.map((event) => (
            <li key={`${event.name}-${event.current_date ?? event.comparison_date}`}>
              <span className="text-fg">{event.name}</span>
              {event.region_code ? ` (${event.region_code})` : ""}: {describe(event)}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
