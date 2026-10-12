import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import betterTailwindcss from "eslint-plugin-better-tailwindcss";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

// A hex colour inside any string. Colours are written in src/styles/tokens.css only;
// scripts/check-tokens.mjs enforces the same rule repo-wide.
const HEX = "#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\\b";
const NO_HEX = [
  { selector: `Literal[value=/${HEX}/]`, message: "No hex colours outside src/styles/tokens.css." },
  {
    selector: `TemplateElement[value.raw=/${HEX}/]`,
    message: "No hex colours outside src/styles/tokens.css.",
  },
];
const NO_INLINE_STYLE = {
  selector: "JSXAttribute[name.name='style']",
  message: "No inline styles: use the token utilities generated from src/styles/tokens.css.",
};

export default defineConfig([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{js,mjs}"],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat["recommended-latest"],
      reactRefresh.configs.vite,
    ],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
  },
  {
    // The design system is enforced here, at lint time, because Tailwind silently drops
    // classes it does not know. `npm run build` runs this config first, so an
    // off-palette or off-scale class fails the build instead of slipping through.
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "better-tailwindcss": betterTailwindcss },
    settings: { "better-tailwindcss": { entryPoint: "src/styles/index.css" } },
    rules: {
      // Only utilities generated from tokens.css exist (Tailwind's defaults are reset).
      "better-tailwindcss/no-unknown-classes": "error",
      // Arbitrary values and variables (p-[13px], bg-(--x), [color:red]) bypass the tokens.
      "better-tailwindcss/no-restricted-classes": [
        "error",
        {
          restrict: [
            {
              pattern: "[\\[\\]()]",
              message: "Arbitrary values bypass the design tokens; use a token utility.",
            },
          ],
        },
      ],
      "better-tailwindcss/no-conflicting-classes": "error",
      "better-tailwindcss/no-duplicate-classes": "error",
      "better-tailwindcss/no-deprecated-classes": "error",
      "no-restricted-syntax": ["error", ...NO_HEX, NO_INLINE_STYLE],
    },
  },
  {
    // The styleguide renders tokens it discovers in the live stylesheet, so it sets
    // var(--token) through `style`. Hex is still banned there.
    files: ["src/pages/styleguide/**/*.{ts,tsx}"],
    rules: { "no-restricted-syntax": ["error", ...NO_HEX] },
  },
  prettier,
]);
