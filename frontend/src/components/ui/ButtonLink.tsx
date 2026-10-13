import type { ReactNode } from "react";
import { Link } from "react-router";

import { buttonClasses, type ButtonSize, type ButtonVariant } from "./button-styles";

type Target = { to: string; href?: never } | { href: string; to?: never };

/** Navigation that looks like a button: a router <Link> for routes, an <a> for anchors. */
export function ButtonLink({
  variant = "primary",
  size = "md",
  className,
  children,
  ...target
}: Target & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  children: ReactNode;
}) {
  const classes = buttonClasses(variant, size, className);
  if (target.to !== undefined) {
    return (
      <Link to={target.to} className={classes}>
        {children}
      </Link>
    );
  }
  return (
    <a href={target.href} className={classes}>
      {children}
    </a>
  );
}
