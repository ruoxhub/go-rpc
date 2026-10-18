WITH candidates AS (
    SELECT
        c.*,
        c.extend::jsonb ->> 'aigcLabelType' AS aigc_label_type,
        EXTRACT(
            EPOCH FROM (timezone('UTC', now()) - c.pub_time)
        ) / 3600.0 AS published_hours
    FROM public.t_busi_content AS c
    WHERE c.platform = 'tiktok'
      AND c.pub_time IS NOT NULL
      AND c.pub_time >= timezone('UTC', now()) - INTERVAL '7 days'
      AND c.pub_time <= timezone('UTC', now())
      AND c.extend IS NOT NULL
      AND c.extend <> ''
      AND c.extend::jsonb ->> 'aigcLabelType' IS NOT NULL
      AND btrim(c.extend::jsonb ->> 'aigcLabelType') <> ''
),
graded AS (
    SELECT
        candidates.*,
        CASE
            WHEN (
                published_hours <= 24
                AND COALESCE(view_count, 0) >= 8000
            ) OR (
                published_hours <= 72
                AND COALESCE(view_count, 0) >= 50000
            )
            THEN 'P1'
            WHEN published_hours <= 24
             AND COALESCE(view_count, 0) >= 5000
            THEN 'P2'
            WHEN published_hours <= 168
             AND COALESCE(view_count, 0) >= 80000
            THEN 'P3'
            ELSE 'UNRATED'
        END AS exposure_grade
    FROM candidates
)
SELECT
    id,
    content_id,
    platform,
    title,
    url,
    pub_time,
    view_count,
    aigc_label_type,
    ROUND(published_hours::numeric, 2) AS published_hours,
    exposure_grade
FROM graded
WHERE exposure_grade <> 'UNRATED'
ORDER BY
    CASE exposure_grade
        WHEN 'P1' THEN 1
        WHEN 'P2' THEN 2
        WHEN 'P3' THEN 3
    END,
    view_count DESC;
