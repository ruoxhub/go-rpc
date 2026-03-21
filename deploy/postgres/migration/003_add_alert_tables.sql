-- 003_add_alert_tables.sql
-- 告警规则和历史表

-- 告警规则表
CREATE TABLE IF NOT EXISTS alert_rule (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    description VARCHAR(512),
    "group" VARCHAR(64),
    api VARCHAR(256),
    metric_name VARCHAR(128) NOT NULL,
    operator VARCHAR(8) NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    window INTEGER NOT NULL,
    webhook_url VARCHAR(512),
    email VARCHAR(256),
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 告警规则表索引
CREATE INDEX idx_alert_rule_group ON alert_rule("group");
CREATE INDEX idx_alert_rule_enabled ON alert_rule(enabled);
CREATE INDEX idx_alert_rule_metric ON alert_rule(metric_name);

-- 告警历史表
CREATE TABLE IF NOT EXISTS alert_history (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT NOT NULL,
    rule_name VARCHAR(128) NOT NULL,
    "group" VARCHAR(64),
    api VARCHAR(256),
    metric_name VARCHAR(128) NOT NULL,
    current_value DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    operator VARCHAR(8) NOT NULL,
    level VARCHAR(16),
    notified BOOLEAN DEFAULT false,
    notify_error VARCHAR(512),
    triggered_at TIMESTAMP WITH TIME ZONE NOT NULL,
    message TEXT
);

-- 告警历史表索引
CREATE INDEX idx_alert_history_rule_id ON alert_history(rule_id);
CREATE INDEX idx_alert_history_group ON alert_history("group");
CREATE INDEX idx_alert_history_triggered_at ON alert_history(triggered_at);
CREATE INDEX idx_alert_history_level ON alert_history(level);

-- 添加表注释
COMMENT ON TABLE alert_rule IS '告警规则配置表';
COMMENT ON TABLE alert_history IS '告警触发历史记录表';

-- 告警规则表字段注释
COMMENT ON COLUMN alert_rule.name IS '规则名称（唯一）';
COMMENT ON COLUMN alert_rule.description IS '规则描述';
COMMENT ON COLUMN alert_rule."group" IS '分组名称，空表示全局规则';
COMMENT ON COLUMN alert_rule.api IS 'API 名称，空表示所有 API';
COMMENT ON COLUMN alert_rule.metric_name IS '指标名称，如 invoke.total, invoke.latency';
COMMENT ON COLUMN alert_rule.operator IS '操作符：>, <, >=, <=, ==, !=';
COMMENT ON COLUMN alert_rule.threshold IS '阈值';
COMMENT ON COLUMN alert_rule.window IS '时间窗口（分钟）';
COMMENT ON COLUMN alert_rule.webhook_url IS 'Webhook URL';
COMMENT ON COLUMN alert_rule.email IS '通知邮箱';
COMMENT ON COLUMN alert_rule.enabled IS '是否启用';

-- 告警历史表字段注释
COMMENT ON COLUMN alert_history.rule_id IS '关联的规则 ID';
COMMENT ON COLUMN alert_history.rule_name IS '规则名称冗余';
COMMENT ON COLUMN alert_history.current_value IS '触发时的当前值';
COMMENT ON COLUMN alert_history.level IS '告警级别：INFO, WARNING, CRITICAL';
COMMENT ON COLUMN alert_history.notified IS '是否已通知';
COMMENT ON COLUMN alert_history.notify_error IS '通知错误信息';
COMMENT ON COLUMN alert_history.message IS '告警详情消息';
