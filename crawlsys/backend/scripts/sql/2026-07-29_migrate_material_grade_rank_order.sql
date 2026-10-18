UPDATE public.t_material_clean
SET grade_rank = CASE grade_rank
    WHEN 1 THEN 3
    WHEN 3 THEN 1
    ELSE grade_rank
END
WHERE grade_rank IN (1, 3);

COMMENT ON COLUMN public.t_material_clean.grade_rank
    IS '评级等级：P1=1、P2=2、P3=3、人工审核=-1';
