import { EmptyState } from "../../components/feedback/EmptyState";
import { PageScaffold } from "../../components/shell/PageScaffold";
import { Card } from "../../components/ui/Card";

export default function Dashboard() {
  return (
    <PageScaffold title="Dashboard" subtitle="How each product is selling, and where.">
      <Card>
        <EmptyState
          title="No sales figures yet"
          description="Sales KPIs and trends by product, region and channel will appear here."
        />
      </Card>
    </PageScaffold>
  );
}
