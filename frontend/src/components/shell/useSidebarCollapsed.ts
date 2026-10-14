import { useCallback, useState } from "react";

/** Per viewer, per browser. A convenience only: losing it costs one click. */
export const SIDEBAR_STORAGE_KEY = "meridian.sidebar.collapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
  } catch {
    return false; // storage blocked (private window, site data off): expanded
  }
}

/**
 * Whether the desktop sidebar is collapsed to icons. Remembered in localStorage; every
 * access is guarded, because storage can be missing or throw, and then it is expanded.
 */
export function useSidebarCollapsed(): [boolean, (collapsed: boolean) => void] {
  const [collapsed, setState] = useState(readCollapsed);
  const setCollapsed = useCallback((value: boolean) => {
    setState(value);
    try {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(value));
    } catch {
      // Not remembered across reloads; the choice still holds for this page.
    }
  }, []);
  return [collapsed, setCollapsed];
}
