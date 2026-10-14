import { useMemo, useState } from "react";

import type { Column, Pagination, SortState } from "./table-types";

const collator = new Intl.Collator("en-IN", { numeric: true, sensitivity: "base" });

function compare(a: string | number | null, b: string | number | null): number {
  if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1; // empty last
  if (typeof a === "number" && typeof b === "number") return a - b;
  return collator.compare(String(a), String(b));
}

/**
 * Sorting and paging done in the browser, for rows that are all loaded already. Spread
 * the result into <DataTable>. Server-paged data passes `sort`, `onSortChange` and
 * `pagination` from its query instead, and DataTable does not change.
 */
export function useClientTable<Row>({
  rows,
  columns,
  pageSize,
  initialSort = null,
}: {
  rows: Row[];
  columns: Column<Row>[];
  pageSize: number;
  initialSort?: SortState | null;
}): {
  rows: Row[];
  sort: SortState | null;
  onSortChange: (sort: SortState) => void;
  pagination: Pagination;
} {
  const [sort, setSort] = useState<SortState | null>(initialSort);
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    const column = sort ? columns.find((c) => c.key === sort.key) : undefined;
    if (!sort || !column) return rows;
    const factor = sort.direction === "asc" ? 1 : -1;
    // Empty values stay last in both directions.
    return [...rows].sort((a, b) => {
      const va = column.value(a);
      const vb = column.value(b);
      if (va === null || vb === null) return compare(va, vb);
      return factor * compare(va, vb);
    });
  }, [rows, columns, sort]);

  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, pageCount - 1);
  return {
    rows: sorted.slice(current * pageSize, (current + 1) * pageSize),
    sort,
    onSortChange: (next) => {
      setSort(next);
      setPage(0);
    },
    pagination: { page: current, pageSize, totalRows: rows.length, onPageChange: setPage },
  };
}
