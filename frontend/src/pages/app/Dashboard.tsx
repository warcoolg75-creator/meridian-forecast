import { useNavigate } from "react-router";

import {
  CHANNEL_LABELS,
  COMPARISON_LABELS,
  useChannels,
  useCoverage,
  useProductsAnalytics,
  useRegions,
  useSummary,
  useTimeseries,
} from "../../api/analytics";
import { BarChart } from "../../components/charts/BarChart";
import { KpiCard } from "../../components/charts/KpiCard";
import { TimeSeriesChart } from "../../components/charts/TimeSeriesChart";
import { SegmentedControl } from "../../components/filters/SegmentedControl";
import { ErrorState } from "../../components/feedback/ErrorState";
import { PageScaffold } from "../../components/shell/PageScaffold";
import { Card } from "../../components/ui/Card";
import { formatRange } from "../../lib/dates";
import {
  errorMessage,
  formatCompact,
  formatCompactRupees,
  formatInteger,
  formatPercent,
  formatRupees,
} from "../../lib/format";
import { ComparisonToggle, MovingFestivalsNote, ViewFilters } from "./analytics/Controls";
import {
  COMPARISON_PHRASE,
  deltaNote,
  partialCaption,
  partialNote,
  X_AXIS_LABEL,
} from "./analytics/present";
import { useAnalyticsView } from "./useAnalyticsView";

const TOP_PRODUCTS = 10;
type Metric = "revenue" | "units";
const METRICS: Array<{ value: Metric; label: string }> = [
  { value: "revenue", label: "Revenue" },
  { value: "units", label: "Units" },
];

