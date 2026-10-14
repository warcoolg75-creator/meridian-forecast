import { Link } from "react-router";

import type { Role } from "../auth/types";
import { PageScaffold } from "../components/shell/PageScaffold";

/** Inside the app frame, for a signed-in role a route does not admit. */
export default function Forbidden({ role }: { role: Role }) {
  return (
    <PageScaffold
      title="You don’t have access to this page"
      subtitle={`Your role (${role}) can’t open it. Ask an admin if you need access.`}
    >
      <Link
        to="/app/dashboard"
        className="inline-block text-primary underline-offset-4 hover:underline"
      >
        Back to the dashboard
      </Link>
    </PageScaffold>
  );
}
