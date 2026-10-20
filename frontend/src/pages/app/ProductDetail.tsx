import { useMemo } from "react";
import { useParams } from "react-router";

import {
  CHANNEL_LABELS,
  useChannels,
  useCoverage,
  useProductDetail,
  useProductsAnalytics,
  useRegions,
  useSummary,
  useTimeseries,
  type ProductEvent,
} from "../../api/analytics";
import { BarChart } from "../../components/charts/BarChart";
import { KpiCard } from "../../components/charts/KpiCard";
import { TimeSeriesChart, type ChartEvent } from "../../components/charts/TimeSeriesChart";
import { DataTable, type Column } from "../../components/data/DataTable";
import { ErrorState } from "../../components/feedback/ErrorState";
import { PageScaffold } from "../../components/shell/PageScaffold";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { formatDate, formatRange } from "../../lib/dates";
import {
  errorMessage,
  formatCompact,
  formatCompactRupees,
  formatInteger,
  formatRupees,
} from "../../lib/format";
import { ComparisonToggle, ViewFilters } from "./analytics/Controls";
import {
  COMPARISON_PHRASE,
  deltaNote,
  partialCaption,
  partialNote,
  X_AXIS_LABEL,
} from "./analytics/present";
import { useAnalyticsView } from "./useAnalyticsView";

const EVENT_TYPE: Record<ProductEvent["event_type"], string> = {
  promotion: "Promotion",
  public_holiday: "Public holiday",
  festival: "Festival",
  plant_shutdown: "Plant shutdown",
  trade_show: "Trade show",
};

function scopeOf(event: ProductEvent): string {
  if (event.scope === "product") return "This product";
  if (event.scope === "plant") return `Plant ${event.plant_code}`;
  if (event.scope === "regional") return event.region_code ?? "Regional";
  return "National";
}

const EVENT_COLUMNS: Column<ProductEvent>[] = [
  {
    key: "date",
    header: "Dates",
    value: (e) => e.date,
    // Never wrapped: in a narrow table a date broke onto three lines.
    render: (e) => (
      <span className="whitespace-nowrap">
        {e.date === e.end_date ? formatDate(e.date) : formatRange(e.date, e.end_date)}
      </span>
    ),
  },
  { key: "name", header: "Event", value: (e) => e.name },
  { key: "type", header: "Type", value: (e) => EVENT_TYPE[e.event_type] },
  { key: "scope", header: "Applies to", value: scopeOf },
];

