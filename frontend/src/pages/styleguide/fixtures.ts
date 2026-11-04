/**
 * FIXTURE DATA: invented numbers for /styleguide/components, to show the component
 * library populated. Not from the API, not from the seeded database, not ground truth.
 * Products are made up and carry an "FX-" SKU so they cannot pass for real ones.
 * Only src/pages/styleguide may import this file.
 */
import type { BarDatum } from "../../components/charts/BarChart";
import type { Series } from "../../components/charts/chart-theme";
import type { DivergingDatum } from "../../components/charts/DivergingBarChart";
import type { TimeSeriesPoint } from "../../components/charts/TimeSeriesChart";
import type { FilterOption } from "../../components/filters/filters";
import { addDays, type IsoDate } from "../../lib/dates";

/** The last day of "actuals". Date presets count back from here. */
export const FIXTURE_AS_OF: IsoDate = "2026-10-04";
/** First forecast week: the Monday after FIXTURE_AS_OF. */
export const FIXTURE_FORECAST_START: IsoDate = "2026-10-05";

const ACTUAL_WEEKS = 26;
const FORECAST_WEEKS = 8;
const FIRST_WEEK = addDays(FIXTURE_FORECAST_START, -7 * ACTUAL_WEEKS);

/** Deterministic noise in [-1, 1]: the page looks the same on every load. */
function wobble(i: number, salt: number): number {
  const x = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453;
  return (x - Math.floor(x)) * 2 - 1;
}

/** A gentle seasonal wave, a slow rise and a festive peak in early November. */
function weeklyLevel(i: number, base: number): number {
  const season = 0.18 * base * Math.sin((2 * Math.PI * (i + 4)) / 26);
  const festive = 0.45 * base * Math.exp(-((i - 30) ** 2) / 5);
  return base + season + festive + i * 4;
}

const weekOf = (i: number) => addDays(FIRST_WEEK, 7 * i);

/** One product's weekly units: 26 weeks actual, then 8 weeks forecast with an 80% band. */
export const unitsWithForecast: TimeSeriesPoint[] = Array.from(
  { length: ACTUAL_WEEKS + FORECAST_WEEKS },
  (_, i) => {
    const forecast = i >= ACTUAL_WEEKS;
    const level = weeklyLevel(i, 1200);
    const value = Math.round(forecast ? level : level + 70 * wobble(i, 1));
    if (!forecast) return { date: weekOf(i), values: { units: value } };
    const spread = 0.07 + 0.015 * (i - ACTUAL_WEEKS); // widens with the horizon
    return {
      date: weekOf(i),
      values: { units: value },
      low: Math.round(value * (1 - spread)),
      high: Math.round(value * (1 + spread)),
    };
  },
);

export const unitsSeries: Series[] = [{ key: "units", label: "Units sold" }];

/** Four years of the same 26 weeks: the first three fill the cap, the fourth breaks it. */
export const yearSeries: Series[] = [
  { key: "y2026", label: "This year" },
  { key: "y2025", label: "Last year" },
  { key: "y2024", label: "Two years ago" },
];
export const fourYearSeries: Series[] = [...yearSeries, { key: "y2023", label: "Three years ago" }];

const YEAR_BASES: Record<string, number> = { y2026: 1200, y2025: 1020, y2024: 860, y2023: 720 };

export const unitsByYear: TimeSeriesPoint[] = Array.from({ length: ACTUAL_WEEKS }, (_, i) => ({
  date: weekOf(i),
  values: Object.fromEntries(
    Object.entries(YEAR_BASES).map(([key, base], salt) => [
      key,
      Math.round(weeklyLevel(i, base) + 0.06 * base * wobble(i, salt + 2)),
    ]),
  ),
}));

/** This year and last year only: the chart a change strip sits under. */
export const twoYearSeries: Series[] = yearSeries.slice(0, 2);

/** Week 9 is made flat (last year = this year), to show the neutral mark. */
const FLAT_WEEK = 9;
/** The first two weeks have no comparison, as if last year's history started later. */
const NO_COMPARISON_WEEKS = 2;

/** unitsByYear with the flat week and the missing comparison weeks applied. */
export const unitsThisYearAndLast: TimeSeriesPoint[] = unitsByYear.map((point, i) => ({
  date: point.date,
  values: {
    y2026: point.values.y2026,
    y2025:
      i < NO_COMPARISON_WEEKS ? null : i === FLAT_WEEK ? point.values.y2026 : point.values.y2025,
  },
}));

/** Each week of unitsThisYearAndLast as a change against last year. */
export const changeByWeek: DivergingDatum[] = unitsThisYearAndLast.map((point) => {
  const now = point.values.y2026 ?? 0;
  const before = point.values.y2025;
  return {
    key: point.date,
    label: point.date,
    heading: point.date,
    value: typeof before === "number" ? now / before - 1 : null,
    reason:
      typeof before === "number"
        ? undefined
        : "Fixture: last year's history starts after this week.",
    details: [
      { label: "This year", value: now.toLocaleString("en-IN") },
      {
        label: "Last year",
        value: typeof before === "number" ? before.toLocaleString("en-IN") : "None",
      },
    ],
  };
});

