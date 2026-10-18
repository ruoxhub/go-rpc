-- Persist ORM models and datatypes metadata in PostgreSQL.

BEGIN;

CREATE TABLE IF NOT EXISTS public.t_sys_datatype (
    datatype_id SERIAL PRIMARY KEY,
    datatype_key VARCHAR(64) NOT NULL UNIQUE,
    table_name VARCHAR(128) NOT NULL,
    model_name VARCHAR(128) NOT NULL,
    description VARCHAR(512),
    unique_field VARCHAR(64),
    update_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    columns JSONB NOT NULL DEFAULT '[]'::jsonb,
    dto_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sys_datatype_active ON public.t_sys_datatype (is_active);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_datatype_key ON public.t_sys_datatype (datatype_key);

COMMIT;
