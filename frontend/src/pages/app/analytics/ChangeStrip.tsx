import type { ReactNode } from "react";

import type { ComparisonMode, TimeseriesResponse } from "../../../api/analytics";
import { COMPARISON_LABELS } from "../../../api/analytics";
import { DivergingBarChart } from "../../../components/charts/DivergingBarChart";
import type { Granularity } from "../../../lib/dates";
import { formatInteger, formatRupees } from "../../../lib/format";
import { ALIGNED_AXIS_WIDTH, bucketChange, COMPARISON_PHRASE, X_AXIS_LABEL } from "./present";

/**
 * Under a time series: each period's change against the comparison period, as bars about
 * a zero line, its own panel lined up with the chart above (same `syncId`, and the series
 * drawn with `alignToBars` and ALIGNED_AXIS_WIDTH). Up and down are always against the
 * comparison period, never the line's own slope: this data is seasonal, and the fall
 * after Diwali is the season, not a decline.
 */
export function ChangeStrip({
  series,
  metric,
  mode,
  granularity,
  period,
  syncId,
  isLoading,
  error,
  onRetry,
  footer,
}: {
  series: TimeseriesResponse | undefined;
  metric: "revenue" | "units";
  mode: ComparisonMode;
  granularity: Granularity;
  /** "10 Jul – 8 Oct 2026", for the description. */
  period: string;
  syncId: string;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  /** Under the strip, e.g. the festivals that moved between the two years. */
  footer?: ReactNode;
}) {
  const isRevenue = metric === "revenue";
  const then = COMPARISON_LABELS[mode];
  const format = isRevenue ? formatRupees : formatInteger;
  const measure = isRevenue ? "Revenue" : "Units sold";
  const data = (series?.points ?? []).map((point) => {
    const current = isRevenue ? point.revenue_minor : point.units;
    const baseline = isRevenue ? point.baseline_revenue_minor : point.baseline_units;
    return {
      key: point.period_start,
      label: point.period_start,
      heading: point.period_start,
      ...bucketChange(point, current, baseline, series?.baseline_history, mode),
      details: [
        { label: "This period", value: format(current) },
        { label: then, value: format(baseline) },
      ],
    };
  });
  return (
    <DivergingBarChart
      title={`${measure}: change ${COMPARISON_PHRASE[mode]}`}
      description={`${measure} per ${granularity} for ${period} against the same days in the ${then.toLowerCase()}, as a percentage. Bars above zero are up, below zero down; a ring marks a ${granularity} with nothing to compare with.`}
      data={data}
      granularity={granularity}
      categoryAxisLabel={X_AXIS_LABEL[granularity]}
      valueAxisLabel={`Change in ${isRevenue ? "revenue" : "units sold"} (%)`}
      comparisonLabel={then.toLowerCase()}
      yAxisWidth={ALIGNED_AXIS_WIDTH}
      syncId={syncId}
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      emptyTitle="Nothing to compare with"
      emptyMessage={data.find((d) => d.reason)?.reason ?? "No comparison for this period."}
      footer={footer}
    />
  );
}