export const REGIONS = ["North", "South", "East", "West", "Central"];
export const CHANNELS = ["Online", "Retail", "Wholesale"];

export const channelSeries: Series[] = CHANNELS.map((c) => ({ key: c.toLowerCase(), label: c }));
export const totalSeries: Series[] = [{ key: "units", label: "Units sold" }];
export const comparisonSeries: Series[] = [
  { key: "now", label: "Last 4 weeks" },
  { key: "before", label: "Same 4 weeks last year" },
];

const REGION_UNITS = [18_420, 22_960, 12_310, 20_770, 9_840];
const CHANNEL_SHARE: Record<string, number[]> = {
  online: [0.42, 0.38, 0.31, 0.45, 0.28],
  retail: [0.41, 0.44, 0.47, 0.36, 0.5],
  wholesale: [0.17, 0.18, 0.22, 0.19, 0.22],
};

export const unitsByRegion: BarDatum[] = REGIONS.map((region, i) => ({
  category: region,
  values: { units: REGION_UNITS[i] },
}));

export const unitsByRegionAndChannel: BarDatum[] = REGIONS.map((region, i) => ({
  category: region,
  values: Object.fromEntries(
    Object.entries(CHANNEL_SHARE).map(([channel, share]) => [
      channel,
      Math.round(REGION_UNITS[i] * share[i]),
    ]),
  ),
}));

export interface FixtureProduct {
  sku: string;
  name: string;
  category: string;
  units: number;
  /** Paise, like the API. */
  revenueMinor: number;
  /** Fraction vs the previous 4 weeks. */
  change: number;
}

const PRODUCTS: Array<[string, string, number]> = [
  ["Steel tiffin box, 3 tier", "Kitchen", 54_900],
  ["Copper water bottle, 1 L", "Kitchen", 79_900],
  ["Cotton bath towel", "Textiles", 49_900],
  ["Brass diya, set of 4", "Festive", 39_900],
  ["Ceramic dinner set, 18 pieces", "Kitchen", 3_49_900],
  ["Bamboo chopping board", "Kitchen", 44_900],
  ["Glass storage jar, 1.5 L", "Storage", 29_900],
  ["Cast iron tawa, 28 cm", "Kitchen", 1_29_900],
  ["Wooden wall clock", "Home décor", 1_49_900],
  ["Sandalwood candle", "Festive", 34_900],
  ["Jute shopping bag", "Storage", 19_900],
  ["Silk cushion cover", "Textiles", 59_900],
  ["Steel water jug, 2 L", "Kitchen", 64_900],
  ["Non-stick kadai, 24 cm", "Kitchen", 1_09_900],
  ["Spice box, 7 bowls", "Kitchen", 89_900],
  ["Terracotta planter", "Home décor", 39_900],
  ["LED string lights, 10 m", "Festive", 49_900],
  ["Rangoli colour set", "Festive", 24_900],
  ["Festive gift hamper", "Festive", 2_49_900],
  ["Dry fruit gift box", "Festive", 1_99_900],
  ["Steel thali set", "Kitchen", 1_79_900],
  ["Handloom table runner", "Textiles", 69_900],
  ["Marble coaster set", "Home décor", 54_900],
];

export const products: FixtureProduct[] = PRODUCTS.map(([name, category, pricePaise], i) => {
  const units = Math.round(400 + 2600 * ((wobble(i, 9) + 1) / 2));
  return {
    sku: `FX-${String(i + 1).padStart(3, "0")}`,
    name,
    category,
    units,
    revenueMinor: units * pricePaise,
    change: Math.round(wobble(i, 5) * 250) / 1000,
  };
});

const topProducts = [...products].sort((a, b) => b.units - a.units);

export const unitsByProduct: BarDatum[] = topProducts.slice(0, 8).map((p) => ({
  category: p.name,
  values: { units: p.units },
}));

export const unitsByProductYearOnYear: BarDatum[] = topProducts.slice(0, 5).map((p, i) => ({
  category: p.name,
  values: { now: p.units, before: Math.round(p.units * (0.78 + 0.08 * wobble(i, 7))) },
}));

/** Twelve weeks of a KPI, oldest first. */
export function kpiTrend(base: number, drift: number, salt: number): number[] {
  return Array.from({ length: 12 }, (_, i) =>
    Math.round(base * (1 + drift * i + 0.05 * wobble(i, salt))),
  );
}

export const productOptions: FilterOption[] = products
  .slice(0, 12)
  .map((p) => ({ value: p.sku, label: p.name }));
export const regionOptions: FilterOption[] = REGIONS.map((r) => ({
  value: r.toLowerCase(),
  label: r,
}));
export const channelOptions: FilterOption[] = CHANNELS.map((c) => ({
  value: c.toLowerCase(),
  label: c,
}));

/** Growth per product against last year, from the largest rise to the largest fall. */
export const growthByProduct: DivergingDatum[] = topProducts
  .slice(0, 10)
  .map((p) => ({ key: p.sku, label: p.name, heading: p.name, value: p.change }))
  .sort((a, b) => b.value - a.value);
