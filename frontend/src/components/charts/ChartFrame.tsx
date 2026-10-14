import { useId, type ReactNode } from "react";

import { cn } from "../../lib/cn";
import { EmptyState } from "../feedback/EmptyState";
import { ErrorState } from "../feedback/ErrorState";
import { Loading, Skeleton } from "../feedback/Skeleton";
import { Card } from "../ui/Card";
import { CHART_HEIGHT, type ChartHeight } from "./chart-theme";
import type { ChartView } from "./chart-view";

/**
 * The card every chart sits in: title, description (the figure's accessible
 * description), then the plot or, in its place and at its height, a skeleton, an error
 * or an empty state. Axes are only ever drawn around data.
 *
 * In the ready state the plot is followed by `dataTable`: the plotted values as a
 * visually hidden table, so a screen reader can read the numbers, not just the summary.
 */
export function ChartFrame({
  title,
  description,
  height,
  view,
  legend,
  yAxisTitle,
  xAxisTitle,
  dataTable,
  children,
}: {
  title: string;
  description: string;
  height: ChartHeight;
  view: ChartView;
  legend?: ReactNode;
  /** Value axis or vertical axis title, with its unit: shown above the plot. */
  yAxisTitle: string;
  /** Horizontal axis title, with its unit: shown below the plot. */
  xAxisTitle: string;
  dataTable: ReactNode;
  /** The plot itself, rendered only when `view` is ready. */
  children: ReactNode;
}) {
  const id = useId();
  const box = CHART_HEIGHT[height];
  return (
    <Card>
      <figure aria-labelledby={`${id}-title`} aria-describedby={`${id}-desc`} className="space-y-4">
        <figcaption className="space-y-1">
          <p id={`${id}-title`} className="font-display text-step-1 font-semibold text-fg">
            {title}
          </p>
          <p id={`${id}-desc`} className="max-w-3xl text-step-n1 text-fg-muted">
            {description}
          </p>
        </figcaption>
        {view.kind === "ready" && (
          <>
            {legend}
            <div className="space-y-2">
              <p className="text-step-n2 text-fg-muted">{yAxisTitle}</p>
              <div className={box}>{children}</div>
              <p className="text-right text-step-n2 text-fg-muted">{xAxisTitle}</p>
            </div>
            {dataTable}
          </>
        )}
        {/* The other states take the plot's place at its height, with the axis titles'
            lines kept, so the card does not jump when data arrives. */}
        {view.kind === "loading" && (
          <Loading label={title} className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className={cn(box, "w-full")} />
            <div aria-hidden className="h-4" />
          </Loading>
        )}
        {view.kind === "error" && (
          <div className="space-y-2">
            <div aria-hidden className="h-4" />
            <ErrorState
              title={view.title}
              message={view.message}
              onRetry={view.onRetry}
              className={box}
            />
            <div aria-hidden className="h-4" />
          </div>
        )}
        {view.kind === "empty" && (
          <div className="space-y-2">
            <div aria-hidden className="h-4" />
            <EmptyState title={view.title} description={view.message} className={box} />
            <div aria-hidden className="h-4" />
          </div>
        )}
      </figure>
    </Card>
  );
}
