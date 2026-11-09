import { cn } from "../../lib/cn";

/**
 * The chart palette, read from tokens.css. Series colours carry identity only: never
 * sage, amber or clay, which mean good, warning and bad.
 *
 * Three slots, in this order, measured with a colour-vision simulation (CLAUDE.md,
 * "Chart rules"). A fourth series is an error state, not a fourth colour.
 */
export const SERIES_COLORS = [
  "var(--color-series-1)", // maroon-500: the primary series
  "var(--color-series-2)", // ink-400: comparison (last year, the rest)
  "var(--color-series-3)", // maroon-900
] as const;

export const MAX_SERIES = SERIES_COLORS.length;

/** The same three colours as utilities, for HTML keys in legends and tooltips. */
export const SERIES_BG = [cn("bg-series-1"), cn("bg-series-2"), cn("bg-series-3")] as const;
export const SERIES_STROKE = [
  cn("stroke-series-1"),
  cn("stroke-series-2"),
  cn("stroke-series-3"),
] as const;

/** Maroon at low opacity, behind the primary series: never a second colour. */
export const BAND_COLOR = "var(--color-band)";
/** The wider interval (95%), drawn under BAND_COLOR: the same maroon, lighter. */
export const BAND_OUTER_COLOR = "var(--color-band-outer)";
/** Recessive hairline grid. */
export const GRID_COLOR = "var(--color-line)";
/** Baselines, the forecast divider and the hover cursor: ink-400 meets 3:1 for marks. */
export const RULE_COLOR = "var(--color-line-strong)";
/** The ring around hover dots, so they stay legible where lines cross. */
export const SURFACE_COLOR = "var(--color-surface)";
/** Event annotations: holidays as rules, promotions as washes (tokens.css). */
export const ANNOTATION_COLOR = "var(--color-annotation)";
export const ANNOTATION_BAND_COLOR = "var(--color-annotation-band)";
/**
 * Up and down against the comparison period: the positive (sage) and negative (clay)
 * tokens. They encode the sign of a difference and nothing else: never a series, and
 * never on or beside a maroon series (CLAUDE.md, Chart rules, has the measured ΔE).
 * Position about the zero line carries the meaning; colour only reinforces it.
 */
export const UP_COLOR = "var(--color-positive)";
export const DOWN_COLOR = "var(--color-negative)";
/** A change that rounds to 0.0%, and the no-comparison marker: neutral ink. */
export const NEUTRAL_MARK_COLOR = "var(--color-line-strong)";
/** Hover band behind a bar group. */
export const CURSOR_FILL = "var(--color-surface-muted)";

/** Number and date ticks: the type scale's 12px step, tabular figures, secondary text. */
export const TICK_CLASS = cn("figure fill-fg-muted text-step-n2");
/** Category ticks are words: proportional figures, so "Non-stick" keeps a normal hyphen. */
export const CATEGORY_TICK_CLASS = cn("fill-fg-muted text-step-n2 normal-nums");

export type ChartHeight = "sm" | "md" | "lg";

export const CHART_HEIGHT: Record<ChartHeight, string> = {
  sm: cn("h-chart-sm"),
  md: cn("h-chart-md"),
  lg: cn("h-chart-lg"),
};

/** One plotted series. `key` is stable (colour follows the entity, never its rank). */
export interface Series {
  key: string;
  label: string;
}

/** Loading, error and empty: every chart takes these, and none draws axes without data. */
export interface ChartStateProps {
  /** True while the data is loading: a skeleton the size of the plot. */
  isLoading?: boolean;
  /** Set when loading failed (e.g. TanStack Query's `error`): an error state. */
  error?: unknown;
  /** Offered as "Try again" in the error state (e.g. `refetch`). */
  onRetry?: () => void;
  /** Empty state wording when there are no values to plot. */
  emptyTitle?: string;
  emptyMessage?: string;
}
