import { useMemo, useSyncExternalStore, type ReactNode } from "react";

import { Badge } from "../../components/ui/Badge";
import { Button, type ButtonVariant, type ForcedState } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { StyleguideNav } from "./StyleguideNav";
import { cn } from "../../lib/cn";
import {
  AA_NORMAL_TEXT,
  contrastRatio,
  formatRatio,
  resolveColor,
  toHex,
  type Rgb,
} from "../../lib/color";
import {
  colorTokens,
  lengthInPx,
  readRootDeclarations,
  withPrefix,
  type ColorToken,
} from "./tokens";

const BACKGROUND = "cream-50";

const ROLES: Record<string, string> = {
  "maroon-900": "Primary pressed",
  "maroon-700": "Primary hover",
  "maroon-500": "Primary actions and brand",
  "maroon-300": "Decorative accents only",
  "maroon-100": "Subtle primary backgrounds, selection",
  "cream-50": "App background and cards",
  "cream-100": "Muted surfaces",
  "cream-200": "Hairlines and dividers",
  "ink-900": "Body text",
  "ink-600": "Secondary text",
  "ink-400": "Placeholder, disabled text, control borders, icons. Never readable text",
  "sage-600": "Positive",
  "amber-600": "Warning: icons, dots, borders. Never text",
  "clay-600": "Negative, errors, destructive actions",
  "sage-100": "Tint behind positive text",
  "amber-100": "Tint behind warning text",
  "clay-100": "Tint behind negative text",
  "amber-800": "Warning text",
  "clay-700": "Destructive hover",
  canvas: "App background",
  surface: "Card and control surfaces",
  "surface-muted": "Muted surfaces, disabled fills",
  line: "Hairlines (decorative, no contrast needed)",
  "line-strong": "Control borders: 3.33:1 meets the 3:1 a control outline needs",
  fg: "Body text",
  "fg-muted": "Secondary text",
  "fg-subtle": "Placeholder and disabled only",
  primary: "Primary actions, links, brand",
  "primary-hover": "Primary hover",
  "primary-active": "Primary pressed",
  "primary-subtle": "Subtle primary backgrounds",
  "on-primary": "Text on primary and destructive fills, not on cream",
  focus: "Focus ring",
  positive: "Positive text, icons, marks",
  "positive-subtle": "Tint behind positive text",
  warning: "Warning icons, dots, borders. Never text",
  "warning-text": "Warning text",
  "warning-subtle": "Tint behind warning text",
  negative: "Negative text, errors, destructive",
  "negative-hover": "Destructive hover",
  "negative-subtle": "Tint behind negative text",
  scrim: "Behind the navigation drawer (ink-900 at 40%)",
  "series-1": "Chart series 1, the primary series. Marks only, never text",
  "series-2": "Chart series 2: comparison. Marks only (3.33:1 meets the 3:1 for marks)",
  "series-3": "Chart series 3. Marks only. There is no series 4",
  band: "Confidence band: maroon-500 at 14%, shown here over cream-50",
  "band-outer": "Wider (95%) band: maroon-500 at 8%, under the 80% band, shown over cream-50",
};

const FAMILIES: Array<[string, RegExp]> = [
  ["Maroon: brand and primary", /^maroon-/],
  ["Cream: surfaces", /^cream-/],
  ["Ink: text", /^ink-/],
  ["Status: positive, warning, negative", /^(sage|amber|clay)-/],
];

const SECTIONS = [
  ["palette", "Palette"],
  ["semantic", "Semantic colours"],
  ["type", "Typography"],
  ["spacing", "Spacing"],
  ["radius-shadow", "Radius and shadow"],
  ["tracking-motion", "Letter-spacing and motion"],
  ["buttons", "Buttons"],
  ["card", "Card"],
  ["inputs", "Input"],
] as const;

