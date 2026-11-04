/** Which way a change against the comparison period goes. */
export type Direction = "up" | "down" | "flat";

/** Anything that rounds to 0.0% is flat. */
export const FLAT = 0.0005;

export function directionOf(change: number): Direction {
  if (Math.abs(change) < FLAT) return "flat";
  return change > 0 ? "up" : "down";
}