/** How each product is selling and where: everything here comes from /analytics. */
export default function Dashboard() {
  const coverage = useCoverage();
  const asOf = coverage.data?.last_date;
  const view = useAnalyticsView(asOf);
  const navigate = useNavigate();
  const metric: Metric = view.params.get("metric") === "units" ? "units" : "revenue";

  const summary = useSummary(view.apiParams);
  const series = useTimeseries(view.apiParams);
  const products = useProductsAnalytics(view.apiParams);
  const regions = useRegions(view.apiParams);
  const channels = useChannels(view.apiParams);

  const comparisonInfo = summary.data?.comparison;
  const complete = comparisonInfo?.complete ?? true;
  const phrase = COMPARISON_PHRASE[view.comparison];
  const note = deltaNote(comparisonInfo, coverage.data?.first_date);
  const period = view.filters
    ? formatRange(view.filters.dateRange.from, view.filters.dateRange.to)
    : "";
  const kpi = (key: keyof NonNullable<typeof summary.data>["change"]) =>
    summary.data ? summary.data.change[key] : undefined;

  if (coverage.error) {
    return (
      <PageScaffold title="Dashboard">
        <Card>
          <ErrorState
            title="Couldn’t load the sales history"
            message={errorMessage(coverage.error)}
            onRetry={() => void coverage.refetch()}
          />
        </Card>
      </PageScaffold>
    );
  }

  const granularity = view.filters?.granularity ?? "week";
  const points = series.data?.points ?? [];
  const isRevenue = metric === "revenue";
  const top = (products.data?.rows ?? []).slice(0, TOP_PRODUCTS);

  return (
    <PageScaffold
      title="Dashboard"
      subtitle={
        period ? `Sales for ${period}, ${phrase}.` : "How each product is selling, and where."
      }
      actions={<ComparisonToggle value={view.comparison} onChange={view.setComparison} />}
    >
      <ViewFilters filters={view.filters} onChange={view.setFilters} asOf={asOf} />

      <section aria-label="Key figures" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Revenue"
          value={summary.data?.current.revenue_minor}
          formatValue={formatCompactRupees}
          delta={kpi("revenue")}
          comparison={phrase}
          deltaNote={note}
          isLoading={summary.isPending || !view.apiParams}
          error={summary.error}
          onRetry={() => void summary.refetch()}
          emptyMessage="No sales in this period."
        />
        <KpiCard
          label="Units sold"
          value={summary.data?.current.units}
          delta={kpi("units")}
          comparison={phrase}
          deltaNote={note}
          isLoading={summary.isPending || !view.apiParams}
          error={summary.error}
          onRetry={() => void summary.refetch()}
        />
        <KpiCard
          label="Gross margin"
          value={summary.data?.current.gross_margin_minor}
          formatValue={formatCompactRupees}
          delta={kpi("gross_margin")}
          comparison={phrase}
          deltaNote={note}
          footnote="At today’s unit costs: past costs are not stored."
          isLoading={summary.isPending || !view.apiParams}
          error={summary.error}
          onRetry={() => void summary.refetch()}
        />
        <KpiCard
          label="Orders"
          value={summary.data?.current.orders}
          delta={kpi("orders")}
          comparison={phrase}
          deltaNote={note}
          isLoading={summary.isPending || !view.apiParams}
          error={summary.error}
          onRetry={() => void summary.refetch()}
        />
      </section>

      <TimeSeriesChart
        title={isRevenue ? "Revenue over time" : "Units sold over time"}
        description={
          complete
            ? `${isRevenue ? "Revenue" : "Units sold"} per ${granularity} for ${period}, against the same days in the ${COMPARISON_LABELS[view.comparison].toLowerCase()}.`
            : `${isRevenue ? "Revenue" : "Units sold"} per ${granularity} for ${period}. ${note}.`
        }
        series={[
          { key: "current", label: "This period" },
          ...(complete ? [{ key: "baseline", label: COMPARISON_LABELS[view.comparison] }] : []),
        ]}
        data={points.map((p) => ({
          date: p.period_start,
          values: {
            current: isRevenue ? p.revenue_minor : p.units,
            baseline: isRevenue ? p.baseline_revenue_minor : p.baseline_units,
          },
          note: partialNote(p, granularity),
        }))}
        granularity={granularity}
        yAxisLabel={isRevenue ? "Revenue (₹)" : "Units sold (units)"}
        xAxisLabel={X_AXIS_LABEL[granularity]}
        formatValue={isRevenue ? formatRupees : formatInteger}
        formatTick={isRevenue ? formatCompactRupees : formatCompact}
        height="lg"
        isLoading={series.isPending || !view.apiParams}
        error={series.error}
        onRetry={() => void series.refetch()}
        emptyTitle="No sales in this period"
        emptyMessage="Nothing matches these filters. Try a longer range or fewer filters."
        actions={
          <SegmentedControl
            label="Measure"
            options={METRICS}
            value={metric}
            onChange={(value) => view.setParam("metric", value === "revenue" ? null : value)}
          />
        }
        footer={
          <>
            {partialCaption(points, granularity) && (
              <p className="text-step-n2 text-fg-muted">{partialCaption(points, granularity)}</p>
            )}
            <MovingFestivalsNote events={series.data?.moving_events ?? []} />
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <BarChart
          title="Top products"
          description={`The ${TOP_PRODUCTS} products with the most revenue, ${period}. Select a bar to open the product.`}
          series={[{ key: "revenue", label: "Revenue" }]}
          data={top.map((row) => ({ category: row.name, values: { revenue: row.revenue_minor } }))}
          orientation="horizontal"
          categoryAxisLabel="Product"
          valueAxisLabel="Revenue (₹)"
          formatValue={formatRupees}
          formatTick={formatCompactRupees}
          height="lg"
          onCategoryClick={(name) => {
            const row = top.find((r) => r.name === name);
            if (row) void navigate(`/app/products/${row.sku}?${view.params}`);
          }}
          isLoading={products.isPending || !view.apiParams}
          error={products.error}
          onRetry={() => void products.refetch()}
          emptyTitle="No product sold in this period"
        />
        <BarChart
          title="Sales by state"
          description={`Revenue per state, ${period}; a state includes its cities.`}
          series={[{ key: "revenue", label: "Revenue" }]}
          data={(regions.data?.rows ?? []).map((row) => ({
            category: row.name,
            values: { revenue: row.revenue_minor },
          }))}
          orientation="horizontal"
          categoryAxisLabel="State"
          valueAxisLabel="Revenue (₹)"
          formatValue={formatRupees}
          formatTick={formatCompactRupees}
          height="lg"
          isLoading={regions.isPending || !view.apiParams}
          error={regions.error}
          onRetry={() => void regions.refetch()}
          emptyTitle="No sales in any state in this period"
        />
      </div>

      <BarChart
        title="Channel mix"
        description={
          complete
            ? `Each channel's share of revenue, ${period}, against the ${COMPARISON_LABELS[view.comparison].toLowerCase()}.`
            : `Each channel's share of revenue, ${period}. ${note}.`
        }
        series={[
          { key: "current", label: "This period" },
          ...(complete ? [{ key: "baseline", label: COMPARISON_LABELS[view.comparison] }] : []),
        ]}
        data={(channels.data?.rows ?? []).map((row) => ({
          category: CHANNEL_LABELS[row.channel],
          values: { current: row.share, baseline: row.baseline_share },
        }))}
        orientation="horizontal"
        categoryAxisLabel="Channel"
        valueAxisLabel="Share of revenue (%)"
        formatValue={formatPercent}
        formatTick={formatPercent}
        isLoading={channels.isPending || !view.apiParams}
        error={channels.error}
        onRetry={() => void channels.refetch()}
        emptyTitle="No sales in any channel in this period"
      />
    </PageScaffold>
  );
}
