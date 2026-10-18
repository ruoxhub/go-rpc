DO $$
BEGIN
    IF to_regclass('public.t_llm_provider') IS NULL THEN
        RETURN;
    END IF;

    ALTER TABLE public.t_llm_provider
        DROP CONSTRAINT IF EXISTS provider_protocol_enum;

    UPDATE public.t_llm_provider
    SET protocol = CASE protocol
        WHEN 'openai_compatible' THEN 'openai-completion'
        WHEN 'native_anthropic' THEN 'claude'
        WHEN 'native_gemini' THEN 'gemini'
        ELSE protocol
    END;

    UPDATE public.t_llm_provider
    SET litellm_prefix = CASE protocol
        WHEN 'openai-completion' THEN 'openai'
        WHEN 'openai-responses' THEN 'responses/openai'
        WHEN 'claude' THEN 'anthropic'
        WHEN 'gemini' THEN 'gemini'
        WHEN 'deepseek' THEN 'deepseek'
    END;

    UPDATE public.t_llm_model AS model
    SET litellm_model = provider.litellm_prefix || '/' || model.remote_model_id
    FROM public.t_llm_provider AS provider
    WHERE provider.id = model.provider_id;

    ALTER TABLE public.t_llm_provider
        ADD CONSTRAINT provider_protocol_enum CHECK (
            protocol IN (
                'openai-completion', 'claude', 'gemini',
                'deepseek', 'openai-responses'
            )
        );
END
$$;
