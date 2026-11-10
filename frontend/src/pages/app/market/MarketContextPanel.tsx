import { useMemo } from "react";

import { useCoverage, useTimeseries } from "../../../api/analytics";
import { useProductMarket, useSignalSeries, type MappedSeries } from "../../../api/market";
import { TimeSeriesChart } from "../../../components/charts/TimeSeriesChart";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { ErrorState } from "../../../components/feedback/ErrorState";
import { Card } from "../../../components/ui/Card";
import { formatDate, formatRange, type IsoDate } from "../../../lib/dates";
import { errorMessage, formatCompact } from "../../../lib/format";
import { ALIGNED_AXIS_WIDTH, X_AXIS_LABEL } from "../analytics/present";
import { CONTEXT_NOTE, SHAPES_NOTE, weekStarts } from "./present";
import { ContextNote, SignalChart } from "./SignalCard";

/** The product's weekly sales and its demand-context signals hover together. */
const SYNC = "market-context";

/**
 * A product's mapped market signals beside its sales, over the whole sales history.
 * The sales chart (maroon) and the weekly demand-context charts (ink) share one week axis
 * and one value-axis width, so a week sits at the same x in each; input costs follow,
 * at their own frequency.
 */
export function MarketContextPanel({ sku }: { sku: string }) {
  const market = useProductMarket(sku);
  const coverage = useCoverage();
  const first = coverage.data?.first_date ?? null;
  const last = coverage.data?.last_date ?? null;
  const demand = useMemo(() => market.data?.demand_context ?? [], [market.data]);
  const cost = useMemo(() => market.data?.input_cost ?? [], [market.data]);
  const keys = [
    ...demand.flatMap((m) => [
      m.series.key,
      ...(m.series.forecast_key ? [m.series.forecast_key] : []),
    ]),
    ...cost.map((m) => m.series.key),
  ];
  const values = useSignalSeries(keys, "week", first);
  const salesParams = useMemo(
    () =>
      first && last ? { date_from: first, date_to: last, skus: [sku], granularity: "week" } : null,
    [first, last, sku],
  );
  const sales = useTimeseries(salesParams);

  // One week axis for the sales and every weekly signal: from the first sales week to the
  // last signal week (which runs past the sales, into the weather forecast).
  const end = useMemo(() => {
    let latest: IsoDate | null = last;
    for (const m of demand) {
      for (const key of [m.series.key, m.series.forecast_key]) {
        const points = key ? values.data?.get(key)?.points : undefined;
        const tail = points?.[points.length - 1]?.period_start;
        if (tail && (!latest || tail > latest)) latest = tail;
      }
    }
    return latest;
  }, [demand, values.data, last]);
  const periods = useMemo(() => (first && end ? weekStarts(first, end) : []), [first, end]);
  const salesByWeek = new Map((sales.data?.points ?? []).map((p) => [p.period_start, p.units]));
  const loading = market.isPending || coverage.isPending;
  const range = first && end ? formatRange(first, end) : "";

  const signal = (m: MappedSeries, aligned: boolean) => (
    <SignalChart
      key={m.series.key}
      mapped={m}
      observed={values.data?.get(m.series.key)}
      forecast={m.series.forecast_key ? values.data?.get(m.series.forecast_key) : undefined}
      periods={aligned ? periods : undefined}
      period={aligned ? `weekly, ${range}` : first ? `from ${formatDate(first)}` : ""}
      syncId={aligned ? SYNC : undefined}
      yAxisWidth={aligned ? ALIGNED_AXIS_WIDTH : undefined}
      isLoading={values.isPending || loading}
      error={values.error}
      onRetry={() => void values.refetch()}
    />
  );

  return (
    <section aria-labelledby="market-context-title" className="space-y-4">
      <div className="space-y-1">
        <h2 id="market-context-title" className="text-step-2">
          Market context
        </h2>
        <p className="text-step-n1 text-fg-muted">{SHAPES_NOTE}</p>
      </div>
      <ContextNote>{CONTEXT_NOTE}</ContextNote>

      {market.error && (
        <Card>
          <ErrorState
            title="Couldn’t load this product’s market signals"
            message={errorMessage(market.error)}
            onRetry={() => void market.refetch()}
          />
        </Card>
      )}
      {market.data && demand.length === 0 && cost.length === 0 && (
        <Card>
          <EmptyState
            title="No market signals mapped"
            description="None of the external sources is mapped to this product."
          />
        </Card>
      )}

      {(loading || demand.length > 0) && (
        <div className="space-y-6">
          <TimeSeriesChart
            title="Units sold"
            description={`This product's weekly units sold over the whole sales history (synthetic data), whatever the filters above, on the same weeks as the signals below${last ? `; sales data ends ${formatDate(last)}` : ""}.`}
            series={[{ key: "units", label: "Units sold" }]}
            data={periods.map((date) => ({
              date,
              values: { units: salesByWeek.get(date) ?? null },
            }))}
            granularity="week"
            tickGranularity="month"
            yAxisLabel="Units sold (units per week)"
            xAxisLabel={X_AXIS_LABEL.week}
            formatTick={formatCompact}
            height="sm"
            yAxisWidth={ALIGNED_AXIS_WIDTH}
            syncId={SYNC}
            isLoading={loading || sales.isPending}
            error={sales.error}
            onRetry={() => void sales.refetch()}
            emptyTitle="No sales"
          />
          {demand.map((m) => signal(m, m.series.frequency !== "monthly"))}
        </div>
      )}

      {cost.length > 0 && (
        <div className="space-y-4">
          <div className="space-y-1">
            <h3 className="text-step-1">Input costs</h3>
            <p className="text-step-n1 text-fg-muted">
              What this product’s materials and freight cost: for production planning, not a demand
              signal.
            </p>
          </div>
          <div className="grid gap-6 lg:grid-cols-2">{cost.map((m) => signal(m, false))}</div>
        </div>
      )}
    </section>
  );
}
