import { useNavigate } from "react-router";

import {
  CHANNEL_LABELS,
  COMPARISON_LABELS,
  useCatalog,
  useChannels,
  useCoverage,
  useProductsAnalytics,
  useRegions,
  useSummary,
  useTimeseries,
} from "../../api/analytics";
import { BarChart } from "../../components/charts/BarChart";
import { DivergingBarChart } from "../../components/charts/DivergingBarChart";
import { KpiCard } from "../../components/charts/KpiCard";
import { TimeSeriesChart } from "../../components/charts/TimeSeriesChart";
import { SegmentedControl } from "../../components/filters/SegmentedControl";
import { ErrorState } from "../../components/feedback/ErrorState";
import { PageScaffold } from "../../components/shell/PageScaffold";
import { Card } from "../../components/ui/Card";
import { formatDate, formatRange } from "../../lib/dates";
import {
  errorMessage,
  formatCompact,
  formatCompactRupees,
  formatInteger,
  formatPercent,
  formatRupees,
} from "../../lib/format";
import { ChangeStrip } from "./analytics/ChangeStrip";
import { ComparisonToggle, MovingFestivalsNote, ViewFilters } from "./analytics/Controls";
import {
  ALIGNED_AXIS_WIDTH,
  COMPARISON_PHRASE,
  deltaNote,
  partialCaption,
  partialNote,
  X_AXIS_LABEL,
} from "./analytics/present";
import { useAnalyticsView } from "./useAnalyticsView";

const TOP_PRODUCTS = 10;
/** The time series and its change strip hover together. */
const SYNC = "dashboard-over-time";
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
  const catalog = useCatalog();

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
  // Growth by product: those with a comparison, from the largest rise to the largest fall.
  const rows = products.data?.rows ?? [];
  const growing = rows
    .filter((r): r is typeof r & { growth: number } => r.growth !== null)
    .sort((a, b) => b.growth - a.growth);
  const then = COMPARISON_LABELS[view.comparison].toLowerCase();
  const launched = new Map((catalog.data?.products ?? []).map((p) => [p.sku, p.launched_on]));
  const leftOut = complete
    ? rows
        .filter((r) => r.growth === null)
        .map((r) => {
          const on = launched.get(r.sku);
          const after = on && comparisonInfo && on > comparisonInfo.date_from;
          return `${r.name} (${after ? `launched ${formatDate(on)}, after the ${then} began` : `nothing sold in the ${then}`})`;
        })
    : [];

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
        yAxisWidth={ALIGNED_AXIS_WIDTH}
        alignToBars
        syncId={SYNC}
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

      <ChangeStrip
        series={series.data}
        metric={metric}
        mode={view.comparison}
        granularity={granularity}
        period={period}
        syncId={SYNC}
        isLoading={series.isPending || !view.apiParams}
        error={series.error}
        onRetry={() => void series.refetch()}
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
        <DivergingBarChart
          title="Growth by product"
          description={`Revenue growth per product, ${period}, ${phrase}, from the largest rise to the largest fall. Bars right of zero are up, left of zero down. Select a bar to open the product.`}
          data={growing.map((r) => ({
            key: r.sku,
            label: r.name,
            heading: r.name,
            value: r.growth,
            details: [
              { label: "This period", value: formatRupees(r.revenue_minor) },
              {
                label: COMPARISON_LABELS[view.comparison],
                value: formatRupees(r.baseline_revenue_minor),
              },
            ],
          }))}
          orientation="horizontal"
          centreZero
          categoryAxisLabel="Product"
          valueAxisLabel="Revenue growth (%)"
          comparisonLabel={then}
          height="lg"
          onCategoryClick={(sku) => void navigate(`/app/products/${sku}?${view.params}`)}
          isLoading={products.isPending || !view.apiParams}
          error={products.error}
          onRetry={() => void products.refetch()}
          emptyTitle="No growth to show"
          emptyMessage={note ? `${note}.` : `No product sold in both this period and the ${then}.`}
          footer={
            leftOut.length > 0 && (
              <p className="text-step-n2 text-fg-muted">
                Left out, as there is nothing to compare with: {leftOut.join("; ")}.
              </p>
            )
          }
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
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
      </div>
    </PageScaffold>
  );
}
