"""
WebSocket 实时推送 API
每0.1秒推送持仓、盈亏、余额等UI数据
"""

from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi import APIRouter
from typing import Dict, Set, Optional
import asyncio
import json
import logging
from datetime import datetime

from api_auth import verify_token_ws
from trading_system_multi_user_manager import get_multi_user_trading_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# WebSocket 连接管理器
# ============================================================================

class ConnectionManager:
    """管理所有WebSocket连接"""
    
    def __init__(self):
        # user_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """连接WebSocket"""
        await websocket.accept()
        
        async with self._lock:
            if user_id not in self.active_connections:
                self.active_connections[user_id] = set()
            self.active_connections[user_id].add(websocket)
        
        logger.info(f"✅ 用户 {user_id} 的WebSocket已连接，当前连接数: {len(self.active_connections[user_id])}")
    
    async def disconnect(self, websocket: WebSocket, user_id: str):
        """断开WebSocket"""
        async with self._lock:
            if user_id in self.active_connections:
                self.active_connections[user_id].discard(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
        
        logger.info(f"❌ 用户 {user_id} 的WebSocket已断开")
    
    async def send_to_user(self, user_id: str, message: dict):
        """发送消息给指定用户的所有连接"""
        if user_id not in self.active_connections:
            return
        
        disconnected = set()
        
        for websocket in self.active_connections[user_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"发送消息失败: {e}")
                disconnected.add(websocket)
        
        # 清理断开的连接
        if disconnected:
            async with self._lock:
                self.active_connections[user_id] -= disconnected
    
    async def broadcast(self, message: dict):
        """广播消息给所有用户"""
        for user_id in list(self.active_connections.keys()):
            await self.send_to_user(user_id, message)
    
    def get_connected_users(self) -> list:
        """获取所有已连接的用户ID"""
        return list(self.active_connections.keys())


# 全局连接管理器
manager = ConnectionManager()


# ============================================================================
# WebSocket 端点
# ============================================================================

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = None
):
    """
    WebSocket 实时数据推送
    
    连接地址: ws://localhost:8000/ws?token=<your_jwt_token>
    
    推送频率:
    - 持仓/盈亏/余额: 0.1秒（100ms）
    - 系统状态: 1秒
    - 交易事件: 即时推送
    """
    
    # 验证token
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    try:
        # 验证JWT token
        user_data = verify_token_ws(token)
        if not user_data:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        user_id = str(user_data.get("user_id") or user_data.get("sub"))
        username = user_data.get("username", "unknown")
        
    except Exception as e:
        logger.error(f"Token验证失败: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    # 连接
    await manager.connect(websocket, user_id)
    
    try:
        # 发送欢迎消息
        await websocket.send_json({
            "event": "connected",
            "data": {
                "user_id": user_id,
                "username": username,
                "timestamp": datetime.now().isoformat()
            }
        })
        
        # 启动数据推送任务
        push_task = asyncio.create_task(
            push_realtime_data(websocket, user_id)
        )
        
        # 监听客户端消息
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0  # 30秒超时
                )
                
                # 处理客户端消息
                message = json.loads(data)
                await handle_client_message(websocket, user_id, message)
                
            except asyncio.TimeoutError:
                # 发送心跳
                await websocket.send_json({
                    "event": "ping",
                    "data": {"timestamp": datetime.now().isoformat()}
                })
            
    except WebSocketDisconnect:
        logger.info(f"用户 {user_id} 主动断开连接")
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
    finally:
        # 取消推送任务
        if 'push_task' in locals():
            push_task.cancel()
        
        # 断开连接
        await manager.disconnect(websocket, user_id)


async def push_realtime_data(websocket: WebSocket, user_id: str):
    """
    推送实时数据
    - 持仓/盈亏/余额: 每0.1秒
    - 系统状态: 每1秒
    """
    
    multi_user_manager = get_multi_user_trading_manager()
    
    update_counter = 0
    
    try:
        while True:
            update_counter += 1
            
            # 每0.1秒推送持仓数据
            try:
                # 获取用户的交易系统状态
                status = multi_user_manager.get_status_for_user(user_id)
                
                if status:
                    # 获取实时持仓
                    positions = multi_user_manager.get_positions_for_user(user_id)
                    
                    # 推送持仓更新
                    await websocket.send_json({
                        "event": "positions_update",
                        "data": {
                            "positions": positions,
                            "timestamp": datetime.now().isoformat()
                        }
                    })
                    
                    # 每1秒推送系统状态（10个周期）
                    if update_counter % 10 == 0:
                        await websocket.send_json({
                            "event": "status_update",
                            "data": {
                                "status": status,
                                "timestamp": datetime.now().isoformat()
                            }
                        })
                
            except Exception as e:
                logger.error(f"推送数据失败: {e}")
            
            # 等待0.1秒
            await asyncio.sleep(0.1)
            
    except asyncio.CancelledError:
        logger.info(f"用户 {user_id} 的数据推送任务已取消")


async def handle_client_message(websocket: WebSocket, user_id: str, message: dict):
    """处理客户端消息"""
    
    event = message.get("event")
    data = message.get("data", {})
    
    if event == "pong":
        # 心跳响应
        pass
    
    elif event == "subscribe":
        # 订阅特定事件
        logger.info(f"用户 {user_id} 订阅事件: {data}")
    
    elif event == "unsubscribe":
        # 取消订阅
        logger.info(f"用户 {user_id} 取消订阅: {data}")
    
    else:
        logger.warning(f"未知事件: {event}")


# ============================================================================
# 事件推送函数（供其他模块调用）
# ============================================================================

async def notify_trade_opened(user_id: str, trade: dict, position: dict):
    """通知新交易开仓"""
    await manager.send_to_user(user_id, {
        "event": "trade_opened",
        "data": {
            "trade": trade,
            "position": position,
            "timestamp": datetime.now().isoformat()
        }
    })


async def notify_trade_closed(user_id: str, trade_id: str, close_data: dict):
    """通知交易平仓"""
    await manager.send_to_user(user_id, {
        "event": "trade_closed",
        "data": {
            "trade_id": trade_id,
            **close_data,
            "timestamp": datetime.now().isoformat()
        }
    })


async def notify_ai_decision(user_id: str, decision: dict):
    """通知新的AI决策"""
    await manager.send_to_user(user_id, {
        "event": "ai_decision",
        "data": {
            "decision": decision,
            "timestamp": datetime.now().isoformat()
        }
    })


async def notify_balance_update(user_id: str, balance: float):
    """通知余额更新"""
    await manager.send_to_user(user_id, {
        "event": "balance_updated",
        "data": {
            "balance": balance,
            "timestamp": datetime.now().isoformat()
        }
    })


async def notify_system_status_changed(user_id: str, status: dict):
    """通知系统状态变化"""
    await manager.send_to_user(user_id, {
        "event": "system_status_changed",
        "data": {
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
    })


async def notify_all_users(event: str, data: dict):
    """通知所有用户"""
    await manager.broadcast({
        "event": event,
        "data": data
    })


# ============================================================================
# 辅助函数
# ============================================================================

def get_connection_manager() -> ConnectionManager:
    """获取连接管理器"""
    return manager


