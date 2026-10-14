import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  formatPeriod,
  formatTick as formatDateTick,
  type Granularity,
  type IsoDate,
} from "../../lib/dates";
import { formatCompact, formatInteger } from "../../lib/format";
import { usePrefersReducedMotion } from "../../lib/usePrefersReducedMotion";
import {
  BAND_COLOR,
  GRID_COLOR,
  RULE_COLOR,
  SERIES_COLORS,
  SURFACE_COLOR,
  TICK_CLASS,
  type ChartHeight,
  type ChartStateProps,
  type Series,
} from "./chart-theme";
import { resolveChartView } from "./chart-view";
import { ChartFrame } from "./ChartFrame";
import {
  ChartLegend,
  HiddenDataTable,
  TooltipBox,
  TooltipRow,
  type LegendEntry,
} from "./ChartParts";

export interface TimeSeriesPoint {
  /** The period's first day, ISO-8601. */
  date: IsoDate;
  /** Keyed by `Series.key`. null or missing: no value for that period. */
  values: Record<string, number | null | undefined>;
  /** The confidence band around the band series at this date, when there is one. */
  low?: number | null;
  high?: number | null;
}

export interface TimeSeriesChartProps extends ChartStateProps {
  title: string;
  /** What the chart shows and over what: the figure's accessible description. */
  description: string;
  /** One to three series. A fourth renders an error state, never a fourth colour. */
  series: Series[];
  /** In date order, one point per period. */
  data: TimeSeriesPoint[];
  /** First forecast date. From here on the lines are dashed, after a divider. */
  forecastStart?: IsoDate;
  /** Names the low-high range, e.g. "80% interval". Set it to draw the band. */
  bandLabel?: string;
  /** The series the band belongs to (default: the first). */
  bandSeries?: string;
  granularity?: Granularity;
  /** Vertical axis title with its unit, e.g. "Units sold (units per week)". */
  yAxisLabel: string;
  /** Horizontal axis title, e.g. "Week starting". */
  xAxisLabel: string;
  /** Values in the tooltip and the hidden table. Default: whole numbers, Indian grouping. */
  formatValue?: (value: number) => string;
  /** Vertical axis ticks. Default: compact (12K, 1.2L). */
  formatTick?: (value: number) => string;
  height?: ChartHeight;
}

type Row = Record<string, string | number | null | [number, number]>;

/**
 * One or more series over time, with an optional confidence band and an optional
 * forecast segment: dashed, after a divider at the last actual period.
 */
