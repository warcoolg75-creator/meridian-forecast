import { EmptyState } from "../../components/feedback/EmptyState";
import { PageScaffold } from "../../components/shell/PageScaffold";
import { Card } from "../../components/ui/Card";

export default function Products() {
  return (
    <PageScaffold title="Products" subtitle="Every product, with its sales history.">
      <Card>
        <EmptyState
          title="No products to show yet"
          description="The product catalogue and each product’s sales history will appear here."
        />
      </Card>
    </PageScaffold>
  );
}
