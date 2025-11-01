-- ═══════════════════════════════════════════════════════════════
-- Bybit AI Trading System - 数据库初始化脚本
-- ═══════════════════════════════════════════════════════════════
-- PostgreSQL 13+ 
-- 用途: 创建数据库、用户、表结构、索引、触发器
-- ═══════════════════════════════════════════════════════════════

-- 1. 创建数据库和用户
-- ═══════════════════════════════════════════════════════════════

-- 创建数据库
CREATE DATABASE bybit_trading
    WITH 
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- 连接到新数据库
\c bybit_trading

-- 创建用户
CREATE USER trading_user WITH PASSWORD 'your_secure_password_here';

-- 授予权限
GRANT ALL PRIVILEGES ON DATABASE bybit_trading TO trading_user;
GRANT ALL PRIVILEGES ON SCHEMA public TO trading_user;

-- 设置默认权限
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO trading_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO trading_user;

-- 2. 创建扩展
-- ═══════════════════════════════════════════════════════════════

-- UUID支持
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 时间处理
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- 3. 创建表结构
-- ═══════════════════════════════════════════════════════════════

-- 3.1 交易记录表
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- 交易信息
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('Buy', 'Sell')),
    order_type VARCHAR(20) NOT NULL,
    
    -- 价格和数量
    entry_price NUMERIC(20, 8) NOT NULL,
    close_price NUMERIC(20, 8),
    position_size NUMERIC(20, 8) NOT NULL,
    leverage INTEGER NOT NULL CHECK (leverage >= 1 AND leverage <= 100),
    
    -- 止盈止损
    stop_loss NUMERIC(20, 8),
    take_profit JSONB,
    
    -- 盈亏
    pnl NUMERIC(20, 8),
    pnl_pct NUMERIC(10, 4),
    fees NUMERIC(20, 8) DEFAULT 0,
    net_pnl NUMERIC(20, 8),
    
    -- 时间
    entry_time TIMESTAMP NOT NULL DEFAULT NOW(),
    close_time TIMESTAMP,
    hold_duration_seconds INTEGER,
    
    -- 理由和状态
    entry_reason TEXT,
    close_reason TEXT,
    status VARCHAR(20) DEFAULT 'open' CHECK (status IN ('open', 'closed', 'cancelled')),
    
    -- 保证金和清算
    margin NUMERIC(20, 8),
    liquidation_price NUMERIC(20, 8),
    
    -- 移动止损
    trailing_stop_updates INTEGER DEFAULT 0,
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- 外键
    ai_decision_id INTEGER REFERENCES ai_decisions(id) ON DELETE SET NULL
);

-- 3.2 AI决策记录表
CREATE TABLE IF NOT EXISTS ai_decisions (
    id SERIAL PRIMARY KEY,
    decision_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- 决策信息
    action VARCHAR(20) NOT NULL CHECK (action IN ('LONG', 'SHORT', 'CLOSE', 'HOLD')),
    target_symbol VARCHAR(50),
    confidence INTEGER CHECK (confidence >= 0 AND confidence <= 100),
    
    -- 市场状态
    market_state VARCHAR(50),
    
    -- 订单参数
    order_type VARCHAR(20),
    entry_price NUMERIC(20, 8),
    position_size NUMERIC(10, 4),
    leverage INTEGER,
    stop_loss NUMERIC(20, 8),
    take_profit JSONB,
    
    -- AI分析
    reasoning TEXT,
    prompt_used TEXT,
    response_raw TEXT,
    
    -- 技术指标
    indicators JSONB,
    
    -- 市场数据
    market_data JSONB,
    
    -- 执行结果
    execution_result VARCHAR(20),
    execution_error TEXT,
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    model_version VARCHAR(50),
    response_time_ms INTEGER
);

-- 3.3 用户配置表
CREATE TABLE IF NOT EXISTS user_configs (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    
    -- DeepSeek配置（加密存储）
    deepseek_api_key_encrypted TEXT,
    deepseek_model VARCHAR(100),
    deepseek_temperature NUMERIC(3, 2) DEFAULT 0.3,
    
    -- Bybit配置（加密存储）
    bybit_api_key_encrypted TEXT,
    bybit_api_secret_encrypted TEXT,
    bybit_testnet BOOLEAN DEFAULT true,
    
    -- 交易配置
    trading_enabled BOOLEAN DEFAULT false,
    default_leverage INTEGER DEFAULT 5 CHECK (default_leverage >= 1 AND default_leverage <= 15),
    max_position_pct NUMERIC(5, 2) DEFAULT 30 CHECK (max_position_pct <= 100),
    min_position_pct NUMERIC(5, 2) DEFAULT 3 CHECK (min_position_pct >= 0),
    
    -- 风险配置
    max_drawdown_pct NUMERIC(5, 2) DEFAULT 10,
    stop_loss_pct NUMERIC(5, 2) DEFAULT 2,
    trailing_stop_enabled BOOLEAN DEFAULT true,
    trailing_activation_pct NUMERIC(5, 2) DEFAULT 1,
    trailing_callback_pct NUMERIC(5, 2) DEFAULT 0.5,
    
    -- 监控配置
    symbols JSONB DEFAULT '["BTCUSDT", "ETHUSDT", "SOLUSDT"]'::JSONB,
    decision_interval_seconds INTEGER DEFAULT 180,
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP
);

