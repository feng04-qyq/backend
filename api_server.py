"""
Bybit AI交易系统 - Web API服务器
提供WebSocket实时推送和REST API接口供前端调用

技术栈: FastAPI + Socket.IO
功能:
1. WebSocket实时推送市场数据、AI决策、持仓信息
2. REST API查询历史数据、统计信息
3. 接收前端控制命令（紧急停止、配置修改等）
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
import asyncio
import logging
from datetime import datetime, timedelta
import os
from collections import deque
import threading

# 导入交易系统
try:
    from bybit_live_trading_system import LiveTradingEngine
    from trade_journal import get_trade_journal
except ImportError:
    print("请确保bybit_live_trading_system.py和trade_journal.py在同一目录")

app = FastAPI(
    title="Bybit AI Trading API",
    description="Bybit AI自动交易系统API接口",
    version="2.0.0"
)

# CORS配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应指定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# 全局变量和状态管理
# ============================================================================

trading_engine: Optional[LiveTradingEngine] = None
websocket_clients: List[WebSocket] = []
system_logs = deque(maxlen=1000)  # 最近1000条日志
last_market_data: Dict[str, Any] = {}
last_ai_decision: Dict[str, Any] = {}
last_position_update: Dict[str, Any] = {}

# ============================================================================
# Pydantic数据模型
# ============================================================================

class SystemStatus(BaseModel):
    """系统状态"""
    is_running: bool
    environment: str  # "testnet" / "demo" / "live"
    uptime_seconds: int
    total_trades: int
    balance: float
    current_position: Optional[str]
    
class ConfigUpdate(BaseModel):
    """配置更新请求"""
    key: str
    value: Any
    
class ManualTradeRequest(BaseModel):
    """手动交易请求"""
    action: str  # "LONG" / "SHORT" / "CLOSE"
    symbol: str
    position_size: float
    leverage: int
    stop_loss: Optional[float]
    take_profit: Optional[List[float]]

# ============================================================================
# WebSocket连接管理
# ============================================================================

class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """接受新连接"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logging.info(f"WebSocket客户端已连接，当前连接数: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
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
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# ============================================================================
# WebSocket端点
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket主端点
    实时推送系统状态、市场数据、AI决策等
    """
    await manager.connect(websocket)
    
    try:
        # 发送初始数据
        await websocket.send_json({
            "event": "connected",
            "message": "连接成功",
            "timestamp": datetime.now().isoformat()
        })
        
        # 发送当前状态
        if trading_engine:
            await websocket.send_json({
                "event": "system_status",
                "data": get_system_status(),
                "timestamp": datetime.now().isoformat()
            })
        
        # 保持连接，接收客户端消息
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # 处理客户端请求
            await handle_websocket_message(websocket, message)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logging.error(f"WebSocket错误: {e}")
        manager.disconnect(websocket)

async def handle_websocket_message(websocket: WebSocket, message: dict):
    """处理WebSocket消息"""
    event_type = message.get("type")
    
    if event_type == "ping":
        await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
    
    elif event_type == "subscribe":
        # 订阅特定事件（可选功能）
        pass
    
    elif event_type == "request_data":
        # 请求特定数据
        data_type = message.get("data_type")
        if data_type == "market":
            await websocket.send_json({
                "event": "market_update",
                "data": last_market_data,
                "timestamp": datetime.now().isoformat()
            })
        elif data_type == "position":
            await websocket.send_json({
                "event": "position_update",
                "data": last_position_update,
                "timestamp": datetime.now().isoformat()
            })

# ============================================================================
# REST API端点
# ============================================================================

@app.get("/")
async def root():
    """API根路径"""
    return {
        "name": "Bybit AI Trading API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "websocket": "/ws",
            "system": "/api/system/*",
            "market": "/api/market/*",
            "trades": "/api/trades/*",
            "positions": "/api/positions/*",
            "analytics": "/api/analytics/*",
            "logs": "/api/logs",
            "config": "/api/config/*"
        }
    }

@app.get("/api/system/status")
async def get_system_status_api():
    """获取系统状态"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="交易引擎未启动")
    
    return get_system_status()

def get_system_status() -> dict:
    """获取系统状态（内部函数）"""
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
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/market/data")
async def get_market_data(symbol: Optional[str] = None):
    """
    获取市场数据
    symbol: BTC/ETH/SOL (可选，不指定则返回所有)
    """
    if not trading_engine:
        raise HTTPException(status_code=503, detail="交易引擎未启动")
    
    if symbol:
        symbol_perpetual = f"{symbol}USDT_PERPETUAL"
        if symbol_perpetual in last_market_data:
            return {symbol: last_market_data[symbol_perpetual]}
        else:
            raise HTTPException(status_code=404, detail=f"未找到{symbol}的数据")
    
    return last_market_data

