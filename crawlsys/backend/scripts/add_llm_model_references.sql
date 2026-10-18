ALTER TABLE public.t_video_analysis_result
    ADD COLUMN IF NOT EXISTS llm_model_id INTEGER;

ALTER TABLE public.t_video_analysis_result
    ALTER COLUMN model TYPE VARCHAR(500);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_video_analysis_llm_model'
          AND conrelid = 'public.t_video_analysis_result'::regclass
    ) THEN
        ALTER TABLE public.t_video_analysis_result
            ADD CONSTRAINT fk_video_analysis_llm_model
            FOREIGN KEY (llm_model_id) REFERENCES public.t_llm_model (id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_video_analysis_llm_model_id
    ON public.t_video_analysis_result (llm_model_id);
