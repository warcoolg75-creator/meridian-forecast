import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";

import type { Channel, ComparisonMode } from "../../api/analytics";
import { analyticsParams } from "../../api/analytics";
import {
  PRESET_LABELS,
  presetRange,
  type DatePreset,
  type Filters,
} from "../../components/filters/filters";
import { isIsoDate, type Granularity, type IsoDate } from "../../lib/dates";

/**
 * The analytics view (filters + comparison mode) lives in the URL, so a view can be
 * bookmarked or shared and survives a reload:
 *
 *   ?range=last-13-weeks            a preset, re-resolved against the latest data
 *   ?range=custom&from=…&to=…       fixed dates
 *   &sku=…&region=…&channel=…       repeated for several; absent = all
 *   &g=week                          granularity
 *   &compare=previous                previous period (default: same period last year)
 *
 * Anything unreadable falls back to the default rather than failing. Page-specific keys
 * (sort, metric, drill) are left alone.
 */

const DEFAULT_PRESET: DatePreset = "last-13-weeks";
const GRANULARITIES: Granularity[] = ["day", "week", "month"];
const CHANNELS: Channel[] = ["distributor", "retail", "ecommerce", "direct", "export"];
const FILTER_KEYS = ["range", "from", "to", "sku", "region", "channel", "g", "compare"];

export function readFilters(params: URLSearchParams, asOf: IsoDate): Filters {
  const range = params.get("range") as DatePreset | null;
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  let dateRange;
  if (range === "custom" && isIsoDate(from) && isIsoDate(to) && from <= to) {
    dateRange = { preset: "custom" as const, from, to };
  } else if (range && range !== "custom" && range in PRESET_LABELS) {
    dateRange = presetRange(range, asOf);
  } else {
    dateRange = presetRange(DEFAULT_PRESET as Exclude<DatePreset, "custom">, asOf);
  }
  const g = params.get("g") as Granularity | null;
  return {
    dateRange,
    products: params.getAll("sku"),
    regions: params.getAll("region"),
    channels: params.getAll("channel").filter((c): c is Channel => CHANNELS.includes(c as Channel)),
    granularity: g && GRANULARITIES.includes(g) ? g : "week",
  };
}

export function readComparison(params: URLSearchParams): ComparisonMode {
  return params.get("compare") === "previous" ? "previous_period" : "same_period_last_year";
}

export function writeView(
  current: URLSearchParams,
  filters: Filters,
  comparison: ComparisonMode,
): URLSearchParams {
  const next = new URLSearchParams(current);
  for (const key of FILTER_KEYS) next.delete(key);
  next.set("range", filters.dateRange.preset);
  if (filters.dateRange.preset === "custom") {
    next.set("from", filters.dateRange.from);
    next.set("to", filters.dateRange.to);
  }
  for (const sku of filters.products) next.append("sku", sku);
  for (const region of filters.regions) next.append("region", region);
  for (const channel of filters.channels) next.append("channel", channel);
  next.set("g", filters.granularity);
  if (comparison === "previous_period") next.set("compare", "previous");
  return next;
}

/** The current view, its API parameters, and setters that write back to the URL. */
export function useAnalyticsView(asOf: IsoDate | null | undefined) {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => (asOf ? readFilters(params, asOf) : null), [params, asOf]);
  const comparison = readComparison(params);
  const apiParams = useMemo(
    () => (filters ? analyticsParams(filters, comparison) : null),
    [filters, comparison],
  );

  const setFilters = useCallback(
    (next: Filters) =>
      setParams((current) => writeView(current, next, readComparison(current)), { replace: true }),
    [setParams],
  );
  const setComparison = useCallback(
    (mode: ComparisonMode) =>
      setParams(
        (current) => (asOf ? writeView(current, readFilters(current, asOf), mode) : current),
        { replace: true },
      ),
    [setParams, asOf],
  );
  /** Set or clear page-specific keys (sort, metric, drill) in one URL update. */
  const setPageParams = useCallback(
    (entries: Record<string, string | null>) =>
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          for (const [key, value] of Object.entries(entries)) {
            if (value === null) next.delete(key);
            else next.set(key, value);
          }
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );
  const setParam = useCallback(
    (key: string, value: string | null) => setPageParams({ [key]: value }),
    [setPageParams],
  );

  return {
    params,
    filters,
    comparison,
    apiParams,
    setFilters,
    setComparison,
    setParam,
    setPageParams,
  };
}
