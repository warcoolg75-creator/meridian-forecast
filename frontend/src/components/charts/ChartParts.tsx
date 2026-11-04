import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import { TrendIcon } from "../brand/icons";
import { SERIES_BG, SERIES_STROKE } from "./chart-theme";

export type KeyShape =
  | "line"
  | "dashed"
  | "bar"
  | "band"
  | "event-band"
  | "event-line"
  // The sign of a change: an arrow in sage or clay, and a ring for "no comparison".
  | "up"
  | "down"
  | "no-comparison";

/**
 * The mark beside a legend or tooltip label: identity comes from this coloured key,
 * never from coloured text. `series` is the slot (0-2); the band key needs none.
 */
export function SeriesKey({ shape, series = 0 }: { shape: KeyShape; series?: number }) {
  if (shape === "bar") {
    return <span aria-hidden className={cn("size-3 shrink-0 rounded-full", SERIES_BG[series])} />;
  }
  if (shape === "band") {
    return <span aria-hidden className="h-3 w-4 shrink-0 rounded-control bg-band" />;
  }
  if (shape === "event-band") {
    return <span aria-hidden className="h-3 w-4 shrink-0 rounded-control bg-annotation-band" />;
  }
  if (shape === "up" || shape === "down") {
    return (
      <TrendIcon
        direction={shape}
        className={cn("size-4 shrink-0", shape === "up" ? "text-positive" : "text-negative")}
      />
    );
  }
  if (shape === "no-comparison") {
    return (
      <svg aria-hidden viewBox="0 0 12 12" className="size-3 shrink-0">
        <circle cx="6" cy="6" r="4" fill="none" strokeWidth="1.5" className="stroke-line-strong" />
      </svg>
    );
  }
  if (shape === "event-line") {
    return (
      <svg aria-hidden viewBox="0 0 4 12" className="h-3 w-1 shrink-0 overflow-visible">
        <line x1="2" y1="0" x2="2" y2="12" strokeWidth="1.5" className="stroke-annotation" />
      </svg>
    );
  }
  return (
    <svg aria-hidden viewBox="0 0 16 4" className="h-1 w-4 shrink-0 overflow-visible">
      <line
        x1="0"
        y1="2"
        x2="16"
        y2="2"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray={shape === "dashed" ? "3 3" : undefined}
        className={SERIES_STROKE[series]}
      />
    </svg>
  );
}

export interface LegendEntry {
  label: string;
  shape: KeyShape;
  series?: number;
}

/** Shown for two or more series, or when dashes and a band need explaining. */
export function ChartLegend({ entries }: { entries: LegendEntry[] }) {
  return (
    <ul role="list" className="flex flex-wrap gap-x-5 gap-y-2 text-step-n2 text-fg-muted">
      {entries.map((entry) => (
        <li key={`${entry.shape}-${entry.label}`} className="flex items-center gap-2">
          <SeriesKey shape={entry.shape} series={entry.series} />
          {entry.label}
        </li>
      ))}
    </ul>
  );
}

/** The hover card: a heading (the date or category) and one row per value. */
export function TooltipBox({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <div className="space-y-2 rounded-control border border-line bg-surface px-3 py-2 text-step-n2 shadow-raised">
      <p className="font-medium text-fg">{heading}</p>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

export function TooltipRow({
  shape,
  series,
  label,
  value,
}: {
  shape: KeyShape;
  series?: number;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <SeriesKey shape={shape} series={series} />
      <span className="text-fg-muted">{label}</span>
      <span className="ml-auto pl-4 font-medium text-fg figure">{value}</span>
    </div>
  );
}

/**
 * The plotted numbers as a table only screen readers see, so the data itself is
 * readable, not only the description. First column: the row heading (date, category).
 */
export function HiddenDataTable({
  caption,
  columns,
  rows,
}: {
  caption: string;
  columns: string[];
  rows: Array<{ key: string; heading: string; cells: string[] }>;
}) {
  // sr-only goes on a wrapper: a table ignores the 1px width and grows to fit its
  // content, which made the page scroll sideways on phones.
  return (
    <div className="sr-only">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">{row.heading}</th>
              {row.cells.map((cell, index) => (
                <td key={columns[index + 1] ?? index}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
