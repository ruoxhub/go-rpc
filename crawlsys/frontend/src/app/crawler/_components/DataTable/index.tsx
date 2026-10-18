import type { Key, ReactNode } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableCaption,
} from "@/app/_components/ui/table";

export interface DataTableColumn<T> {
  id: string;
  header: ReactNode;
  accessor?: keyof T | ((row: T) => ReactNode);
  render?: (row: T) => ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  caption: string;
  columns: DataTableColumn<T>[];
  rows: T[];
  getRowKey: (row: T) => Key;
  emptyText: string;
}

export function DataTable<T>({
  caption,
  columns,
  rows,
  getRowKey,
  emptyText,
}: DataTableProps<T>) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <Table>
        <TableCaption className="sr-only">{caption}</TableCaption>
        <TableHeader>
          <TableRow>
            {columns.map((column) => (
              <TableHead
                key={column.id}
                scope="col"
                className={column.className}
              >
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={columns.length}
                className="px-4 py-10 text-center text-muted-foreground"
              >
                {emptyText}
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row) => (
              <TableRow key={getRowKey(row)}>
                {columns.map((column) => (
                  <TableCell
                    key={column.id}
                    className={column.className}
                  >
                    {column.render
                      ? column.render(row)
                      : typeof column.accessor === "function"
                        ? column.accessor(row)
                        : column.accessor
                          ? String(row[column.accessor] ?? "")
                          : null}
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
