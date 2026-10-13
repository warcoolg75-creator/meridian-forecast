import type { ReactNode } from "react";
import { Navigate, useLocation, type Location } from "react-router";

import { FullPageLoading } from "../components/FullPageLoading";
import { useAuth } from "./auth-context";

/**
 * For /login: a signed-in user goes to the page they were sent here from, or the
 * dashboard. This is also how a successful sign-in navigates away.
 */
export function RedirectIfSignedIn({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const from = (useLocation().state as { from?: Location } | null)?.from;
  if (status === "loading") return <FullPageLoading />;
  if (status === "authenticated") {
    const target = from ? `${from.pathname}${from.search}${from.hash}` : "/app/dashboard";
    return <Navigate to={target} replace />;
  }
  return children;
}