/** The production CSS is minified (".25rem"); show values as written in tokens.css. */
function pretty(value: string): string {
  return value.replace(
    /(^|[\s(,+])\.(\d)/g,
    (_, before: string, digit: string) => `${before}0.${digit}`,
  );
}

function subscribeToResize(onChange: () => void) {
  window.addEventListener("resize", onChange);
  return () => window.removeEventListener("resize", onChange);
}

function useViewportWidth() {
  return useSyncExternalStore(subscribeToResize, () => window.innerWidth);
}

/** Everything the page shows, read from the live stylesheet once. */
function useTokens() {
  return useMemo(() => {
    const declarations = readRootDeclarations();
    const colors = colorTokens(declarations);
    const background = resolveColor(`var(--color-${BACKGROUND})`);
    const rgb = new Map<string, Rgb>(
      colors.map((t) => [t.name, resolveColor(`var(${t.cssVar})`, background)]),
    );
    return { declarations, colors, background, rgb };
  }, []);
}

export default function Styleguide() {
  const tokens = useTokens();
  return (
    <div className="mx-auto max-w-6xl space-y-12 px-4 py-10 sm:px-6 lg:px-8">
      <header className="space-y-4">
        <StyleguideNav current="tokens" />
        <h1 className="text-step-5">Styleguide</h1>
        <p className="max-w-3xl text-fg-muted">
          Every token in <code className="font-mono text-step-n1">src/styles/tokens.css</code>, read
          live from the stylesheet. Each colour is marked for readable text: WCAG AA at normal size
          needs {AA_NORMAL_TEXT}:1 against {BACKGROUND}, the app background.
        </p>
        <nav aria-label="Sections" className="flex flex-wrap gap-x-4 gap-y-2 text-step-n1">
          {SECTIONS.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="text-primary underline-offset-4 hover:underline">
              {label}
            </a>
          ))}
        </nav>
      </header>

      <PaletteSection {...tokens} />
      <SemanticSection {...tokens} />
      <TypeSection declarations={tokens.declarations} />
      <SpacingSection declarations={tokens.declarations} />
      <RadiusShadowSection declarations={tokens.declarations} />
      <TrackingMotionSection declarations={tokens.declarations} />
      <ButtonSection />
      <CardSection />
      <InputSection />
    </div>
  );
}

function Section({
  id,
  title,
  intro,
  children,
}: {
  id: string;
  title: string;
  intro?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className="space-y-6 border-t border-line pt-10"
    >
      <div className="max-w-3xl space-y-2">
        <h2 id={`${id}-title`} className="text-step-3">
          {title}
        </h2>
        {intro && <p className="text-fg-muted">{intro}</p>}
      </div>
      {children}
    </section>
  );
}

/** Pass/fail for readable text at normal size, so the constraint is visible, not computed. */
function Verdict({ ratio, on = BACKGROUND }: { ratio: number; on?: string }) {
  const pass = ratio >= AA_NORMAL_TEXT;
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-step-n2 text-fg-muted">
        Text on {on}: <span className="figure">{formatRatio(ratio)}</span>
      </span>
      <Badge tone={pass ? "positive" : "negative"}>{pass ? "AA pass" : "AA fail"}</Badge>
    </div>
  );
}

// ------------------------------------------------------------------------------- palette

type TokenProps = ReturnType<typeof useTokens>;

function PaletteSection({ colors, rgb, background }: TokenProps) {
  const palette = colors.filter((t) => t.kind === "palette");
  const derived = colors.filter((t) => t.kind === "derived");
  const aliases = colors.filter((t) => t.kind === "alias");
  const swatches = (list: ColorToken[]) => (
    <ul role="list" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {list.map((token) => (
        <Swatch
          key={token.cssVar}
          token={token}
          rgb={rgb.get(token.name)!}
          ratio={contrastRatio(rgb.get(token.name)!, background)}
        />
      ))}
    </ul>
  );
  return (
    <Section
      id="palette"
      title="Palette"
      intro="The fifteen palette colours, the colours derived from them (mixed, never new hex values) and the semantic aliases components use."
    >
      {FAMILIES.map(([label, pattern]) => (
        <div key={label} className="space-y-3">
          <h3 className="text-step-1">{label}</h3>
          {swatches(palette.filter((t) => pattern.test(t.name)))}
        </div>
      ))}
      <div className="space-y-3">
        <h3 className="text-step-1">Derived</h3>
        {swatches(derived)}
      </div>
      <div className="space-y-3">
        <h3 className="text-step-1">Semantic aliases</h3>
        {swatches(aliases)}
      </div>
    </Section>
  );
}

