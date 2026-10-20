/**
 * The sales analytics API (/api/v1/analytics/*, /products/{sku}): response types mirror
 * backend/app/schemas/analytics.py, and every hook is a TanStack Query keyed by its
 * parameters. Money is integer paise, dates are ISO strings.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import type { Filters } from "../components/filters/filters";
import type { Granularity, IsoDate } from "../lib/dates";
import { apiFetch } from "./client";

export type ComparisonMode = "same_period_last_year" | "previous_period";
export type Channel = "distributor" | "retail" | "ecommerce" | "direct" | "export";
export type RegionLevel = "country" | "state" | "city";

export const CHANNEL_LABELS: Record<Channel, string> = {
  distributor: "Distributor",
  retail: "Retail",
  ecommerce: "Ecommerce",
  direct: "Direct",
  export: "Export",
};

export const COMPARISON_LABELS: Record<ComparisonMode, string> = {
  same_period_last_year: "Same period last year",
  previous_period: "Previous period",
};

export interface PeriodInfo {
  date_from: IsoDate;
  date_to: IsoDate;
  days: number;
  days_with_data: number;
}

export interface ComparisonInfo extends PeriodInfo {
  mode: ComparisonMode;
  shift_days: number;
  complete: boolean;
}

export interface Totals {
  revenue_minor: number;
  units: number;
  orders: number;
  gross_margin_minor: number;
  average_selling_price_minor: number | null;
  margin_rate: number | null;
}

export interface SummaryResponse {
  period: PeriodInfo;
  comparison: ComparisonInfo;
  current: Totals;
  baseline: Totals;
  change: Record<
    "revenue" | "units" | "orders" | "gross_margin" | "average_selling_price",
    number | null
  >;
}

export interface TimeseriesPoint {
  period_start: IsoDate;
  period_end: IsoDate;
  days_covered: number;
  is_partial: boolean;
  units: number;
  revenue_minor: number;
  baseline_units: number;
  baseline_revenue_minor: number;
}

export interface MovingEvent {
  name: string;
  region_code: string | null;
  current_date: IsoDate | null;
  comparison_date: IsoDate | null;
  aligned_date: IsoDate | null;
  days_apart: number | null;
}

export interface TimeseriesResponse {
  period: PeriodInfo;
  comparison: ComparisonInfo;
  granularity: Granularity;
  points: TimeseriesPoint[];
  moving_events: MovingEvent[];
}

export interface ProductRow {
  rank: number;
  sku: string;
  name: string;
  category: string;
  revenue_minor: number;
  units: number;
  gross_margin_minor: number;
  share: number;
  baseline_revenue_minor: number;
  growth: number | null;
  abc: "A" | "B" | "C" | null;
  xyz: "X" | "Y" | "Z" | null;
  xyz_cv: number | null;
  xyz_weeks: number;
  sparkline: number[];
}

export type ProductSort =
  | "rank"
  | "sku"
  | "name"
  | "category"
  | "revenue"
  | "units"
  | "margin"
  | "share"
  | "growth"
  | "abc"
  | "xyz";

export interface ProductsResponse {
  period: PeriodInfo;
  comparison: ComparisonInfo;
  classification: {
    abc_a_share: number;
    abc_b_share: number;
    xyz_x_below: number;
    xyz_y_up_to: number;
    xyz_window: PeriodInfo;
    xyz_min_weeks: number;
  };
  sort: ProductSort;
  order: "asc" | "desc";
  rows: ProductRow[];
}

export interface RegionRow {
  code: string;
  name: string;
  level: RegionLevel;
  parent_code: string | null;
  revenue_minor: number;
  units: number;
  share: number;
  baseline_revenue_minor: number;
  growth: number | null;
}

export interface RegionsResponse {
  period: PeriodInfo;
  comparison: ComparisonInfo;
  level: RegionLevel;
  parent_code: string | null;
  rows: RegionRow[];
}

export interface ChannelRow {
  channel: Channel;
  revenue_minor: number;
  units: number;
  share: number;
  baseline_revenue_minor: number;
  baseline_share: number | null;
  growth: number | null;
}

export interface ChannelsResponse {
  period: PeriodInfo;
  comparison: ComparisonInfo;
  rows: ChannelRow[];
}

export interface ProductEvent {
  date: IsoDate;
  end_date: IsoDate;
  name: string;
  event_type: "public_holiday" | "festival" | "promotion" | "plant_shutdown" | "trade_show";
  scope: "product" | "national" | "regional" | "plant";
  region_code: string | null;
  plant_code: string | null;
  impact_note: string | null;
}

export interface ProductDetail {
  id: number;
  sku: string;
  name: string;
  category: string;
  subcategory: string;
  unit_cost_minor: number;
  unit_price_minor: number;
  unit_of_measure: string;
  launched_on: IsoDate;
  is_active: boolean;
  events: ProductEvent[];
  events_from: IsoDate | null;
  events_to: IsoDate | null;
}

export interface CatalogProduct {
  sku: string;
  name: string;
  category: string;
  is_active: boolean;
}

export interface CatalogRegion {
  code: string;
  name: string;
  level: RegionLevel;
  parent_code: string | null;
}

interface Page<T> {
  items: T[];
}

type Params = Record<string, string | number | string[] | undefined | null>;

/** GET JSON from the API; repeated keys for arrays, errors carry the server's detail. */
export async function getJson<T>(path: string, params: Params = {}): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    for (const item of Array.isArray(value) ? value : [value]) query.append(key, String(item));
  }
  const response = await apiFetch(`/api/v1${path}${query.size ? `?${query}` : ""}`);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof body?.detail === "string" ? body.detail : null;
    throw new Error(
      detail ??
        (response.status >= 500
          ? "The server had a problem. Try again in a moment."
          : `Request failed (${response.status}).`),
    );
  }
  return (await response.json()) as T;
}

