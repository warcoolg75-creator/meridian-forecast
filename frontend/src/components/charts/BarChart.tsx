import { useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  BarChart as RechartsBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatCompact, formatInteger } from "../../lib/format";
import { usePrefersReducedMotion } from "../../lib/usePrefersReducedMotion";
import {
  CATEGORY_TICK_CLASS,
  CURSOR_FILL,
  GRID_COLOR,
  RULE_COLOR,
  SERIES_COLORS,
  TICK_CLASS,
  type ChartHeight,
  type ChartStateProps,
  type Series,
} from "./chart-theme";
import { resolveChartView } from "./chart-view";
import { ChartFrame } from "./ChartFrame";
import { ChartLegend, HiddenDataTable, TooltipBox, TooltipRow } from "./ChartParts";

export interface BarDatum {
  /** The category: a region, a channel, a product. */
  category: string;
  /** Keyed by `Series.key`. null or missing: no bar. */
  values: Record<string, number | null | undefined>;
}

export interface BarChartProps extends ChartStateProps {
  title: string;
  /** What the chart compares: the figure's accessible description. */
  description: string;
  /** One series: single bars. Two or three: grouped. A fourth is an error state. */
  series: Series[];
  data: BarDatum[];
  /** "vertical": columns rising from the bottom. "horizontal": bars from the left, for long labels. */
  orientation?: "vertical" | "horizontal";
  /** Category axis title, e.g. "Region". */
  categoryAxisLabel: string;
  /** Value axis title with its unit, e.g. "Units sold (units)". */
  valueAxisLabel: string;
  formatValue?: (value: number) => string;
  formatTick?: (value: number) => string;
  height?: ChartHeight;
}

type Row = Record<string, string | number | null>;

/** Bars at most 24px thick with 4px rounded ends, 2px apart within a group. */
const BAR_SIZE = 24;
const RADIUS = 4;
/** Horizontal bars: the label column takes about a third of the plot, within these bounds. */
const LABEL_WIDTH_MIN = 88;
const LABEL_WIDTH_MAX = 160;

/** Compares values across categories, vertically or horizontally, single or grouped. */
export function BarChart({
  title,
  description,
  series,
  data,
  orientation = "vertical",
  categoryAxisLabel,
  valueAxisLabel,
  formatValue = formatInteger,
  formatTick = formatCompact,
  height = "md",
  ...state
}: BarChartProps) {
  const reducedMotion = usePrefersReducedMotion();
  const vertical = orientation === "vertical";
  // Horizontal bars on a phone: a fixed 160px label column would leave the bars no room.
  const [plotWidth, setPlotWidth] = useState(0);
  const labelWidth = Math.round(
    Math.min(LABEL_WIDTH_MAX, Math.max(LABEL_WIDTH_MIN, plotWidth * 0.32)),
  );
  const hasValues = data.some((datum) =>
    series.some((s) => typeof datum.values[s.key] === "number"),
  );
  const view = resolveChartView(state, { seriesCount: series.length, hasValues });

  const rows = useMemo<Row[]>(
    () =>
      data.map((datum) => {
        const row: Row = { category: datum.category };
        series.forEach((s, slot) => {
          row[`series${slot}`] = datum.values[s.key] ?? null;
        });
        return row;
      }),
    [data, series],
  );
  const byCategory = useMemo(() => new Map(data.map((d) => [d.category, d])), [data]);

  const categoryAxis = {
    dataKey: "category",
    type: "category" as const,
    tick: { className: CATEGORY_TICK_CLASS },
    tickLine: false,
    axisLine: { stroke: RULE_COLOR },
  };
  const valueAxis = {
    type: "number" as const,
    tickFormatter: formatTick,
    tick: { className: TICK_CLASS },
    tickLine: false,
    axisLine: false,
  };

  return (
    <ChartFrame
      title={title}
      description={description}
      height={height}
      view={view}
      legend={
        series.length > 1 ? (
          <ChartLegend
            entries={series.map((s, slot) => ({ label: s.label, shape: "bar", series: slot }))}
          />
        ) : undefined
      }
      // Titles sit where their axes are: the vertical axis's above the plot.
      yAxisTitle={vertical ? valueAxisLabel : categoryAxisLabel}
      xAxisTitle={vertical ? categoryAxisLabel : valueAxisLabel}
      dataTable={
        <HiddenDataTable
          caption={`${title}. Values: ${valueAxisLabel}.`}
          columns={[categoryAxisLabel, ...series.map((s) => s.label)]}
          rows={data.map((datum) => ({
            key: datum.category,
            heading: datum.category,
            cells: series.map((s) => {
              const value = datum.values[s.key];
              return typeof value === "number" ? formatValue(value) : "No data";
            }),
          }))}
        />
      }
    >
      <ResponsiveContainer width="100%" height="100%" onResize={(width) => setPlotWidth(width)}>
        <RechartsBarChart
          data={rows}
          layout={vertical ? "horizontal" : "vertical"}
          role="img"
          title={`${title}. The values follow as a table.`}
          barGap={2}
          barCategoryGap="20%"
          margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
        >
          <CartesianGrid vertical={!vertical} horizontal={vertical} stroke={GRID_COLOR} />
          {vertical ? (
            <>
              <XAxis {...categoryAxis} tickMargin={8} interval={0} />
              <YAxis {...valueAxis} width={48} />
            </>
          ) : (
            <>
              <XAxis {...valueAxis} tickMargin={8} />
              <YAxis {...categoryAxis} width={labelWidth} interval={0} />
            </>
          )}
          <Tooltip
            cursor={{ fill: CURSOR_FILL }}
            isAnimationActive={false}
            content={({ active, label }) => {
              const datum = active ? byCategory.get(String(label)) : undefined;
              if (!datum) return null;
              return (
                <TooltipBox heading={datum.category}>
                  {series.map((s, slot) => {
                    const value = datum.values[s.key];
                    return (
                      <TooltipRow
                        key={s.key}
                        shape="bar"
                        series={slot}
                        label={s.label}
                        value={typeof value === "number" ? formatValue(value) : "No data"}
                      />
                    );
                  })}
                </TooltipBox>
              );
            }}
          />
          {series.map((s, slot) => (
            <Bar
              key={s.key}
              dataKey={`series${slot}`}
              name={s.label}
              fill={SERIES_COLORS[slot]}
              maxBarSize={BAR_SIZE}
              radius={vertical ? [RADIUS, RADIUS, 0, 0] : [0, RADIUS, RADIUS, 0]}
              isAnimationActive={!reducedMotion}
            />
          ))}
        </RechartsBarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
