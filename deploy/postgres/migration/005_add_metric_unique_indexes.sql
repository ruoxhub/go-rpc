-- 005_add_metric_unique_indexes.sql
--
-- 背景：
--   metric_minute / metric_hour / metric_day 的聚合 SQL 使用
--   ON CONFLICT (name, tags_md5, time_key) DO UPDATE ...，
--   要求三列上存在唯一约束（UNIQUE INDEX 或 PRIMARY KEY）。
--   早期部署若未执行 migration.sql 中的 CREATE UNIQUE INDEX 语句，
--   rollup 任务会抛 SQLSTATE 42P10：
--     there is no unique or exclusion constraint matching the ON CONFLICT specification
--
-- 本脚本：
--   1. 先清理因历史并发写入可能产生的 (name, tags_md5, time_key) 重复行，
--      每组保留 id 最大的一条。
--   2. 再创建唯一索引（如已存在则跳过）。
--
-- 适用于 PostgreSQL 11+。

-- ==================== metric_minute ====================
DELETE FROM metric_minute
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY name, tags_md5, time_key
                   ORDER BY id DESC
               ) AS rn
        FROM metric_minute
    ) t WHERE t.rn > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_metric_minute
    ON metric_minute (name, tags_md5, time_key);

CREATE INDEX IF NOT EXISTS idx_metric_minute_query
    ON metric_minute (name, tags_md5);

CREATE INDEX IF NOT EXISTS idx_metric_minute_delete
    ON metric_minute (name, create_time);

-- ==================== metric_hour ====================
DELETE FROM metric_hour
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY name, tags_md5, time_key
                   ORDER BY id DESC
               ) AS rn
        FROM metric_hour
    ) t WHERE t.rn > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_metric_hour
    ON metric_hour (name, tags_md5, time_key);

CREATE INDEX IF NOT EXISTS idx_metric_hour_query
    ON metric_hour (name, tags_md5);

CREATE INDEX IF NOT EXISTS idx_metric_hour_delete
    ON metric_hour (name, create_time);

-- ==================== metric_day ====================
DELETE FROM metric_day
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY name, tags_md5, time_key
                   ORDER BY id DESC
               ) AS rn
        FROM metric_day
    ) t WHERE t.rn > 1
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_metric_day
    ON metric_day (name, tags_md5, time_key);

CREATE INDEX IF NOT EXISTS idx_metric_day_query
    ON metric_day (name, tags_md5);

CREATE INDEX IF NOT EXISTS idx_metric_day_delete
    ON metric_day (name, create_time);