/** One product: its figures, its history with promotions and holidays, where it sells. */
export default function ProductDetail() {
  const { sku = "" } = useParams();
  const coverage = useCoverage();
  const asOf = coverage.data?.last_date;
  const view = useAnalyticsView(asOf);
  const product = useProductDetail(sku);

  // This product only; the class comes from the full ranking, so it is not "A of one".
  const own = useMemo(
    () => (view.apiParams ? { ...view.apiParams, skus: [sku] } : null),
    [view.apiParams, sku],
  );
  const drill = view.params.get("drill");
  const regionParams = useMemo(
    () => (own ? (drill ? { ...own, level: "city", parent: drill } : own) : null),
    [own, drill],
  );
  const summary = useSummary(own);
  const series = useTimeseries(own);
  const ranking = useProductsAnalytics(view.apiParams);
  const regions = useRegions(regionParams);
  const states = useRegions(own);
  const channels = useChannels(own);

  const row = ranking.data?.rows.find((r) => r.sku === sku);
  const phrase = COMPARISON_PHRASE[view.comparison];
  const note = deltaNote(summary.data?.comparison, coverage.data?.first_date);
  const filters = view.filters;
  const period = filters ? formatRange(filters.dateRange.from, filters.dateRange.to) : "";
  const granularity = filters?.granularity ?? "week";
  const name = product.data?.name ?? sku;
  const drillName = states.data?.rows.find((r) => r.code === drill)?.name ?? drill;

  const inPeriod = useMemo(
    () =>
      (product.data?.events ?? []).filter(
        (e) => filters && e.date <= filters.dateRange.to && e.end_date >= filters.dateRange.from,
      ),
    [product.data, filters],
  );
  const chartEvents: ChartEvent[] = inPeriod
    .filter(
      (e) =>
        e.event_type === "promotion" ||
        e.event_type === "public_holiday" ||
        e.event_type === "festival",
    )
    .map((e) => ({
      from: e.date,
      to: e.end_date,
      label: e.region_code ? `${e.name} (${e.region_code})` : e.name,
      kind: e.event_type === "promotion" ? "span" : "day",
    }));

  if (product.error) {
    return (
      <PageScaffold title={sku}>
        <Card>
          <ErrorState
            title="Couldn’t load this product"
            message={errorMessage(product.error)}
            onRetry={() => void product.refetch()}
          />
        </Card>
      </PageScaffold>
    );
  }

  const loading = (q: { isPending: boolean }) => q.isPending || !own;

  return (
    <PageScaffold
      title={name}
      subtitle={
        product.data
          ? `${product.data.sku} · ${product.data.category} · ${period}, ${phrase}`
          : undefined
      }
      actions={
        <>
          {row?.abc && (
            <Badge>{`Class ${row.abc}${row.xyz ?? ""}${row.xyz ? "" : " (variability not yet classifiable)"}`}</Badge>
          )}
          <ComparisonToggle value={view.comparison} onChange={view.setComparison} />
        </>
      }
    >
      <ViewFilters filters={view.filters} onChange={view.setFilters} asOf={asOf} hideProducts />

      <section aria-label="Key figures" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Revenue"
          value={summary.data?.current.revenue_minor}
          formatValue={formatCompactRupees}
          delta={summary.data?.change.revenue}
          comparison={phrase}
          deltaNote={note}
          isLoading={loading(summary)}
          error={summary.error}
          onRetry={() => void summary.refetch()}
          emptyMessage="No sales in this period."
        />
        <KpiCard
          label="Units sold"
          value={summary.data?.current.units}
          delta={summary.data?.change.units}
          comparison={phrase}
          deltaNote={note}
          isLoading={loading(summary)}
          error={summary.error}
          onRetry={() => void summary.refetch()}
        />
        <KpiCard
          label="Gross margin"
          value={summary.data?.current.gross_margin_minor}
          formatValue={formatCompactRupees}
          delta={summary.data?.change.gross_margin}
          comparison={phrase}
          deltaNote={note}
          footnote="At today’s unit cost: past costs are not stored."
          isLoading={loading(summary)}
          error={summary.error}
          onRetry={() => void summary.refetch()}
        />
        <KpiCard
          label="Average selling price"
          value={summary.data?.current.average_selling_price_minor}
          formatValue={formatRupees}
          delta={summary.data?.change.average_selling_price}
          upIsGood={null}
          comparison={phrase}
          deltaNote={note}
          footnote="Revenue per unit, after discounts."
          isLoading={loading(summary)}
          error={summary.error}
          onRetry={() => void summary.refetch()}
        />
      </section>

      <TimeSeriesChart
        title="Sales history"
        description={`Units sold per ${granularity}, ${period}, with this product's promotions and the holidays and festivals in the period.`}
        series={[{ key: "units", label: "Units sold" }]}
        data={(series.data?.points ?? []).map((p) => ({
          date: p.period_start,
          values: { units: p.units },
          note: partialNote(p, granularity),
        }))}
        events={chartEvents}
        granularity={granularity}
        yAxisLabel="Units sold (units)"
        xAxisLabel={X_AXIS_LABEL[granularity]}
        formatTick={formatCompact}
        height="lg"
        isLoading={loading(series)}
        error={series.error}
        onRetry={() => void series.refetch()}
        emptyTitle="No sales in this period"
        emptyMessage="This product sold nothing that matches these filters."
        footer={
          partialCaption(series.data?.points ?? [], granularity) && (
            <p className="text-step-n2 text-fg-muted">
              {partialCaption(series.data?.points ?? [], granularity)}
            </p>
          )
        }
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <BarChart
          title={drill ? `Sales in ${drillName}, by city` : "Sales by state"}
          description={
            drill
              ? `Revenue per city in ${drillName}, ${period}.`
              : `Revenue per state, ${period}; a state includes its cities. Select a state to see its cities.`
          }
          series={[{ key: "revenue", label: "Revenue" }]}
          data={(regions.data?.rows ?? []).map((r) => ({
            category: r.name,
            values: { revenue: r.revenue_minor },
          }))}
          orientation="horizontal"
          categoryAxisLabel={drill ? "City" : "State"}
          valueAxisLabel="Revenue (₹)"
          formatValue={formatRupees}
          formatTick={formatCompactRupees}
          onCategoryClick={
            drill
              ? undefined
              : (stateName) => {
                  const state = regions.data?.rows.find((r) => r.name === stateName);
                  if (state) view.setParam("drill", state.code);
                }
          }
          actions={
            drill ? (
              <Button variant="secondary" size="sm" onClick={() => view.setParam("drill", null)}>
                All states
              </Button>
            ) : (
              <label className="flex items-center gap-2 text-step-n1 text-fg-muted">
                Cities in
                <select
                  className="h-8 rounded-control border border-line-strong bg-surface px-2 text-step-n1 text-fg"
                  value=""
                  onChange={(event) =>
                    event.target.value && view.setParam("drill", event.target.value)
                  }
                >
                  <option value="">Choose a state</option>
                  {(states.data?.rows ?? []).map((r) => (
                    <option key={r.code} value={r.code}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </label>
            )
          }
          isLoading={loading(regions)}
          error={regions.error}
          onRetry={() => void regions.refetch()}
          emptyTitle="No sales in these regions"
        />
        <BarChart
          title="Sales by channel"
          description={`Revenue per sales channel, ${period}.`}
          series={[{ key: "revenue", label: "Revenue" }]}
          data={(channels.data?.rows ?? []).map((r) => ({
            category: CHANNEL_LABELS[r.channel],
            values: { revenue: r.revenue_minor },
          }))}
          orientation="horizontal"
          categoryAxisLabel="Channel"
          valueAxisLabel="Revenue (₹)"
          formatValue={formatRupees}
          formatTick={formatCompactRupees}
          isLoading={loading(channels)}
          error={channels.error}
          onRetry={() => void channels.refetch()}
          emptyTitle="No sales in any channel"
        />
      </div>

      <section aria-labelledby="events-title" className="space-y-3">
        <h2 id="events-title" className="text-step-2">
          Events in this period
        </h2>
        <DataTable
          caption={`Events touching ${name}, ${period}`}
          columns={EVENT_COLUMNS}
          rows={inPeriod}
          rowKey={(e) => `${e.date}-${e.name}-${e.scope}`}
          isLoading={product.isPending}
          emptyTitle="No events in this period"
          emptyMessage="No promotions, holidays or shutdowns fall in these dates."
        />
        {product.data && (
          <p className="text-step-n2 text-fg-muted">
            Plant shutdowns are listed but not marked on the chart: they limit supply, not demand.{" "}
            {formatInteger(inPeriod.length)} events in {period}.
          </p>
        )}
      </section>
    </PageScaffold>
  );
}
