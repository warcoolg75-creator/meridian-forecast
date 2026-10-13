import type { ButtonHTMLAttributes } from "react";

import {
  buttonClasses,
  type ButtonSize,
  type ButtonVariant,
  type ForcedState,
} from "./button-styles";

export type { ButtonSize, ButtonVariant, ForcedState } from "./button-styles";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  forcedState?: ForcedState;
}

export function Button({
  variant = "primary",
  size = "md",
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
      className={buttonClasses(variant, size, className)}
      {...props}
    />
  );
}
