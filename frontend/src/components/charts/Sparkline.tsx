import { cn } from "../../lib/cn";

const WIDTH = 100;
const HEIGHT = 32;
const PAD = 2; // keeps the 2px line inside the box at the extremes

/**
 * A trend line without axes, for KPI cards. Plain SVG, so a row of KPIs does not load
 * Recharts. Stretches to its box; the stroke stays 2px wide whatever the scale.
 */
export function Sparkline({
  values,
  label,
  className,
}: {
  values: number[];
  /** The accessible name: what the trend shows, with its first and last value. */
  label: string;
  className?: string;
}) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values.map((value, i) => {
    const x = (i / (values.length - 1)) * WIDTH;
    const y = PAD + (1 - (value - min) / span) * (HEIGHT - 2 * PAD);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const line = `M${points.join("L")}`;
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      preserveAspectRatio="none"
      className={cn("block h-10 w-full", className)}
    >
      <path d={`${line}L${WIDTH},${HEIGHT}L0,${HEIGHT}Z`} className="fill-band" />
      <path
        d={line}
        fill="none"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        className="stroke-series-1"
      />
    </svg>
  );
}