export function TimeSeriesChart({
  title,
  description,
  series,
  data,
  forecastStart,
  bandLabel,
  bandSeries,
  granularity = "week",
  yAxisLabel,
  xAxisLabel,
  formatValue = formatInteger,
  formatTick = formatCompact,
  height = "md",
  ...state
}: TimeSeriesChartProps) {
  const reducedMotion = usePrefersReducedMotion();
  const hasValues = data.some((point) =>
    series.some((s) => typeof point.values[s.key] === "number"),
  );
  const view = resolveChartView(state, { seriesCount: series.length, hasValues });

  // The last actual period: the forecast line starts there too, so the two join up.
  const lastActual = useMemo(() => {
    if (!forecastStart) return -1;
    let index = -1;
    data.forEach((point, i) => {
      if (point.date < forecastStart) index = i;
    });
    return index;
  }, [data, forecastStart]);

  const bandSlot = Math.max(0, bandSeries ? series.findIndex((s) => s.key === bandSeries) : 0);

  const rows = useMemo<Row[]>(
    () =>
      data.map((point, i) => {
        const isForecast = forecastStart !== undefined && point.date >= forecastStart;
        const row: Row = { date: point.date };
        series.forEach((s, slot) => {
          const value = point.values[s.key] ?? null;
          row[`actual${slot}`] = isForecast ? null : value;
          row[`forecast${slot}`] = isForecast || i === lastActual ? value : null;
        });
        const bandKey = series[bandSlot]?.key;
        const bandValue = bandKey === undefined ? undefined : point.values[bandKey];
        row.band =
          typeof point.low === "number" && typeof point.high === "number"
            ? [point.low, point.high]
            : // The band opens out of the last actual value instead of starting a week late.
              i === lastActual && typeof bandValue === "number"
              ? [bandValue, bandValue]
              : null;
        return row;
      }),
    [data, series, forecastStart, lastActual, bandSlot],
  );

  const byDate = useMemo(() => new Map(data.map((point) => [point.date, point])), [data]);
  const hasBand = Boolean(bandLabel) && data.some((point) => typeof point.low === "number");
  const hasForecast = lastActual >= 0 && lastActual < data.length - 1;
  const isForecastDate = (date: IsoDate) => forecastStart !== undefined && date >= forecastStart;

  const legend: LegendEntry[] = series.map((s, slot) => ({
    label: s.label,
    shape: "line",
    series: slot,
  }));
  if (hasForecast) legend.push({ label: "Forecast", shape: "dashed", series: bandSlot });
  if (hasBand && bandLabel) legend.push({ label: bandLabel, shape: "band" });
  const showLegend = series.length > 1 || hasForecast || hasBand;

  const tableColumns = [
    xAxisLabel,
    ...series.map((s) => s.label),
    ...(hasForecast ? ["Actual or forecast"] : []),
    ...(hasBand && bandLabel ? [`${bandLabel}, low`, `${bandLabel}, high`] : []),
  ];
  const tableRows = data.map((point) => {
    const cells = series.map((s) => {
      const value = point.values[s.key];
      return typeof value === "number" ? formatValue(value) : "No data";
    });
    if (hasForecast) cells.push(isForecastDate(point.date) ? "Forecast" : "Actual");
    if (hasBand && bandLabel) {
      cells.push(
        typeof point.low === "number" ? formatValue(point.low) : "None",
        typeof point.high === "number" ? formatValue(point.high) : "None",
      );
    }
    return { key: point.date, heading: formatPeriod(point.date, granularity), cells };
  });

  return (
    <ChartFrame
      title={title}
      description={description}
      height={height}
      view={view}
      legend={showLegend ? <ChartLegend entries={legend} /> : undefined}
      yAxisTitle={yAxisLabel}
      xAxisTitle={xAxisLabel}
      dataTable={
        <HiddenDataTable
          caption={`${title}. Values: ${yAxisLabel}.`}
          columns={tableColumns}
          rows={tableRows}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={rows}
          role="img"
          title={`${title}. The values follow as a table.`}
          // Room on the right for the last tick label, centred on the plot's edge.
          margin={{ top: 8, right: 24, bottom: 0, left: 0 }}
        >
          <CartesianGrid vertical={false} stroke={GRID_COLOR} />
          <XAxis
            dataKey="date"
            tickFormatter={(date: IsoDate) => formatDateTick(date, granularity)}
            tick={{ className: TICK_CLASS }}
            tickLine={false}
            axisLine={{ stroke: RULE_COLOR }}
            minTickGap={24}
            tickMargin={8}
          />
          <YAxis
            tickFormatter={formatTick}
            tick={{ className: TICK_CLASS }}
            tickLine={false}
            axisLine={false}
            width={48}
          />
          <Tooltip
            cursor={{ stroke: RULE_COLOR, strokeWidth: 1 }}
            isAnimationActive={false}
            content={({ active, label }) => {
              const point = active ? byDate.get(String(label)) : undefined;
              if (!point) return null;
              const forecast = isForecastDate(point.date);
              return (
                <TooltipBox
                  heading={`${formatPeriod(point.date, granularity)}${forecast ? " · forecast" : ""}`}
                >
                  {series.map((s, slot) => {
                    const value = point.values[s.key];
                    return (
                      <TooltipRow
                        key={s.key}
                        shape={forecast ? "dashed" : "line"}
                        series={slot}
                        label={s.label}
                        value={typeof value === "number" ? formatValue(value) : "No data"}
                      />
                    );
                  })}
                  {bandLabel && typeof point.low === "number" && typeof point.high === "number" && (
                    <TooltipRow
                      shape="band"
                      label={bandLabel}
                      value={`${formatValue(point.low)} – ${formatValue(point.high)}`}
                    />
                  )}
                </TooltipBox>
              );
            }}
          />
          {hasBand && (
            <Area
              dataKey="band"
              stroke="none"
              fill={BAND_COLOR}
              fillOpacity={1}
              activeDot={false}
              isAnimationActive={!reducedMotion}
            />
          )}
          {hasForecast && (
            <ReferenceLine
              x={data[lastActual].date}
              stroke={RULE_COLOR}
              // Text starts at the divider and runs over the forecast side.
              label={{ value: "Forecast", position: "insideTopLeft", className: TICK_CLASS }}
            />
          )}
          {series.map((s, slot) => (
            <Line
              key={`actual-${s.key}`}
              dataKey={`actual${slot}`}
              name={s.label}
              stroke={SERIES_COLORS[slot]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, stroke: SURFACE_COLOR, strokeWidth: 2 }}
              isAnimationActive={!reducedMotion}
            />
          ))}
          {hasForecast &&
            series.map((s, slot) => (
              <Line
                key={`forecast-${s.key}`}
                dataKey={`forecast${slot}`}
                name={`${s.label}, forecast`}
                stroke={SERIES_COLORS[slot]}
                strokeWidth={2}
                strokeDasharray="6 4"
                dot={false}
                activeDot={{ r: 4, stroke: SURFACE_COLOR, strokeWidth: 2 }}
                isAnimationActive={!reducedMotion}
              />
            ))}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
