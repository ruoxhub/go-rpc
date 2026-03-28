-- Sekiro PostgreSQL 数据库迁移脚本
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
('使用自定义 ssl 证书', 'sekiro.useCustomSSLCertificate', 'false'),
('为配置的 host 自动生成 ssl 证书', 'sekiro.autoGenSSLCertificateHostList', ''),
('开启 443 服务端口', 'sekiro.open443Website', 'false'),
('空转调用保护', 'sekiro.defendIdleInvoke', 'true');
