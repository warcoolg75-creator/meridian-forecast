import { cn } from "../../lib/cn";
import { errorMessage, formatInteger, formatSignedPercent } from "../../lib/format";
import { AlertIcon, TrendIcon } from "../brand/icons";
import { Loading, Skeleton } from "../feedback/Skeleton";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Sparkline } from "./Sparkline";

export interface KpiCardProps {
  /** Sentence case, no colon: "Units sold". */
  label: string;
  /** The headline number. null or undefined (not loading, no error): the empty state. */
  value: number | null | undefined;
  /** Default: a whole number with Indian grouping. Pass formatRupees for money. */
  formatValue?: (value: number) => string;
  /** Relative change against the comparison period, as a fraction: 0.062 is +6.2%. */
  delta?: number | null;
  /**
   * Whether a rise is good news. False for stockouts, returns, forecast error. null:
   * neither (e.g. average selling price): the arrow shows the direction, in ink.
   */
  upIsGood?: boolean | null;
  /** Said instead of a delta when there is none, e.g. why no comparison is shown. */
  deltaNote?: string;
  /** A small note under the figure, e.g. how a figure is costed. */
  footnote?: string;
  /** Names the comparison period, e.g. "vs previous 4 weeks". */
  comparison?: string;
  /** Recent values, oldest first, drawn as a trend line under the figure. */
  sparkline?: number[];
  /** The sparkline's span, e.g. "last 12 weeks". */
  sparklineSpan?: string;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  /** Shown when there is no value, e.g. "No sales in this period". */
  emptyMessage?: string;
}

type Direction = "up" | "down" | "flat";

/** Anything that rounds to 0.0% is flat. */
const FLAT = 0.0005;

function directionOf(delta: number): Direction {
  if (Math.abs(delta) < FLAT) return "flat";
  return delta > 0 ? "up" : "down";
}

/**
 * One headline number with its change and trend. The arrow gives the direction; the
 * colour says whether that is good (sage), bad (clay) or neither (ink). With
 * `upIsGood={false}` a rise is clay.
 */
export function KpiCard({
  label,
  value,
  formatValue = formatInteger,
  delta,
  upIsGood = true,
  comparison,
  sparkline,
  sparklineSpan,
  isLoading,
  error,
  onRetry,
  emptyMessage = "No data for this period.",
  deltaNote,
  footnote,
}: KpiCardProps) {
  return (
    <Card className="flex flex-col gap-3">
      <p className="text-step-n1 font-medium text-fg-muted">{label}</p>
      {isLoading ? (
        <Loading label={label} className="flex flex-col gap-3">
          <Skeleton className="h-10 w-24" />
          <Skeleton className="h-5 w-20" />
          {sparkline && <Skeleton className="h-10 w-full" />}
        </Loading>
      ) : error ? (
        <div className="flex flex-1 flex-col items-start gap-2">
          <p className="flex items-center gap-2 text-step-n1 text-fg">
            <AlertIcon className="size-5 shrink-0 text-negative" />
            Couldn’t load {label.toLowerCase()}
          </p>
          <p className="text-step-n2 text-fg-muted">{errorMessage(error)}</p>
          {onRetry && (
            <Button variant="secondary" size="sm" onClick={onRetry}>
              Try again
            </Button>
          )}
        </div>
      ) : typeof value !== "number" ? (
        <div className="flex flex-col gap-1">
          <p aria-hidden className="text-step-4 font-semibold text-fg-subtle figure">
            –
          </p>
          <p className="text-step-n1 text-fg-muted">{emptyMessage}</p>
        </div>
      ) : (
        <>
          <p className="text-step-4 font-semibold text-fg figure">{formatValue(value)}</p>
          {typeof delta === "number" ? (
            <Delta
              delta={delta}
              upIsGood={upIsGood}
              comparison={comparison ?? "vs previous period"}
            />
          ) : (
            deltaNote && <p className="text-step-n2 text-fg-muted">{deltaNote}</p>
          )}
          {sparkline && sparkline.length > 1 && (
            <Sparkline
              values={sparkline}
              label={`${label}${sparklineSpan ? `, ${sparklineSpan}` : ""}: from ${formatValue(sparkline[0])} to ${formatValue(sparkline[sparkline.length - 1])}`}
              className="mt-1"
            />
          )}
          {footnote && <p className="text-step-n2 text-fg-muted">{footnote}</p>}
        </>
      )}
    </Card>
  );
}

function Delta({
  delta,
  upIsGood,
  comparison,
}: {
  delta: number;
  upIsGood: boolean | null;
  comparison: string;
}) {
  const direction = directionOf(delta);
  const judged = direction !== "flat" && upIsGood !== null;
  const good = judged && (direction === "up") === upIsGood;
  const tone = !judged ? "text-fg-muted" : good ? "text-positive" : "text-negative";
  const shown = direction === "flat" ? formatSignedPercent(0) : formatSignedPercent(delta);
  const spoken =
    direction === "flat"
      ? `Unchanged ${comparison}`
      : `${direction === "up" ? "Up" : "Down"} ${shown.replace(/^[+-]/, "")} ${comparison}${judged ? (good ? ", favourable" : ", unfavourable") : ""}`;
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-step-n1">
      <span className={cn("inline-flex items-center gap-1 font-medium", tone)}>
        <TrendIcon direction={direction} className="size-4" />
        <span aria-hidden className="figure">
          {shown}
        </span>
      </span>
      <span aria-hidden className="text-fg-muted">
        {comparison}
      </span>
      <span className="sr-only">{spoken}</span>
    </p>
  );
}
