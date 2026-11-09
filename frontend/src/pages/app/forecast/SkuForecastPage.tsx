import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router";

import {
  downloadForecastCsv,
  HORIZONS,
  useSkuForecast,
  useSkuForecastContext,
  type Allocation,
  type Horizon,
  type HorizonEvent,
} from "../../../api/forecast";
import { BarChart } from "../../../components/charts/BarChart";
import { TimeSeriesChart, type ChartEvent } from "../../../components/charts/TimeSeriesChart";
import { ErrorState } from "../../../components/feedback/ErrorState";
import { SegmentedControl } from "../../../components/filters/SegmentedControl";
import { PageScaffold } from "../../../components/shell/PageScaffold";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { formatDate, formatRange } from "../../../lib/dates";
import { errorMessage, formatCompact, formatInteger } from "../../../lib/format";
import { isPointerClick } from "../../../lib/pointer";
import { pct, shownModel, signedPct } from "./present";
import { ForecastTabs, RunFacts } from "./shared";

const EVENT_TYPE: Record<HorizonEvent["event_type"], string> = {
  public_holiday: "Public holiday",
  festival: "Festival",
};

function eventLabel(e: HorizonEvent): string {
  return e.region_code ? `${e.name} (${e.region_code})` : e.name;
}

const HORIZON_OPTIONS = HORIZONS.map((h) => ({ value: String(h), label: `${h} weeks` }));

function HorizonPicker({ value, onChange }: { value: Horizon; onChange: (h: Horizon) => void }) {
  return (
    <SegmentedControl
      label="Weeks ahead"
      options={HORIZON_OPTIONS}
      value={String(value)}
      onChange={(v) => onChange(Number(v) as Horizon)}
      className="w-full sm:w-auto"
    />
  );
}

/** One plain sentence under each accuracy figure, saying how to read it. */
function Measure({ label, value, reading }: { label: string; value: string; reading: string }) {
  return (
    <Card className="flex flex-col gap-2">
      <p className="text-step-n1 font-medium text-fg-muted">{label}</p>
      <p className="text-step-4 font-semibold text-fg figure">{value}</p>
      <p className="text-step-n2 text-fg-muted">{reading}</p>
    </Card>
  );
}

