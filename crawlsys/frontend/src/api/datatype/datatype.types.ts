export interface DatatypeColumnMeta {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
  comment: string | null;
}

export interface DatatypeDtoFieldMeta {
  name: string;
  target: string;
  required: boolean;
  value_types: string[];
  description: string | null;
}

export interface DatatypeItem {
  datatype_id: number;
  datatype_key: string;
  table_name: string;
  model_name: string;
  description: string | null;
  unique_field: string | null;
  update_fields: string[];
  columns: DatatypeColumnMeta[];
  dto_fields: DatatypeDtoFieldMeta[];
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface DatatypeListResponse {
  items: DatatypeItem[];
  total: number;
}

export interface DatatypeSyncResponse {
  success: boolean;
  synced_count: number;
  datatypes: string[];
}

export type DatatypeValueType =
  | "string"
  | "integer"
  | "number"
  | "boolean"
  | "datetime"
  | "json"
  | "binary";

export interface DatatypeRowColumn {
  name: string;
  sql_type: string;
  value_type: DatatypeValueType;
  nullable: boolean;
  primary_key: boolean;
  comment: string | null;
  max_length: number | null;
  editable: boolean;
  required: boolean;
}

export interface DatatypeRowsMeta {
  datatype_key: string;
  table_name: string;
  model_name: string;
  description: string | null;
  unique_field: string | null;
  pk_columns: string[];
  columns: DatatypeRowColumn[];
}

/** 行记录以列名为键；值可能是任意 JSON 标量或结构化值。 */
export type DatatypeRow = Record<string, unknown>;

export type DatatypeRowFilterOperator =
  | "eq"
  | "ne"
  | "contains"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "is_null";

export interface DatatypeRowFilter {
  field: string;
  operator: DatatypeRowFilterOperator;
  value: unknown;
}

export interface DatatypeRowPage {
  items: DatatypeRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface DatatypeRowPayload {
  values: Record<string, unknown>;
}

export interface DatatypeRowResponse {
  item: DatatypeRow;
}
