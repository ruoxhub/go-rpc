-- Persist Action parser samples and versioned definitions in PostgreSQL.

BEGIN;

ALTER TABLE public.t_busi_action
    ADD COLUMN IF NOT EXISTS ba_sample_safe BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS public.t_busi_action_parser_sample (
    sample_id SERIAL PRIMARY KEY,
    ba_id INTEGER NOT NULL,
    request_params_redacted JSONB NOT NULL,
    request_params_hmac_sha256 VARCHAR(64) NOT NULL,
    request_hmac_key_version VARCHAR(32) NOT NULL,
    raw_object_key VARCHAR(512) NOT NULL UNIQUE,
    redacted_object_key VARCHAR(512) NOT NULL UNIQUE,
    response_sha256 VARCHAR(64) NOT NULL,
    response_bytes INTEGER NOT NULL,
    sanitizer_version VARCHAR(32) NOT NULL,
    rpc_duration_ms INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    CONSTRAINT fk_action_parser_sample_action
        FOREIGN KEY (ba_id)
        REFERENCES public.t_busi_action(ba_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS public.t_busi_action_parser_revision (
    revision_id SERIAL PRIMARY KEY,
    ba_id INTEGER NOT NULL,
    revision_no INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL,
    definition JSONB NOT NULL,
    definition_sha256 VARCHAR(64) NOT NULL,
    source VARCHAR(16) NOT NULL,
    source_sample_id INTEGER,
    restored_from_revision_id INTEGER,
    validation_report JSONB,
    lock_version INTEGER NOT NULL DEFAULT 1,
    generation_metadata JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    published_at TIMESTAMP WITHOUT TIME ZONE,
    CONSTRAINT uq_action_parser_revision_number UNIQUE (ba_id, revision_no),
    CONSTRAINT ck_action_parser_revision_status
        CHECK (status IN ('draft', 'published', 'archived')),
    CONSTRAINT ck_action_parser_revision_source
        CHECK (source IN ('manual', 'ai', 'restore')),
    CONSTRAINT fk_action_parser_revision_action
        FOREIGN KEY (ba_id)
        REFERENCES public.t_busi_action(ba_id) ON DELETE RESTRICT,
    CONSTRAINT fk_action_parser_revision_source_sample
        FOREIGN KEY (source_sample_id)
        REFERENCES public.t_busi_action_parser_sample(sample_id) ON DELETE RESTRICT,
    CONSTRAINT fk_action_parser_revision_restored_from
        FOREIGN KEY (restored_from_revision_id)
        REFERENCES public.t_busi_action_parser_revision(revision_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS public.t_busi_action_parser_revision_sample (
    revision_id INTEGER NOT NULL,
    sample_id INTEGER NOT NULL,
    sample_sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    PRIMARY KEY (revision_id, sample_id),
    CONSTRAINT fk_action_parser_revision_sample_revision
        FOREIGN KEY (revision_id)
        REFERENCES public.t_busi_action_parser_revision(revision_id) ON DELETE CASCADE,
    CONSTRAINT fk_action_parser_revision_sample_sample
        FOREIGN KEY (sample_id)
        REFERENCES public.t_busi_action_parser_sample(sample_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_action_parser_sample_ba_id
    ON public.t_busi_action_parser_sample (ba_id);

CREATE INDEX IF NOT EXISTS idx_action_parser_revision_ba_id
    ON public.t_busi_action_parser_revision (ba_id);

CREATE INDEX IF NOT EXISTS idx_action_parser_revision_status
    ON public.t_busi_action_parser_revision (status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_action_parser_revision_draft_per_action
    ON public.t_busi_action_parser_revision (ba_id)
    WHERE status = 'draft';

CREATE UNIQUE INDEX IF NOT EXISTS uq_action_parser_revision_published_per_action
    ON public.t_busi_action_parser_revision (ba_id)
    WHERE status = 'published';

COMMIT;
