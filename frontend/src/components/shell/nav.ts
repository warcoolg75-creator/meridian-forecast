import type { ReactNode } from "react";

import { PLANNING_ROLES } from "../../auth/roles";
import type { Role } from "../../auth/types";
import { cn } from "../../lib/cn";
import {
  DashboardIcon,
  ForecastIcon,
  MarketIcon,
  PlanningIcon,
  ProductsIcon,
} from "../brand/icons";

export interface NavItem {
  to: string;
  label: string;
  icon: (props: { className?: string }) => ReactNode;
  /** Only these roles see the item. Unset: everyone signed in. Mirror the route guard. */
  roles?: Role[];
}

/** The app's sections, in sidebar order. */
export const NAV_ITEMS: NavItem[] = [
  { to: "/app/dashboard", label: "Dashboard", icon: DashboardIcon },
  { to: "/app/products", label: "Products", icon: ProductsIcon },
  { to: "/app/forecast", label: "Forecast", icon: ForecastIcon },
  { to: "/app/market", label: "Market", icon: MarketIcon },
  { to: "/app/planning", label: "Planning", icon: PlanningIcon, roles: PLANNING_ROLES },
];

export function navItemsFor(role: Role | undefined): NavItem[] {
  return NAV_ITEMS.filter(
    (item) => !item.roles || (role !== undefined && item.roles.includes(role)),
  );
}

/** Sidebar: icons only from 768 to 1023px (and from 1024 when collapsed). Drawer: always labelled. */
export type NavListMode = "sidebar" | "drawer";

// Shown beside an icon-only item on hover and keyboard focus. Screen readers get the
// label itself, which stays in the DOM as sr-only.
const TOOLTIP = cn(
  "pointer-events-none absolute left-full z-30 ml-3 hidden rounded-control bg-ink-900 px-2 py-1 text-step-n2 font-medium whitespace-nowrap text-cream-50 shadow-raised",
);

/** Classes that hide a label and show its tooltip wherever the sidebar is icons-only. */
export function railClasses(mode: NavListMode, collapsed: boolean) {
  if (mode === "drawer") return { label: cn("truncate"), tooltip: cn("hidden") };
  return {
    label: cn("truncate md:max-lg:sr-only", collapsed && "lg:sr-only"),
    tooltip: cn(
      TOOLTIP,
      "md:max-lg:group-hover:block md:max-lg:group-focus-visible:block",
      collapsed && "lg:group-hover:block lg:group-focus-visible:block",
    ),
  };
}