/** The analytics query parameters for a set of filters. */
export function analyticsParams(filters: Filters, comparison: ComparisonMode): Params {
  return {
    date_from: filters.dateRange.from,
    date_to: filters.dateRange.to,
    skus: filters.products,
    regions: filters.regions,
    channels: filters.channels,
    granularity: filters.granularity,
    comparison,
  };
}

// Sales data changes only on import or rollup: no need to refetch on every focus.
const STALE = 5 * 60 * 1000;
const common = { staleTime: STALE, placeholderData: keepPreviousData } as const;

export function useCoverage() {
  return useQuery({
    queryKey: ["analytics", "coverage"],
    queryFn: () =>
      getJson<{ first_date: IsoDate | null; last_date: IsoDate | null }>("/analytics/coverage"),
    staleTime: STALE,
  });
}

export function useSummary(params: Params | null) {
  return useQuery({
    queryKey: ["analytics", "summary", params],
    queryFn: () => getJson<SummaryResponse>("/analytics/summary", params!),
    enabled: params !== null,
    ...common,
  });
}

export function useTimeseries(params: Params | null) {
  return useQuery({
    queryKey: ["analytics", "timeseries", params],
    queryFn: () => getJson<TimeseriesResponse>("/analytics/timeseries", params!),
    enabled: params !== null,
    ...common,
  });
}

export function useProductsAnalytics(params: Params | null) {
  return useQuery({
    queryKey: ["analytics", "products", params],
    queryFn: () => getJson<ProductsResponse>("/analytics/products", params!),
    enabled: params !== null,
    ...common,
  });
}

export function useRegions(params: Params | null) {
  return useQuery({
    queryKey: ["analytics", "regions", params],
    queryFn: () => getJson<RegionsResponse>("/analytics/regions", params!),
    enabled: params !== null,
    ...common,
  });
}

export function useChannels(params: Params | null) {
  return useQuery({
    queryKey: ["analytics", "channels", params],
    queryFn: () => getJson<ChannelsResponse>("/analytics/channels", params!),
    enabled: params !== null,
    ...common,
  });
}

export function useProductDetail(sku: string | undefined) {
  return useQuery({
    queryKey: ["products", sku],
    queryFn: () => getJson<ProductDetail>(`/products/${encodeURIComponent(sku!)}`),
    enabled: Boolean(sku),
    staleTime: STALE,
  });
}

/** Filter options: every product and every state and city (public master data). */
export function useCatalog() {
  return useQuery({
    queryKey: ["catalog"],
    queryFn: async () => {
      const [products, regions] = await Promise.all([
        getJson<Page<CatalogProduct>>("/products", { limit: 1000 }),
        getJson<Page<CatalogRegion>>("/regions", { limit: 1000 }),
      ]);
      return { products: products.items, regions: regions.items };
    },
    staleTime: STALE,
  });
}
