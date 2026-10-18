-- Add ba_schema_source and ba_synced_at to public.t_busi_action.
-- ba_schema_source: 'synced' (default, synced from action catalog) or 'manual' (manually edited).
-- ba_synced_at: timestamp of last successful sync.

ALTER TABLE public.t_busi_action
    ADD COLUMN IF NOT EXISTS ba_schema_source VARCHAR(16) DEFAULT 'synced',
    ADD COLUMN IF NOT EXISTS ba_synced_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_action_schema_source'
          AND conrelid = 'public.t_busi_action'::regclass
    ) THEN
        ALTER TABLE public.t_busi_action
            ADD CONSTRAINT ck_action_schema_source
            CHECK (ba_schema_source IS NULL OR ba_schema_source IN ('synced', 'manual'));
    END IF;
END $$;
