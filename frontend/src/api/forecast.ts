/**
 * The forecast and backtest API (/api/v1/forecasts/*, /backtest/*): response types mirror
 * backend/app/schemas/forecasting.py. Everything comes from the stored runs: the page
 * never computes a forecast figure itself, it only sums, formats and plots what it gets.
 */
import { useQuery } from "@tanstack/react-query";

import type { IsoDate } from "../lib/dates";
import { getJson } from "./analytics";
import { apiFetch } from "./client";

const STALE = 5 * 60 * 1000;

export type Horizon = 4 | 13 | 26;
export const HORIZONS: Horizon[] = [4, 13, 26];

export interface RunInfo {
  id: number;
  kind: "production" | "backtest";
  data_end_date: IsoDate;
  training_cutoff: IsoDate;
  trained_at: string;
  random_seed: number;
  library_versions: Record<string, string>;
}

export interface Assumptions {
  promotions: string;
  supply_shocks: string;
}

export interface ForecastWeek {
  week: IsoDate;
  horizon: number;
  p50: number;
  lo80: number;
  hi80: number;
  lo95: number;
  hi95: number;
}

export interface SkuForecast {
  sku: string;
  name: string;
  model: string;
  short_history: boolean;
  weeks: ForecastWeek[];
}

export interface AllocatedGroup {
  code: string;
  name: string;
  share: number;
  weeks: { week: IsoDate; horizon: number; p50: number }[];
}

export interface Allocation {
  view: "state" | "channel";
  allocated: true;
  method: string;
  share_from: IsoDate;
  share_to: IsoDate;
  groups: AllocatedGroup[];
}

export interface SkuForecastResponse {
  run: RunInfo;
  assumptions: Assumptions;
  forecast: SkuForecast;
  allocation: Allocation | null;
}

export interface OverviewRow {
  sku: string;
  name: string;
  model: string;
  short_history: boolean;
  next_4: number;
  next_13: number;
  last_year_4: number | null;
  last_year_13: number | null;
  change_4: number | null;
  change_13: number | null;
  no_comparison_reason: string | null;
  skill: number | null;
  abc: string | null;
  forecastability: string | null;
  error_cv: number | null;
}

export interface ForecastOverviewResponse {
  run: RunInfo;
  backtest_run_id: number;
  assumptions: Assumptions;
  models: string[];
  abc_from: IsoDate;
  abc_to: IsoDate;
  xyz_x_below: number;
  xyz_y_up_to: number;
  items: OverviewRow[];
}

export interface HorizonEvent {
  date: IsoDate;
  end_date: IsoDate;
  week: IsoDate;
  name: string;
  event_type: "public_holiday" | "festival";
  region_code: string | null;
}

export interface SkuAccuracy {
  model: string;
  n_weeks: number;
  wape: number | null;
  baseline_wape: number | null;
  skill: number | null;
  bias: number | null;
  coverage_80: number | null;
  coverage_95: number | null;
}

export interface PastForecastWeek {
  week: IsoDate;
  origin: IsoDate;
  weeks_before: number;
  actual: number;
  p50: number;
  lo80: number;
  hi80: number;
}

export interface SkuForecastContext {
  run: RunInfo;
  backtest_run_id: number;
  sku: string;
  name: string;
  short_history: boolean;
  launched_on: IsoDate;
  actuals: { week: IsoDate; units: number | null }[];
  events: HorizonEvent[];
  accuracy: SkuAccuracy | null;
  held_out_from: IsoDate;
  past_forecasts: PastForecastWeek[];
}

export interface LeaderboardRow {
  model: string;
  wape: number | null;
  skill: number | null;
  median_sku_skill: number | null;
  bias: number | null;
  mase: number | null;
  coverage_80: number | null;
  coverage_95: number | null;
  n_weeks: number;
}

export interface LeaderboardResponse {
  run: RunInfo;
  window: "selection" | "held_out" | "festive_2025";
  shocks: "included" | "excluded";
  target_skill: number;
  headline_skus: string[];
  models: LeaderboardRow[];
  champions: {
    sku: string;
    model: string;
    short_history: boolean;
    wape: number | null;
    baseline_wape: number | null;
    skill: number | null;
    coverage_80: number | null;
  }[];
}

export interface OracleTestScore {
  skus: string[];
  champion_wape: number | null;
  naive_wape: number | null;
  skill: number | null;
}

export interface OracleTestResponse {
  run: RunInfo;
  weeks_from: IsoDate;
  weeks_to: IsoDate;
  pooled: OracleTestScore;
  festive: OracleTestScore;
}

/** How models are named on screen. Unknown names show as stored. */
export const MODEL_LABELS: Record<string, string> = {
  seasonal_naive: "Seasonal naive",
  ets: "ETS",
  prophet: "Prophet",
  lightgbm: "LightGBM",
  prophet_lightgbm: "Prophet + LightGBM (mean)",
  champion: "Champions",
  oracle: "Oracle floor",
};

export function modelLabel(model: string): string {
  return MODEL_LABELS[model] ?? model;
}

export function useForecastOverview() {
  return useQuery({
    queryKey: ["forecasts", "overview"],
    queryFn: () => getJson<ForecastOverviewResponse>("/forecasts/overview"),
    staleTime: STALE,
  });
}

export function useSkuForecast(
  sku: string,
  horizon: Horizon,
  view: "sku" | "state" | "channel" = "sku",
) {
  return useQuery({
    queryKey: ["forecasts", sku, horizon, view],
    queryFn: () =>
      getJson<SkuForecastResponse>(`/forecasts/${encodeURIComponent(sku)}`, { horizon, view }),
    enabled: Boolean(sku),
    staleTime: STALE,
  });
}

export function useSkuForecastContext(sku: string) {
  return useQuery({
    queryKey: ["forecasts", sku, "context"],
    queryFn: () => getJson<SkuForecastContext>(`/forecasts/${encodeURIComponent(sku)}/context`),
    enabled: Boolean(sku),
    staleTime: STALE,
  });
}

export function useLeaderboard() {
  return useQuery({
    queryKey: ["backtest", "leaderboard", "held_out"],
    queryFn: () => getJson<LeaderboardResponse>("/backtest/leaderboard", { window: "held_out" }),
    staleTime: STALE,
  });
}

export function useOracleTest() {
  return useQuery({
    queryKey: ["forecasts", "oracle-test"],
    queryFn: () => getJson<OracleTestResponse>("/forecasts/oracle-test"),
    staleTime: STALE,
  });
}

/** Fetches a file with the access token and hands it to the browser as a download. */
async function download(path: string, filename: string): Promise<void> {
  const response = await apiFetch(`/api/v1${path}`);
  if (!response.ok) throw new Error(`Download failed (${response.status}).`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** The CSV the API builds for this SKU and horizon: the same numbers as the JSON. */
export function downloadForecastCsv(sku: string, horizon: Horizon): Promise<void> {
  return download(
    `/forecasts/${encodeURIComponent(sku)}/csv?horizon=${horizon}`,
    `forecast-${sku}-${horizon}w.csv`,
  );
}

/** docs/backtest-report.md, served by the API (sign-in needed, so not a plain link). */
export function downloadBacktestReport(): Promise<void> {
  return download("/backtest/report", "backtest-report.md");
}