function AllocatedChart({
  allocation,
  title,
  axis,
  horizon,
  isLoading,
  error,
  onRetry,
}: {
  allocation: Allocation | null | undefined;
  title: string;
  axis: string;
  horizon: Horizon;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  const data = (allocation?.groups ?? []).map((g) => ({
    category: g.name,
    values: { units: g.weeks.reduce((sum, w) => sum + w.p50, 0) },
  }));
  return (
    <BarChart
      title={title}
      description={`Allocated, not modelled: the product's weekly median forecast for the next ${horizon} weeks, split by each ${axis.toLowerCase()}'s share of its units over the 13 weeks to the training cutoff, summed.`}
      series={[{ key: "units", label: "Allocated units" }]}
      data={data}
      orientation="horizontal"
      categoryAxisLabel={axis}
      valueAxisLabel={`Allocated units, next ${horizon} weeks (units)`}
      formatTick={formatCompact}
      isLoading={isLoading}
      error={error}
      onRetry={onRetry}
      emptyTitle="Nothing to allocate"
      footer={
        allocation && (
          <p className="text-step-n2 text-fg-muted">
            Shares from {formatRange(allocation.share_from, allocation.share_to)}. Medians only: a
            share of an interval is not an interval.
          </p>
        )
      }
    />
  );
}

/** One SKU's stored forecast, its accuracy in the backtest and its allocated splits. */
export default function SkuForecastPage() {
  const { sku = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const asked = Number(params.get("h"));
  const horizon: Horizon = (HORIZONS as number[]).includes(asked) ? (asked as Horizon) : 26;
  const setHorizon = (h: Horizon) => {
    const next = new URLSearchParams(params);
    if (h === 26) next.delete("h");
    else next.set("h", String(h));
    setParams(next, { replace: true });
  };

  const forecast = useSkuForecast(sku, horizon);
  const byState = useSkuForecast(sku, horizon, "state");
  const byChannel = useSkuForecast(sku, horizon, "channel");
  const context = useSkuForecastContext(sku);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const ctx = context.data;
  const fc = forecast.data?.forecast;
  const name = fc?.name ?? ctx?.name ?? sku;
  const lastWeek = fc?.weeks[fc.weeks.length - 1]?.week;
  const visibleEvents = useMemo(
    () => (ctx?.events ?? []).filter((e) => lastWeek !== undefined && e.week <= lastWeek),
    [ctx, lastWeek],
  );

  const chartData = useMemo(() => {
    if (!ctx || !fc) return [];
    return [
      ...ctx.actuals.map((a) => ({ date: a.week, values: { units: a.units } })),
      ...fc.weeks.map((w) => ({
        date: w.week,
        values: { units: w.p50 },
        low: w.lo80,
        high: w.hi80,
        outerLow: w.lo95,
        outerHigh: w.hi95,
      })),
    ];
  }, [ctx, fc]);
  const chartEvents: ChartEvent[] = visibleEvents.map((e) => ({
    from: e.date,
    to: e.end_date,
    label: eventLabel(e),
    kind: "day",
  }));

  const pastData = (ctx?.past_forecasts ?? []).map((p) => {
    const inside = p.actual >= p.lo80 && p.actual <= p.hi80;
    return {
      date: p.week,
      values: { forecast: p.p50, actual: p.actual },
      low: p.lo80,
      high: p.hi80,
      note: `Forecast made ${p.weeks_before} week${p.weeks_before === 1 ? "" : "s"} before (from w/c ${formatDate(p.origin)}); actual ${inside ? "inside" : "outside"} the 80% interval`,
    };
  });

  if (forecast.error && !fc) {
    return (
      <PageScaffold title={sku}>
        <Card>
          <ErrorState
            title="Couldn’t load this forecast"
            message={errorMessage(forecast.error)}
            onRetry={() => void forecast.refetch()}
          />
        </Card>
      </PageScaffold>
    );
  }

  const accuracy = ctx?.accuracy;
  const shortHistory = fc?.short_history ?? ctx?.short_history ?? false;

  return (
    <PageScaffold
      title={name}
      subtitle={
        fc ? `${fc.sku} · forecast by ${shownModel(fc.model, fc.short_history)}` : undefined
      }
      actions={
        <>
          {shortHistory && <Badge tone="warning">Short history</Badge>}
          <HorizonPicker value={horizon} onChange={setHorizon} />
          <Button
            variant="secondary"
            onClick={(e) => {
              setDownloadError(null);
              downloadForecastCsv(sku, horizon).catch((err: unknown) =>
                setDownloadError(errorMessage(err)),
              );
              if (isPointerClick(e)) e.currentTarget.blur();
            }}
          >
            Download CSV
          </Button>
        </>
      }
    >
      <ForecastTabs />
      {downloadError && <p className="text-step-n1 text-negative">{downloadError}</p>}
      {forecast.data && (
        <Card>
          <RunFacts
            run={forecast.data.run}
            models={[forecast.data.forecast.model]}
            modelText={shownModel(
              forecast.data.forecast.model,
              forecast.data.forecast.short_history,
            )}
            promotionsAssumed={forecast.data.assumptions.promotions}
          />
        </Card>
      )}

      {shortHistory && ctx && (
        <Card className="space-y-2 text-step-n1">
          <h2 className="text-step-1">Why this forecast is less certain</h2>
          <p className="max-w-3xl text-fg-muted">
            {name} launched on {formatDate(ctx.launched_on)}, so it has under a year of sales. Its
            intervals are wider because they come from a simulation: products with long histories
            were forecast as if they had just launched, from their most recent weeks only, and those
            forecasts missed by far more than forecasts made from several years. Prophet needs two
            years of data, so the forecast is LightGBM’s alone.
          </p>
          <p className="max-w-3xl text-fg-muted">
            There is no seasonal-naive comparison: seasonal naive repeats last year’s week, and a
            year ago this product was not on sale. Its skill against seasonal naive is unknown, and
            it is left out of every headline figure.
          </p>
        </Card>
      )}

      <TimeSeriesChart
        title="Forecast"
        description={`Units per week for ${name}: the last 52 weeks of sales, then the median forecast for the next ${horizon} weeks with its 80% and 95% intervals, and the public holidays and festivals in those weeks.`}
        series={[{ key: "units", label: "Units" }]}
        data={chartData}
        forecastStart={fc?.weeks[0]?.week}
        bandLabel="80% interval"
        outerBandLabel="95% interval"
        events={chartEvents}
        eventLabels={{ span: "Promotion", day: "Holiday or festival" }}
        yAxisLabel="Units (units per week)"
        xAxisLabel="Week starting"
        height="lg"
        isLoading={forecast.isPending || context.isPending}
        error={forecast.error ?? context.error}
        onRetry={() => {
          void forecast.refetch();
          void context.refetch();
        }}
        emptyTitle="No forecast for this product"
        footer={
          visibleEvents.length > 0 && (
            <div className="space-y-1 text-step-n2 text-fg-muted">
              <p className="font-medium text-fg">Holidays and festivals in these weeks</p>
              <ul className="flex flex-wrap gap-x-4 gap-y-1">
                {visibleEvents.map((e) => (
                  <li key={`${e.date}-${e.name}`}>
                    <span className="figure">{formatDate(e.date)}</span> {eventLabel(e)} ·{" "}
                    {EVENT_TYPE[e.event_type]}
                  </li>
                ))}
              </ul>
            </div>
          )
        }
      />

      <section aria-labelledby="accuracy-title" className="space-y-3">
        <div className="space-y-1">
          <h2 id="accuracy-title" className="text-step-2">
            How accurate it was
          </h2>
          {ctx && accuracy && (
            <p className="max-w-3xl text-step-n1 text-fg-muted">
              Backtest scores of {shownModel(accuracy.model, shortHistory)} for this product over
              the held-out weeks from {formatDate(ctx.held_out_from)}, 1 to 26 weeks ahead (
              {formatInteger(accuracy.n_weeks)} forecast-weeks).
            </p>
          )}
        </div>
        {accuracy ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Measure
              label="Error (WAPE)"
              value={pct(accuracy.wape)}
              reading="Of every 100 units sold, the forecast was off by this many, counting misses either way."
            />
            <Measure
              label="Skill vs seasonal naive"
              value={accuracy.skill === null ? "None" : signedPct(accuracy.skill)}
              reading={
                accuracy.skill === null
                  ? "No comparison: seasonal naive needs a year of sales, and this product has less."
                  : `How much smaller the error was than repeating last year’s week (WAPE ${pct(accuracy.baseline_wape)}). Above zero is better.`
              }
            />
            <Measure
              label="Bias"
              value={signedPct(accuracy.bias)}
              reading="Total forecast against total sales: below zero, it forecast too little; above, too much."
            />
            <Measure
              label="80% interval coverage"
              value={pct(accuracy.coverage_80)}
              reading="The share of weeks whose sales fell inside the 80% interval: near 80% means the range is honest."
            />
          </div>
        ) : (
          !context.isPending && (
            <p className="text-step-n1 text-fg-muted">No backtest scores for this product.</p>
          )
        )}
      </section>

      <TimeSeriesChart
        title="How past forecasts did"
        description={`Each held-out week's sales of ${name} against the forecast made 1 to 4 weeks before it, with that forecast's 80% interval: where the sales line leaves the band, the interval missed.`}
        series={[
          { key: "forecast", label: "Forecast made 1-4 weeks before" },
          { key: "actual", label: "Actual" },
        ]}
        bandSeries="forecast"
        bandLabel="80% interval"
        data={pastData}
        yAxisLabel="Units (units per week)"
        xAxisLabel="Week starting"
        formatValue={(v) => formatInteger(Math.round(v))}
        isLoading={context.isPending}
        error={context.error}
        onRetry={() => void context.refetch()}
        emptyTitle="No past forecasts stored"
        emptyMessage="Run make backtest-forecasts to store the held-out forecasts."
        footer={
          <p className="text-step-n2 text-fg-muted">
            Backtest forecasts are made every 4 weeks, so each week shows the latest one made 1 to 4
            weeks before it. These are the held-out weeks: no model or interval was picked on them.
          </p>
        }
      />

      <section aria-labelledby="allocated-title" className="space-y-3">
        <div className="space-y-1">
          <h2 id="allocated-title" className="text-step-2">
            By state and channel
          </h2>
          <p className="max-w-3xl text-step-n1 text-fg-muted">
            Allocated from this product’s forecast using its recent shares, not modelled separately:
            each week’s median is split by where and how it sold over the last 13 weeks.
          </p>
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <AllocatedChart
            allocation={byState.data?.allocation}
            title="Allocated by state"
            axis="State"
            horizon={horizon}
            isLoading={byState.isPending}
            error={byState.error}
            onRetry={() => void byState.refetch()}
          />
          <AllocatedChart
            allocation={byChannel.data?.allocation}
            title="Allocated by channel"
            axis="Channel"
            horizon={horizon}
            isLoading={byChannel.isPending}
            error={byChannel.error}
            onRetry={() => void byChannel.refetch()}
          />
        </div>
      </section>
    </PageScaffold>
  );
}
