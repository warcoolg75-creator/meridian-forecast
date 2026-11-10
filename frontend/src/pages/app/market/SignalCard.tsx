import type { ReactNode } from "react";

import type { MappedSeries, SeriesData, SignalStatus } from "../../../api/market";
import { InfoIcon } from "../../../components/brand/icons";
import { TimeSeriesChart } from "../../../components/charts/TimeSeriesChart";
import { Badge } from "../../../components/ui/Badge";
import { cn } from "../../../lib/cn";
import { formatDate, type IsoDate } from "../../../lib/dates";
import { X_AXIS_LABEL } from "../analytics/present";
import {
  citationText,
  signalAxisLabel,
  signalPoints,
  signalTickFormatter,
  signalValueFormatter,
  timestampDate,
} from "./present";

/** The permanent note at the top of every market view. Not dismissible, by design. */
export function ContextNote({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      role="note"
      className={cn(
        "flex items-start gap-3 rounded-card border border-line-strong bg-surface-muted px-4 py-3 text-step-n1 text-fg",
        className,
      )}
    >
      <InfoIcon className="mt-px size-5 shrink-0 text-fg-muted" />
      <p className="font-medium">{children}</p>
    </div>
  );
}

const STATUS_LABEL: Record<Exclude<SignalStatus, "fresh">, string> = {
  stale: "Stale",
  partial: "Partial",
  never_fetched: "Not fetched yet",
  not_configured: "Not configured",
};

/** Nothing when fresh; otherwise a badge whose reason is in its tooltip and for screen readers. */
export function SignalStatusBadge({
  status,
  reason,
}: {
  status: SignalStatus;
  reason: string | null;
}) {
  if (status === "fresh") return null;
  return (
    <span title={reason ?? undefined}>
      <Badge tone={status === "stale" || status === "partial" ? "warning" : "neutral"}>
        {STATUS_LABEL[status]}
      </Badge>
      {reason && <span className="sr-only">{` ${reason}`}</span>}
    </span>
  );
}

/** Source, unit and dates under a signal chart, and why the series is here. */
export function SignalFacts({ mapped }: { mapped: MappedSeries }) {
  const s = mapped.series;
  const updated = timestampDate(s.last_success_at);
  return (
    <div className="space-y-2 text-step-n2 text-fg-muted">
      <p>{mapped.reason}</p>
      <p>
        <a
          href={s.source_homepage}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-fg underline decoration-line-strong underline-offset-2 hover:decoration-fg"
        >
          {s.source_name}
        </a>
        {`: ${citationText(s)}`}
      </p>
      <dl className="flex flex-wrap gap-x-4 gap-y-1">
        <div className="flex gap-1">
          <dt>Unit</dt>
          <dd className="text-fg">{s.unit}</dd>
        </div>
        <div className="flex gap-1">
          <dt>Updated</dt>
          <dd className="figure text-fg">{updated ? formatDate(updated) : "never"}</dd>
        </div>
        <div className="flex gap-1">
          <dt>Latest value</dt>
          <dd className="figure text-fg">
            {s.latest_observed_on ? formatDate(s.latest_observed_on) : "none"}
          </dd>
        </div>
      </dl>
      {s.status !== "fresh" && s.status_reason && (
        <p className="break-words text-warning-text">{s.status_reason}</p>
      )}
    </div>
  );
}

/** One market signal over time, in ink: context, never our sales (which are maroon). */
export function SignalChart({
  mapped,
  observed,
  forecast,
  periods,
  period,
  title,
  syncId,
  yAxisWidth,
  actions,
  isLoading,
  error,
  onRetry,
}: {
  mapped: MappedSeries;
  observed?: SeriesData;
  forecast?: SeriesData;
  /** Shared x positions across a panel's charts (see signalPoints). */
  periods?: IsoDate[];
  /** For the description, e.g. "9 Oct 2023 – 24 Nov 2026". */
  period: string;
  title?: string;
  syncId?: string;
  yAxisWidth?: number;
  actions?: ReactNode;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
}) {
  const s = mapped.series;
  const granularity = observed?.granularity ?? (s.frequency === "monthly" ? "month" : "week");
  const { points, forecastStart } = signalPoints(observed, forecast, periods);
  const formatValue = signalValueFormatter(s.unit);
  return (
    <TimeSeriesChart
      tone="context"
      title={title ?? s.label}
      description={`${s.description}, ${period}${forecastStart ? ", then the latest forecast, dashed" : ""}.`}
      series={[{ key: "value", label: s.label }]}
      data={points}
      forecastStart={forecastStart}
      granularity={granularity}
      // Years of weekly points: "Oct 2023" ticks, since "9 Oct" alone does not say which year.
      tickGranularity={points.length > 26 ? "month" : granularity}
      yAxisLabel={signalAxisLabel(s, granularity)}
      xAxisLabel={X_AXIS_LABEL[granularity]}
      formatValue={formatValue}
      formatTick={signalTickFormatter(s.unit)}
      height="sm"
      syncId={syncId}
      yAxisWidth={yAxisWidth}
      actions={
        <>
          {actions}
          <SignalStatusBadge status={s.status} reason={s.status_reason} />
        </>
      }
      persistentFooter={<SignalFacts mapped={mapped} />}
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      emptyTitle={s.status === "not_configured" ? "Not configured" : "No values yet"}
      emptyMessage={
        s.status_reason ??
        "This series has no stored values in this period. Run make signals-refresh."
      }
    />
  );
}
