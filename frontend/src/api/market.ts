/**
 * The market signals API (/api/v1/market/*, /products/{sku}/market): response types mirror
 * backend/app/schemas/market.py. Context only: the sales data is synthetic, so none of
 * these signals feeds the forecast. The page only formats and plots what it gets.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import type { Granularity, IsoDate } from "../lib/dates";
import { getJson } from "./analytics";

const STALE = 5 * 60 * 1000;

/** "partial": news only, when its last run stopped early but earlier runs stored headlines. */
export type SignalStatus = "fresh" | "stale" | "partial" | "never_fetched" | "not_configured";
export type SignalRole = "demand_context" | "input_cost";

export interface SourceStatus {
  code: string;
  name: string;
  homepage: string;
  licence: string;
  attribution: string;
  terms_url: string;
  requires_key: boolean;
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  status: SignalStatus;
  status_reason: string | null;
}

export interface SeriesInfo {
  key: string;
  label: string;
  description: string;
  unit: string;
  geography: string;
  geography_name: string;
  frequency: "daily" | "weekly" | "monthly";
  aggregation: "mean" | "sum";
  role: SignalRole;
  group_key: string;
  forecast_key: string | null;
  source: string;
  source_name: string;
  source_homepage: string;
  attribution: string;
  citation: string | null;
  first_observed_on: IsoDate | null;
  latest_observed_on: IsoDate | null;
  last_success_at: string | null;
  last_attempt_at: string | null;
  status: SignalStatus;
  status_reason: string | null;
}

export interface MappedSeries {
  series: SeriesInfo;
  reason: string;
}

export interface CategoryMarket {
  category: string;
  demand_context: MappedSeries[];
  input_cost: MappedSeries[];
}

export interface MarketOverview {
  note: string;
  sales_first_date: IsoDate | null;
  sales_last_date: IsoDate | null;
  categories: CategoryMarket[];
  sources: SourceStatus[];
}

export interface SignalPoint {
  period_start: IsoDate;
  value: number;
  days: number;
}

export interface SeriesData {
  key: string;
  granularity: Granularity;
  aggregation: "mean" | "sum";
  is_forecast: boolean;
  points: SignalPoint[];
}

export interface Headline {
  title: string;
  url: string;
  publisher: string;
  published_at: string;
  language: string;
}

export interface HeadlinesResponse {
  category: string;
  items: Headline[];
  total: number;
  source: SourceStatus;
}

export interface ProductMarket {
  note: string;
  shapes_note: string;
  sku: string;
  name: string;
  category: string;
  demand_context: MappedSeries[];
  input_cost: MappedSeries[];
}

export function useMarketOverview() {
  return useQuery({
    queryKey: ["market", "overview"],
    queryFn: () => getJson<MarketOverview>("/market/overview"),
    staleTime: STALE,
  });
}

/** Values for these series, bucketed by `granularity` (monthly series stay monthly). */
export function useSignalSeries(
  keys: string[],
  granularity: Granularity,
  dateFrom?: IsoDate | null,
) {
  const sorted = [...new Set(keys)].sort();
  return useQuery({
    queryKey: ["market", "series", sorted, granularity, dateFrom ?? null],
    queryFn: async () => {
      const response = await getJson<{ items: SeriesData[] }>("/market/series", {
        keys: sorted,
        granularity,
        date_from: dateFrom ?? undefined,
      });
      return new Map(response.items.map((item) => [item.key, item]));
    },
    enabled: sorted.length > 0,
    staleTime: STALE,
    placeholderData: keepPreviousData,
  });
}

export function useHeadlines(category: string, limit = 6) {
  return useQuery({
    queryKey: ["market", "headlines", category, limit],
    queryFn: () => getJson<HeadlinesResponse>("/market/headlines", { category, limit }),
    staleTime: STALE,
  });
}

export function useProductMarket(sku: string) {
  return useQuery({
    queryKey: ["market", "product", sku],
    queryFn: () => getJson<ProductMarket>(`/products/${encodeURIComponent(sku)}/market`),
    enabled: Boolean(sku),
    staleTime: STALE,
  });
}
