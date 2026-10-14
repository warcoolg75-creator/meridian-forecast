import { useCallback, useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router";

import { NavDrawer } from "./NavDrawer";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { useSidebarCollapsed } from "./useSidebarCollapsed";

/**
 * The signed-in frame. Below 768px: a top bar whose hamburger opens the navigation
 * drawer. From 768px: a persistent sidebar, icons only up to 1023px, then full width
 * unless the viewer collapses it (remembered per browser). Pages render in <main>, each
 * inside a PageScaffold.
 *
 * After every navigation focus moves to <main> (named by the page's h1), as a full page
 * load would leave it. Left on the clicked nav link, focus would show its ring as soon
 * as any key was pressed (a screenshot shortcut is enough): browsers treat a key press
 * on a focused element as keyboard use, which turns :focus-visible on.
 */
export function AppLayout() {
  const [collapsed, setCollapsed] = useSidebarCollapsed();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);

  const location = useLocation();
  const main = useRef<HTMLElement>(null);
  // The key already handled: skips the first render (and StrictMode's second run of it),
  // so loading a page never moves focus.
  const handledKey = useRef(location.key);
  useEffect(() => {
    if (handledKey.current === location.key) return;
    handledKey.current = location.key;
    main.current?.focus({ preventScroll: true });
  }, [location.key]);

  return (
    <div className="flex min-h-screen">
      <a
        href="#main"
        className="sr-only rounded-control bg-primary px-4 py-2 text-step-n1 font-medium text-on-primary focus-visible:not-sr-only focus-visible:fixed focus-visible:top-2 focus-visible:left-2 focus-visible:z-50"
      >
        Skip to content
      </a>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <NavDrawer open={drawerOpen} onClose={closeDrawer} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar drawerOpen={drawerOpen} onOpenNav={() => setDrawerOpen(true)} />
        <main
          ref={main}
          id="main"
          tabIndex={-1}
          aria-labelledby="page-title"
          className="flex-1 focus-visible:outline-none"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
