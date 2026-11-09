import { useState } from "react";

import {
  downloadBacktestReport,
  modelLabel,
  useLeaderboard,
  useOracleTest,
  type LeaderboardRow,
} from "../../../api/forecast";
import { BarChart } from "../../../components/charts/BarChart";
import { DataTable, type Column } from "../../../components/data/DataTable";
import { PageScaffold } from "../../../components/shell/PageScaffold";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { formatDate, formatRange } from "../../../lib/dates";
import { errorMessage, formatInteger, formatPercent } from "../../../lib/format";
import { isPointerClick } from "../../../lib/pointer";
import { pct, signedPct } from "./present";
import { ForecastTabs } from "./shared";

const ORACLE = "oracle";

const COLUMNS: Column<LeaderboardRow>[] = [
  { key: "model", header: "Model", value: (r) => modelLabel(r.model) },
  {
    key: "wape",
    header: "Error (WAPE)",
    value: (r) => r.wape,
    render: (r) => pct(r.wape),
    numeric: true,
  },
  {
    key: "skill",
    header: "Skill vs seasonal naive",
    value: (r) => r.skill,
    render: (r) => (r.skill === null ? "–" : signedPct(r.skill)),
    numeric: true,
  },
  {
    key: "median",
    header: "Median per-product skill",
    value: (r) => r.median_sku_skill,
    render: (r) => (r.median_sku_skill === null ? "–" : signedPct(r.median_sku_skill)),
    numeric: true,
  },
  {
    key: "coverage_80",
    header: "80% coverage",
    value: (r) => r.coverage_80,
    render: (r) => pct(r.coverage_80),
    numeric: true,
  },
  {
    key: "n",
    header: "Forecast-weeks",
    value: (r) => r.n_weeks,
    render: (r) => formatInteger(r.n_weeks),
    numeric: true,
  },
];

/** The backtest's leaderboard, the noise floor and the forward oracle test, all as stored. */
export default function Evidence() {
  const leaderboard = useLeaderboard();
  const oracleTest = useOracleTest();
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const board = leaderboard.data;
  const floor = board?.models.find((m) => m.model === ORACLE);
  const festive = oracleTest.data?.festive;

  return (
    <PageScaffold
      title="Model evidence"
      subtitle="How the forecasting models scored in the backtest, and how close any model can get."
    >
      <ForecastTabs />

      <Card className="space-y-2 text-step-n1">
        <h2 className="text-step-1">Read these numbers with this in mind</h2>
        <p className="max-w-3xl text-fg-muted">
          The held-out weeks and the forward oracle test were each looked at twice, once per model
          version, and the second version was changed after seeing the first’s results. So neither
          figure is a clean out-of-sample result. The past forecasts on each product page view the
          held-out weeks a third time, only to draw them: nothing was chosen or scored from that
          look. The clean test is a sealed year of new data, scored once at the end of the project.
        </p>
        <p>
          <Button
            variant="secondary"
            size="sm"
            onClick={(e) => {
              setDownloadError(null);
              downloadBacktestReport().catch((err: unknown) => setDownloadError(errorMessage(err)));
              if (isPointerClick(e)) e.currentTarget.blur();
            }}
          >
            Download the backtest report
          </Button>
          <span className="ml-2 text-step-n2 text-fg-muted">
            docs/backtest-report.md, every figure in full
          </span>
        </p>
        {downloadError && <p className="text-negative">{downloadError}</p>}
      </Card>

      <BarChart
        title="Held-out error by model"
        description="Pooled WAPE of each model over the held-out 13 weeks, 1 to 26 weeks ahead, on the products with a year of sales, next to the oracle floor."
        series={[{ key: "wape", label: "WAPE" }]}
        data={(board?.models ?? []).map((m) => ({
          category: m.model === ORACLE ? "Oracle floor (noise)" : modelLabel(m.model),
          values: { wape: m.wape },
        }))}
        orientation="horizontal"
        categoryAxisLabel="Model"
        valueAxisLabel="Error, WAPE (% of units sold)"
        formatValue={formatPercent}
        formatTick={formatPercent}
        isLoading={leaderboard.isPending}
        error={leaderboard.error}
        onRetry={() => void leaderboard.refetch()}
        emptyTitle="No backtest yet"
        footer={
          floor && (
            <p className="text-step-n2 text-fg-muted">
              The oracle floor ({pct(floor.wape)}) is the error of a forecast that knows the true
              expected demand: what is left is pure week-to-week randomness, which no model can
              beat.
            </p>
          )
        }
      />

      <DataTable
        caption="Backtest leaderboard, held-out window"
        columns={COLUMNS}
        rows={board?.models ?? []}
        rowKey={(r) => r.model}
        isLoading={leaderboard.isPending}
        error={leaderboard.error}
        onRetry={() => void leaderboard.refetch()}
        emptyTitle="No backtest yet"
        capHeight={false}
      />
      {board && (
        <p className="max-w-4xl text-step-n1 text-fg-muted">
          Backtest run {board.run.id}, trained {formatDate(board.run.trained_at.slice(0, 10))}.
          Pooled error weighs products by volume; the median per-product skill counts each of the{" "}
          {formatInteger(board.headline_skus.length)} products once. The target is a skill of{" "}
          {formatPercent(board.target_skill)} against seasonal naive.
        </p>
      )}

      <section aria-labelledby="oracle-test-title" className="space-y-3">
        <h2 id="oracle-test-title" className="text-step-2">
          Forward oracle test
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Card className="flex flex-col gap-2">
            <p className="text-step-n1 font-medium text-fg-muted">Festive products’ skill</p>
            <p className="text-step-4 font-semibold text-fg figure">
              {oracleTest.isPending ? "…" : signedPct(festive?.skill)}
            </p>
            <p className="text-step-n2 text-fg-muted">
              {festive
                ? `Error ${pct(festive.champion_wape)} against seasonal naive’s ${pct(festive.naive_wape)}, over ${formatInteger(festive.skus.length)} packaged-food and kitchen products.`
                : oracleTest.error
                  ? errorMessage(oracleTest.error)
                  : ""}
            </p>
          </Card>
          <Card className="flex flex-col gap-2">
            <p className="text-step-n1 font-medium text-fg-muted">All products’ skill</p>
            <p className="text-step-4 font-semibold text-fg figure">
              {oracleTest.isPending ? "…" : signedPct(oracleTest.data?.pooled.skill)}
            </p>
            <p className="text-step-n2 text-fg-muted">
              {oracleTest.data
                ? `Error ${pct(oracleTest.data.pooled.champion_wape)} against seasonal naive’s ${pct(oracleTest.data.pooled.naive_wape)}, over ${formatInteger(oracleTest.data.pooled.skus.length)} products.`
                : ""}
            </p>
          </Card>
        </div>
        {oracleTest.data && (
          <p className="max-w-4xl text-step-n1 text-fg-muted">
            The stored forecast for the weeks starting{" "}
            {formatRange(oracleTest.data.weeks_from, oracleTest.data.weeks_to)}, scored against the
            demand the data was generated from, with no promotions and no supply shocks. It measures
            something different from the backtest error above, so the two are not comparable.
          </p>
        )}
      </section>
    </PageScaffold>
  );
}