function Swatch({ token, rgb, ratio }: { token: ColorToken; rgb: Rgb; ratio: number }) {
  const hex = token.kind === "palette" ? token.declared.toUpperCase() : toHex(rgb);
  const role = ROLES[token.name];
  // Phones: colour strip beside the details, which halves the page height. Wider: on top.
  return (
    <li className="flex overflow-hidden rounded-card border border-line bg-surface shadow-rest sm:flex-col">
      <div
        className="w-16 shrink-0 border-r border-line sm:h-16 sm:w-full sm:border-r-0 sm:border-b"
        style={{ backgroundColor: `var(${token.cssVar})` }}
      />
      <div className="min-w-0 flex-1 space-y-2 p-4">
        <div className="flex items-baseline justify-between gap-2">
          <p className="font-medium">{token.name}</p>
          <p className="font-mono text-step-n2 text-fg-muted">{hex}</p>
        </div>
        <p className="font-mono text-step-n2 break-all text-fg-muted">{token.cssVar}</p>
        {token.kind !== "palette" && (
          <p className="font-mono text-step-n2 break-all text-fg-muted">= {token.declared}</p>
        )}
        {role && <p className="text-step-n1 text-fg-muted">{role}</p>}
        <div className="border-t border-line pt-2">
          <Verdict ratio={ratio} />
        </div>
      </div>
    </li>
  );
}

// ------------------------------------------------------------------------------- semantic

function WarningIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 20 20"
      aria-hidden
      fill="currentColor"
      className={cn("size-5 shrink-0", className)}
    >
      <path fillRule="evenodd" d="M10 2 1 18h18L10 2Zm-.9 6h1.8v5H9.1V8Zm0 6.2h1.8V16H9.1v-1.8Z" />
    </svg>
  );
}

function SemanticSection({ rgb, background }: TokenProps) {
  const ratio = (fg: string, bg?: string) =>
    contrastRatio(rgb.get(fg)!, bg ? rgb.get(bg)! : background);
  return (
    <Section
      id="semantic"
      title="Semantic colours"
      intro="Sage, amber and clay carry positive, warning and negative. Maroon is the primary action and the brand: it never means bad."
    >
      <div className="grid gap-4 md:grid-cols-2">
        <Card className="space-y-4">
          <h3 className="flex items-center gap-2 text-step-2">
            <span aria-hidden className="size-4 rounded-full bg-primary" /> Primary / brand
          </h3>
          <p className="text-fg-muted">
            maroon-500. Primary actions and brand moments only. Errors, losses and destructive
            actions are clay, never maroon.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button>Save plan</Button>
            <Button variant="destructive">Delete plan</Button>
          </div>
          <Verdict ratio={ratio("primary")} />
        </Card>

        <Card className="space-y-4">
          <h3 className="flex items-center gap-2 text-step-2">
            <span aria-hidden className="size-4 rounded-full bg-positive" /> Positive
          </h3>
          <p className="text-fg-muted">sage-600. Growth, on-track plans, healthy stock.</p>
          <p className="figure text-step-2 font-medium text-positive">+6.2% vs last year</p>
          <Verdict ratio={ratio("positive")} />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Badge tone="positive">On track</Badge>
            <span className="text-step-n2 text-fg-muted">
              Badge text on sage-100:{" "}
              <span className="figure">{formatRatio(ratio("positive", "positive-subtle"))}</span>
            </span>
          </div>
        </Card>

        <Card className="space-y-4">
          <h3 className="flex items-center gap-2 text-step-2">
            <WarningIcon className="text-warning" /> Warning
          </h3>
          <p className="text-fg-muted">
            amber-600 is for the icon, dot and border only: as text it fails AA. Warning text uses
            the darker <code className="font-mono text-step-n1">warning-text</code> (amber-800,
            mixed from amber-600 and ink-900).
          </p>
          <div className="space-y-2 rounded-control border border-line p-3">
            <p className="text-step-n2 font-medium text-negative">Don't: amber-600 text</p>
            <p className="text-warning">Peak season starts in 3 weeks</p>
            <Verdict ratio={ratio("warning")} />
          </div>
          <div className="space-y-2 rounded-control border border-line p-3">
            <p className="text-step-n2 font-medium text-positive">Do: warning-text (amber-800)</p>
            <p className="text-warning-text">Peak season starts in 3 weeks</p>
            <Verdict ratio={ratio("warning-text")} />
          </div>
          <div className="flex gap-3 rounded-control border border-warning bg-warning-subtle p-3">
            <WarningIcon className="text-warning" />
            <div className="space-y-2">
              <p className="text-warning-text">Peak season starts in 3 weeks: review capacity.</p>
              <Verdict ratio={ratio("warning-text", "warning-subtle")} on="amber-100" />
            </div>
          </div>
          <Badge tone="warning">Peak in 3 weeks</Badge>
        </Card>

        <Card className="space-y-4">
          <h3 className="flex items-center gap-2 text-step-2">
            <span aria-hidden className="size-4 rounded-full bg-negative" /> Negative
          </h3>
          <p className="text-fg-muted">clay-600. Shortfalls, errors, destructive actions.</p>
          <p className="figure text-step-2 font-medium text-negative">−3.1% vs plan</p>
          <Verdict ratio={ratio("negative")} />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Badge tone="negative">Below plan</Badge>
            <span className="text-step-n2 text-fg-muted">
              Badge text on clay-100:{" "}
              <span className="figure">{formatRatio(ratio("negative", "negative-subtle"))}</span>
            </span>
          </div>
        </Card>
      </div>
    </Section>
  );
}

