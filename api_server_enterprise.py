"""
Bybit AI交易系统 - 企业级API服务器
包含：认证、数据库集成、监控、限流、日志等完整功能

版本: v3.0 Enterprise Edition
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import json
import asyncio
import logging
from datetime import datetime, timedelta
import os
from collections import deque
import threading
import time
import secrets
import hashlib
from functools import wraps

# 数据库
from database_models import (
    get_db, DatabaseManager, Trade, AIDecision, MarketData,
    SystemLog, RiskEvent, AccountSnapshot, User, APIAccessLog
)
from sqlalchemy.orm import Session

# 导入交易系统
try:
    from bybit_live_trading_system import LiveTradingEngine
    from trade_journal import get_trade_journal
except ImportError:
    print("请确保bybit_live_trading_system.py在同一目录")

# ============================================================================
# FastAPI应用初始化
# ============================================================================

app = FastAPI(
    title="Bybit AI Trading API - Enterprise",
    description="企业级加密货币AI自动交易系统API",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ============================================================================
# 中间件配置
# ============================================================================

# CORS（跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gzip压缩
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ============================================================================
# 安全和认证
# ============================================================================

security = HTTPBearer()

# API密钥存储（生产环境应使用数据库）
API_KEYS = {
    os.getenv("API_KEY", "dev_api_key_123456"): {
        "name": "Development Key",
        "permissions": ["read", "write", "admin"]
    }
}

def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证API密钥"""
    token = credentials.credentials
    if token not in API_KEYS:
        raise HTTPException(status_code=401, detail="无效的API密钥")
    return API_KEYS[token]

# 可选认证（某些端点不需要认证）
def optional_verify_api_key(authorization: Optional[str] = Header(None)):
    """可选的API密钥验证"""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        return API_KEYS.get(token)
    return None

# ============================================================================
# 限流器
# ============================================================================

class RateLimiter:
    """简单的限流器"""
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}
    
    def is_allowed(self, key: str) -> bool:
        """检查是否允许请求"""
        now = time.time()
        
        # 清理过期记录
        if key in self.requests:
            self.requests[key] = [
                timestamp for timestamp in self.requests[key]
                if now - timestamp < self.window_seconds
            ]
        else:
            self.requests[key] = []
        
        # 检查限流
        if len(self.requests[key]) >= self.max_requests:
            return False
        
        self.requests[key].append(now)
        return True

rate_limiter = RateLimiter(max_requests=100, window_seconds=60)

# ============================================================================
# 请求日志中间件
# ============================================================================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录所有HTTP请求"""
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = (time.time() - start_time) * 1000
    
    # 记录到数据库（异步）
    asyncio.create_task(log_api_access(
        endpoint=str(request.url.path),
        method=request.method,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent"),
        status_code=response.status_code,
        response_time_ms=process_time
    ))
    
    return response

async def log_api_access(endpoint: str, method: str, ip_address: str, 
                        user_agent: str, status_code: int, response_time_ms: float):
    """记录API访问日志到数据库"""
    try:
        db = DatabaseManager()
        from database_models import APIAccessLog
        log = APIAccessLog(
            endpoint=endpoint,
            method=method,
            ip_address=ip_address,
            user_agent=user_agent,
            status_code=status_code,
            response_time_ms=response_time_ms
        )
        db.session.add(log)
        db.session.commit()
        db.close()
    except Exception as e:
        logging.error(f"记录API访问日志失败: {e}")

# ============================================================================
# 全局变量
# ============================================================================

trading_engine: Optional[LiveTradingEngine] = None
websocket_clients: List[WebSocket] = []
db_manager = DatabaseManager()

# ============================================================================
# Pydantic模型
# ============================================================================

class TradeResponse(BaseModel):
    """交易响应模型"""
    id: int
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    close_price: Optional[float]
    pnl: Optional[float]
    pnl_pct: Optional[float]
    status: str
    entry_time: datetime
    close_time: Optional[datetime]

class AIDecisionResponse(BaseModel):
    """AI决策响应模型"""
    id: int
    decision_id: str
    action: str
    target_symbol: str
    confidence: int
    reason: str
    executed: bool
    created_at: datetime

