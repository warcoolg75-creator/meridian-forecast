import { Navigate, Outlet, useLocation } from "react-router";

import { FullPageLoading } from "../components/FullPageLoading";
import Forbidden from "../pages/Forbidden";
import { useAuth } from "./auth-context";
import type { Role } from "./types";

/**
 * Guard for /app routes. While the start-up refresh runs it shows a loading screen (no
 * flash of the login page); signed-out visitors go to /login, which returns them here
 * after sign-in; a role outside `roles` gets the "no access" page.
 */
export function RequireAuth({ roles }: { roles?: Role[] }) {
  const { status, user } = useAuth();
  const location = useLocation();
  if (status === "loading") return <FullPageLoading />;
  if (status === "anonymous" || !user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  if (roles && !roles.includes(user.role)) return <Forbidden role={user.role} />;
  return <Outlet />;
}
