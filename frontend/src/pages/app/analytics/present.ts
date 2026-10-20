/** Wording and options shared by the analytics pages. */
import {
  CHANNEL_LABELS,
  type CatalogProduct,
  type CatalogRegion,
  type Channel,
  type ComparisonInfo,
  type ComparisonMode,
  type TimeseriesPoint,
} from "../../../api/analytics";
import type { FilterOption } from "../../../components/filters/filters";
import { formatDate, type Granularity, type IsoDate } from "../../../lib/dates";

export const COMPARISON_PHRASE: Record<ComparisonMode, string> = {
  same_period_last_year: "vs same period last year",
  previous_period: "vs previous period",
};

export const X_AXIS_LABEL: Record<Granularity, string> = {
  day: "Day",
  week: "Week starting (Monday)",
  month: "Month",
};

/** Why a delta is missing, when the comparison reaches before the stored history. */
export function deltaNote(
  comparison: ComparisonInfo | undefined,
  firstDate: IsoDate | null | undefined,
) {
  if (!comparison || comparison.complete) return undefined;
  return firstDate
    ? `No comparison: history starts ${formatDate(firstDate)}`
    : "No comparison period in the history";
}

const UNIT: Record<Granularity, string> = { day: "day", week: "week", month: "month" };

/** "Partial week: 3 of 7 days" for a bucket the range or the history cuts short. */
export function partialNote(point: TimeseriesPoint, granularity: Granularity): string | undefined {
  if (!point.is_partial) return undefined;
  const length =
    (Date.parse(`${point.period_end}T00:00:00Z`) - Date.parse(`${point.period_start}T00:00:00Z`)) /
      86_400_000 +
    1;
  return `Partial ${UNIT[granularity]}: ${point.days_covered} of ${length} days`;
}

/**
 * "The first and last weeks are partial (3 and 4 of 7 days), so they read low." The
 * comparison covers the same days, so it is partial in the same way.
 */
export function partialCaption(points: TimeseriesPoint[], granularity: Granularity): string | null {
  const unit = UNIT[granularity];
  const days = (p: TimeseriesPoint) =>
    (Date.parse(`${p.period_end}T00:00:00Z`) - Date.parse(`${p.period_start}T00:00:00Z`)) /
      86_400_000 +
    1;
  const first = points[0];
  const last = points[points.length - 1];
  if (!first || granularity === "day") return null;
  const parts = [first.is_partial && first, points.length > 1 && last.is_partial && last].filter(
    Boolean,
  ) as TimeseriesPoint[];
  if (parts.length === 0) return null;
  const which =
    parts.length === 2
      ? `first and last ${unit}s are`
      : `${parts[0] === first ? "first" : "last"} ${unit} is`;
  const counts = parts.map((p) => p.days_covered).join(" and ");
  return `The ${which} partial (${counts} of ${days(parts[0])} days), so ${parts.length === 2 ? "they read" : "it reads"} low; the comparison covers the same days.`;
}

export function filterOptions(products: CatalogProduct[], regions: CatalogRegion[]) {
  const names = new Map(regions.map((r) => [r.code, r.name]));
  const states = regions
    .filter((r) => r.level === "state")
    .sort((a, b) => a.name.localeCompare(b.name));
  const regionOptions: FilterOption[] = [];
  for (const state of states) {
    regionOptions.push({ value: state.code, label: state.name });
    for (const city of regions
      .filter((r) => r.level === "city" && r.parent_code === state.code)
      .sort((a, b) => a.name.localeCompare(b.name))) {
      regionOptions.push({ value: city.code, label: `${city.name} (${names.get(state.code)})` });
    }
  }
  return {
    products: products
      .filter((p) => p.is_active)
      .map((p) => ({ value: p.sku, label: p.name }))
      .sort((a, b) => a.label.localeCompare(b.label)),
    regions: regionOptions,
    channels: (Object.keys(CHANNEL_LABELS) as Channel[]).map((c) => ({
      value: c,
      label: CHANNEL_LABELS[c],
    })),
  };
}
