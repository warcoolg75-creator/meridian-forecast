import { modelLabel } from "../../../api/forecast";
import { formatPercent, formatSignedPercent } from "../../../lib/format";

/** "Prophet + LightGBM (mean)", or several joined, from the stored forecast rows. */
export function modelsPhrase(models: string[]): string {
  return models.map(modelLabel).join(", ");
}

/** A fraction as a percentage, or a dash when there is none. */
export function pct(value: number | null | undefined): string {
  return typeof value === "number" ? formatPercent(value) : "–";
}

/** A signed fraction with a true minus, or a dash when there is none. */
export function signedPct(value: number | null | undefined): string {
  return typeof value === "number" ? formatSignedPercent(value) : "–";
}

/**
 * The stored model name. Forecast run 8 stored "prophet_lightgbm" for a short-history SKU
 * whose forecast is LightGBM alone (Prophet cannot fit it); later runs store "lightgbm"
 * (CLAUDE.md, Known issues). This maps run 8's label.
 */
export function shownModel(model: string, shortHistory: boolean): string {
  return shortHistory && model === "prophet_lightgbm"
    ? "LightGBM (alone: under two years of sales)"
    : modelLabel(model);
}
