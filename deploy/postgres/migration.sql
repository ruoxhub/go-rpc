-- Rpc PostgreSQL 数据库迁移脚本
-- 注意：数据库已在容器启动时创建，此处跳过 CREATE DATABASE

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 删除已存在的表（注意顺序，先删除外键依赖的表）
DROP TABLE IF EXISTS metric_day CASCADE;
DROP TABLE IF EXISTS metric_hour CASCADE;
DROP TABLE IF EXISTS metric_minute CASCADE;
DROP TABLE IF EXISTS metric_tag CASCADE;
DROP TABLE IF EXISTS group_device CASCADE;
DROP TABLE IF EXISTS group_actions CASCADE;
DROP TABLE IF EXISTS group_config CASCADE;
DROP TABLE IF EXISTS sys_log CASCADE;
DROP TABLE IF EXISTS sys_config CASCADE;
DROP TABLE IF EXISTS server_node CASCADE;
DROP TABLE IF EXISTS user_info CASCADE;

-- 用户信息表
CREATE TABLE user_info (
    id BIGSERIAL PRIMARY KEY,
    user_name VARCHAR(64),
    password VARCHAR(64),
    last_active TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    login_token VARCHAR(64),
    api_token VARCHAR(64) DEFAULT '',
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    update_time TIMESTAMP DEFAULT NULL,
    permission TEXT DEFAULT '',
    quota_qps DOUBLE PRECISION NOT NULL DEFAULT 10
);

-- 加速 FindUserByToken 查询；使用部分唯一索引以兼容默认空串。
CREATE UNIQUE INDEX IF NOT EXISTS uniq_user_info_api_token
    ON user_info(api_token) WHERE api_token <> '';