// ------------------------------------------------------------------------------- type

const rupees = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

function TypeSection({ declarations }: { declarations: Map<string, string> }) {
  const viewport = useViewportWidth();
  const steps = withPrefix(declarations, "--text-step-").filter(
    ([name]) => !name.endsWith("--line-height"),
  );
  const fonts = withPrefix(declarations, "--font-").filter(([name]) => !name.includes("weight"));
  const weights = withPrefix(declarations, "--font-weight-");
  return (
    <Section
      id="type"
      title="Typography"
      intro={`Fraunces for headings; Inter for body text and every number, with tabular figures. Sizes come from named steps only. Steps 1 to 5 scale with the viewport (now ${viewport}px wide).`}
    >
      <div className="grid gap-4 md:grid-cols-3">
        {fonts.map(([name, stack]) => (
          <Card key={name} className="space-y-2">
            <p className="font-mono text-step-n2 text-fg-muted">{name}</p>
            <p className="text-step-5" style={{ fontFamily: `var(${name})` }}>
              Aa 0123
            </p>
            <p className="font-mono text-step-n2 break-all text-fg-muted">{stack}</p>
          </Card>
        ))}
      </div>
      <p className="text-step-n1 text-fg-muted">
        Weights:{" "}
        {weights.map(([name, value]) => (
          <span key={name} className="mr-4 inline-block" style={{ fontWeight: `var(${name})` }}>
            {name.replace("--font-weight-", "")} <span className="figure">{value}</span>
          </span>
        ))}
      </p>

      <ul role="list" className="divide-y divide-line rounded-card border border-line bg-surface">
        {steps.map(([name, value]) => {
          const lineHeight = declarations.get(`${name}--line-height`) ?? "";
          const px = lengthInPx(value, viewport);
          return (
            <li key={name} className="grid gap-3 p-4 lg:grid-cols-3">
              <div className="space-y-1">
                <p className="font-medium">
                  {name.replace("--text-", "")}{" "}
                  <span className="figure text-step-n1 font-normal text-fg-muted">
                    {Number.isNaN(px) ? "" : `now ${px.toFixed(1)}px`}
                  </span>
                </p>
                <p className="font-mono text-step-n2 break-all text-fg-muted">
                  {pretty(value)} / line-height {pretty(lineHeight)}
                </p>
              </div>
              <div className="min-w-0 space-y-1 lg:col-span-2">
                <p
                  className="font-display"
                  style={{ fontSize: `var(${name})`, lineHeight: `var(${name}--line-height)` }}
                >
                  Festive demand outlook
                </p>
                <p
                  className="figure"
                  style={{ fontSize: `var(${name})`, lineHeight: `var(${name}--line-height)` }}
                >
                  {rupees.format(847320)} from 1,284 units
                </p>
              </div>
            </li>
          );
        })}
      </ul>

      <Card className="max-w-sm space-y-3">
        <p className="text-step-n1 text-fg-muted">
          Tabular figures keep columns aligned (illustrative numbers)
        </p>
        <table className="w-full">
          <tbody>
            {[
              ["Week 38", 96780],
              ["Week 39", 847320],
              ["Week 40", 1102450],
              ["Week 41", 12004500],
            ].map(([label, value]) => (
              <tr key={label} className="border-t border-line">
                <td className="py-2">{label}</td>
                <td className="figure py-2 text-right">{rupees.format(Number(value))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </Section>
  );
}

// ------------------------------------------------------------------------------- spacing

function SpacingSection({ declarations }: { declarations: Map<string, string> }) {
  const viewport = useViewportWidth();
  return (
    <Section
      id="spacing"
      title="Spacing"
      intro="A 4px scale. Padding, margin, gap and sizes use these steps only (p-4, gap-6, h-10, ...); there is no p-2.5 or p-7."
    >
      <ul role="list" className="space-y-3">
        {withPrefix(declarations, "--spacing-").map(([name, value]) => (
          <li key={name} className="flex items-center gap-4">
            <span className="w-24 shrink-0 font-mono text-step-n2 text-fg-muted">
              {name.replace("--", "")}
            </span>
            <span
              className="h-4 shrink-0 rounded-full bg-maroon-300"
              style={{ width: `var(${name})` }}
            />
            <span className="figure text-step-n2 text-fg-muted">
              {pretty(value)} · {lengthInPx(value, viewport)}px
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

// ------------------------------------------------------------------------------- radius & shadow

function TrackingMotionSection({ declarations }: { declarations: Map<string, string> }) {
  const tracking = withPrefix(declarations, "--tracking-");
  const motion = withPrefix(declarations, "--motion-");
  return (
    <Section
      id="tracking-motion"
      title="Letter-spacing and motion"
      intro="Letter-spacing tokens, and the motion behind scroll reveals and card lifts (all of it off under prefers-reduced-motion)."
    >
      <ul role="list" className="divide-y divide-line rounded-card border border-line bg-surface">
        {[...tracking, ...motion].map(([name, value]) => (
          <li key={name} className="grid gap-2 p-4 sm:grid-cols-3 sm:items-baseline">
            <p className="font-mono text-step-n2 text-fg-muted">{name}</p>
            <p className="figure text-step-n1">{pretty(value)}</p>
            {name.startsWith("--tracking-") ? (
              <p
                className="font-display font-semibold text-primary"
                style={{ letterSpacing: `var(${name})` }}
              >
                MERIDIAN
              </p>
            ) : (
              <p className="text-step-n1 text-fg-muted">{MOTION_USE[name] ?? ""}</p>
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
}

const MOTION_USE: Record<string, string> = {
  "--motion-duration": "Scroll reveals and card lifts",
  "--motion-rise": "How far below its place a reveal starts",
  "--motion-lift": "How far a card rises on hover",
};

function RadiusShadowSection({ declarations }: { declarations: Map<string, string> }) {
  return (
    <Section
      id="radius-shadow"
      title="Radius and shadow"
      intro="6px for controls, 8px for cards. Shadows are tinted from ink-900 at 4–12% opacity: soft, never black."
    >
      <div className="grid gap-4 sm:grid-cols-3">
        {withPrefix(declarations, "--radius-").map(([name, value]) => (
          <div key={name} className="space-y-2">
            <div
              className="flex h-24 items-center justify-center border border-line-strong bg-surface-muted"
              style={{ borderRadius: `var(${name})` }}
            >
              <span className="font-mono text-step-n2">{name.replace("--", "")}</span>
            </div>
            <p className="font-mono text-step-n2 text-fg-muted">{pretty(value)}</p>
          </div>
        ))}
      </div>
      <div className="grid gap-6 sm:grid-cols-3">
        {withPrefix(declarations, "--shadow-").map(([name]) => (
          <div
            key={name}
            className="flex h-24 items-center justify-center rounded-card bg-surface"
            style={{ boxShadow: `var(${name})` }}
          >
            <span className="font-mono text-step-n2">{name.replace("--", "")}</span>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ------------------------------------------------------------------------------- buttons

const VARIANT_NOTES: Array<[ButtonVariant, string]> = [
  ["primary", "Primary: the one main action on a view"],
  ["secondary", "Secondary"],
  ["ghost", "Ghost: low-emphasis and toolbar actions"],
  ["destructive", "Destructive: clay, never maroon"],
];

const STATES: Array<{ label: string; forced?: ForcedState; disabled?: boolean }> = [
  { label: "Rest" },
  { label: "Hover", forced: "hover" },
  { label: "Active", forced: "active" },
  { label: "Focus", forced: "focus" },
  { label: "Disabled", disabled: true },
];

function ButtonSection() {
  return (
    <Section
      id="buttons"
      title="Buttons"
      intro="Each variant in every state, rendered statically for review. The last row is live."
    >
      <div className="space-y-6">
        {VARIANT_NOTES.map(([variant, note]) => (
          <div key={variant} className="space-y-3">
            <h3 className="text-step-1">{note}</h3>
            <div className="flex flex-wrap items-end gap-4">
              {STATES.map((state) => (
                <div key={state.label} className="flex flex-col items-start gap-2">
                  <Button variant={variant} forcedState={state.forced} disabled={state.disabled}>
                    Save plan
                  </Button>
                  <span className="text-step-n2 text-fg-muted">{state.label}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
        <div className="space-y-3">
          <h3 className="text-step-1">Live</h3>
          <div className="flex flex-wrap gap-4">
            {VARIANT_NOTES.map(([variant]) => (
              <Button key={variant} variant={variant}>
                {variant[0].toUpperCase() + variant.slice(1)}
              </Button>
            ))}
          </div>
        </div>
      </div>
    </Section>
  );
}

// ------------------------------------------------------------------------------- card & input

function CardSection() {
  return (
    <Section
      id="card"
      title="Card"
      intro="cream-50 surface, cream-200 hairline, resting shadow, 8px radius, 24px padding. Example content only."
    >
      <Card className="max-w-md space-y-4">
        <div className="space-y-1">
          <p className="text-step-n2 font-medium tracking-wide text-fg-muted uppercase">
            Example product
          </p>
          <h3 className="text-step-2">Dry fruit gift box</h3>
        </div>
        <p className="figure text-step-4 font-semibold">{rupees.format(847320)}</p>
        <p className="text-step-n1 text-fg-muted">
          Revenue, last 4 weeks · <span className="figure text-positive">+6.2%</span> vs last year
        </p>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Badge tone="warning">Peak in 3 weeks</Badge>
          <Button variant="secondary">View forecast</Button>
        </div>
      </Card>
    </Section>
  );
}

function InputSection() {
  return (
    <Section
      id="inputs"
      title="Input"
      intro="ink-400 border (3:1 against the background, enough for a control outline), maroon focus ring, clay for errors."
    >
      <div className="grid max-w-3xl gap-6 md:grid-cols-2">
        <Input label="Default" placeholder="e.g. 1,200" hint="Units per week" />
        <Input label="Focus" defaultValue="1,200" forcedState="focus" hint="Shown statically" />
        <Input label="Disabled" defaultValue="1,200" disabled hint="Locked by the plan" />
        <Input label="Invalid" defaultValue="12.5" error="Enter a whole number of units." />
      </div>
    </Section>
  );
}
