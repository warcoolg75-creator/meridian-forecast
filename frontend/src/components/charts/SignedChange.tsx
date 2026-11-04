import { cn } from "../../lib/cn";
import { formatSignedPercent } from "../../lib/format";
import { TrendIcon } from "../brand/icons";
import { directionOf } from "./change";

/**
 * A change against the comparison period: arrow, sign and colour together, so colour is
 * never the only signal. Sage up, clay down, ink when it rounds to 0.0%.
 */
export function SignedChange({ value, className }: { value: number; className?: string }) {
  const direction = directionOf(value);
  const tone =
    direction === "up" ? "text-positive" : direction === "down" ? "text-negative" : "text-fg-muted";
  return (
    // Baseline-aligned with the icon centred, so the figure sets the box's baseline and sits
    // level with the numbers beside it. The icon keeps LineIcon's 24px box (the arrow is
    // drawn in its middle 10px, right for 14px text); -my-1 stops it making the row taller.
    <span className={cn("inline-flex items-baseline gap-1 font-medium", tone, className)}>
      <TrendIcon direction={direction} className="-my-1 shrink-0 self-center" />
      <span className="figure">{formatSignedPercent(direction === "flat" ? 0 : value)}</span>
      <span className="sr-only">{direction === "flat" ? "unchanged" : direction}</span>
    </span>
  );
}
