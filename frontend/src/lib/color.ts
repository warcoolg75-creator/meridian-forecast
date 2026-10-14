/**
 * WCAG 2.x contrast helpers for the styleguide. Colours are read from the live CSS
 * (src/styles/tokens.css), never written here.
 */

export type Rgb = readonly [number, number, number];

/** WCAG AA minimum for normal-size text. */
export const AA_NORMAL_TEXT = 4.5;

/**
 * Resolve a CSS colour expression such as `var(--color-maroon-500)` to sRGB 0..255.
 * A translucent colour (the chart band, the scrim) is composited over `background`, so
 * its contrast is measured as it is seen.
 */
export function resolveColor(expression: string, background?: Rgb): Rgb {
  const probe = document.createElement("span");
  probe.style.display = "none";
  probe.style.color = expression;
  document.body.append(probe);
  const computed = getComputedStyle(probe).color;
  probe.remove();
  const { rgb, alpha } = parseComputedColor(computed);
  if (alpha >= 1 || !background) return rgb;
  return [0, 1, 2].map((i) => rgb[i] * alpha + background[i] * (1 - alpha)) as unknown as Rgb;
}

function parseAlpha(value: string | undefined): number {
  if (value === undefined) return 1;
  return value.endsWith("%") ? Number(value.slice(0, -1)) / 100 : Number(value);
}

/** Browsers serialise hex tokens in the legacy RGB syntax and srgb mixes in CSS Color 4 form. */
function parseComputedColor(value: string): { rgb: Rgb; alpha: number } {
  const legacy = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?/i.exec(
    value,
  );
  if (legacy) {
    return {
      rgb: [Number(legacy[1]), Number(legacy[2]), Number(legacy[3])],
      alpha: parseAlpha(legacy[4]),
    };
  }
  const srgb =
    /^color\(srgb\s+([\d.e+-]+)\s+([\d.e+-]+)\s+([\d.e+-]+)(?:\s*\/\s*([\d.e+-]+%?))?/i.exec(value);
  if (srgb) {
    return {
      rgb: [Number(srgb[1]) * 255, Number(srgb[2]) * 255, Number(srgb[3]) * 255],
      alpha: parseAlpha(srgb[4]),
    };
  }
  throw new Error(`Unsupported computed colour: ${value}`);
}

function linear(channel: number): number {
  const s = channel / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function luminance([r, g, b]: Rgb): number {
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

export function contrastRatio(a: Rgb, b: Rgb): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/** Truncated, not rounded, so 4.499:1 never displays as a passing 4.50:1. */
export function formatRatio(ratio: number): string {
  return `${(Math.floor(ratio * 100) / 100).toFixed(2)}:1`;
}

export function toHex(rgb: Rgb): string {
  return `#${rgb.map((c) => Math.round(c).toString(16).padStart(2, "0")).join("")}`.toUpperCase();
}
