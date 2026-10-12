import { lazy, Suspense } from "react";

const Styleguide = lazy(() => import("./Styleguide"));

/** The styleguide is a review tool: lazy, so it stays out of the main bundle. */
export function LazyStyleguide() {
  return (
    <Suspense fallback={null}>
      <Styleguide />
    </Suspense>
  );
}
