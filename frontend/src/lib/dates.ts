/**
 * Calendar dates as ISO-8601 strings ("2026-10-13"), the API's format. Arithmetic and
 * formatting happen in UTC, so a date never shifts by a day with the viewer's time zone.
 */

export type IsoDate = string;

export type Granularity = "day" | "week" | "month";

const DAY_MS = 86_400_000;

export function toUtcDate(date: IsoDate): Date {
  return new Date(`${date}T00:00:00Z`);
}

export function toIsoDate(date: Date): IsoDate {
  return date.toISOString().slice(0, 10);
}

export function addDays(date: IsoDate, days: number): IsoDate {
  return toIsoDate(new Date(toUtcDate(date).getTime() + days * DAY_MS));
}

/** Today's date in UTC. */
export function todayIso(): IsoDate {
  return toIsoDate(new Date());
}

export function isIsoDate(value: string): value is IsoDate {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(toUtcDate(value).getTime());
}

const full = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const dayMonth = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
const monthYear = new Intl.DateTimeFormat("en-IN", {
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const longMonthYear = new Intl.DateTimeFormat("en-IN", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

/** "13 Oct 2026" */
export function formatDate(date: IsoDate): string {
  return full.format(toUtcDate(date));
}

/** A whole period, for tooltips and tables: "13 Oct 2026", "Week of 13 Oct 2026", "October 2026". */
export function formatPeriod(date: IsoDate, granularity: Granularity): string {
  if (granularity === "month") return longMonthYear.format(toUtcDate(date));
  if (granularity === "week") return `Week of ${full.format(toUtcDate(date))}`;
  return full.format(toUtcDate(date));
}

/** A short axis tick: "13 Oct" for days and weeks, "Oct 2026" for months. */
export function formatTick(date: IsoDate, granularity: Granularity): string {
  return granularity === "month"
    ? monthYear.format(toUtcDate(date))
    : dayMonth.format(toUtcDate(date));
}

/** "8 Jul – 6 Oct 2026", or with both years when the range crosses one. */
export function formatRange(from: IsoDate, to: IsoDate): string {
  const sameYear = from.slice(0, 4) === to.slice(0, 4);
  const start = sameYear ? dayMonth.format(toUtcDate(from)) : formatDate(from);
  return `${start} – ${formatDate(to)}`;
}
