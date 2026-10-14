import { NavLink } from "react-router";

import { useAuth } from "../../auth/auth-context";
import { cn } from "../../lib/cn";
import { navItemsFor, railClasses, type NavListMode } from "./nav";

const LINK = cn(
  "group relative mx-2 flex h-10 items-center gap-3 rounded-control px-3 text-step-n1 font-medium transition-colors",
);
// The active item: a 2px maroon rule flush with the sidebar's left edge, and maroon text.
const ACTIVE = cn(
  "text-primary before:absolute before:inset-y-2 before:-left-2 before:border-l-2 before:border-primary",
);
const INACTIVE = cn("text-fg-muted hover:bg-line hover:text-fg");
/** The app's sections for the signed-in role: Planning only for admins and planners. */
export function NavList({
  mode,
  collapsed = false,
  onNavigate,
}: {
  mode: NavListMode;
  collapsed?: boolean;
  /** Called after a link is chosen, e.g. to close the drawer. */
  onNavigate?: () => void;
}) {
  const { user } = useAuth();
  const rail = railClasses(mode, collapsed);
  return (
    <nav aria-label="Main">
      <ul role="list" className="space-y-1 py-4">
        {navItemsFor(user?.role).map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              onClick={onNavigate}
              className={({ isActive }) => cn(LINK, isActive ? ACTIVE : INACTIVE)}
            >
              <Icon className="size-6 shrink-0" />
              <span className={rail.label}>{label}</span>
              <span aria-hidden className={rail.tooltip}>
                {label}
              </span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
