import type { ButtonHTMLAttributes } from "react";

import { cn } from "../../lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";
/** Styleguide only: render an interaction state statically so it can be reviewed. */
export type ForcedState = "hover" | "active" | "focus";

const BASE = cn(
  "inline-flex h-10 items-center justify-center gap-2 rounded-control px-4 text-step-n1 font-medium whitespace-nowrap transition-colors",
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
  "data-force-focus:outline-2 data-force-focus:outline-offset-2 data-force-focus:outline-focus",
  "active:translate-y-px data-force-active:translate-y-px",
  "disabled:translate-y-0 disabled:cursor-not-allowed disabled:text-fg-subtle",
);

// Maroon is the primary action. Destructive actions are clay: maroon never means "bad".
const VARIANTS: Record<ButtonVariant, string> = {
  primary: cn(
    "bg-primary text-on-primary shadow-rest",
    "hover:bg-primary-hover data-force-hover:bg-primary-hover",
    "active:bg-primary-active data-force-active:bg-primary-active",
    "disabled:bg-surface-muted disabled:shadow-none",
  ),
  secondary: cn(
    "border border-primary bg-surface text-primary",
    "hover:bg-primary-subtle data-force-hover:bg-primary-subtle",
    "active:border-primary-active active:bg-primary-subtle active:text-primary-active",
    "data-force-active:border-primary-active data-force-active:bg-primary-subtle data-force-active:text-primary-active",
    "disabled:border-line disabled:bg-surface",
  ),
  ghost: cn(
    "text-fg",
    "hover:bg-surface-muted data-force-hover:bg-surface-muted",
    "active:bg-line data-force-active:bg-line",
    "disabled:bg-transparent",
  ),
  destructive: cn(
    "bg-negative text-on-primary shadow-rest",
    "hover:bg-negative-hover data-force-hover:bg-negative-hover",
    "active:bg-negative-hover data-force-active:bg-negative-hover",
    "disabled:bg-surface-muted disabled:shadow-none",
  ),
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  forcedState?: ForcedState;
}

export function Button({
  variant = "primary",
  forcedState,
  className,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      data-force-hover={forcedState === "hover" || undefined}
      data-force-active={forcedState === "active" || undefined}
      data-force-focus={forcedState === "focus" || undefined}
      className={cn(BASE, VARIANTS[variant], className)}
      {...props}
    />
  );
}
