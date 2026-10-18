ALTER TABLE public.t_material_clean
    ADD COLUMN IF NOT EXISTS is_analysis SMALLINT NOT NULL DEFAULT 0;

COMMENT ON COLUMN public.t_material_clean.is_analysis
    IS '分析状态：0=未分析，1=分析成功，2=分析中，3=分析失败';
