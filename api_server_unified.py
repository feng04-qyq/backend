"""
统一API服务器 - 集成所有功能模块
整合认证、配置管理、交易等所有API端点

版本: v3.1 Unified
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import uvicorn
import logging
import json
import os
from pathlib import Path
from dotenv import load_dotenv

# 先加载环境变量（包含DATABASE_URL、JWT配置等）
ENV_PATH = Path(__file__).resolve().parent / ".env"
loaded_primary = load_dotenv(ENV_PATH, override=True)
loaded_secondary = load_dotenv(override=False)

print(f"[api_server_unified] load_dotenv primary={loaded_primary} secondary={loaded_secondary} path={ENV_PATH}")

# 现在加载依赖模块（确保环境变量已就绪）
from api_bridge_unified import router as bridge_router
from api_auth import router as auth_router, get_current_user, get_current_admin_user
from fastapi import APIRouter

try:
    from config_manager_api import router as config_router
except ImportError:
    print("⚠️ config_manager_api未找到，将创建基础配置路由")
    config_router = APIRouter()

try:
    from trading_api import router as trading_router
except ImportError:
    print("⚠️ trading_api未找到，交易功能将不可用")
    trading_router = APIRouter()

# 注意：用户管理功能已经在 api_bridge_unified.py 中实现
# 这里不再需要重复的用户管理路由

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# FastAPI应用初始化
# ============================================================================

app = FastAPI(
    title="Bybit AI Trading API - Unified",
    description="统一加密货币AI自动交易系统API",
    version="3.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ============================================================================
# 中间件配置
# ============================================================================

# CORS（跨域）- 根据环境变量动态配置
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "https://wxf888.top",  # 生产环境域名
    "https://www.wxf888.top",
    "https://api.wxf888.top",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# 注册所有路由
# ============================================================================

# 认证路由 (JWT) - auth_router 已经包含 /api/auth 前缀
app.include_router(auth_router)

# 配置管理路由 - config_router 已经包含 /api/config 前缀
# 先注册基础路由，桥接层路由后注册以覆盖相同路径
app.include_router(
    config_router,
    tags=["配置管理"]
)

# 桥接层路由最后注册，以覆盖可能存在冲突的路由（如 /api/users, /api/config）
# FastAPI 路由匹配：后注册的路由会覆盖先注册的相同路径路由
app.include_router(bridge_router, tags=["🌉 统一API桥接"])

# 注意：用户管理路由已经在 api_bridge_unified 中实现，不需要重复注册

# 交易路由 - 需要添加前缀
app.include_router(
    trading_router,
    prefix="/api",
    tags=["交易"]
)

# ============================================================================
# 基础端点
# ============================================================================

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Bybit AI Trading System API",
        "version": "3.1.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "auth": "/api/auth",
            "config": "/api/config",
            "trading": "/api/trades",
            "positions": "/api/positions",
            "market": "/api/market",
            "health": "/health"
        }
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": "3.1.0",
        "timestamp": "2025-10-30"
    }

# ============================================================================
# WebSocket端点（占位符）
# ============================================================================

active_connections = []

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    """
    WebSocket端点
    用于实时数据推送
    """
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        logger.info(f"WebSocket连接建立: {websocket.client}")
        
        # 发送连接成功消息
        await websocket.send_json({
            "event": "connected",
            "data": {
                "success": True,
                "message": "WebSocket连接成功"
            }
        })
        
        # 保持连接
        while True:
            # 接收消息
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # 回显消息（测试用）
            await websocket.send_json({
                "event": "message",
                "data": message
            })
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket连接断开: {websocket.client}")
        active_connections.remove(websocket)
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)

# ============================================================================
# 错误处理
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """HTTP异常处理"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """通用异常处理"""
    logger.error(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "内部服务器错误"}
    )

# ============================================================================
# 启动配置
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 Bybit AI Trading System - Unified API Server")
    print("="*60)
    print(f"📡 服务地址: http://0.0.0.0:8000")
    print(f"📚 API文档: http://localhost:8000/docs")
    print(f"🔐 默认登录: admin / admin123")
    print("="*60 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )



