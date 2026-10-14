import { EmptyState } from "../../components/feedback/EmptyState";
import { PageScaffold } from "../../components/shell/PageScaffold";
import { Card } from "../../components/ui/Card";

export default function Forecast() {
  return (
    <PageScaffold title="Forecast" subtitle="Expected demand for the next 1 to 26 weeks.">
      <Card>
        <EmptyState
          title="No forecast yet"
          description="Demand forecasts, with their confidence ranges and peak-season warnings, will appear here."
        />
      </Card>
    </PageScaffold>
  );
}