@app.get("/api/positions/current")
async def get_current_position():
    """获取当前持仓"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="交易引擎未启动")
    
    if not trading_engine.current_position:
        return {"position": None, "message": "当前无持仓"}
    
    return last_position_update

@app.get("/api/trades")
async def get_trades(limit: int = 20, offset: int = 0):
    """
    获取交易历史
    limit: 返回条数
    offset: 偏移量
    """
    try:
        trade_journal = get_trade_journal()
        trades = trade_journal.get_recent_trades(limit + offset)
        
        # 分页
        paginated_trades = trades[offset:offset + limit]
        
        return {
            "total": len(trades),
            "limit": limit,
            "offset": offset,
            "trades": paginated_trades
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取交易历史失败: {str(e)}")

@app.get("/api/analytics")
async def get_analytics(period: str = "30d"):
    """
    获取统计分析数据
    period: 时间范围 (7d/30d/90d/all)
    """
    try:
        trade_journal = get_trade_journal()
        
        # 解析时间范围
        days_map = {"7d": 7, "30d": 30, "90d": 90, "all": 9999}
        days = days_map.get(period, 30)
        
        # 获取统计数据
        stats = trade_journal.get_statistics(days=days)
        
        return {
            "period": period,
            "statistics": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {str(e)}")

@app.get("/api/logs")
async def get_logs(level: str = "all", limit: int = 100):
    """
    获取系统日志
    level: all/INFO/WARNING/ERROR
    limit: 返回条数
    """
    filtered_logs = system_logs
    
    if level != "all":
        filtered_logs = [log for log in system_logs if log.get("level") == level]
    
    return {
        "total": len(filtered_logs),
        "limit": limit,
        "logs": list(filtered_logs)[-limit:]
    }

@app.get("/api/ai/history")
async def get_ai_history(limit: int = 50):
    """获取AI决策历史"""
    # TODO: 实现AI决策历史记录
    return {
        "total": 0,
        "limit": limit,
        "decisions": []
    }

@app.post("/api/emergency/stop")
async def emergency_stop():
    """紧急停止交易"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="交易引擎未启动")
    
    try:
        trading_engine.stop()
        
        # 广播停止事件
        await manager.broadcast({
            "event": "emergency_stop",
            "message": "系统已紧急停止",
            "timestamp": datetime.now().isoformat()
        })
        
        return {"success": True, "message": "系统已停止"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止失败: {str(e)}")

@app.post("/api/config/update")
async def update_config(config: ConfigUpdate):
    """更新配置"""
    # TODO: 实现配置更新
    return {"success": True, "key": config.key, "value": config.value}

@app.post("/api/trade/manual")
async def manual_trade(trade: ManualTradeRequest):
    """手动交易"""
    # TODO: 实现手动交易
    return {"success": True, "message": "手动交易功能开发中"}

# ============================================================================
# 后台任务：推送实时数据
# ============================================================================

async def broadcast_market_data():
    """定期广播市场数据"""
    while True:
        try:
            if trading_engine and trading_engine.is_running:
                await manager.broadcast({
                    "event": "market_update",
                    "data": last_market_data,
                    "timestamp": datetime.now().isoformat()
                })
        except Exception as e:
            logging.error(f"广播市场数据失败: {e}")
        
        await asyncio.sleep(3)  # 每3秒推送一次

async def broadcast_system_status():
    """定期广播系统状态"""
    while True:
        try:
            if trading_engine:
                await manager.broadcast({
                    "event": "system_status",
                    "data": get_system_status(),
                    "timestamp": datetime.now().isoformat()
                })
        except Exception as e:
            logging.error(f"广播系统状态失败: {e}")
        
        await asyncio.sleep(5)  # 每5秒推送一次

# ============================================================================
# 启动和关闭事件
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """API服务器启动事件"""
    global trading_engine
    
    logging.info("🚀 API服务器启动中...")
    
    # 启动后台任务
    asyncio.create_task(broadcast_market_data())
    asyncio.create_task(broadcast_system_status())
    
    logging.info("✅ API服务器启动成功")
    logging.info("📡 WebSocket端点: ws://localhost:8000/ws")
    logging.info("🌐 REST API文档: http://localhost:8000/docs")

@app.on_event("shutdown")
async def shutdown_event():
    """API服务器关闭事件"""
    logging.info("🛑 API服务器关闭中...")
    
    # 关闭所有WebSocket连接
    for connection in manager.active_connections:
        await connection.close()
    
    logging.info("✅ API服务器已关闭")

# ============================================================================
# 工具函数：与交易引擎交互
# ============================================================================

def attach_trading_engine(engine: LiveTradingEngine):
    """
    附加交易引擎实例
    从主程序调用此函数，将交易引擎传递给API服务器
    """
    global trading_engine
    trading_engine = engine
    logging.info("✅ 交易引擎已附加到API服务器")

def update_market_data(data: dict):
    """更新市场数据（由交易引擎调用）"""
    global last_market_data
    last_market_data = data
    
    # 异步广播
    asyncio.create_task(manager.broadcast({
        "event": "market_update",
        "data": data,
        "timestamp": datetime.now().isoformat()
    }))

def update_ai_decision(decision: dict):
    """更新AI决策（由交易引擎调用）"""
    global last_ai_decision
    last_ai_decision = decision
    
    # 异步广播
    asyncio.create_task(manager.broadcast({
        "event": "ai_decision",
        "data": decision,
        "timestamp": datetime.now().isoformat()
    }))

def update_position(position: dict):
    """更新持仓信息（由交易引擎调用）"""
    global last_position_update
    last_position_update = position
    
    # 异步广播
    asyncio.create_task(manager.broadcast({
        "event": "position_update",
        "data": position,
        "timestamp": datetime.now().isoformat()
    }))

def log_event(level: str, message: str):
    """记录日志事件"""
    log_entry = {
        "level": level,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    system_logs.append(log_entry)
    
    # 广播日志
    asyncio.create_task(manager.broadcast({
        "event": "log",
        "data": log_entry
    }))

# ============================================================================
# 主程序入口（测试用）
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 启动API服务器
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )



