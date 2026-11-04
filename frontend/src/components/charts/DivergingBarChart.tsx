import { useMemo, useState, type ReactNode } from "react";
import {
  Bar,
  CartesianGrid,
  BarChart as RechartsBarChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatPeriod, formatTick as formatDateTick, type Granularity } from "../../lib/dates";
import { formatSignedPercent, formatSignedPercentTick } from "../../lib/format";
import { usePrefersReducedMotion } from "../../lib/usePrefersReducedMotion";
import { directionOf } from "./change";
import {
  CATEGORY_TICK_CLASS,
  CURSOR_FILL,
  DOWN_COLOR,
  GRID_COLOR,
  NEUTRAL_MARK_COLOR,
  RULE_COLOR,
  TICK_CLASS,
  UP_COLOR,
  type ChartHeight,
  type ChartStateProps,
} from "./chart-theme";
import { resolveChartView } from "./chart-view";
import { ChartFrame } from "./ChartFrame";
import { ChartLegend, HiddenDataTable, TooltipBox, type LegendEntry } from "./ChartParts";
import { SignedChange } from "./SignedChange";

export interface DivergingDatum {
  /** Stable key: the period's first day on a time axis, a SKU for products. */
  key: string;
  /** The category's name on a category axis (ignored on a time axis, which shows `key`). */
  label: string;
  /** Tooltip heading and the hidden table's row heading. */
  heading: string;
  /** The change as a fraction (0.12 = +12%); null when there is nothing to compare with. */
  value: number | null;
  /** Why there is no comparison: shown in the tooltip and the hidden table. */
  reason?: string;
  /** Rows above the change in the tooltip and the table, e.g. this year's and last year's revenue. */
  details?: Array<{ label: string; value: string }>;
}

export interface DivergingBarChartProps extends ChartStateProps {
  title: string;
  /** What changed against what: the figure's accessible description. */
  description: string;
  data: DivergingDatum[];
  /** "vertical": columns over time, under a time series. "horizontal": bars per category. */
  orientation?: "vertical" | "horizontal";
  /** Set for a time axis: `key` is then the period's first day. */
  granularity?: Granularity;
  /** Category axis title, e.g. "Week starting (Monday)" or "Product". */
  categoryAxisLabel: string;
  /** Value axis title with its unit, e.g. "Change in revenue (%)". */
  valueAxisLabel: string;
  /** What the change is against, for the tooltip and the table: "same period last year". */
  comparisonLabel: string;
  /** Zero in the middle of the value axis, so rises and falls get equal room. */
  centreZero?: boolean;
  height?: ChartHeight;
  /**
   * A fixed value-axis width. Set the same width on a TimeSeriesChart with `alignToBars`
   * above it and the bars sit exactly under its points.
   */
  yAxisWidth?: number;
  /** Recharts' syncId: hovering one chart shows the same period in the other. */
  syncId?: string;
  /** Makes the bars clickable, called with the datum's key. Offer a keyboard way too. */
  onCategoryClick?: (key: string) => void;
  actions?: ReactNode;
  footer?: ReactNode;
}

interface Row {
  key: string;
  label: string;
  /** 0 where there is no comparison, so the marker has a place on the zero line. */
  value: number;
  missing: boolean;
}

const BAR_SIZE = 24;
const RADIUS = 4;
const RING_RADIUS = 4;
// Wider than BarChart's 88px: 11 product rows on a phone leave no room for a label that
// wraps onto three lines ("Induction / Cooktop / 2000W" ran into its neighbour).
const LABEL_WIDTH_MIN = 112;
const LABEL_WIDTH_MAX = 160;

/**
 * A change against the comparison period, per period or per category: bars about a zero
 * line, up (sage) on one side and down (clay) on the other. Position carries the meaning
 * and colour only reinforces it; a period with no comparison gets a neutral ring on the
 * zero line, never a colour, and says why in the tooltip and the hidden table.
 */
export function DivergingBarChart({
  title,
  description,
  data,
  orientation = "vertical",
  granularity,
  categoryAxisLabel,
  valueAxisLabel,
  comparisonLabel,
  centreZero = false,
  height = "sm",
  yAxisWidth,
  syncId,
  onCategoryClick,
  actions,
  footer,
  ...state
}: DivergingBarChartProps) {
  const reducedMotion = usePrefersReducedMotion();
  const vertical = orientation === "vertical";
  const [plotWidth, setPlotWidth] = useState(0);
  const labelWidth = Math.round(
    Math.min(LABEL_WIDTH_MAX, Math.max(LABEL_WIDTH_MIN, plotWidth * 0.32)),
  );
  const hasValues = data.some((datum) => datum.value !== null);
  const view = resolveChartView(state, { seriesCount: 1, hasValues });

  const rows = useMemo<Row[]>(
    () =>
      data.map((datum) => ({
        key: datum.key,
        label: datum.label,
        value: datum.value ?? 0,
        missing: datum.value === null,
      })),
    [data],
  );
  const byKey = useMemo(() => new Map(data.map((d) => [d.key, d])), [data]);
  const byLabel = useMemo(() => new Map(data.map((d) => [d.label, d])), [data]);
  const scale = useMemo(
    () =>
      changeScale(
        data.flatMap((d) => (d.value === null ? [] : [d.value])),
        centreZero,
      ),
    [data, centreZero],
  );

  const legend: LegendEntry[] = [
    { label: "Up", shape: "up" },
    { label: "Down", shape: "down" },
  ];
  if (data.some((d) => d.value === null))
    legend.push({ label: "No comparison", shape: "no-comparison" });

  const detailLabels = data.find((d) => d.details?.length)?.details?.map((d) => d.label) ?? [];
  const changeColumn = `Change vs ${comparisonLabel}`;
  const headingOf = (datum: DivergingDatum) =>
    granularity ? formatPeriod(datum.key, granularity) : datum.heading;

  const valueAxis = {
    type: "number" as const,
    domain: scale.domain,
    ticks: scale.ticks,
    tickFormatter: formatSignedPercentTick,
    tick: { className: TICK_CLASS },
    tickLine: false,
    axisLine: false,
    allowDataOverflow: true,
  };

  return (
    <ChartFrame
      title={title}
      description={description}
      height={height}
      view={view}
      legend={<ChartLegend entries={legend} />}
      yAxisTitle={vertical ? valueAxisLabel : categoryAxisLabel}
      xAxisTitle={vertical ? categoryAxisLabel : valueAxisLabel}
      actions={actions}
      footer={footer}
      dataTable={
        <HiddenDataTable
          caption={`${title}. Values: ${valueAxisLabel}, signed.`}
          columns={[categoryAxisLabel, ...detailLabels, changeColumn]}
          rows={data.map((datum) => ({
            key: datum.key,
            heading: headingOf(datum),
            cells: [...(datum.details ?? []).map((d) => d.value), spokenChange(datum)],
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
          syncId={syncId}
          barCategoryGap="20%"
          cursor={onCategoryClick ? "pointer" : undefined}
          onClick={
            onCategoryClick
              ? (chartState) => {
                  const active = chartState?.activeLabel;
                  if (active === undefined || active === null) return;
                  const datum = vertical ? byKey.get(String(active)) : byLabel.get(String(active));
                  if (datum) onCategoryClick(datum.key);
                }
              : undefined
          }
          // The same right margin as TimeSeriesChart, so the two plots line up.
          margin={{ top: 8, right: vertical ? 32 : 24, bottom: 0, left: 0 }}
        >
          <CartesianGrid vertical={!vertical} horizontal={vertical} stroke={GRID_COLOR} />
          {vertical ? (
            <>
              <XAxis
                dataKey="key"
                tickFormatter={(key: string) =>
                  granularity ? formatDateTick(key, granularity) : (byKey.get(key)?.label ?? key)
                }
                tick={{ className: granularity ? TICK_CLASS : CATEGORY_TICK_CLASS }}
                tickLine={false}
                axisLine={false}
                minTickGap={24}
                tickMargin={8}
              />
              <YAxis {...valueAxis} width={yAxisWidth ?? "auto"} />
            </>
          ) : (
            <>
              <XAxis {...valueAxis} tickMargin={8} />
              <YAxis
                dataKey="label"
                type="category"
                width={labelWidth}
                interval={0}
                tick={{ className: CATEGORY_TICK_CLASS }}
                tickLine={false}
                axisLine={false}
              />
            </>
          )}
          {vertical ? (
            <ReferenceLine y={0} stroke={RULE_COLOR} />
          ) : (
            <ReferenceLine x={0} stroke={RULE_COLOR} />
          )}
          <Tooltip
            cursor={{ fill: CURSOR_FILL }}
            isAnimationActive={false}
            content={({ active, label }) => {
              const datum = active
                ? vertical
                  ? byKey.get(String(label))
                  : byLabel.get(String(label))
                : undefined;
              if (!datum) return null;
              return (
                <TooltipBox heading={headingOf(datum)}>
                  {datum.details?.map((detail) => (
                    <div key={detail.label} className="flex items-center gap-2">
                      <span className="text-fg-muted">{detail.label}</span>
                      <span className="ml-auto pl-4 font-medium text-fg figure">
                        {detail.value}
                      </span>
                    </div>
                  ))}
                  <div className="flex items-center gap-2">
                    <span className="text-fg-muted">{changeColumn}</span>
                    <span className="ml-auto pl-4">
                      {datum.value === null ? (
                        <span className="text-fg-muted">None</span>
                      ) : (
                        <SignedChange value={datum.value} />
                      )}
                    </span>
                  </div>
                  {datum.value === null && datum.reason && (
                    <p className="max-w-xs text-fg-muted">{datum.reason}</p>
                  )}
                </TooltipBox>
              );
            }}
          />
          <Bar
            dataKey="value"
            maxBarSize={BAR_SIZE}
            isAnimationActive={!reducedMotion}
            shape={(props: unknown) => (
              <ChangeBar {...(props as BarShapeProps)} vertical={vertical} />
            )}
          />
        </RechartsBarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/** "+12.3% (up)", "−4.0% (down)", "0.0% (no change)" or "No comparison: <why>". */
function spokenChange(datum: DivergingDatum): string {
  if (datum.value === null) return `No comparison${datum.reason ? `: ${datum.reason}` : ""}`;
  const direction = directionOf(datum.value);
  if (direction === "flat") return `${formatSignedPercent(0)} (no change)`;
  return `${formatSignedPercent(datum.value)} (${direction})`;
}

interface BarShapeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: Row;
}

/**
 * One bar: the far end rounded, the end on the zero line square. No comparison: a neutral
 * ring on the zero line. A change that rounds to 0.0%: a neutral 2px mark.
 */
function ChangeBar({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  payload,
  vertical,
}: BarShapeProps & { vertical: boolean }) {
  if (!payload) return null;
  if (payload.missing) {
    // Recharts gives a zero-length bar on the zero line: its middle is where the ring goes.
    const cx = vertical ? x + width / 2 : x;
    const cy = vertical ? y : y + height / 2;
    return (
      <circle
        cx={cx}
        cy={cy}
        r={RING_RADIUS}
        fill="none"
        strokeWidth={1.5}
        stroke={NEUTRAL_MARK_COLOR}
      />
    );
  }
  const direction = directionOf(payload.value);
  const left = Math.min(x, x + width);
  const top = Math.min(y, y + height);
  const w = Math.abs(width);
  const h = Math.abs(height);
  if (direction === "flat") {
    return vertical ? (
      <rect x={left} y={top - 1} width={w} height={2} fill={NEUTRAL_MARK_COLOR} />
    ) : (
      <rect x={left - 1} y={top} width={2} height={h} fill={NEUTRAL_MARK_COLOR} />
    );
  }
  const up = direction === "up";
  const end = vertical ? (up ? "top" : "bottom") : up ? "right" : "left";
  return (
    <path
      // At least a pixel long, so a small change still shows.
      d={roundedBar(left, top, vertical ? w : Math.max(w, 1), vertical ? Math.max(h, 1) : h, end)}
      fill={up ? UP_COLOR : DOWN_COLOR}
    />
  );
}

/** A rectangle with its `end` side's two corners rounded (4px, less on a short bar). */
function roundedBar(
  x: number,
  y: number,
  w: number,
  h: number,
  end: "top" | "bottom" | "left" | "right",
) {
  const across = end === "top" || end === "bottom" ? w : h;
  const along = end === "top" || end === "bottom" ? h : w;
  const r = Math.max(0, Math.min(RADIUS, across / 2, along));
  const arc = (toX: number, toY: number) => `A${r},${r} 0 0 1 ${toX},${toY}`;
  switch (end) {
    case "top":
      return `M${x},${y + h}V${y + r}${arc(x + r, y)}H${x + w - r}${arc(x + w, y + r)}V${y + h}Z`;
    case "bottom":
      return `M${x},${y}H${x + w}V${y + h - r}${arc(x + w - r, y + h)}H${x + r}${arc(x, y + h - r)}Z`;
    case "right":
      return `M${x},${y}H${x + w - r}${arc(x + w, y + r)}V${y + h - r}${arc(x + w - r, y + h)}H${x}Z`;
    case "left":
      return `M${x + w},${y}V${y + h}H${x + r}${arc(x, y + h - r)}V${y + r}${arc(x + r, y)}Z`;
  }
}

/**
 * A value axis that always includes zero, in round steps (1, 2, 2.5 or 5 x a power of
 * ten). With `centreZero` it is symmetric, so zero sits in the middle.
 */
function changeScale(values: number[], centreZero: boolean) {
  let lo = Math.min(0, ...values);
  let hi = Math.max(0, ...values);
  if (centreZero) {
    const reach = Math.max(-lo, hi);
    lo = -reach;
    hi = reach;
  }
  const rough = (hi - lo || 0.1) / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= rough) ?? 10 * power;
  // Whole steps out from zero; the epsilon keeps -0.2 / 0.1 = -2.0000000000000004 at -2.
  const first = Math.floor(lo / step + 1e-9);
  const last = Math.ceil(hi / step - 1e-9);
  const reach = Math.max(-first, last);
  const [from, to] = centreZero ? [-reach, reach] : [first, Math.max(last, first + 1)];
  const ticks: number[] = [];
  for (let k = from; k <= to; k++) ticks.push(k * step);
  return { domain: [from * step, to * step] as [number, number], ticks };
}
