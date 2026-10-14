import { lazy, Suspense } from "react";

const Styleguide = lazy(() => import("./Styleguide"));
const Components = lazy(() => import("./Components"));

/** The styleguide is a review tool: lazy, so it stays out of the main bundle. */
export function LazyStyleguide() {
  return (
    <Suspense fallback={null}>
      <Styleguide />
    </Suspense>
  );
}

/** The component library in every state, on fixture data. Lazy, and Recharts with it. */
export function LazyComponents() {
  return (
    <Suspense fallback={null}>
      <Components />
    </Suspense>
  );
}
