import { Link, Outlet } from "react-router";

import { useAuth } from "../auth/auth-context";
import { Wordmark } from "./brand/Wordmark";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";

/** The signed-in frame: who you are and a way out. No navigation until a phase asks for it. */
export function AppLayout() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <Link to="/app/dashboard" aria-label="Meridian dashboard">
            <Wordmark size="sm" />
          </Link>
          <div className="flex items-center gap-3">
            <span className="hidden text-step-n1 text-fg sm:inline">{user?.full_name}</span>
            {user && <Badge>{user.role}</Badge>}
            <Button variant="ghost" size="sm" onClick={() => void logout()}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
