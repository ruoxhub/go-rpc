CREATE TABLE IF NOT EXISTS public.t_material_clean (
    id              BIGSERIAL PRIMARY KEY,
    datatype        VARCHAR(10) NOT NULL DEFAULT 'clean',
    platform        VARCHAR(50) NOT NULL,
    content_id      VARCHAR(64) NOT NULL,
    grade_rank      INTEGER NOT NULL,
    grade_reason    TEXT,
    grade_time      TIMESTAMP NOT NULL,
    snap_view_count BIGINT,
    snap_pub_time   TIMESTAMP,
    snap_hours      DOUBLE PRECISION,
    clean_status    VARCHAR(16) NOT NULL DEFAULT 'graded',
    is_delete       SMALLINT NOT NULL DEFAULT 0,
    expire_time     TIMESTAMP NOT NULL,
    created_time    TIMESTAMP DEFAULT now(),
    updated_time    TIMESTAMP DEFAULT now(),
    CONSTRAINT uq_material_clean_platform_content
        UNIQUE (platform, content_id)
);

CREATE INDEX IF NOT EXISTS idx_mc_expire
    ON public.t_material_clean (expire_time);

CREATE INDEX IF NOT EXISTS idx_mc_grade_rank
    ON public.t_material_clean (grade_rank);
