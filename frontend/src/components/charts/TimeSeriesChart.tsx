import { useMemo, useState, type ReactNode } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
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
  ANNOTATION_BAND_COLOR,
  ANNOTATION_COLOR,
  BAND_COLOR,
  BAND_OUTER_COLOR,
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
  /** A wider interval around the same series (e.g. 95%), drawn lighter under low-high. */
  outerLow?: number | null;
  outerHigh?: number | null;
  /** Shown in the tooltip and the hidden table, e.g. "Partial week: 3 of 7 days". */
  note?: string;
}

/** A dated event drawn on the chart: a wash over a span, or a rule on a day. */
export interface ChartEvent {
  from: IsoDate;
  to: IsoDate;
  label: string;
  kind: "span" | "day";
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
  /** Names the wider outerLow-outerHigh range, e.g. "95% interval". Set it to draw it. */
  outerBandLabel?: string;
  /** The series the band belongs to (default: the first). */
  bandSeries?: string;
  granularity?: Granularity;
  /** Date ticks as if at this granularity: "month" labels weekly points over years "Oct 2023". */
  tickGranularity?: Granularity;
  /** Vertical axis title with its unit, e.g. "Units sold (units per week)". */
  yAxisLabel: string;
  /** Horizontal axis title, e.g. "Week starting". */
  xAxisLabel: string;
  /** Values in the tooltip and the hidden table. Default: whole numbers, Indian grouping. */
  formatValue?: (value: number) => string;
  /** Vertical axis ticks. Default: compact (12K, 1.2L). */
  formatTick?: (value: number) => string;
  height?: ChartHeight;
  /**
   * Events to mark, snapped to the bucket they fall in: spans (promotions) as an ink wash,
   * days (holidays) as an ink rule. Only on charts whose series do not use ink-400.
   */
  events?: ChartEvent[];
  /** Names the two event kinds in the legend. */
  eventLabels?: { span: string; day: string };
  /** Controls beside the title, e.g. a metric toggle. */
  actions?: ReactNode;
  /** Under the plot, e.g. a note on festivals that moved between years. */
  footer?: ReactNode;
  /** Under the plot or the state that replaces it (not while loading), e.g. a data source. */
  persistentFooter?: ReactNode;
  /** A fixed value-axis width instead of one sized to the ticks; needed by `alignToBars`. */
  yAxisWidth?: number;
  /**
   * Centre each point on its period's band, as a bar chart does, so a DivergingBarChart
   * below with the same `yAxisWidth` puts each bar exactly under its point.
   */
  alignToBars?: boolean;
  /** Recharts' syncId: hovering one chart shows the same period in the other. */
  syncId?: string;
  /**
   * "context": one outside series (a market signal) drawn in ink (series slot 2), never
   * maroon, which means our sales. A context chart takes exactly one series.
   */
  tone?: "primary" | "context";
}

type Row = Record<string, string | number | null | [number, number]>;

/** Room on the right for the last tick label, centred on the plot's edge: "Oct 2026" is
 * 50px wide, so 24px clipped it by a pixel. DivergingBarChart uses the same margin. */
