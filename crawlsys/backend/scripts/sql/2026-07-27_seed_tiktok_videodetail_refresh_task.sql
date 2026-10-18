-- Seed TikTok videoDetail 7-day stats refresh loop task.
-- Idempotent via uq_task_platform_action (platform, action) + NOT EXISTS guard.
-- Resolves ba_id / platform_id from t_busi_action + t_busi_platform (bs_platform_code).

INSERT INTO public.t_crawl_task (
    platform,
    action,
    ba_id,
    platform_id,
    status,
    attempts,
    error_msg,
    config,
    loop_enabled,
    loop_interval_seconds,
    next_run_at
)
SELECT
    'tiktok',
    'videoDetail',
    a.ba_id,
    p.bs_id,
    'pending',
    0,
    NULL,
    jsonb_build_object(
        'source', jsonb_build_object(
            'table', 't_busi_content',
            'key_column', 'content_id',
            'param_map', jsonb_build_object('content_id', 'itemId'),
            'where', 'pub_time >= now() - interval ''7 days'' AND content_id IS NOT NULL',
            'order_by', jsonb_build_array('updated_time ASC', 'id ASC'),
            'limit', 50,
            'filter_by_platform', true
        ),
        'sink', jsonb_build_object(
            'mode', 'standard'
        )
    ),
    TRUE,
    600,
    NOW()
FROM public.t_busi_platform p
JOIN public.t_busi_action a
  ON a.bs_id = p.bs_id
 AND a.ba_action = 'videoDetail'
 AND a.ba_enabled IS TRUE
WHERE p.bs_platform_code = 'tiktok'
  AND NOT EXISTS (
      SELECT 1
      FROM public.t_crawl_task t
      WHERE t.platform = 'tiktok'
        AND t.action = 'videoDetail'
  )
ORDER BY a.ba_id
LIMIT 1;
