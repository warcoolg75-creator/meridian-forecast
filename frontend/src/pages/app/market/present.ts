import type { SeriesData, SeriesInfo, SignalPoint } from "../../../api/market";
import type { TimeSeriesPoint } from "../../../components/charts/TimeSeriesChart";
import type { Granularity, IsoDate } from "../../../lib/dates";

/** Shown permanently on every market view (the API's MarketOverview.note says the same). */
export const CONTEXT_NOTE =
  "Context only. Our sales data is synthetic, so these signals are not used in the forecast.";
/** Under the product page's Market context heading: the panel invites a causal reading. */
export const SHAPES_NOTE = "Similar shapes here reflect shared seasons, not cause and effect.";

const oneDecimal = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 });
const twoDecimals = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const whole = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat("en-IN", {
  notation: "compact",
  maximumSignificantDigits: 3,
});

/** A signal value with its unit's natural precision: 31.4 °C, 12.6 mm, 94.94 ₹ per US$. */
export function signalValueFormatter(unit: string): (value: number) => string {
  if (unit === "°C") return (v) => `${oneDecimal.format(v)} °C`;
  if (unit === "mm") return (v) => `${oneDecimal.format(v)} mm`;
  if (unit.startsWith("views")) return (v) => `${whole.format(v)} views`;
  if (unit.includes("tonne")) return (v) => `US$${whole.format(v)}`;
  if (unit.startsWith("₹")) return (v) => `₹${twoDecimals.format(v)}`;
  if (unit.includes("cents")) return (v) => `${twoDecimals.format(v)}¢`;
  if (unit.includes("barrel")) return (v) => `US$${twoDecimals.format(v)}`;
  return (v) => oneDecimal.format(v);
}

export function signalTickFormatter(unit: string): (value: number) => string {
  if (unit.startsWith("views") || unit.includes("tonne")) return (v) => compact.format(v);
  return (v) => oneDecimal.format(v);
}

const PER: Record<Granularity, string> = { day: "day", week: "week", month: "month" };
const AVERAGE: Record<Granularity, string> = { day: "daily", week: "weekly", month: "monthly" };

/** The value axis title, with its unit and how a period's value was made. */
export function signalAxisLabel(series: SeriesInfo, granularity: Granularity): string {
  if (series.aggregation === "sum" && granularity !== "day") {
    const base = series.unit.replace(/ per day$/, "");
    return `${series.label} (${base} per ${PER[granularity]})`;
  }
  if (series.frequency === "monthly") return `${series.label} (${series.unit}, monthly average)`;
  return granularity === "day"
    ? `${series.label} (${series.unit})`
    : `${series.label} (${series.unit}, ${AVERAGE[granularity]} average)`;
}

/** Strips the leading "Source: " a citation carries, since the card already says it. */
export function citationText(series: SeriesInfo): string {
  return (series.citation ?? series.attribution).replace(/^Source:\s*/, "");
}

function noteFor(
  point: SignalPoint,
  fullDays: number,
  granularity: Granularity,
): string | undefined {
  if (granularity === "day" || point.days >= fullDays) return undefined;
  return `Partial ${PER[granularity]}: ${point.days} of ${fullDays} days with a value`;
}

/**
 * Observed points, then the forecast's later periods (dashed after `forecastStart`).
 * A period both cover keeps the observed value, so a forecast never overwrites a measurement.
 * With `periods`, every chart in a panel gets the same x positions (null where no value).
 */
export function signalPoints(
  observed: SeriesData | undefined,
  forecast: SeriesData | undefined,
  periods?: IsoDate[],
): { points: TimeSeriesPoint[]; forecastStart?: IsoDate } {
  const obs = observed?.points ?? [];
  const granularity = observed?.granularity ?? "week";
  const fullDays = Math.max(0, ...obs.map((p) => p.days));
  const lastObserved = obs.length ? obs[obs.length - 1].period_start : undefined;
  const later = (forecast?.points ?? []).filter(
    (p) => lastObserved === undefined || p.period_start > lastObserved,
  );
  const byDate = new Map<IsoDate, TimeSeriesPoint>();
  for (const p of obs) {
    byDate.set(p.period_start, {
      date: p.period_start,
      values: { value: p.value },
      note: noteFor(p, fullDays, granularity),
    });
  }
  for (const p of later) {
    byDate.set(p.period_start, {
      date: p.period_start,
      values: { value: p.value },
      note: "Forecast (Open-Meteo, latest run)",
    });
  }
  const forecastStart = later.length ? later[0].period_start : undefined;
  if (!periods) {
    return {
      points: [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date)),
      forecastStart,
    };
  }
  return {
    points: periods.map((date) => byDate.get(date) ?? { date, values: { value: null } }),
    forecastStart,
  };
}

/** Monday-start week starts from `from` to `to`, inclusive. */
export function weekStarts(from: IsoDate, to: IsoDate): IsoDate[] {
  const start = new Date(`${from}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 6) % 7));
  const end = new Date(`${to}T00:00:00Z`);
  const out: IsoDate[] = [];
  for (const d = start; d <= end; d.setUTCDate(d.getUTCDate() + 7)) {
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

/** "10 Nov 2026" from an ISO timestamp, in UTC like every date here. */
export function timestampDate(value: string | null): IsoDate | null {
  return value ? value.slice(0, 10) : null;
}
