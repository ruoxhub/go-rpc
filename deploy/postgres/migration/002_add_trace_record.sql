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
