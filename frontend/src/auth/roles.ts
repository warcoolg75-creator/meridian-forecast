import type { Role } from "./types";

/**
 * Who may open production planning: it changes the plan. Admins and planners only, as on
 * the API. The route guard (router.tsx) and the sidebar (shell/nav.ts) both read this.
 */
export const PLANNING_ROLES: Role[] = ["admin", "planner"];
