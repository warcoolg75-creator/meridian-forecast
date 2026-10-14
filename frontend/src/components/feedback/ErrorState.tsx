import { cn } from "../../lib/cn";
import { AlertIcon } from "../brand/icons";
import { Button } from "../ui/Button";

/**
 * Something failed to load. Clay, never maroon: maroon is the primary action, not "bad".
 * With `onRetry` it offers a retry; leave it out when retrying cannot help (a bug).
 */
export function ErrorState({
  title = "Couldn’t load this",
  message,
  onRetry,
  className,
}: {
  title?: string;
  /** What went wrong, in words the viewer can act on. */
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 px-4 py-8 text-center",
        className,
      )}
    >
      <AlertIcon className="size-8 text-negative" />
      <p className="font-medium text-fg">{title}</p>
      {message && <p className="max-w-sm text-step-n1 text-fg-muted">{message}</p>}
      {onRetry && (
        <div className="pt-2">
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </div>
  );
}
