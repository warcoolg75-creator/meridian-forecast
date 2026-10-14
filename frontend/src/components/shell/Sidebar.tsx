import { Link } from "react-router";

import { cn } from "../../lib/cn";
import { isPointerClick } from "../../lib/pointer";
import { SidebarIcon } from "../brand/icons";
import { Wordmark } from "../brand/Wordmark";
import { railClasses } from "./nav";
import { NavList } from "./NavList";

/**
 * The persistent sidebar from 768px up: icons only below 1024px, full width above unless
 * the viewer collapsed it (remembered by AppLayout). Below 768px the drawer replaces it.
 */
export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const rail = railClasses("sidebar", collapsed);
  return (
    <aside
      id="app-sidebar"
      className={cn(
        "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-line bg-surface-muted md:flex md:w-16",
        collapsed ? "lg:w-16" : "lg:w-3xs",
      )}
    >
      <div className="flex h-16 shrink-0 items-center border-b border-line px-5">
        <Link to="/app/dashboard" aria-label="Meridian dashboard" className="rounded-control">
          <Wordmark size="sm" className={cn("md:max-lg:hidden", collapsed && "lg:hidden")} />
          <span
            aria-hidden
            className={cn(
              "hidden font-display text-step-1 font-semibold text-primary md:max-lg:inline",
              collapsed && "lg:inline",
            )}
          >
            M
          </span>
        </Link>
      </div>
      <NavList mode="sidebar" collapsed={collapsed} />
      <div className="mt-auto hidden border-t border-line py-2 lg:block">
        <button
          type="button"
          onClick={(event) => {
            onToggle();
            // Mouse users get no lingering focus to ring on a later key press.
            if (isPointerClick(event)) event.currentTarget.blur();
          }}
          aria-expanded={!collapsed}
          aria-controls="app-sidebar"
          className="group relative mx-2 flex h-10 items-center gap-3 rounded-control px-3 text-step-n1 font-medium text-fg-muted transition-colors hover:bg-line hover:text-fg"
        >
          <SidebarIcon collapsed={collapsed} className="size-6 shrink-0" />
          <span className={rail.label}>{collapsed ? "Expand sidebar" : "Collapse sidebar"}</span>
          <span aria-hidden className={rail.tooltip}>
            {collapsed ? "Expand sidebar" : "Collapse sidebar"}
          </span>
        </button>
      </div>
    </aside>
  );
}