-- 3.4 用户认证表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT false,
    
    -- 安全字段
    failed_login_attempts INTEGER DEFAULT 0,
    last_login TIMESTAMP,
    account_locked BOOLEAN DEFAULT false,
    
    -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 3.5 系统配置表
CREATE TABLE IF NOT EXISTS system_configs (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 3.6 账户快照表（每日）
CREATE TABLE IF NOT EXISTS account_snapshots (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    
    -- 账户数据
    balance NUMERIC(20, 8) NOT NULL,
    equity NUMERIC(20, 8) NOT NULL,
    available_balance NUMERIC(20, 8) NOT NULL,
    used_margin NUMERIC(20, 8) NOT NULL,
    
    -- 持仓统计
    open_positions INTEGER DEFAULT 0,
    total_unrealized_pnl NUMERIC(20, 8) DEFAULT 0,
    
    -- 交易统计
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    win_rate NUMERIC(5, 2),
    
    -- 性能指标
    total_pnl NUMERIC(20, 8) DEFAULT 0,
    max_drawdown NUMERIC(20, 8) DEFAULT 0,
    sharpe_ratio NUMERIC(10, 4),
    
    snapshot_time TIMESTAMP DEFAULT NOW(),
    UNIQUE(username, DATE(snapshot_time))
);

-- 3.7 市场数据缓存表
CREATE TABLE IF NOT EXISTS market_data_cache (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    
    -- OHLCV数据
    open_price NUMERIC(20, 8) NOT NULL,
    high_price NUMERIC(20, 8) NOT NULL,
    low_price NUMERIC(20, 8) NOT NULL,
    close_price NUMERIC(20, 8) NOT NULL,
    volume NUMERIC(20, 8) NOT NULL,
    
    -- 技术指标（存储为JSONB）
    indicators JSONB,
    
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(symbol, timeframe, timestamp)
);

-- 3.8 操作日志表
CREATE TABLE IF NOT EXISTS operation_logs (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100),
    operation_type VARCHAR(50) NOT NULL,
    operation_detail JSONB,
    ip_address INET,
    user_agent TEXT,
    status VARCHAR(20),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3.9 系统告警表
CREATE TABLE IF NOT EXISTS system_alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    resolved BOOLEAN DEFAULT false,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 4. 创建索引
-- ═══════════════════════════════════════════════════════════════

-- trades表索引
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_trades_entry_time ON trades(entry_time DESC);
CREATE INDEX idx_trades_close_time ON trades(close_time DESC);
CREATE INDEX idx_trades_symbol_status ON trades(symbol, status);

-- ai_decisions表索引
CREATE INDEX idx_ai_decisions_created_at ON ai_decisions(created_at DESC);
CREATE INDEX idx_ai_decisions_action ON ai_decisions(action);
CREATE INDEX idx_ai_decisions_target_symbol ON ai_decisions(target_symbol);

-- user_configs表索引
CREATE INDEX idx_user_configs_username ON user_configs(username);
CREATE INDEX idx_user_configs_last_active ON user_configs(last_active DESC);

-- users表索引
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_last_login ON users(last_login DESC);

-- account_snapshots表索引
CREATE INDEX idx_account_snapshots_username ON account_snapshots(username);
CREATE INDEX idx_account_snapshots_time ON account_snapshots(snapshot_time DESC);

-- market_data_cache表索引
CREATE INDEX idx_market_data_symbol_time ON market_data_cache(symbol, timeframe, timestamp DESC);

-- operation_logs表索引
CREATE INDEX idx_operation_logs_username ON operation_logs(username);
CREATE INDEX idx_operation_logs_created_at ON operation_logs(created_at DESC);
CREATE INDEX idx_operation_logs_type ON operation_logs(operation_type);

-- system_alerts表索引
CREATE INDEX idx_system_alerts_severity ON system_alerts(severity);
CREATE INDEX idx_system_alerts_resolved ON system_alerts(resolved);
CREATE INDEX idx_system_alerts_created_at ON system_alerts(created_at DESC);

-- 5. 创建触发器
-- ═══════════════════════════════════════════════════════════════

-- 自动更新updated_at字段
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 为需要的表添加触发器
CREATE TRIGGER update_trades_updated_at BEFORE UPDATE ON trades
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_configs_updated_at BEFORE UPDATE ON user_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_system_configs_updated_at BEFORE UPDATE ON system_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 6. 插入默认数据
-- ═══════════════════════════════════════════════════════════════

-- 插入默认管理员用户（密码: admin123，使用SHA256哈希）
INSERT INTO users (username, password_hash, is_admin)
VALUES ('admin', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', true)
ON CONFLICT (username) DO NOTHING;

-- 插入默认系统配置
INSERT INTO system_configs (config_key, config_value, description)
VALUES 
    ('system_version', '"4.0"', '系统版本号'),
    ('maintenance_mode', 'false', '维护模式开关'),
    ('max_concurrent_users', '100', '最大并发用户数'),
    ('cache_ttl_seconds', '300', '缓存过期时间（秒）'),
    ('ai_rate_limit', '{"requests_per_minute": 20, "requests_per_hour": 100}', 'AI调用频率限制')
ON CONFLICT (config_key) DO NOTHING;

-- 7. 创建视图
-- ═══════════════════════════════════════════════════════════════

-- 交易统计视图
CREATE OR REPLACE VIEW v_trade_statistics AS
SELECT 
    symbol,
    COUNT(*) AS total_trades,
    SUM(CASE WHEN status = 'closed' AND net_pnl > 0 THEN 1 ELSE 0 END) AS winning_trades,
    SUM(CASE WHEN status = 'closed' AND net_pnl < 0 THEN 1 ELSE 0 END) AS losing_trades,
    ROUND(
        100.0 * SUM(CASE WHEN status = 'closed' AND net_pnl > 0 THEN 1 ELSE 0 END) / 
        NULLIF(SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END), 0), 
        2
    ) AS win_rate,
    SUM(net_pnl) AS total_pnl,
    AVG(net_pnl) AS avg_pnl,
    MAX(net_pnl) AS max_profit,
    MIN(net_pnl) AS max_loss,
    AVG(hold_duration_seconds) AS avg_hold_duration_seconds
FROM trades
WHERE status = 'closed'
GROUP BY symbol;

-- 用户活动视图
CREATE OR REPLACE VIEW v_user_activity AS
SELECT 
    u.username,
    u.is_admin,
    u.last_login,
    uc.trading_enabled,
    uc.last_active,
    COUNT(DISTINCT t.id) AS total_trades,
    SUM(t.net_pnl) AS total_pnl
FROM users u
LEFT JOIN user_configs uc ON u.username = uc.username
LEFT JOIN trades t ON u.username = uc.username
GROUP BY u.username, u.is_admin, u.last_login, uc.trading_enabled, uc.last_active;

-- AI决策统计视图
CREATE OR REPLACE VIEW v_ai_decision_stats AS
SELECT 
    DATE(created_at) AS decision_date,
    action,
    COUNT(*) AS decision_count,
    AVG(confidence) AS avg_confidence,
    AVG(response_time_ms) AS avg_response_time_ms,
    SUM(CASE WHEN execution_result = 'success' THEN 1 ELSE 0 END) AS successful_executions,
    SUM(CASE WHEN execution_result = 'failed' THEN 1 ELSE 0 END) AS failed_executions
FROM ai_decisions
GROUP BY DATE(created_at), action
ORDER BY decision_date DESC, action;

-- 8. 授予权限
-- ═══════════════════════════════════════════════════════════════

-- 授予所有表的权限
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trading_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trading_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO trading_user;

-- 授予视图的权限
GRANT SELECT ON v_trade_statistics TO trading_user;
GRANT SELECT ON v_user_activity TO trading_user;
GRANT SELECT ON v_ai_decision_stats TO trading_user;

-- 9. 数据库性能优化
-- ═══════════════════════════════════════════════════════════════

-- 启用自动清理
ALTER TABLE trades SET (autovacuum_enabled = true);
ALTER TABLE ai_decisions SET (autovacuum_enabled = true);
ALTER TABLE operation_logs SET (autovacuum_enabled = true);

-- 10. 完成信息
-- ═══════════════════════════════════════════════════════════════

DO $$
BEGIN
    RAISE NOTICE '═══════════════════════════════════════════════════════════════';
    RAISE NOTICE '✅ 数据库初始化完成！';
    RAISE NOTICE '═══════════════════════════════════════════════════════════════';
    RAISE NOTICE '';
    RAISE NOTICE '数据库: bybit_trading';
    RAISE NOTICE '用户: trading_user';
    RAISE NOTICE '表数量: 9';
    RAISE NOTICE '视图数量: 3';
    RAISE NOTICE '';
    RAISE NOTICE '默认管理员账号:';
    RAISE NOTICE '  用户名: admin';
    RAISE NOTICE '  密码: admin123';
    RAISE NOTICE '  ⚠️  请立即修改默认密码！';
    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════════════';
END $$;



