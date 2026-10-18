-- Apply Action and BusTask model constraints/indexes to existing PostgreSQL databases.
-- CREATE INDEX CONCURRENTLY requires this script to run outside a transaction block.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_action_name_not_blank'
          AND conrelid = 'public.t_busi_action'::regclass
    ) THEN
        ALTER TABLE public.t_busi_action
            ADD CONSTRAINT ck_action_name_not_blank
            CHECK (length(trim(ba_action)) > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_action_http_method'
          AND conrelid = 'public.t_busi_action'::regclass
    ) THEN
        ALTER TABLE public.t_busi_action
            ADD CONSTRAINT ck_action_http_method
            CHECK (
                ba_api_method IS NULL OR ba_api_method IN
                ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_task_status'
          AND conrelid = 'public.t_crawl_task'::regclass
    ) THEN
        ALTER TABLE public.t_crawl_task
            ADD CONSTRAINT ck_task_status
            CHECK (status IN ('pending', 'running', 'paused', 'done', 'failed'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_task_attempts_non_negative'
          AND conrelid = 'public.t_crawl_task'::regclass
    ) THEN
        ALTER TABLE public.t_crawl_task
            ADD CONSTRAINT ck_task_attempts_non_negative
            CHECK (attempts >= 0);
    END IF;
END
$$;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_action_platform_enabled
    ON public.t_busi_action (bs_id, ba_enabled);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_ready
    ON public.t_crawl_task (status, next_run_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_platform_status
    ON public.t_crawl_task (platform, status);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_action_id
    ON public.t_crawl_task (ba_id);
