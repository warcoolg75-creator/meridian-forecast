import { extendTailwindMerge } from "tailwind-merge";

import tokens from "../styles/tokens.css?raw";

/**
 * The theme's keys in one tokens.css namespace: "--radius-card:" gives "card". Wildcard
 * resets ("--color-*: initial") and sub-properties ("--text-step-1--line-height") are not
 * keys, and neither are names in comments (no colon after them).
 */
function themeKeys(namespace: string): string[] {
  const pattern = new RegExp(`--${namespace}-([a-z0-9]+(?:-[a-z0-9]+)*):`, "g");
  return [...new Set([...tokens.matchAll(pattern)].map((match) => match[1]))];
}

const sizes = themeKeys("size");

/**
 * tailwind-merge, taught this design system from tokens.css itself, so it cannot drift.
 * Its defaults assume Tailwind's stock theme: any word after "text-" counts as a colour,
 * so "text-step-1 text-fg" would have lost the size, and "rounded-card", "shadow-rest" or
 * "tracking-wordmark" would not be recognised at all.
 */
const twMerge = extendTailwindMerge({
  override: {
    theme: {
      color: ["inherit", "current", "transparent", ...themeKeys("color")],
      text: themeKeys("text"),
      font: themeKeys("font").filter((key) => !key.startsWith("weight-")),
      "font-weight": themeKeys("font-weight"),
      radius: themeKeys("radius"),
      shadow: themeKeys("shadow"),
      tracking: themeKeys("tracking"),
    },
  },
  extend: {
    classGroups: {
      // index.css's @utility rules: h-chart-md and h-10 set the same property.
      h: [{ h: sizes.filter((key) => key.startsWith("chart-")) }],
      "max-h": [{ "max-h": sizes.filter((key) => key.startsWith("scroll-")) }],
    },
  },
});

/**
 * Join class names, skipping falsy ones; when two set the same property, the later one
 * wins. That is what lets a caller override a component's default: LineIcon starts at
 * size-6, and an icon given size-4 is 16px. Until 2026-11-04 cn() only joined strings,
 * and which class won was decided by the order of rules in the generated CSS, where
 * size-6 comes after size-4 and size-5: every icon asking for 16 or 20px drew at 24px,
 * and the products table's sparklines took Sparkline's h-10 w-full over their h-8 w-24.
 *
 * Named `cn` on purpose: ESLint's Tailwind rules lint the arguments of cn() calls, so
 * class strings kept in variables stay checked.
 */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return twMerge(...classes);
}
