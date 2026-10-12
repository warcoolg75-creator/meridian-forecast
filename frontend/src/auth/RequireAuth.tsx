import { Outlet } from "react-router";

/**
 * Guard for every /app route. PLACEHOLDER: it lets everyone through. Phase 2 replaces
 * the body with a real session check that redirects signed-out visitors to /login.
 */
export function RequireAuth() {
  return <Outlet />;
}
