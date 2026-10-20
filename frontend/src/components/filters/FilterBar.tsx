import type { IsoDate } from "../../lib/dates";
import { DateRangePicker } from "./DateRangePicker";
import type { FilterOption, Filters, Granularity } from "./filters";
import { MultiSelect } from "./MultiSelect";
import { SegmentedControl } from "./SegmentedControl";

export type { DateRange, DatePreset, FilterOption, Filters, Granularity } from "./filters";

const GRANULARITIES: Array<{ value: Granularity; label: string }> = [
  { value: "day", label: "Day" },
  { value: "week", label: "Week" },
  { value: "month", label: "Month" },
];

/**
 * The analytics filters in one row: date range, product, region and channel, and the
 * granularity. It owns no data: the caller passes the options and the current filters,
 * and gets a complete new Filters object on every change (`defaultFilters` makes the
 * first one). Below 640px every control takes the full width.
 */
export function FilterBar({
  value,
  onChange,
  options,
  asOf,
  optionsLoading,
  optionsError,
  onRetryOptions,
  show = {},
}: {
  value: Filters;
  onChange: (filters: Filters) => void;
  options: { products: FilterOption[]; regions: FilterOption[]; channels: FilterOption[] };
  /** The last day with data: the date presets count back from it. */
  asOf: IsoDate;
  /** The product, region and channel options are still loading. */
  optionsLoading?: boolean;
  /** Loading those options failed; the date range and granularity still work. */
  optionsError?: string | null;
  onRetryOptions?: () => void;
  /** Hide a picker the page fixes itself, e.g. products on a product's own page. */
  show?: Partial<Record<"products" | "regions" | "channels", boolean>>;
}) {
  const set = <K extends keyof Filters>(key: K, next: Filters[K]) =>
    onChange({ ...value, [key]: next });
  const dimension = (key: "products" | "regions" | "channels", label: string) => (
    <MultiSelect
      label={label}
      options={options[key]}
      value={value[key]}
      onChange={(next) => set(key, next)}
      isLoading={optionsLoading}
      error={optionsError}
      onRetry={onRetryOptions}
    />
  );
  return (
    <div role="group" aria-label="Filters" className="flex flex-wrap items-center gap-3">
      <DateRangePicker
        value={value.dateRange}
        onChange={(range) => set("dateRange", range)}
        asOf={asOf}
      />
      {show.products !== false && dimension("products", "Products")}
      {show.regions !== false && dimension("regions", "Regions")}
      {show.channels !== false && dimension("channels", "Channels")}
      <SegmentedControl
        label="Granularity"
        options={GRANULARITIES}
        value={value.granularity}
        onChange={(granularity) => set("granularity", granularity)}
        className="w-full sm:ml-auto sm:w-auto"
      />
    </div>
  );
}