const RIGHT_MARGIN = 32;

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
  outerBandLabel,
  bandSeries,
  granularity = "week",
  tickGranularity,
  yAxisLabel,
  xAxisLabel,
  formatValue = formatInteger,
  formatTick = formatCompact,
  height = "md",
  events = [],
  eventLabels = { span: "Promotion", day: "Holiday or festival" },
  actions,
  footer,
  persistentFooter,
  yAxisWidth,
  alignToBars = false,
  syncId,
  tone = "primary",
  ...state
}: TimeSeriesChartProps) {
  // Colour slot of each series: in context tone the lone series takes ink (slot 1).
  const colorSlot = (index: number) => (tone === "context" ? 1 : index);
  const reducedMotion = usePrefersReducedMotion();
  const [chartWidth, setChartWidth] = useState(0);
  // Half a band each side: points then sit where a bar chart centres its bars.
  const bandPadding =
    alignToBars && yAxisWidth !== undefined && chartWidth > 0 && data.length > 0
      ? Math.max(0, (chartWidth - RIGHT_MARGIN - yAxisWidth) / data.length / 2)
      : 0;
  const hasValues = data.some((point) =>
    series.some((s) => typeof point.values[s.key] === "number"),
  );
  const view =
    tone === "context" && series.length !== 1 && !state.isLoading && !state.error
      ? ({
          kind: "error",
          title: "A context chart shows one series",
          message: "Market signals are drawn one per chart, in ink, so none is read as our sales.",
        } as const)
      : resolveChartView(state, { seriesCount: series.length, hasValues });

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
        row.outer =
          typeof point.outerLow === "number" && typeof point.outerHigh === "number"
            ? [point.outerLow, point.outerHigh]
            : i === lastActual && typeof bandValue === "number"
              ? [bandValue, bandValue]
              : null;
        return row;
      }),
    [data, series, forecastStart, lastActual, bandSlot],
  );

  const byDate = useMemo(() => new Map(data.map((point) => [point.date, point])), [data]);

  // Each event snaps to the bucket it falls in: the last point starting on or before it.
  const placed = useMemo(() => {
    const starts = data.map((point) => point.date);
    const bucketOf = (date: IsoDate) => {
      let found: IsoDate | null = null;
      for (const start of starts) if (start <= date) found = start;
      return found;
    };
    const last = data[data.length - 1]?.date;
    return events
      .filter((e) => starts.length && e.to >= starts[0] && last !== undefined && e.from <= last)
      .map((e) => ({
        ...e,
        x1: bucketOf(e.from < starts[0] ? starts[0] : e.from)!,
        x2: bucketOf(e.to)!,
      }));
  }, [data, events]);
  const eventsByBucket = useMemo(() => {
    const map = new Map<IsoDate, string[]>();
    for (const e of placed) {
      for (const point of data) {
        if (point.date >= e.x1 && point.date <= e.x2) {
          map.set(point.date, [...(map.get(point.date) ?? []), e.label]);
        }
      }
    }
    return map;
  }, [placed, data]);
  const hasBand = Boolean(bandLabel) && data.some((point) => typeof point.low === "number");
  const hasOuter =
    Boolean(outerBandLabel) && data.some((point) => typeof point.outerLow === "number");
  const hasForecast = lastActual >= 0 && lastActual < data.length - 1;
  const isForecastDate = (date: IsoDate) => forecastStart !== undefined && date >= forecastStart;

  const legend: LegendEntry[] = series.map((s, slot) => ({
    label: s.label,
    shape: "line",
    series: colorSlot(slot),
  }));
  if (hasForecast) legend.push({ label: "Forecast", shape: "dashed", series: colorSlot(bandSlot) });
  if (hasBand && bandLabel)
    legend.push({ label: bandLabel, shape: hasOuter ? "band-inner" : "band" });
  if (hasOuter && outerBandLabel) legend.push({ label: outerBandLabel, shape: "band-outer" });
  if (placed.some((e) => e.kind === "span"))
    legend.push({ label: eventLabels.span, shape: "event-band" });
  if (placed.some((e) => e.kind === "day"))
    legend.push({ label: eventLabels.day, shape: "event-line" });
  const showLegend = series.length > 1 || hasForecast || hasBand || placed.length > 0;
  const hasNotes = data.some((point) => point.note) || placed.length > 0;

  const tableColumns = [
    xAxisLabel,
    ...series.map((s) => s.label),
    ...(hasForecast ? ["Actual or forecast"] : []),
    ...(hasBand && bandLabel ? [`${bandLabel}, low`, `${bandLabel}, high`] : []),
    ...(hasOuter && outerBandLabel ? [`${outerBandLabel}, low`, `${outerBandLabel}, high`] : []),
    ...(hasNotes ? ["Notes"] : []),
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
    if (hasOuter && outerBandLabel) {
      cells.push(
        typeof point.outerLow === "number" ? formatValue(point.outerLow) : "None",
        typeof point.outerHigh === "number" ? formatValue(point.outerHigh) : "None",
      );
    }
    if (hasNotes) {
      cells.push(
        [point.note, ...(eventsByBucket.get(point.date) ?? [])].filter(Boolean).join("; "),
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
      actions={actions}
      footer={footer}
      persistentFooter={persistentFooter}
      dataTable={
        <HiddenDataTable
          caption={`${title}. Values: ${yAxisLabel}.`}
          columns={tableColumns}
          rows={tableRows}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%" onResize={(width) => setChartWidth(width)}>
        <ComposedChart
          data={rows}
          role="img"
          title={`${title}. The values follow as a table.`}
          syncId={syncId}
          margin={{ top: 8, right: RIGHT_MARGIN, bottom: 0, left: 0 }}
        >
          <CartesianGrid vertical={false} stroke={GRID_COLOR} />
          <XAxis
            dataKey="date"
            tickFormatter={(date: IsoDate) => formatDateTick(date, tickGranularity ?? granularity)}
            tick={{ className: TICK_CLASS }}
            tickLine={false}
            axisLine={{ stroke: RULE_COLOR }}
            minTickGap={24}
            tickMargin={8}
            padding={{ left: bandPadding, right: bandPadding }}
          />
          <YAxis
            tickFormatter={formatTick}
            tick={{ className: TICK_CLASS }}
            tickLine={false}
            axisLine={false}
            // Sized to the widest tick unless fixed: a fixed 48px clipped the ₹ off "₹2.25Cr".
            width={yAxisWidth ?? "auto"}
            // A context line (a price, a rate, a temperature) is read for its shape: fit the
            // axis to its range instead of from zero, which flattened ₹ per US$ near 95.
            // Sales stay from zero. Sums (rain, views) reach zero on their own.
            domain={tone === "context" ? ["auto", "auto"] : undefined}
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
                        series={colorSlot(slot)}
                        label={s.label}
                        value={typeof value === "number" ? formatValue(value) : "No data"}
                      />
                    );
                  })}
                  {bandLabel && typeof point.low === "number" && typeof point.high === "number" && (
                    <TooltipRow
                      shape={hasOuter ? "band-inner" : "band"}
                      label={bandLabel}
                      value={`${formatValue(point.low)} – ${formatValue(point.high)}`}
                    />
                  )}
                  {outerBandLabel &&
                    typeof point.outerLow === "number" &&
                    typeof point.outerHigh === "number" && (
                      <TooltipRow
                        shape="band-outer"
                        label={outerBandLabel}
                        value={`${formatValue(point.outerLow)} – ${formatValue(point.outerHigh)}`}
                      />
                    )}
                  {point.note && <p className="pt-1 text-fg-muted">{point.note}</p>}
                  {eventsByBucket.get(point.date)?.map((label) => (
                    <p key={label} className="text-fg-muted">
                      {label}
                    </p>
                  ))}
                </TooltipBox>
              );
            }}
          />
          {placed
            .filter((e) => e.kind === "span")
            .map((e) => (
              <ReferenceArea
                key={`span-${e.label}-${e.from}`}
                x1={e.x1}
                x2={e.x2}
                fill={ANNOTATION_BAND_COLOR}
                fillOpacity={1}
                stroke="none"
                ifOverflow="hidden"
              />
            ))}
          {placed
            .filter((e) => e.kind === "day")
            .map((e) => (
              <ReferenceLine
                key={`day-${e.label}-${e.from}`}
                x={e.x1}
                stroke={ANNOTATION_COLOR}
                strokeWidth={1}
                // Dotted, so a holiday never reads as the solid actual/forecast divider.
                strokeDasharray="2 3"
              />
            ))}
          {hasOuter && (
            <Area
              dataKey="outer"
              stroke="none"
              fill={BAND_OUTER_COLOR}
              fillOpacity={1}
              activeDot={false}
              isAnimationActive={!reducedMotion}
            />
          )}
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
              // Text starts at the divider and runs over the forecast side; a forecast tail
              // too short to hold it (a few weeks at the end of years) has the legend's key only.
              label={
                data.length - lastActual - 1 >= Math.max(3, data.length / 10)
                  ? { value: "Forecast", position: "insideTopLeft", className: TICK_CLASS }
                  : undefined
              }
            />
          )}
          {series.map((s, slot) => (
            <Line
              key={`actual-${s.key}`}
              dataKey={`actual${slot}`}
              name={s.label}
              stroke={SERIES_COLORS[colorSlot(slot)]}
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
                stroke={SERIES_COLORS[colorSlot(slot)]}
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