class StatisticsResponse(BaseModel):
    """统计响应模型"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    average_win: float
    average_loss: float

class EmergencyStopRequest(BaseModel):
    """紧急停止请求"""
    reason: Optional[str] = "手动停止"
    force: bool = False

class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""
    key: str
    value: Any
    description: Optional[str] = None

# ============================================================================
# WebSocket连接管理
# ============================================================================

class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_info: Dict[WebSocket, Dict] = {}
    
    async def connect(self, websocket: WebSocket, client_info: dict = None):
        """接受新连接"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_info[websocket] = client_info or {}
        logging.info(f"WebSocket客户端已连接，当前连接数: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            self.connection_info.pop(websocket, None)
        logging.info(f"WebSocket客户端已断开，当前连接数: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """广播消息给所有客户端"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logging.error(f"发送消息失败: {e}")
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)
    
    async def send_personal(self, websocket: WebSocket, message: dict):
        """发送消息给特定客户端"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logging.error(f"发送个人消息失败: {e}")
            self.disconnect(websocket)

manager = ConnectionManager()

# ============================================================================
# WebSocket端点
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket主端点"""
    await manager.connect(websocket, {
        "connected_at": datetime.now(),
        "ip": websocket.client.host
    })
    
    try:
        # 发送欢迎消息
        await websocket.send_json({
            "event": "connected",
            "message": "欢迎连接Bybit AI Trading API",
            "version": "3.0.0",
            "timestamp": datetime.now().isoformat()
        })
        
        # 发送初始数据
        if trading_engine:
            await websocket.send_json({
                "event": "system_status",
                "data": await get_system_status_data(),
                "timestamp": datetime.now().isoformat()
            })
        
        # 保持连接
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            await handle_websocket_message(websocket, message)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logging.error(f"WebSocket错误: {e}")
        manager.disconnect(websocket)

async def handle_websocket_message(websocket: WebSocket, message: dict):
    """处理WebSocket消息"""
    msg_type = message.get("type")
    
    if msg_type == "ping":
        await manager.send_personal(websocket, {
            "type": "pong",
            "timestamp": datetime.now().isoformat()
        })
    
    elif msg_type == "subscribe":
        # 订阅特定事件
        events = message.get("events", [])
        manager.connection_info[websocket]["subscriptions"] = events
        await manager.send_personal(websocket, {
            "type": "subscribed",
            "events": events,
            "timestamp": datetime.now().isoformat()
        })

# ============================================================================
# REST API端点 - 基础
# ============================================================================

@app.get("/")
async def root():
    """API根路径"""
    return {
        "name": "Bybit AI Trading API - Enterprise Edition",
        "version": "3.0.0",
        "status": "running",
        "database": "PostgreSQL 17.6",
        "features": [
            "实时WebSocket推送",
            "REST API接口",
            "数据库持久化",
            "认证和授权",
            "限流保护",
            "日志记录",
            "性能监控"
        ],
        "endpoints": {
            "websocket": "/ws",
            "docs": "/docs",
            "health": "/health",
            "system": "/api/system/*",
            "market": "/api/market/*",
            "trades": "/api/trades/*",
            "positions": "/api/positions/*",
            "analytics": "/api/analytics/*",
            "logs": "/api/logs",
            "config": "/api/config/*"
        }
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database": "connected",
        "trading_engine": "running" if trading_engine and trading_engine.is_running else "stopped",
        "websocket_connections": len(manager.active_connections)
    }

# ============================================================================
# REST API端点 - 系统
# ============================================================================

@app.get("/api/system/status")
async def get_system_status():
    """获取系统状态"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="交易引擎未启动")
    
    return await get_system_status_data()

async def get_system_status_data() -> dict:
    """获取系统状态数据（内部函数）"""
    if not trading_engine:
        return {"error": "交易引擎未启动"}
    
    return {
        "is_running": trading_engine.is_running,
        "environment": "demo" if trading_engine.use_demo else ("testnet" if trading_engine.use_testnet else "live"),
        "total_trades": trading_engine.total_trades,
        "successful_trades": trading_engine.successful_trades,
        "failed_trades": trading_engine.failed_trades,
        "current_symbol": trading_engine.current_symbol or "NONE",
        "current_position": trading_engine.current_position or "NONE",
        "trailing_stop_updates": trading_engine.trailing_stop_updates,
        "uptime_seconds": int(time.time() - getattr(trading_engine, 'start_time', time.time())),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/system/metrics")
async def get_system_metrics(auth: dict = Depends(verify_api_key)):
    """获取系统性能指标"""
    import psutil
    
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory": {
            "total": psutil.virtual_memory().total,
            "available": psutil.virtual_memory().available,
            "percent": psutil.virtual_memory().percent
        },
        "disk": {
            "total": psutil.disk_usage('/').total,
            "used": psutil.disk_usage('/').used,
            "percent": psutil.disk_usage('/').percent
        },
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# REST API端点 - 交易
# ============================================================================

@app.get("/api/trades", response_model=Dict[str, Any])
async def get_trades(
    limit: int = 20,
    offset: int = 0,
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取交易历史"""
    query = db.query(Trade).order_by(Trade.created_at.desc())
    
    if status:
        query = query.filter(Trade.status == status)
    if symbol:
        query = query.filter(Trade.symbol == symbol)
    
    total = query.count()
    trades = query.offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "trades": [trade_to_dict(t) for t in trades]
    }

