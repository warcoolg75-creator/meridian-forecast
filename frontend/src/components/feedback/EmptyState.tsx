import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import { EmptyIcon } from "../brand/icons";

/**
 * Nothing to show, said plainly: what is missing and, when there is one, what to do
 * about it. Centred in whatever box it is given; pass that box's height via className
 * (e.g. `h-chart-md`) so the layout matches the populated state.
 */
export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description?: ReactNode;
  /** Usually a secondary or ghost Button: "Clear filters", "Import sales". */
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-4 py-8 text-center",
        className,
      )}
    >
      <EmptyIcon className="size-8 text-fg-subtle" />
      <p className="font-medium text-fg">{title}</p>
      {description && <p className="max-w-sm text-step-n1 text-fg-muted">{description}</p>}
      {action && <div className="pt-2">{action}</div>}
    </div>
  );
}
