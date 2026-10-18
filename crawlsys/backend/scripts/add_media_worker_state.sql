CREATE TABLE IF NOT EXISTS public.t_video_clean_cursor (
    id BIGSERIAL PRIMARY KEY,
    consumer_key VARCHAR(128) NOT NULL,
    platform VARCHAR(50) NOT NULL,
    policy_hash VARCHAR(64) NOT NULL,
    watermark_ts TIMESTAMP NOT NULL,
    watermark_id BIGINT NOT NULL DEFAULT 0,
    updated_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_video_clean_cursor_consumer_platform
    ON public.t_video_clean_cursor (consumer_key, platform);

ALTER TABLE public.t_material_clean
    ADD COLUMN IF NOT EXISTS download_claim_token VARCHAR(64);
ALTER TABLE public.t_material_clean
    ADD COLUMN IF NOT EXISTS download_claimed_at TIMESTAMP;
ALTER TABLE public.t_material_clean
    ADD COLUMN IF NOT EXISTS download_attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.t_material_clean
    ADD COLUMN IF NOT EXISTS download_next_retry_at TIMESTAMP;
ALTER TABLE public.t_material_clean
    ADD COLUMN IF NOT EXISTS download_last_error TEXT;

CREATE INDEX IF NOT EXISTS idx_mc_download_claim
    ON public.t_material_clean (
        clean_status,
        download_next_retry_at,
        download_claimed_at,
        download_attempt_count
    );