@app.get("/api/trades/{trade_id}")
async def get_trade_detail(trade_id: str, db: Session = Depends(get_db)):
    """获取交易详情"""
    trade = db.query(Trade).filter(Trade.trade_id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="交易记录未找到")
    
    return trade_to_dict(trade)

def trade_to_dict(trade: Trade) -> dict:
    """交易对象转字典"""
    return {
        "id": trade.id,
        "trade_id": trade.trade_id,
        "symbol": trade.symbol,
        "side": trade.side,
        "order_type": trade.order_type,
        "entry_price": trade.entry_price,
        "close_price": trade.close_price,
        "position_size": trade.position_size,
        "leverage": trade.leverage,
        "stop_loss": trade.stop_loss,
        "take_profit": trade.take_profit,
        "pnl": trade.pnl,
        "pnl_pct": trade.pnl_pct,
        "fees": trade.fees,
        "net_pnl": trade.net_pnl,
        "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
        "close_time": trade.close_time.isoformat() if trade.close_time else None,
        "hold_duration_seconds": trade.hold_duration_seconds,
        "entry_reason": trade.entry_reason,
        "close_reason": trade.close_reason,
        "status": trade.status,
        "trailing_stop_updates": trade.trailing_stop_updates
    }

# ============================================================================
# REST API端点 - AI决策
# ============================================================================

