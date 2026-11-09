import { useMemo } from "react";
import { useNavigate } from "react-router";

import {
  useCoverage,
  useProductsAnalytics,
  type ProductRow,
  type ProductSort,
} from "../../api/analytics";
import { SignedChange } from "../../components/charts/SignedChange";
import { Sparkline } from "../../components/charts/Sparkline";
import { DataTable, type Column, type SortState } from "../../components/data/DataTable";
import { PageScaffold } from "../../components/shell/PageScaffold";
import { Badge } from "../../components/ui/Badge";
import { formatDate, formatRange } from "../../lib/dates";
import { formatInteger, formatPercent, formatRupees } from "../../lib/format";
import { ComparisonToggle, ViewFilters } from "./analytics/Controls";
import { DEMAND_VARIABILITY_TIP } from "./forecast/Forecastability";
import { COMPARISON_PHRASE } from "./analytics/present";
import { useAnalyticsView } from "./useAnalyticsView";

const SORTABLE: ProductSort[] = [
  "rank",
  "name",
  "category",
  "revenue",
  "units",
  "margin",
  "growth",
  "abc",
];

/** Arrow, sign and colour: colour is never the only signal of up or down. */
function growthCell(row: ProductRow) {
  if (row.growth === null) {
    return (
      <span className="text-fg-muted">
        <span aria-hidden>–</span>
        <span className="sr-only">No comparison</span>
      </span>
    );
  }
  return <SignedChange value={row.growth} />;
}

function classBadge(row: ProductRow) {
  if (!row.abc) return <span className="text-fg-muted">–</span>;
  const xyz = row.xyz ?? "–";
  const title =
    row.xyz === null
      ? `${row.abc}: by revenue share. Demand variability: not yet classifiable (${row.xyz_weeks} weeks of sales). ${DEMAND_VARIABILITY_TIP}`
      : `${row.abc}: by revenue share. Demand variability ${row.xyz}: weekly volume CV ${row.xyz_cv?.toFixed(2)} over ${row.xyz_weeks} weeks. ${DEMAND_VARIABILITY_TIP}`;
  return (
    <span title={title}>
      <Badge>{`${row.abc}${xyz}`}</Badge>
      <span className="sr-only">{title}</span>
    </span>
  );
}

/** Every SKU, ranked by revenue, with growth, ABC-XYZ class and a 13-week trend. */
export default function Products() {
  const coverage = useCoverage();
  const asOf = coverage.data?.last_date;
  const view = useAnalyticsView(asOf);
  const navigate = useNavigate();

  const sortParam = view.params.get("sort") as ProductSort | null;
  const sort: ProductSort = sortParam && SORTABLE.includes(sortParam) ? sortParam : "rank";
  const order = view.params.get("order") === "desc" ? "desc" : "asc";
  const apiParams = useMemo(
    () => (view.apiParams ? { ...view.apiParams, sort, order } : null),
    [view.apiParams, sort, order],
  );
  const products = useProductsAnalytics(apiParams);
  const period = view.filters
    ? formatRange(view.filters.dateRange.from, view.filters.dateRange.to)
    : "";
  const xyzWindow = products.data?.classification.xyz_window;

  const columns: Column<ProductRow>[] = [
    { key: "rank", header: "Rank", value: (r) => r.rank, numeric: true, sortable: true },
    {
      key: "name",
      header: "Product",
      value: (r) => r.name,
      sortable: true,
      render: (r) => (
        <span className="flex flex-col">
          <span className="font-medium">{r.name}</span>
          <span className="text-step-n2 text-fg-muted">{r.sku}</span>
        </span>
      ),
    },
    {
      key: "revenue",
      header: "Revenue",
      value: (r) => r.revenue_minor,
      render: (r) => formatRupees(r.revenue_minor),
      numeric: true,
      sortable: true,
    },
    {
      key: "units",
      header: "Units",
      value: (r) => r.units,
      render: (r) => formatInteger(r.units),
      numeric: true,
      sortable: true,
    },
    {
      key: "margin",
      header: "Gross margin",
      value: (r) => r.gross_margin_minor,
      render: (r) => formatRupees(r.gross_margin_minor),
      numeric: true,
      sortable: true,
    },
    {
      key: "growth",
      header: "Growth",
      value: (r) => r.growth,
      render: growthCell,
      numeric: true,
      sortable: true,
    },
    { key: "abc", header: "Class", value: (r) => r.abc, render: classBadge, sortable: true },
    {
      key: "trend",
      header: "Last 13 weeks",
      value: () => null,
      render: (r) => (
        <Sparkline
          values={r.sparkline}
          label={`${r.name}, units per week over the last 13 weeks: from ${formatInteger(r.sparkline[0] ?? 0)} to ${formatInteger(r.sparkline[r.sparkline.length - 1] ?? 0)}`}
          className="h-8 w-24"
        />
      ),
    },
    // Last, so that on a phone the figures come straight after the product name; the table
    // scrolls sideways there, and Category first hid every figure off-screen.
    { key: "category", header: "Category", value: (r) => r.category, sortable: true },
  ];

  return (
    <PageScaffold
      title="Products"
      subtitle={
        period
          ? `Every product for ${period}; growth ${COMPARISON_PHRASE[view.comparison]}.`
          : undefined
      }
      actions={<ComparisonToggle value={view.comparison} onChange={view.setComparison} />}
    >
      <ViewFilters filters={view.filters} onChange={view.setFilters} asOf={asOf} />
      <DataTable
        caption={`Products, ${period}`}
        columns={columns}
        rows={products.data?.rows ?? []}
        rowKey={(r) => r.sku}
        sort={{ key: sort, direction: order } satisfies SortState}
        onSortChange={(next) => {
          const isDefault = next.key === "rank" && next.direction === "asc";
          view.setPageParams({
            sort: isDefault ? null : next.key,
            order: next.direction === "asc" ? null : next.direction,
          });
        }}
        onRowClick={(r) => {
          const params = new URLSearchParams(view.params);
          params.delete("sort");
          params.delete("order");
          void navigate(`/app/products/${r.sku}?${params}`);
        }}
        isLoading={products.isPending || !apiParams}
        error={products.error ?? coverage.error}
        onRetry={() => void products.refetch()}
        emptyTitle="No products match"
        emptyMessage="Try fewer filters."
        capHeight={false}
      />
      {products.data && (
        <p className="max-w-4xl text-step-n1 text-fg-muted">
          <span className="font-medium text-fg">Class.</span> A, B, C by share of revenue in the
          period: A are the products making up the first{" "}
          {formatPercent(products.data.classification.abc_a_share)}, B the next{" "}
          {formatPercent(
            products.data.classification.abc_b_share - products.data.classification.abc_a_share,
          )}
          , C the rest. X, Y, Z are <span className="font-medium text-fg">demand variability</span>:
          how much weekly volume varies (coefficient of variation) over the 52 full weeks
          {xyzWindow
            ? ` from ${formatDate(xyzWindow.date_from)} to ${formatDate(xyzWindow.date_to)}`
            : ""}
          : X under {products.data.classification.xyz_x_below}, Y up to{" "}
          {products.data.classification.xyz_y_up_to}, Z above. It measures volume variability, not
          predictability: a regular festival peak still reads as Z. The forecast pages show
          forecastability instead, from the forecast’s own errors.
        </p>
      )}
    </PageScaffold>
  );
}
