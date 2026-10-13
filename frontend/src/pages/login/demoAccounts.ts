/**
 * The `make seed` demo users (see the README). Development builds only: Vite replaces
 * import.meta.env.DEV with false in a production build, so this list, and the public
 * demo password with it, is dropped from the bundle.
 */
export interface DemoAccount {
  label: string;
  email: string;
  password: string;
}

const DEMO_PASSWORD = "meridian-demo-2026";

export const DEMO_ACCOUNTS: DemoAccount[] = import.meta.env.DEV
  ? [
      { label: "Admin", email: "admin@meridian.demo", password: DEMO_PASSWORD },
      { label: "Planner", email: "planner@meridian.demo", password: DEMO_PASSWORD },
      { label: "Analyst", email: "analyst@meridian.demo", password: DEMO_PASSWORD },
      { label: "Viewer", email: "viewer@meridian.demo", password: DEMO_PASSWORD },
    ]
  : [];
