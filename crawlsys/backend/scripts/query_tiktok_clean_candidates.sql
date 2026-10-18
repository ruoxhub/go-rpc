-- TikTok 清洗过滤、分级与待下载候选检查。
-- 对应 backend/config.toml 当前规则：
--   extend.aigcLabelType > 0
--   P1: <= 24h 且 >= 3000 播放，或 <= 72h 且 >= 20000 播放
--   P2: <= 24h 且 >= 2500 播放
--   P3: <= 168h 且 >= 40000 播放
--
-- 注意：当前 Python 清洗 Worker 使用 CURRENT_TIMESTAMP - INTERVAL '1 day'
-- 作为分级参考时间，以下 SQL 保持相同行为。

DROP TABLE IF EXISTS tmp_tiktok_clean_candidates;

CREATE TEMP TABLE tmp_tiktok_clean_candidates AS
WITH filtered AS (
    SELECT
        c.id,
        c.content_id,
        c.platform,
        c.pub_time,
        c.download_time,
        c.view_count,
        c.created_time,
        c.updated_time,
        c.extend,
        CASE
            WHEN c.extend IS NULL OR c.extend = '' THEN NULL
            WHEN jsonb_typeof(
                jsonb_extract_path(c.extend::jsonb, 'aigcLabelType')
            ) = 'number'
            THEN (
                jsonb_extract_path(c.extend::jsonb, 'aigcLabelType') #>> '{}'
            )::numeric
            WHEN jsonb_typeof(
                jsonb_extract_path(c.extend::jsonb, 'aigcLabelType')
            ) = 'string'
            AND (
                jsonb_extract_path(c.extend::jsonb, 'aigcLabelType') #>> '{}'
            ) ~ '^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$'
            THEN (
                jsonb_extract_path(c.extend::jsonb, 'aigcLabelType') #>> '{}'
            )::numeric
            ELSE NULL
        END AS aigc_label_type,
        EXTRACT(
            EPOCH FROM (
                CURRENT_TIMESTAMP - INTERVAL '1 day' - c.pub_time
            )
        ) / 3600.0 AS published_hours
    FROM public.t_busi_content c
    WHERE c.platform = 'tiktok'
),
graded AS (
    SELECT
        *,
        CASE
            WHEN aigc_label_type IS NULL OR aigc_label_type <= 0 THEN NULL
            WHEN pub_time IS NULL THEN -1
            WHEN published_hours < 0 THEN -1
            WHEN download_time IS NOT NULL
                 AND ABS(EXTRACT(EPOCH FROM (pub_time - download_time))) < 120
                THEN -1
            WHEN view_count IS NULL OR view_count < 0 THEN 0
            WHEN published_hours <= 24 AND view_count >= 3000 THEN 1
            WHEN published_hours <= 72 AND view_count >= 20000 THEN 1
            WHEN published_hours <= 24 AND view_count >= 2500 THEN 2
            WHEN published_hours <= 168 AND view_count >= 40000 THEN 3
            ELSE 0
        END AS grade_rank
    FROM filtered
)
SELECT *
FROM graded
WHERE aigc_label_type > 0;

-- 结果一：过滤及分级数量统计。
SELECT
    COUNT(*) AS filtered_total,
    COUNT(*) FILTER (WHERE grade_rank BETWEEN 1 AND 3) AS graded_total,
    COUNT(*) FILTER (WHERE grade_rank = -1) AS manual_review_total,
    COUNT(*) FILTER (WHERE grade_rank = 0) AS skipped_total
FROM tmp_tiktok_clean_candidates;

-- 结果二：过滤及分级明细。
SELECT
    id,
    content_id,
    pub_time,
    download_time,
    view_count,
    aigc_label_type,
    ROUND(published_hours::numeric, 2) AS published_hours,
    grade_rank,
    CASE grade_rank
        WHEN 1 THEN 'P1'
        WHEN 2 THEN 'P2'
        WHEN 3 THEN 'P3'
        WHEN -1 THEN 'manual_review'
        WHEN 0 THEN 'unrated'
    END AS grade_result
FROM tmp_tiktok_clean_candidates
ORDER BY grade_rank, view_count DESC;

-- 结果三：现有清洗记录是否满足下载条件。
SELECT
    mc.content_id,
    mc.grade_rank,
    mc.clean_status,
    COALESCE(c.is_download, false) AS is_download,
    NULLIF(c.extend::jsonb ->> 'video_url', '') IS NOT NULL AS has_video,
    NULLIF(c.extend::jsonb ->> 'music_url', '') IS NOT NULL AS has_audio,
    NULLIF(c.extend::jsonb ->> 'pic_url', '') IS NOT NULL AS has_cover
FROM public.t_material_clean mc
JOIN public.t_busi_content c
  ON c.platform = mc.platform
 AND c.content_id = mc.content_id
WHERE mc.platform = 'tiktok'
  AND mc.grade_rank BETWEEN 1 AND 3
ORDER BY mc.grade_rank, mc.id;

-- 结果四：下载 Worker 实际可选中的记录。
SELECT
    mc.content_id,
    mc.grade_rank,
    c.extend::jsonb ->> 'video_url' AS video_url,
    c.extend::jsonb ->> 'music_url' AS music_url,
    c.extend::jsonb ->> 'pic_url' AS pic_url
FROM public.t_material_clean mc
JOIN public.t_busi_content c
  ON c.platform = mc.platform
 AND c.content_id = mc.content_id
WHERE mc.platform = 'tiktok'
  AND mc.clean_status = 'graded'
  AND mc.is_delete = 0
  AND mc.grade_rank BETWEEN 1 AND 3
  AND COALESCE(c.is_download, false) = false
  AND NULLIF(c.extend::jsonb ->> 'video_url', '') IS NOT NULL
  AND NULLIF(c.extend::jsonb ->> 'music_url', '') IS NOT NULL
  AND NULLIF(c.extend::jsonb ->> 'pic_url', '') IS NOT NULL
ORDER BY mc.grade_rank, mc.id;