@app.get("/api/ai/decisions")
async def get_ai_decisions(
    limit: int = 50,
    offset: int = 0,
    action: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取AI决策历史"""
    query = db.query(AIDecision).order_by(AIDecision.created_at.desc())
    
    if action:
        query = query.filter(AIDecision.action == action)
    
    total = query.count()
    decisions = query.offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "decisions": [decision_to_dict(d) for d in decisions]
    }

def decision_to_dict(decision: AIDecision) -> dict:
    """AI决策对象转字典"""
    return {
        "id": decision.id,
        "decision_id": decision.decision_id,
        "action": decision.action,
        "target_symbol": decision.target_symbol,
        "confidence": decision.confidence,
        "market_state": decision.market_state,
        "order_type": decision.order_type,
        "entry_price": decision.entry_price,
        "position_size": decision.position_size,
        "leverage": decision.leverage,
        "stop_loss": decision.stop_loss,
        "take_profit": decision.take_profit,
        "reason": decision.reason,
        "risk_reward_ratio": decision.risk_reward_ratio,
        "executed": decision.executed,
        "execution_time": decision.execution_time.isoformat() if decision.execution_time else None,
        "created_at": decision.created_at.isoformat()
    }

# ============================================================================
# REST API端点 - 统计分析
# ============================================================================

@app.get("/api/analytics/statistics")
async def get_statistics(period: str = "30d", db: Session = Depends(get_db)):
    """获取交易统计"""
    days_map = {"7d": 7, "30d": 30, "90d": 90, "all": 9999}
    days = days_map.get(period, 30)
    
    from_date = datetime.utcnow() - timedelta(days=days)
    
    trades = db.query(Trade).filter(
        Trade.close_time >= from_date,
        Trade.status == "closed"
    ).all()
    
    if not trades:
        return {
            "period": period,
            "total_trades": 0,
            "statistics": {}
        }
    
    winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
    losing_trades = [t for t in trades if t.pnl and t.pnl < 0]
    
    total_pnl = sum(t.net_pnl or t.pnl or 0 for t in trades)
    total_wins = sum(t.pnl for t in winning_trades)
    total_losses = sum(abs(t.pnl) for t in losing_trades)
    
    return {
        "period": period,
        "total_trades": len(trades),
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate": len(winning_trades) / len(trades) * 100 if trades else 0,
        "total_pnl": total_pnl,
        "average_win": total_wins / len(winning_trades) if winning_trades else 0,
        "average_loss": total_losses / len(losing_trades) if losing_trades else 0,
        "profit_factor": total_wins / total_losses if total_losses > 0 else 0,
        "largest_win": max(t.pnl for t in trades if t.pnl) if trades else 0,
        "largest_loss": min(t.pnl for t in trades if t.pnl) if trades else 0,
        "avg_hold_duration": sum(t.hold_duration_seconds or 0 for t in trades) / len(trades) if trades else 0
    }

# ============================================================================
# REST API端点 - 控制
# ============================================================================

@app.post("/api/emergency/stop")
async def emergency_stop(request: EmergencyStopRequest, auth: dict = Depends(verify_api_key)):
    """紧急停止交易"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="交易引擎未启动")
    
    try:
        trading_engine.stop()
        
        # 广播停止事件
        await manager.broadcast({
            "event": "emergency_stop",
            "data": {
                "reason": request.reason,
                "timestamp": datetime.now().isoformat()
            }
        })
        
        # 记录日志
        db_manager.create_log(
            level="WARNING",
            message=f"紧急停止: {request.reason}",
            source="api",
            extra_data={"forced": request.force}
        )
        
        return {
            "success": True,
            "message": "系统已停止",
            "reason": request.reason,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止失败: {str(e)}")

# ============================================================================
# 启动和关闭事件
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """API服务器启动事件"""
    logging.info("🚀 企业级API服务器启动中...")
    
    # 初始化数据库
    try:
        from database_models import init_database
        init_database()
        logging.info("✅ 数据库初始化完成")
    except Exception as e:
        logging.error(f"❌ 数据库初始化失败: {e}")
    
    # 启动后台任务
    asyncio.create_task(broadcast_market_data())
    asyncio.create_task(broadcast_system_status())
    asyncio.create_task(save_market_data_periodically())
    
    logging.info("✅ 企业级API服务器启动成功")
    logging.info("📡 WebSocket: ws://localhost:8000/ws")
    logging.info("🌐 REST API: http://localhost:8000/docs")

@app.on_event("shutdown")
async def shutdown_event():
    """API服务器关闭事件"""
    logging.info("🛑 API服务器关闭中...")
    
    for connection in manager.active_connections:
        await connection.close()
    
    db_manager.close()
    
    logging.info("✅ API服务器已关闭")

# ============================================================================
# 后台任务
# ============================================================================

async def broadcast_market_data():
    """定期广播市场数据"""
    while True:
        try:
            if trading_engine and trading_engine.is_running:
                # TODO: 获取实际市场数据
                await manager.broadcast({
                    "event": "market_update",
                    "data": {},
                    "timestamp": datetime.now().isoformat()
                })
        except Exception as e:
            logging.error(f"广播市场数据失败: {e}")
        
        await asyncio.sleep(3)

async def broadcast_system_status():
    """定期广播系统状态"""
    while True:
        try:
            if trading_engine:
                await manager.broadcast({
                    "event": "system_status",
                    "data": await get_system_status_data(),
                    "timestamp": datetime.now().isoformat()
                })
        except Exception as e:
            logging.error(f"广播系统状态失败: {e}")
        
        await asyncio.sleep(5)

async def save_market_data_periodically():
    """定期保存市场数据到数据库"""
    while True:
        try:
            # TODO: 保存市场数据
            pass
        except Exception as e:
            logging.error(f"保存市场数据失败: {e}")
        
        await asyncio.sleep(60)

# ============================================================================
# 工具函数
# ============================================================================

def attach_trading_engine(engine: LiveTradingEngine):
    """附加交易引擎"""
    global trading_engine
    trading_engine = engine
    if not hasattr(engine, 'start_time'):
        engine.start_time = time.time()
    logging.info("✅ 交易引擎已附加到API服务器")

# ============================================================================
# 主程序入口
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )



