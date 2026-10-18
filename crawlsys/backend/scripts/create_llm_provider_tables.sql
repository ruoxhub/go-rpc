CREATE TABLE IF NOT EXISTS public.t_llm_provider (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(100) NOT NULL UNIQUE,
    litellm_prefix   VARCHAR(100) NOT NULL,
    protocol         VARCHAR(32) NOT NULL,
    base_url         VARCHAR(2048),
    api_key          TEXT NOT NULL,
    enabled          BOOLEAN NOT NULL DEFAULT true,
    last_sync_status VARCHAR(32),
    last_sync_at     TIMESTAMP,
    last_sync_error  TEXT,
    created_at       TIMESTAMP NOT NULL DEFAULT now(),
    updated_at       TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT provider_protocol_enum CHECK (
        protocol IN (
            'openai-completion', 'claude', 'gemini',
            'deepseek', 'openai-responses'
        )
    )
);

COMMENT ON COLUMN public.t_llm_provider.api_key IS
    'Fernet credential token using the fernet:v1: prefix; legacy plaintext must be migrated';

CREATE INDEX IF NOT EXISTS idx_llm_provider_enabled
    ON public.t_llm_provider (enabled);

CREATE TABLE IF NOT EXISTS public.t_llm_model (
    id                 SERIAL PRIMARY KEY,
    provider_id        INTEGER NOT NULL,
    remote_model_id    VARCHAR(255) NOT NULL,
    litellm_model      VARCHAR(500) NOT NULL,
    display_name       VARCHAR(255) NOT NULL,
    enabled            BOOLEAN NOT NULL DEFAULT true,
    remote_available   BOOLEAN NOT NULL DEFAULT true,
    last_discovered_at TIMESTAMP,
    created_at         TIMESTAMP NOT NULL DEFAULT now(),
    updated_at         TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT fk_llm_model_provider
        FOREIGN KEY (provider_id) REFERENCES public.t_llm_provider (id),
    CONSTRAINT uq_llm_model_provider_remote_model
        UNIQUE (provider_id, remote_model_id)
);

CREATE INDEX IF NOT EXISTS idx_llm_model_provider_id
    ON public.t_llm_model (provider_id);

CREATE INDEX IF NOT EXISTS idx_llm_model_enabled
    ON public.t_llm_model (enabled);

CREATE INDEX IF NOT EXISTS idx_llm_model_remote_available
    ON public.t_llm_model (remote_available);
