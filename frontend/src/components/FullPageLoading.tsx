import { Wordmark } from "./brand/Wordmark";

/** Shown while the start-up refresh decides whether there is a session. */
export function FullPageLoading() {
  return (
    <div role="status" className="flex min-h-screen items-center justify-center">
      <Wordmark className="animate-pulse motion-reduce:animate-none" />
      <span className="sr-only">Loading</span>
    </div>
  );
}
