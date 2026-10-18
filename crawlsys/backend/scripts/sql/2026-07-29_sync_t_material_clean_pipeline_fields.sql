ALTER TABLE public.t_material_clean
    ADD COLUMN IF NOT EXISTS datatype VARCHAR(10);

UPDATE public.t_material_clean
SET datatype = 'clean'
WHERE datatype IS NULL OR datatype = '';

ALTER TABLE public.t_material_clean
    ALTER COLUMN datatype SET DEFAULT 'clean',
    ALTER COLUMN datatype SET NOT NULL,
    DROP COLUMN IF EXISTS source_id,
    DROP COLUMN IF EXISTS title,
    DROP COLUMN IF EXISTS url;

COMMENT ON COLUMN public.t_material_clean.datatype
    IS 'Pipeline 数据类型标识';
