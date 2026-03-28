-- 插入默认系统配置（如果不存在）
INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '是否允许注册用户', 'sekiro.user.allowRegister', 'true'
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.user.allowRegister');

INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '出口 ip 探测 URL', 'sekiro.outIpTestUrl', 'http://api.ipify.org'
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.outIpTestUrl');

INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '系统通告信息', 'sekiro.systemNotice', ''
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.systemNotice');

INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '文档首页通告信息', 'sekiro.docNotice', ''
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.docNotice');

INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '是否允许匿名访问', 'sekiro.allowAnonymousAccess', 'true'
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.allowAnonymousAccess');

INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '匿名访问 qps 限制', 'sekiro.anonymousAccessRateLimit', '10'
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.anonymousAccessRateLimit');

INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '注册用户默认 qps 限制', 'sekiro.defaultRegisterQuotaUser', '10'
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.defaultRegisterQuotaUser');

INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '注册 group 默认 qps 限制', 'sekiro.defaultRegisterQuotaGroup', '100'
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.defaultRegisterQuotaGroup');

INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '使用自定义 ssl 证书', 'sekiro.useCustomSSLCertificate', 'false'
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.useCustomSSLCertificate');

INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '为配置的 host 自动生成 ssl 证书', 'sekiro.autoGenSSLCertificateHostList', ''
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.autoGenSSLCertificateHostList');

INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '开启 443 服务端口', 'sekiro.open443Website', 'false'
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.open443Website');

INSERT INTO sys_config (config_comment, config_key, config_value)
SELECT '空转调用保护', 'sekiro.defendIdleInvoke', 'true'
WHERE NOT EXISTS (SELECT 1 FROM sys_config WHERE config_key = 'sekiro.defendIdleInvoke');
