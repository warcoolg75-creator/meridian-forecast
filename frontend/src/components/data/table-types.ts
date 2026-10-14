import type { ReactNode } from "react";

export interface Column<Row> {
  key: string;
  header: string;
  /** The cell's value: shown when there is no `render`, and what sorting compares. */
  value: (row: Row) => string | number | null;
  /** Custom cell content, e.g. a formatted figure or a badge. */
  render?: (row: Row) => ReactNode;
  /** Right-aligned with tabular figures, and sorted largest first on the first click. */
  numeric?: boolean;
  sortable?: boolean;
}

export type SortDirection = "asc" | "desc";

export interface SortState {
  key: string;
  direction: SortDirection;
}

export interface Pagination {
  /** Zero-based. */
  page: number;
  pageSize: number;
  /** Rows across all pages. */
  totalRows: number;
  onPageChange: (page: number) => void;
}
