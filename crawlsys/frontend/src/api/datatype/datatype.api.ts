import { crawlerRequest } from "../../utils/crawler/crawler-api";
import type {
  DatatypeItem,
  DatatypeListResponse,
  DatatypeRowFilter,
  DatatypeRowPage,
  DatatypeRowPayload,
  DatatypeRowResponse,
  DatatypeRowsMeta,
  DatatypeSyncResponse,
} from "./datatype.types";

export function getDatatypes(isActive?: boolean) {
  const query = isActive === undefined ? "" : `?is_active=${isActive}`;
  return crawlerRequest<DatatypeListResponse>(`/datatypes${query}`);
}

export function getDatatype(key: string) {
  return crawlerRequest<DatatypeItem>(`/datatypes/${encodeURIComponent(key)}`);
}

export function syncDatatypes() {
  return crawlerRequest<DatatypeSyncResponse>("/datatypes/sync", { method: "POST" });
}

export function updateDatatypeStatus(key: string, isActive: boolean) {
  return crawlerRequest<DatatypeItem>(
    `/datatypes/${encodeURIComponent(key)}/status`,
    { method: "PATCH", body: JSON.stringify({ is_active: isActive }) },
  );
}

export interface DatatypeRowQuery {
  page?: number;
  pageSize?: number;
  keyword?: string;
  sort?: string;
  order?: "asc" | "desc";
  filters?: DatatypeRowFilter[];
}

export function getDatatypeRowsMeta(key: string) {
  return crawlerRequest<DatatypeRowsMeta>(
    `/datatypes/${encodeURIComponent(key)}/rows/meta`,
  );
}

export function listDatatypeRows(key: string, query: DatatypeRowQuery = {}) {
  const params = new URLSearchParams();
  if (query.page !== undefined) params.set("page", String(query.page));
  if (query.pageSize !== undefined) params.set("page_size", String(query.pageSize));
  if (query.keyword) params.set("keyword", query.keyword);
  if (query.sort) params.set("sort", query.sort);
  if (query.order) params.set("order", query.order);
  if (query.filters && query.filters.length > 0) {
    params.set("filters", JSON.stringify(query.filters));
  }
  const encoded = params.toString();
  return crawlerRequest<DatatypeRowPage>(
    `/datatypes/${encodeURIComponent(key)}/rows${encoded ? `?${encoded}` : ""}`,
  );
}

function primaryKeyQuery(primaryKey: Record<string, unknown>) {
  return new URLSearchParams({ pk: JSON.stringify(primaryKey) });
}

export function createDatatypeRow(key: string, payload: DatatypeRowPayload) {
  return crawlerRequest<DatatypeRowResponse>(
    `/datatypes/${encodeURIComponent(key)}/rows`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function updateDatatypeRow(
  key: string,
  primaryKey: Record<string, unknown>,
  payload: DatatypeRowPayload,
) {
  return crawlerRequest<DatatypeRowResponse>(
    `/datatypes/${encodeURIComponent(key)}/rows?${primaryKeyQuery(primaryKey)}`,
    { method: "PUT", body: JSON.stringify(payload) },
  );
}

export function deleteDatatypeRow(
  key: string,
  primaryKey: Record<string, unknown>,
) {
  return crawlerRequest<{ deleted: boolean }>(
    `/datatypes/${encodeURIComponent(key)}/rows?${primaryKeyQuery(primaryKey)}`,
    { method: "DELETE" },
  );
}
