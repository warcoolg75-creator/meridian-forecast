import { errorMessage } from "../../lib/format";
import { MAX_SERIES, type ChartStateProps } from "./chart-theme";

/** What a chart's frame shows instead of, or as, its plot. */
export type ChartView =
  | { kind: "loading" }
  | { kind: "error"; title: string; message: string; onRetry?: () => void }
  | { kind: "empty"; title: string; message?: string }
  | { kind: "ready" };

/**
 * Loading wins, then a load error, then too many series (a caller bug: it has no retry),
 * then no values at all. Only "ready" draws axes.
 */
export function resolveChartView(
  state: ChartStateProps,
  { seriesCount, hasValues }: { seriesCount: number; hasValues: boolean },
): ChartView {
  if (state.isLoading) return { kind: "loading" };
  if (state.error) {
    return {
      kind: "error",
      title: "Couldn’t load this chart",
      message: errorMessage(state.error),
      onRetry: state.onRetry,
    };
  }
  if (seriesCount > MAX_SERIES) {
    return {
      kind: "error",
      title: `Too many series: ${seriesCount}`,
      message: `A chart shows at most ${MAX_SERIES} series, because a fourth colour cannot be told apart from the others. Fold the smallest into “Other”, or split them across charts.`,
    };
  }
  if (!hasValues) {
    return {
      kind: "empty",
      title: state.emptyTitle ?? "No data to plot",
      message: state.emptyMessage ?? "Nothing matches the current filters.",
    };
  }
  return { kind: "ready" };
}
