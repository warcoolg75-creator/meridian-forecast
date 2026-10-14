import { addDays, type Granularity, type IsoDate } from "../../lib/dates";

export type { Granularity } from "../../lib/dates";

export type DatePreset =
  "last-7-days" | "last-4-weeks" | "last-13-weeks" | "last-52-weeks" | "year-to-date" | "custom";

/** Inclusive on both ends. */
export interface DateRange {
  preset: DatePreset;
  from: IsoDate;
  to: IsoDate;
}

/**
 * What FilterBar emits. An empty list means "all", not "none": no products selected
 * filters nothing.
 */
export interface Filters {
  dateRange: DateRange;
  products: string[];
  regions: string[];
  channels: string[];
  granularity: Granularity;
}

export interface FilterOption {
  value: string;
  label: string;
}

export const PRESET_LABELS: Record<DatePreset, string> = {
  "last-7-days": "Last 7 days",
  "last-4-weeks": "Last 4 weeks",
  "last-13-weeks": "Last 13 weeks",
  "last-52-weeks": "Last 52 weeks",
  "year-to-date": "Year to date",
  custom: "Custom range",
};

const PRESET_DAYS: Partial<Record<DatePreset, number>> = {
  "last-7-days": 7,
  "last-4-weeks": 28,
  "last-13-weeks": 91,
  "last-52-weeks": 364,
};

/** A preset's dates, ending on `asOf` (the last day with data, usually not today). */
export function presetRange(preset: Exclude<DatePreset, "custom">, asOf: IsoDate): DateRange {
  if (preset === "year-to-date") return { preset, from: `${asOf.slice(0, 4)}-01-01`, to: asOf };
  return { preset, from: addDays(asOf, 1 - PRESET_DAYS[preset]!), to: asOf };
}

/** Everything, over the last 13 weeks, by week. */
export function defaultFilters(asOf: IsoDate): Filters {
  return {
    dateRange: presetRange("last-13-weeks", asOf),
    products: [],
    regions: [],
    channels: [],
    granularity: "week",
  };
}