-- 系统配置表
CREATE TABLE sys_config (
    id BIGSERIAL PRIMARY KEY,
    config_comment VARCHAR(128),
    config_key VARCHAR(64),
    config_value VARCHAR(1024),
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uniq_sys_config ON sys_config(config_comment, config_key);

-- 系统日志表
CREATE TABLE sys_log (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(100),
    operation VARCHAR(200),
    params VARCHAR(500),
    method_name VARCHAR(200),
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 服务器节点表
CREATE TABLE server_node (
    id BIGSERIAL PRIMARY KEY,
    server_id VARCHAR(64) NOT NULL,
    last_active_time TIMESTAMP,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip VARCHAR(512) NOT NULL DEFAULT '',
    port INTEGER NOT NULL,
    enable BOOLEAN NOT NULL DEFAULT TRUE,
    local_ip VARCHAR(512),
    out_ip VARCHAR(512)
);

CREATE UNIQUE INDEX uniq_server_node ON server_node(server_id);

-- 分组信息表
CREATE TABLE group_config (
    id BIGSERIAL PRIMARY KEY,
    group_name VARCHAR(64) NOT NULL,
    user_name VARCHAR(64),
    quota_qps_group DOUBLE PRECISION NOT NULL DEFAULT 100,
    quota_qps_per_device DOUBLE PRECISION NOT NULL DEFAULT -1,
    create_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 分组下 action 表
CREATE TABLE group_actions (
    id BIGSERIAL PRIMARY KEY,
    group_name VARCHAR(64) NOT NULL,
    action_name VARCHAR(64),
    action_params TEXT DEFAULT '',
    create_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uniq_group_actions ON group_actions(group_name, action_name);

-- 分组下挂有的设备表
CREATE TABLE group_device (
    id BIGSERIAL PRIMARY KEY,
    group_name VARCHAR(64) NOT NULL,
    device_id VARCHAR(128),
    remote_ip VARCHAR(64),
    create_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_time TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX uniq_group_device ON group_device(group_name, device_id);

-- 指标 tag 定义表
CREATE TABLE metric_tag (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    tag1_name VARCHAR(64),
    tag2_name VARCHAR(64),
    tag3_name VARCHAR(64),
    tag4_name VARCHAR(64),
    tag5_name VARCHAR(64)
);

CREATE UNIQUE INDEX uniq_metric_tag ON metric_tag(name);

-- 监控指标 - 分钟级表
CREATE TABLE metric_minute (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    time_key VARCHAR(64) NOT NULL,
    tags_md5 VARCHAR(64) NOT NULL,
    tag1 VARCHAR(64) DEFAULT NULL,
    tag2 VARCHAR(64) DEFAULT NULL,
    tag3 VARCHAR(64) DEFAULT NULL,
    tag4 VARCHAR(64) DEFAULT NULL,
    tag5 VARCHAR(64) DEFAULT NULL,
    type VARCHAR(8) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uniq_metric_minute ON metric_minute(name, tags_md5, time_key);
CREATE INDEX idx_metric_minute_query ON metric_minute(name, tags_md5);
CREATE INDEX idx_metric_minute_delete ON metric_minute(name, create_time);

-- 监控指标 - 小时级表
CREATE TABLE metric_hour (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    time_key VARCHAR(64) NOT NULL,
    tags_md5 VARCHAR(64) NOT NULL,
    tag1 VARCHAR(64) DEFAULT NULL,
    tag2 VARCHAR(64) DEFAULT NULL,
    tag3 VARCHAR(64) DEFAULT NULL,
    tag4 VARCHAR(64) DEFAULT NULL,
    tag5 VARCHAR(64) DEFAULT NULL,
    type VARCHAR(8) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uniq_metric_hour ON metric_hour(name, tags_md5, time_key);
CREATE INDEX idx_metric_hour_query ON metric_hour(name, tags_md5);
CREATE INDEX idx_metric_hour_delete ON metric_hour(name, create_time);

-- 监控指标 - 天级表
CREATE TABLE metric_day (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    time_key VARCHAR(64) NOT NULL,
    tags_md5 VARCHAR(64) NOT NULL,
    tag1 VARCHAR(64) DEFAULT NULL,
    tag2 VARCHAR(64) DEFAULT NULL,
    tag3 VARCHAR(64) DEFAULT NULL,
    tag4 VARCHAR(64) DEFAULT NULL,
    tag5 VARCHAR(64) DEFAULT NULL,
    type VARCHAR(8) NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uniq_metric_day ON metric_day(name, tags_md5, time_key);
CREATE INDEX idx_metric_day_query ON metric_day(name, tags_md5);
CREATE INDEX idx_metric_day_delete ON metric_day(name, create_time);

-- 插入默认管理员用户
INSERT INTO user_info (user_name, password, is_admin, api_token, quota_qps)
VALUES ('admin', '$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy', TRUE, uuid_generate_v4()::text, 1000);

-- 插入默认系统配置
INSERT INTO sys_config (config_comment, config_key, config_value) VALUES
('是否允许注册用户', 'sekiro.user.allowRegister', 'true'),
('出口 ip 探测 URL', 'sekiro.outIpTestUrl', 'http://api.ipify.org'),
('系统通告信息', 'sekiro.systemNotice', ''),
('文档首页通告信息', 'sekiro.docNotice', ''),
('是否允许匿名访问', 'sekiro.allowAnonymousAccess', 'true'),
('匿名访问 qps 限制', 'sekiro.anonymousAccessRateLimit', '10'),
('注册用户默认 qps 限制', 'sekiro.defaultRegisterQuotaUser', '10'),
('注册 group 默认 qps 限制', 'sekiro.defaultRegisterQuotaGroup', '100'),
('设备默认 qps 限制', 'sekiro.defaultRegisterQuotaPerDevice', '10'),
('使用自定义 ssl 证书', 'sekiro.useCustomSSLCertificate', 'false'),
('为配置的 host 自动生成 ssl 证书', 'sekiro.autoGenSSLCertificateHostList', ''),
('开启 443 服务端口', 'sekiro.open443Website', 'false'),
('空转调用保护', 'sekiro.defendIdleInvoke', 'true');

-- 调用链路追踪表
CREATE TABLE IF NOT EXISTS trace_record (
    id BIGSERIAL PRIMARY KEY,
    trace_id VARCHAR(64) NOT NULL,
    span_id VARCHAR(64) NOT NULL,
    parent_span_id VARCHAR(64),
    "group" VARCHAR(64),
    device_id VARCHAR(128),
    api VARCHAR(256),
    caller VARCHAR(128),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    duration_ms BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL,
    error_message TEXT,
    extra_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_trace_record_trace_id ON trace_record(trace_id);
CREATE INDEX IF NOT EXISTS idx_trace_record_group ON trace_record("group");
CREATE INDEX IF NOT EXISTS idx_trace_record_start_time ON trace_record(start_time);
CREATE INDEX IF NOT EXISTS idx_trace_record_status ON trace_record(status);
CREATE INDEX IF NOT EXISTS idx_trace_record_api ON trace_record(api);

-- 注释
COMMENT ON TABLE trace_record IS '调用链路追踪记录';
COMMENT ON COLUMN trace_record.trace_id IS '追踪 ID';
COMMENT ON COLUMN trace_record.span_id IS 'Span ID';
COMMENT ON COLUMN trace_record.parent_span_id IS '父 Span ID';
COMMENT ON COLUMN trace_record.duration_ms IS '耗时 (毫秒)';
COMMENT ON COLUMN trace_record.status IS '状态：SUCCESS, FAILURE';

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

-- 表注释
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
