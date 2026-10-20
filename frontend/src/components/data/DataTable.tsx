import type { KeyboardEvent, ReactNode } from "react";

import { cn } from "../../lib/cn";
import { errorMessage, formatInteger } from "../../lib/format";
import { ChevronIcon, SortIcon } from "../brand/icons";
import { EmptyState } from "../feedback/EmptyState";
import { ErrorState } from "../feedback/ErrorState";
import { Skeleton } from "../feedback/Skeleton";
import { Button } from "../ui/Button";
import type { Column, Pagination, SortState } from "./table-types";

export type { Column, Pagination, SortDirection, SortState } from "./table-types";

export interface DataTableProps<Row> {
  /** Names the table for screen readers (visually hidden). */
  caption: string;
  columns: Column<Row>[];
  /** The rows to show now: one page when paginated. */
  rows: Row[];
  rowKey: (row: Row) => string;
  sort?: SortState | null;
  /** Without it, no header is sortable. */
  onSortChange?: (sort: SortState) => void;
  /** Without it, every row shows and there are no paging controls. */
  pagination?: Pagination;
  /** Makes rows clickable, and focusable: Enter or Space opens them too. */
  onRowClick?: (row: Row) => void;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyMessage?: ReactNode;
  /**
   * Cap the height and scroll inside (default), keeping the header in view. Pass false
   * for short tables that read better at full length.
   */
  capHeight?: boolean;
}

const CELL = "border-b border-line px-4 py-3";

/**
 * Sortable, paginated rows with a sticky header. Numbers are right-aligned in tabular
 * figures. Sorting and paging are controlled: pair it with useClientTable for local rows
 * or with a query's state for server-paged ones.
 */
export function DataTable<Row>({
  caption,
  columns,
  rows,
  rowKey,
  sort,
  onSortChange,
  pagination,
  onRowClick,
  isLoading,
  error,
  onRetry,
  emptyTitle = "No rows to show",
  emptyMessage = "Nothing matches the current filters.",
  capHeight = true,
}: DataTableProps<Row>) {
  const state = isLoading ? "loading" : error ? "error" : rows.length === 0 ? "empty" : "ready";
  const skeletonRows = Math.min(pagination?.pageSize ?? 5, 8);

  const toggleSort = (column: Column<Row>) => {
    if (!onSortChange) return;
    const direction =
      sort?.key === column.key
        ? sort.direction === "asc"
          ? "desc"
          : "asc"
        : column.numeric
          ? "desc"
          : "asc";
    onSortChange({ key: column.key, direction });
  };

  const onRowKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, row: Row) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onRowClick?.(row);
    }
  };

  return (
    <div className="overflow-hidden rounded-card border border-line bg-surface shadow-rest">
      {state === "loading" && (
        <p role="status" className="sr-only">
          Loading {caption}
        </p>
      )}
      {/* relative: absolutely positioned content in a cell (screen-reader text, a tooltip)
          is contained and scrolls with the table instead of widening the page. */}
      <div className={cn("relative overflow-auto", capHeight && "max-h-scroll-table")}>
        <table className="w-full border-separate border-spacing-0 text-step-n1">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {columns.map((column) => {
                const active = sort?.key === column.key ? sort.direction : null;
                const sortable = column.sortable && onSortChange;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={
                      active === "asc" ? "ascending" : active === "desc" ? "descending" : undefined
                    }
                    className={cn(
                      "sticky top-0 z-10 border-b border-line bg-surface-muted px-4 py-3 font-medium whitespace-nowrap text-fg-muted normal-nums",
                      column.numeric ? "text-right" : "text-left",
                    )}
                  >
                    {sortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column)}
                        className={cn(
                          "-mx-1 inline-flex items-center gap-1 rounded-control px-1 hover:text-fg",
                          column.numeric && "flex-row-reverse",
                          active && "text-fg",
                        )}
                      >
                        {column.header}
                        <SortIcon
                          direction={active}
                          className={cn("size-4", active ? "text-fg" : "text-fg-subtle")}
                        />
                      </button>
                    ) : (
                      column.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {state === "loading" &&
              Array.from({ length: skeletonRows }, (_, i) => (
                <tr key={i} aria-hidden>
                  {columns.map((column) => (
                    <td key={column.key} className={CELL}>
                      <Skeleton className={cn("h-4", column.numeric ? "ml-auto w-16" : "w-24")} />
                    </td>
                  ))}
                </tr>
              ))}
            {state === "ready" &&
              rows.map((row) => (
                <tr
                  key={rowKey(row)}
                  tabIndex={onRowClick ? 0 : undefined}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={onRowClick ? (event) => onRowKeyDown(event, row) : undefined}
                  className={cn(
                    onRowClick &&
                      "cursor-pointer hover:bg-surface-muted focus-visible:bg-surface-muted focus-visible:-outline-offset-2",
                  )}
                >
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      // Text cells drop the table's tabular figures, which would widen the
                      // hyphen in "FX-015" or "Non-stick" to a digit's width.
                      className={cn(
                        CELL,
                        "text-fg",
                        column.numeric ? "text-right figure" : "normal-nums",
                      )}
                    >
                      {column.render ? column.render(row) : column.value(row)}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {/* Below the scrolling table, not in a full-width cell, so on a phone the message
          sits in view instead of centred across columns scrolled out of sight. */}
      {state === "error" && (
        <ErrorState
          title={`Couldn’t load ${caption.toLowerCase()}`}
          message={errorMessage(error)}
          onRetry={onRetry}
        />
      )}
      {state === "empty" && <EmptyState title={emptyTitle} description={emptyMessage} />}
      {pagination && state === "ready" && <PageControls {...pagination} />}
    </div>
  );
}

function PageControls({ page, pageSize, totalRows, onPageChange }: Pagination) {
  const pageCount = Math.max(1, Math.ceil(totalRows / pageSize));
  const first = page * pageSize + 1;
  const last = Math.min(totalRows, (page + 1) * pageSize);
  return (
    <nav
      aria-label="Pagination"
      className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-step-n1 text-fg-muted"
    >
      <p>
        Rows <span className="figure">{formatInteger(first)}</span>–
        <span className="figure">{formatInteger(last)}</span> of{" "}
        <span className="figure">{formatInteger(totalRows)}</span>
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          disabled={page === 0}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronIcon direction="left" className="size-4" />
          Previous
        </Button>
        <span>
          Page <span className="figure">{formatInteger(page + 1)}</span> of{" "}
          <span className="figure">{formatInteger(pageCount)}</span>
        </span>
        <Button
          variant="ghost"
          size="sm"
          disabled={page >= pageCount - 1}
          onClick={() => onPageChange(page + 1)}
        >
          Next
          <ChevronIcon direction="right" className="size-4" />
        </Button>
      </div>
    </nav>
  );
}
