/**
 * Reads the design tokens back out of the live stylesheet, so the styleguide shows
 * exactly what src/styles/tokens.css declares. A new token appears on the page without
 * editing it.
 */

export interface ColorToken {
  /** e.g. "maroon-500" */
  name: string;
  /** e.g. "--color-maroon-500" */
  cssVar: string;
  /** As declared: a hex value, a mix of other tokens, or a reference to one. */
  declared: string;
  kind: "palette" | "derived" | "alias";
}

/**
 * Custom properties declared on :root, in declaration order, with values as written:
 * var() references intact (getComputedStyle would substitute them).
 *
 * Tailwind emits each mixed colour twice inside the :root rule: a precomputed fallback,
 * then the authored value in a nested @supports block. The CSSOM splits such a rule, so
 * declarations after the first nested block live in nested-declaration rules; the later,
 * authored value overwrites the fallback here (Map order stays the declaration order).
 */
export function readRootDeclarations(): Map<string, string> {
  const declarations = new Map<string, string>();
  const read = (style: CSSStyleDeclaration) => {
    for (let i = 0; i < style.length; i++) {
      const property = style.item(i);
      if (property.startsWith("--")) {
        declarations.set(property, style.getPropertyValue(property).trim());
      }
    }
  };
  const visitNested = (rules: CSSRuleList) => {
    for (const rule of Array.from(rules)) {
      if ("style" in rule) read((rule as CSSRule & { style: CSSStyleDeclaration }).style);
      if ("cssRules" in rule) visitNested((rule as CSSGroupingRule).cssRules);
    }
  };
  const visit = (rules: CSSRuleList) => {
    for (const rule of Array.from(rules)) {
      if (rule instanceof CSSStyleRule && /(^|,)\s*:root\b/.test(rule.selectorText)) {
        read(rule.style);
        visitNested(rule.cssRules);
      } else if ("cssRules" in rule) {
        visit((rule as CSSGroupingRule).cssRules);
      }
    }
  };
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      visit(sheet.cssRules);
    } catch {
      // A cross-origin stylesheet: not one of ours.
    }
  }
  return declarations;
}

export function colorTokens(declarations: Map<string, string>): ColorToken[] {
  const tokens: ColorToken[] = [];
  for (const [cssVar, declared] of declarations) {
    if (!cssVar.startsWith("--color-")) continue;
    const kind = declared.startsWith("#")
      ? "palette"
      : declared.startsWith("var(")
        ? "alias"
        : "derived";
    tokens.push({ name: cssVar.slice("--color-".length), cssVar, declared, kind });
  }
  return tokens;
}

/** [cssVar, value] for every declaration under a prefix, e.g. "--spacing-". */
export function withPrefix(
  declarations: Map<string, string>,
  prefix: string,
): Array<[string, string]> {
  return [...declarations].filter(([name]) => name.startsWith(prefix));
}

/** px value of a rem/px length or a clamp(rem, rem + vw, rem) at a given viewport width. */
export function lengthInPx(value: string, viewportWidth: number, rootPx = 16): number {
  if (/^0(?:rem|px)?$/.test(value)) return 0;
  const rem = /^([\d.]+)rem$/.exec(value);
  if (rem) return Number(rem[1]) * rootPx;
  const px = /^([\d.]+)px$/.exec(value);
  if (px) return Number(px[1]);
  const clamp =
    /^clamp\(\s*([\d.]+)rem\s*,\s*([\d.]+)rem\s*\+\s*([\d.]+)vw\s*,\s*([\d.]+)rem\s*\)$/.exec(
      value,
    );
  if (clamp) {
    const [min, base, vw, max] = clamp.slice(1).map(Number);
    const fluid = base * rootPx + (vw * viewportWidth) / 100;
    return Math.min(Math.max(fluid, min * rootPx), max * rootPx);
  }
  return Number.NaN;
}
