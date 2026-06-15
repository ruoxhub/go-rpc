-- 004_add_action_params.sql
-- Store client-reported action parameter schemas.

ALTER TABLE group_actions
    ADD COLUMN IF NOT EXISTS action_params TEXT DEFAULT '';
