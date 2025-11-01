"""
数据库模型定义 - PostgreSQL
使用SQLAlchemy ORM
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, JSON, Text, ForeignKey, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
import os

# 数据库连接配置
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://trading_user:your_password@localhost:5432/bybit_trading"
)

# 调试输出（避免泄露密码，只打印是否来自环境变量）
if "your_password" in DATABASE_URL:
    print("[database_models] ⚠️ DATABASE_URL 使用默认占位密码，请检查环境变量加载")
else:
    print("[database_models] ✅ DATABASE_URL 已从环境变量加载")

engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============================================================================
# 数据库模型
# ============================================================================

class Trade(Base):
    """交易记录表"""
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(String(100), unique=True, index=True)
    
    # 用户关联（多用户支持）
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    
    # 交易信息
    symbol = Column(String(50), index=True)
    side = Column(String(10))  # Buy/Sell
    order_type = Column(String(20))  # Market/Limit
    
    # 价格和数量
    entry_price = Column(Float)
    close_price = Column(Float, nullable=True)
    position_size = Column(Float)
    leverage = Column(Integer)
    
    # 止盈止损
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(JSON, nullable=True)  # 存储数组
    
    # 盈亏
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    fees = Column(Float, default=0)
    net_pnl = Column(Float, nullable=True)
    
    # 时间
    entry_time = Column(DateTime, default=datetime.utcnow)
    close_time = Column(DateTime, nullable=True)
    hold_duration_seconds = Column(Integer, nullable=True)
    
    # 理由和状态
    entry_reason = Column(Text, nullable=True)
    close_reason = Column(Text, nullable=True)
    status = Column(String(20), default="open")  # open/closed/cancelled
    
    # 保证金和清算
    margin = Column(Float, nullable=True)
    liquidation_price = Column(Float, nullable=True)
    
    # 移动止损
    trailing_stop_updates = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    ai_decision_id = Column(Integer, ForeignKey("ai_decisions.id"), nullable=True)
    ai_decision = relationship("AIDecision", back_populates="trades")


class AIDecision(Base):
    """AI决策记录表"""
    __tablename__ = "ai_decisions"
    
    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(String(100), unique=True, index=True)
    
    # 用户关联（多用户支持）
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    
    # 决策信息
    action = Column(String(20))  # LONG/SHORT/CLOSE/HOLD
    target_symbol = Column(String(50))
    confidence = Column(Integer)
    
    # 市场状态
    market_state = Column(String(50), nullable=True)
    
    # 订单参数
    order_type = Column(String(20), nullable=True)
    entry_price = Column(Float, nullable=True)
    position_size = Column(Float, nullable=True)
    leverage = Column(Integer, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(JSON, nullable=True)
    
    # 分析
    reason = Column(Text)
    risk_reward_ratio = Column(Float, nullable=True)
    
    # 市场数据快照
    market_data_snapshot = Column(JSON, nullable=True)
    
    # 执行状态
    executed = Column(Boolean, default=False)
    execution_time = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # 关系
    trades = relationship("Trade", back_populates="ai_decision")


class MarketData(Base):
    """市场数据表（用于历史查询和分析）"""
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True, index=True)
    
    symbol = Column(String(50), index=True)
    price = Column(Float)
    change_24h = Column(Float)
    change_pct = Column(Float)
    volume_24h = Column(Float)
    funding_rate = Column(Float, nullable=True)
    
    high_24h = Column(Float, nullable=True)
    low_24h = Column(Float, nullable=True)
    mark_price = Column(Float, nullable=True)
    index_price = Column(Float, nullable=True)
    open_interest = Column(Float, nullable=True)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class SystemLog(Base):
    """系统日志表"""
    __tablename__ = "system_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    level = Column(String(20), index=True)  # INFO/WARNING/ERROR
    message = Column(Text)
    source = Column(String(100), nullable=True)  # 日志来源
    
    # 额外数据
    extra_data = Column(JSON, nullable=True)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class RiskEvent(Base):
    """风险事件记录表"""
    __tablename__ = "risk_events"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 用户关联（多用户支持）
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    
    event_type = Column(String(50), index=True)  # flash_crash/liquidity/etc
    severity = Column(String(20))  # low/medium/high/critical
    
    symbol = Column(String(50), nullable=True)
    trigger_value = Column(Float, nullable=True)
    threshold_value = Column(Float, nullable=True)
    
    message = Column(Text)
    actions_taken = Column(JSON, nullable=True)  # 采取的行动列表
    
    avoided_loss = Column(Float, nullable=True)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class AccountSnapshot(Base):
    """账户快照表（用于资金曲线和回撤分析）"""
    __tablename__ = "account_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 用户关联（多用户支持）
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    
    balance = Column(Float)
    available_balance = Column(Float)
    used_margin = Column(Float, nullable=True)
    
    unrealized_pnl = Column(Float, default=0)
    realized_pnl = Column(Float, default=0)
    
    peak_balance = Column(Float, nullable=True)
    drawdown_pct = Column(Float, nullable=True)
    
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class Configuration(Base):
    """配置表（存储系统配置）- v3.3 支持多用户"""
    __tablename__ = "configurations"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 用户关联（v3.3 多用户支持）
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=True)
    
    key = Column(String(100), index=True)  # 移除 unique，因为不同用户可以有相同的 key
    value = Column(JSON)
    description = Column(Text, nullable=True)
    
    category = Column(String(50), nullable=True)  # trading/risk/ai/etc
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 添加复合唯一约束：同一用户不能有重复的 (category, key)
    __table_args__ = (
        UniqueConstraint('user_id', 'category', 'key', name='uq_user_category_key'),
    )
    
    # 关系
    user = relationship("User", backref="configurations")


class User(Base):
    """用户表（如果需要多用户支持）"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)  # 注意：数据库中是password_hash不是hashed_password
    
    is_admin = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    last_login = Column(DateTime, nullable=True)
    account_locked = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 为了兼容旧代码，添加属性别名
    @property
    def hashed_password(self):
        return self.password_hash
    
    @hashed_password.setter
    def hashed_password(self, value):
        self.password_hash = value
    
    @property
    def is_active(self):
        return not self.account_locked
    
    @is_active.setter  
    def is_active(self, value):
        self.account_locked = not value
    
    # 关系
    api_keys = relationship("APIKey", back_populates="user", uselist=False)


