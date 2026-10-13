import { cn } from "../../lib/cn";

// Colours are token utilities (fill-*, stroke-*), so the design-token lint covers them.
const TONES = {
  // Maroon on cream: the landing-page hero.
  light: {
    grid: cn("stroke-line"),
    today: cn("stroke-maroon-300"),
    outer: cn("fill-maroon-100"),
    inner: cn("fill-maroon-300"),
    line: cn("stroke-primary"),
    dot: cn("fill-primary stroke-canvas"),
  },
  // Cream on deep maroon: the login panel, shown at low opacity.
  dark: {
    grid: cn("stroke-maroon-700"),
    today: cn("stroke-maroon-300"),
    outer: cn("fill-maroon-700"),
    inner: cn("fill-maroon-500"),
    line: cn("stroke-cream-50"),
    dot: cn("fill-cream-50 stroke-maroon-900"),
  },
};

const GRID_Y = [70, 150, 230, 310, 390];

/**
 * Decorative: a sales history that runs into today, then a dashed forecast whose
 * confidence band widens the further ahead it looks. Drawn tall (520 x 460) so it holds
 * its own beside a headline, with strokes heavy enough to read at hero size.
 */
export function ForecastArt({
  tone = "light",
  className,
}: {
  tone?: keyof typeof TONES;
  className?: string;
}) {
  const t = TONES[tone];
  return (
    <svg
      viewBox="0 0 520 460"
      aria-hidden="true"
      focusable="false"
      fill="none"
      className={cn("h-auto", className)}
    >
      {GRID_Y.map((y) => (
        <line key={y} x1="16" x2="504" y1={y} y2={y} strokeWidth="1.5" className={t.grid} />
      ))}

      {/* Confidence bands, 95% (outer) and 80% (inner), opening out from today. */}
      <path d="M270 230 Q390 160 496 30 L496 230 Q390 248 270 230 Z" className={t.outer} />
      <path
        d="M270 230 Q390 188 496 60 L496 180 Q390 224 270 230 Z"
        opacity="0.55"
        className={t.inner}
      />

      {/* Today. */}
      <line
        x1="270"
        x2="270"
        y1="40"
        y2="420"
        strokeWidth="2"
        strokeDasharray="3 8"
        strokeLinecap="round"
        className={t.today}
      />

      {/* History, with a weekly rhythm and a slow climb. */}
      <path
        d="M24 330 C40 314 50 302 60 300 S82 320 90 318 S118 284 130 282 S155 298 165 296 S195 260 205 258 S232 272 240 270 S262 240 270 230"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={t.line}
      />

      {/* Median forecast. */}
      <path
        d="M270 230 Q390 205 496 120"
        strokeWidth="4"
        strokeDasharray="2 11"
        strokeLinecap="round"
        className={t.line}
      />

      <circle cx="270" cy="230" r="7" strokeWidth="4" className={t.dot} />
    </svg>
  );
}
