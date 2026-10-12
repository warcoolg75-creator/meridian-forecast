/**
 * Design-token guard. Runs in `npm run check`, so in `npm run build`, `make lint` and the
 * pre-commit hook.
 *
 * 1. No hex colour anywhere in the repo (every file git tracks or would track) except
 *    frontend/src/styles/tokens.css.
 * 2. No colour functions (rgb, hsl, oklch, color-mix, ...) in frontend code outside
 *    tokens.css: new colours are derived there, from the palette.
 * 3. In any other CSS file, colour properties may only use var(--color-*) or a keyword
 *    (transparent, currentColor, inherit, ...).
 * 4. tokens.css still resets every Tailwind default namespace it replaces, so no default
 *    palette or scale can creep back in.
 *
 * Unknown and arbitrary-value Tailwind classes are caught by ESLint (better-tailwindcss).
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = execFileSync("git", ["rev-parse", "--show-toplevel"], { encoding: "utf8" }).trim();
const TOKENS = "frontend/src/styles/tokens.css";
const SELF = path.relative(root, fileURLToPath(import.meta.url)).replaceAll("\\", "/");

const BINARY = /\.(?:png|jpe?g|gif|webp|avif|ico|woff2?|ttf|otf|eot|pdf|db|sqlite|zip|gz)$/i;
const HEX = /#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b/;
const COLOUR_FUNCTION = /\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color|color-mix)\(/i;
const FRONTEND_CODE = /^frontend\/.*\.(?:css|tsx?|jsx?|mjs|cjs|html)$/;
const COLOUR_PROPERTY =
  /(?:^|[;{\s])((?:background-)?color|border(?:-(?:top|right|bottom|left|block|inline)(?:-(?:start|end))?)?-color|outline-color|text-decoration-color|caret-color|accent-color|column-rule-color|fill|stroke)\s*:\s*([^;}]+)/gi;
const ALLOWED_VALUE =
  /^(?:var\(--color-[a-z0-9-]+\)|transparent|currentcolor|inherit|initial|unset|revert|none)$/i;
const REQUIRED_RESETS = [
  "--color-*",
  "--font-*",
  "--font-weight-*",
  "--text-*",
  "--leading-*",
  "--spacing",
  "--spacing-*",
  "--radius-*",
  "--shadow-*",
  "--inset-shadow-*",
  "--drop-shadow-*",
  "--text-shadow-*",
];

const files = execFileSync(
  "git",
  ["ls-files", "--cached", "--others", "--exclude-standard", "-z"],
  {
    cwd: root,
    encoding: "utf8",
  },
)
  .split("\0")
  .filter(Boolean);

const problems = [];
let scanned = 0;
for (const file of files) {
  if (file === TOKENS || file === SELF || BINARY.test(file)) continue;
  let text;
  try {
    text = readFileSync(path.join(root, file), "utf8");
  } catch {
    continue; // deleted in the working tree but still in the index
  }
  scanned++;
  const lines = text.split(/\r?\n/);
  lines.forEach((line, i) => {
    const hex = line.match(HEX);
    if (hex)
      problems.push(`${file}:${i + 1}: hex colour ${hex[0]} (only ${TOKENS} may hold colours)`);
    if (FRONTEND_CODE.test(file)) {
      const fn = line.match(COLOUR_FUNCTION);
      if (fn)
        problems.push(
          `${file}:${i + 1}: colour function ${fn[0]}...) (derive colours in ${TOKENS})`,
        );
    }
  });
  if (file.startsWith("frontend/") && file.endsWith(".css")) {
    for (const match of text.matchAll(COLOUR_PROPERTY)) {
      const value = match[2].replace(/!important/i, "").trim();
      if (!ALLOWED_VALUE.test(value)) {
        const line = text.slice(0, match.index).split("\n").length;
        problems.push(`${file}:${line}: ${match[1]}: ${value} (use var(--color-*) from ${TOKENS})`);
      }
    }
  }
}

const tokens = readFileSync(path.join(root, TOKENS), "utf8");
for (const namespace of REQUIRED_RESETS) {
  const escaped = namespace.replace(/[*]/g, "\\*");
  if (!new RegExp(`(^|\\s)${escaped}\\s*:\\s*initial\\s*;`).test(tokens)) {
    problems.push(`${TOKENS}: missing "${namespace}: initial;" (Tailwind's defaults would return)`);
  }
}

if (problems.length) {
  console.error(`check-tokens: ${problems.length} problem(s)\n  ${problems.join("\n  ")}`);
  process.exit(1);
}
console.log(`check-tokens: OK (${scanned} files scanned; colours live only in ${TOKENS})`);
