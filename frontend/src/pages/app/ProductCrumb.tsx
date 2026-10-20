import { useProductDetail } from "../../api/analytics";

/** The breadcrumb's last step on a product page: its name, or its SKU while it loads. */
export function ProductCrumb({ sku }: { sku: string }) {
  const product = useProductDetail(sku);
  return <>{product.data?.name ?? sku}</>;
}