class APIKey(Base):
    """用户API密钥表 - 存储用户的Bybit和DeepSeek API密钥"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Bybit API 密钥
    bybit_api_key = Column(String(255), nullable=True)
    bybit_api_secret = Column(String(255), nullable=True)
    
    # DeepSeek API 密钥
    deepseek_api_key = Column(String(255), nullable=True)
    
    # 状态
    is_active = Column(Boolean, default=True)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="api_keys")


class APIAccessLog(Base):
    """API访问日志表"""
    __tablename__ = "api_access_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    endpoint = Column(String(200))
    method = Column(String(10))
    ip_address = Column(String(50))
    user_agent = Column(String(500), nullable=True)
    
    status_code = Column(Integer)
    response_time_ms = Column(Float)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


# ============================================================================
# 数据库工具函数
# ============================================================================

def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database():
    """初始化数据库（创建所有表）"""
    print("正在创建数据库表...")
    Base.metadata.create_all(bind=engine)
    print("✅ 数据库表创建完成")


def drop_all_tables():
    """删除所有表（谨慎使用！）"""
    print("⚠️ 警告：正在删除所有表...")
    Base.metadata.drop_all(bind=engine)
    print("✅ 所有表已删除")


# ============================================================================
# 数据库操作类
# ============================================================================

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        self.session = SessionLocal()
    
    def close(self):
        """关闭会话"""
        self.session.close()
    
    # 交易相关
    def create_trade(self, trade_data: dict) -> Trade:
        """创建交易记录"""
        trade = Trade(**trade_data)
        self.session.add(trade)
        self.session.commit()
        self.session.refresh(trade)
        return trade
    
    def update_trade(self, trade_id: str, update_data: dict):
        """更新交易记录"""
        trade = self.session.query(Trade).filter(Trade.trade_id == trade_id).first()
        if trade:
            for key, value in update_data.items():
                setattr(trade, key, value)
            trade.updated_at = datetime.utcnow()
            self.session.commit()
            return trade
        return None
    
    def get_trade(self, trade_id: str) -> Trade:
        """获取交易记录"""
        return self.session.query(Trade).filter(Trade.trade_id == trade_id).first()
    
    def get_recent_trades(self, limit: int = 20, offset: int = 0):
        """获取最近的交易"""
        return self.session.query(Trade).order_by(Trade.created_at.desc()).offset(offset).limit(limit).all()
    
    def get_open_trades(self):
        """获取所有未平仓交易"""
        return self.session.query(Trade).filter(Trade.status == "open").all()
    
    # AI决策相关
    def create_ai_decision(self, decision_data: dict) -> AIDecision:
        """创建AI决策记录"""
        decision = AIDecision(**decision_data)
        self.session.add(decision)
        self.session.commit()
        self.session.refresh(decision)
        return decision
    
    def get_recent_ai_decisions(self, limit: int = 50):
        """获取最近的AI决策"""
        return self.session.query(AIDecision).order_by(AIDecision.created_at.desc()).limit(limit).all()
    
    # 市场数据相关
    def save_market_data(self, market_data: dict):
        """保存市场数据快照"""
        for symbol, data in market_data.items():
            snapshot = MarketData(
                symbol=symbol,
                price=data.get('price'),
                change_24h=data.get('change_24h'),
                change_pct=data.get('change_pct'),
                volume_24h=data.get('volume_24h'),
                funding_rate=data.get('funding_rate'),
                high_24h=data.get('high_24h'),
                low_24h=data.get('low_24h'),
                mark_price=data.get('mark_price'),
                index_price=data.get('index_price'),
                open_interest=data.get('open_interest')
            )
            self.session.add(snapshot)
        self.session.commit()
    
    # 日志相关
    def create_log(self, level: str, message: str, source: str = None, extra_data: dict = None):
        """创建日志记录"""
        log = SystemLog(
            level=level,
            message=message,
            source=source,
            extra_data=extra_data
        )
        self.session.add(log)
        self.session.commit()
    
    def get_logs(self, level: str = None, limit: int = 100):
        """获取日志"""
        query = self.session.query(SystemLog)
        if level and level != "all":
            query = query.filter(SystemLog.level == level)
        return query.order_by(SystemLog.timestamp.desc()).limit(limit).all()
    
    # 风险事件相关
    def create_risk_event(self, event_data: dict):
        """创建风险事件记录"""
        event = RiskEvent(**event_data)
        self.session.add(event)
        self.session.commit()
        return event
    
    # 账户快照相关
    def create_account_snapshot(self, snapshot_data: dict):
        """创建账户快照"""
        snapshot = AccountSnapshot(**snapshot_data)
        self.session.add(snapshot)
        self.session.commit()
        return snapshot
    
    def get_account_history(self, days: int = 30):
        """获取账户历史"""
        from_date = datetime.utcnow() - timedelta(days=days)
        return self.session.query(AccountSnapshot).filter(
            AccountSnapshot.timestamp >= from_date
        ).order_by(AccountSnapshot.timestamp).all()
    
    # 统计分析
    def get_trading_statistics(self, days: int = 30):
        """获取交易统计"""
        from_date = datetime.utcnow() - timedelta(days=days)
        
        trades = self.session.query(Trade).filter(
            Trade.close_time >= from_date,
            Trade.status == "closed"
        ).all()
        
        if not trades:
            return None
        
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl and t.pnl < 0]
        
        total_pnl = sum(t.net_pnl or t.pnl or 0 for t in trades)
        
        return {
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": len(winning_trades) / total_trades * 100 if total_trades > 0 else 0,
            "total_pnl": total_pnl,
            "average_win": sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0,
            "average_loss": sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0,
            "best_trade": max(trades, key=lambda t: t.pnl or 0) if trades else None,
            "worst_trade": min(trades, key=lambda t: t.pnl or 0) if trades else None
        }


if __name__ == "__main__":
    # 初始化数据库
    init_database()
    print("数据库初始化完成")



