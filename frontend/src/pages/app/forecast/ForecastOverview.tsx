import { useNavigate } from "react-router";

import { useForecastOverview, type OverviewRow } from "../../../api/forecast";
import { SignedChange } from "../../../components/charts/SignedChange";
import { DataTable, type Column } from "../../../components/data/DataTable";
import { useClientTable } from "../../../components/data/useClientTable";
import { PageScaffold } from "../../../components/shell/PageScaffold";
import { Badge } from "../../../components/ui/Badge";
import { Card } from "../../../components/ui/Card";
import { formatRange } from "../../../lib/dates";
import { formatInteger } from "../../../lib/format";
import { FORECASTABILITY_TIP, ForecastabilityNote } from "./Forecastability";
import { modelsPhrase, signedPct } from "./present";
import { ForecastTabs, RunFacts } from "./shared";

function changeCell(value: number | null, row: OverviewRow) {
  if (value === null) {
    const reason = row.no_comparison_reason ?? "Nothing sold in the same weeks last year";
    return (
      <span className="text-fg-muted" title={reason}>
        <span aria-hidden>–</span>
        <span className="sr-only">No comparison: {reason}</span>
      </span>
    );
  }
  return <SignedChange value={value} />;
}

function classCell(row: OverviewRow) {
  if (!row.abc && !row.forecastability) return <span className="text-fg-muted">–</span>;
  const abc = row.abc ?? "–";
  const xyz = row.forecastability ?? "–";
  const title = `${abc}: by revenue share. Forecastability ${xyz}${
    row.error_cv === null
      ? ": no backtest errors yet"
      : `: forecast error CV ${row.error_cv.toFixed(2)}`
  }. ${FORECASTABILITY_TIP}`;
  return (
    <span title={title}>
      <Badge>{`${abc}${xyz}`}</Badge>
      <span className="sr-only">{title}</span>
    </span>
  );
}

const COLUMNS: Column<OverviewRow>[] = [
  {
    key: "name",
    header: "Product",
    value: (r) => r.name,
    sortable: true,
    render: (r) => (
      <span className="flex flex-col items-start gap-1">
        <span className="font-medium">{r.name}</span>
        <span className="flex flex-wrap items-center gap-2 text-step-n2 text-fg-muted normal-nums">
          {r.sku}
          {r.short_history && <Badge tone="warning">Short history</Badge>}
        </span>
      </span>
    ),
  },
  {
    key: "next_4",
    header: "Next 4 weeks",
    value: (r) => r.next_4,
    render: (r) => formatInteger(r.next_4),
    numeric: true,
    sortable: true,
  },
  {
    key: "change_4",
    header: "vs last year (4 wk)",
    value: (r) => r.change_4,
    render: (r) => changeCell(r.change_4, r),
    numeric: true,
    sortable: true,
  },
  {
    key: "next_13",
    header: "Next 13 weeks",
    value: (r) => r.next_13,
    render: (r) => formatInteger(r.next_13),
    numeric: true,
    sortable: true,
  },
  {
    key: "change_13",
    header: "vs last year (13 wk)",
    value: (r) => r.change_13,
    render: (r) => changeCell(r.change_13, r),
    numeric: true,
    sortable: true,
  },
  {
    key: "skill",
    header: "Skill vs seasonal naive",
    value: (r) => r.skill,
    render: (r) =>
      r.skill === null ? (
        <span className="text-fg-muted" title="No seasonal-naive forecast: under a year of sales">
          <span aria-hidden>–</span>
          <span className="sr-only">None: under a year of sales</span>
        </span>
      ) : (
        <span className="figure">{signedPct(r.skill)}</span>
      ),
    numeric: true,
    sortable: true,
  },
  {
    key: "class",
    header: "Class",
    value: (r) => `${r.abc ?? ""}${r.forecastability ?? ""}`,
    render: classCell,
    sortable: true,
  },
];

/** Every SKU's stored forecast at a glance; a row opens that SKU's forecast. */
export default function ForecastOverview() {
  const overview = useForecastOverview();
  const navigate = useNavigate();
  const table = useClientTable({
    rows: overview.data?.items ?? [],
    columns: COLUMNS,
    pageSize: 50,
    initialSort: { key: "next_13", direction: "desc" },
  });
  const data = overview.data;

  return (
    <PageScaffold
      title="Forecast"
      subtitle="Expected demand per product for the next 1 to 26 weeks."
    >
      <ForecastTabs />
      {data && (
        <Card>
          <RunFacts
            run={data.run}
            models={data.models}
            promotionsAssumed={data.assumptions.promotions}
            modelText={
              data.items.some((r) => r.short_history)
                ? `${modelsPhrase(data.models)}; LightGBM alone for products with under two years of sales`
                : undefined
            }
          />
        </Card>
      )}
      <DataTable
        caption="Forecast per product"
        columns={COLUMNS}
        rows={table.rows}
        rowKey={(r) => r.sku}
        sort={table.sort}
        onSortChange={table.onSortChange}
        onRowClick={(r) => void navigate(`/app/forecast/${r.sku}`)}
        isLoading={overview.isPending}
        error={overview.error}
        onRetry={() => void overview.refetch()}
        emptyTitle="No forecast yet"
        emptyMessage="Run make backtest, then make forecast."
        capHeight={false}
      />
      {data && (
        <div className="max-w-4xl space-y-2 text-step-n1 text-fg-muted">
          <p>
            <span className="font-medium text-fg">Units.</span> Sums of the weekly median forecasts.
            “vs last year” compares them with the units sold in the same weeks 52 weeks earlier, so
            weekdays line up; a festival that moved between the two years (Diwali, Dussehra) swings
            it without any change in demand.
          </p>
          <p>
            <span className="font-medium text-fg">Skill.</span> How much lower the forecast’s error
            was than seasonal naive (last year’s sales for the same week) over the held-out 13
            weeks, 1 to 26 weeks ahead.
          </p>
          <p>
            <span className="font-medium text-fg">Class.</span> A, B, C by share of revenue from{" "}
            {formatRange(data.abc_from, data.abc_to)}; then forecastability.
          </p>
          <ForecastabilityNote xBelow={data.xyz_x_below} yUpTo={data.xyz_y_up_to} />
        </div>
      )}
    </PageScaffold>
  );
}
