import { useAuth } from "../../auth/auth-context";
import { MenuIcon } from "../brand/icons";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Breadcrumbs } from "./Breadcrumbs";

/** Where you are (breadcrumb), who you are (name and role) and the way out. */
export function TopBar({ drawerOpen, onOpenNav }: { drawerOpen: boolean; onOpenNav: () => void }) {
  const { user, logout } = useAuth();
  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b border-line bg-surface px-4 sm:px-6 lg:px-8">
      <button
        type="button"
        aria-label="Open navigation"
        aria-haspopup="dialog"
        aria-expanded={drawerOpen}
        onClick={onOpenNav}
        className="-ml-1 inline-flex size-8 shrink-0 items-center justify-center rounded-control text-fg hover:bg-surface-muted md:hidden"
      >
        <MenuIcon open={false} className="size-5" />
      </button>
      <Breadcrumbs className="flex-1" />
      <div className="flex shrink-0 items-center gap-3">
        <span className="hidden text-step-n1 text-fg sm:inline">{user?.full_name}</span>
        {user && <Badge>{user.role}</Badge>}
        <Button variant="ghost" size="sm" onClick={() => void logout()}>
          Sign out
        </Button>
      </div>
    </header>
  );
}
