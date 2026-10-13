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

const GRID_Y = [60, 120, 180, 240, 300];

/**
 * Decorative: a sales history that runs into today, then a dashed forecast whose
 * confidence band widens the further ahead it looks.
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
      viewBox="0 0 560 340"
      aria-hidden="true"
      focusable="false"
      fill="none"
      className={cn("h-auto", className)}
    >
      {GRID_Y.map((y) => (
        <line key={y} x1="20" x2="540" y1={y} y2={y} strokeWidth="1" className={t.grid} />
      ))}

      {/* Confidence bands: 95% (outer) and 80% (inner), opening out from today. */}
      <path d="M300 170 Q420 130 520 40 L520 168 Q420 168 300 170 Z" className={t.outer} />
      <path
        d="M300 170 Q420 141 520 69 L520 139 Q420 158 300 170 Z"
        opacity="0.45"
        className={t.inner}
      />

      {/* Today. */}
      <line
        x1="300"
        x2="300"
        y1="30"
        y2="310"
        strokeWidth="1.5"
        strokeDasharray="3 7"
        strokeLinecap="round"
        className={t.today}
      />

      {/* History, with a weekly rhythm and a slow climb. */}
      <path
        d="M40 262 C55 250 65 242 80 240 S100 254 110 252 S135 224 150 222 S172 234 185 232 S208 202 220 200 S245 212 255 210 S285 178 300 170"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={t.line}
      />

      {/* Median forecast. */}
      <path
        d="M300 170 Q420 152 520 104"
        strokeWidth="3"
        strokeDasharray="2 9"
        strokeLinecap="round"
        className={t.line}
      />

      <circle cx="300" cy="170" r="6" strokeWidth="3" className={t.dot} />
    </svg>
  );
}
