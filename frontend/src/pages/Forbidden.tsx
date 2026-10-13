import { Link } from "react-router";

import type { Role } from "../auth/types";

export default function Forbidden({ role }: { role: Role }) {
  return (
    <main className="mx-auto max-w-5xl space-y-3 px-4 py-12 sm:px-6">
      <h1 className="text-step-4">You don’t have access to this page</h1>
      <p className="text-fg-muted">
        Your role ({role}) can’t open it. Ask an admin if you need access.
      </p>
      <Link
        to="/app/dashboard"
        className="inline-block text-primary underline-offset-4 hover:underline"
      >
        Back to the dashboard
      </Link>
    </main>
  );
}
