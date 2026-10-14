import { EmptyState } from "../../components/feedback/EmptyState";
import { PageScaffold } from "../../components/shell/PageScaffold";
import { Card } from "../../components/ui/Card";

export default function Planning() {
  return (
    <PageScaffold title="Planning" subtitle="Turn the forecast into a production plan.">
      <Card>
        <EmptyState
          title="No production plan yet"
          description="Production plans built from the forecast will appear here."
        />
      </Card>
    </PageScaffold>
  );
}
