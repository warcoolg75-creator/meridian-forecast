import { cn } from "../../lib/cn";

const TONES = {
  maroon: cn("text-primary"),
  cream: cn("text-cream-50"),
};

const SIZES = {
  sm: cn("text-step-0"),
  md: cn("text-step-1"),
};

/** "MERIDIAN" in the heading serif, letterspaced. */
export function Wordmark({
  tone = "maroon",
  size = "md",
  className,
}: {
  tone?: keyof typeof TONES;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "font-display font-semibold tracking-wordmark",
        TONES[tone],
        SIZES[size],
        className,
      )}
    >
      MERIDIAN
    </span>
  );
}
