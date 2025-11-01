"""
多用户交易API路由 - Multi-User Trading API
支持每个用户独立运行自己的交易系统

每个用户有：
- 独立的交易系统实例
- 独立的配置
- 独立的策略
- 独立的API密钥
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
from sqlalchemy.orm import Session

# 导入认证依赖
from api_auth import get_current_user, get_current_admin_user
# 导入数据库
from database_models import get_db, Trade, User, APIKey
# 导入多用户交易系统管理器
from trading_system_multi_user_manager import (
    get_multi_user_trading_manager,
    TradingSystemState
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["用户交易系统"])

# ============================================================================
# Pydantic 模型
# ============================================================================

class StartTradingRequest(BaseModel):
    """启动交易请求"""
    mode: str = Field(default="demo", description="运行模式 demo/testnet/live")
    symbols: List[str] = Field(default=["BTCUSDT"], description="交易对列表")
    check_interval: int = Field(default=60, ge=10, le=300, description="检查间隔(秒)")
    max_positions: int = Field(default=3, ge=1, le=10, description="最大持仓数")
    use_ai: bool = Field(default=True, description="是否使用AI决策")

class TradingSystemStatusResponse(BaseModel):
    """交易系统状态响应"""
    user_id: str
    username: str
    state: str
    is_running: bool
    config: Dict[str, Any]
    stats: Dict[str, Any]
    thread_alive: bool

class UserTradingConfigResponse(BaseModel):
    """用户交易配置响应"""
    has_bybit_key: bool
    has_deepseek_key: bool
    mode: str
    symbols: List[str]
    max_positions: int

# 获取多用户管理器
multi_user_manager = get_multi_user_trading_manager()

# ============================================================================
# 用户交易系统控制端点
# ============================================================================

@router.post("/trading/start")
async def start_user_trading_system(
    request: StartTradingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    启动当前用户的交易系统
    
    - 每个用户独立的交易系统实例
    - 使用用户自己的 API 密钥
    - 支持个性化配置
    """
    try:
        # 获取用户的 API 密钥（从数据库）
        user_api_keys = db.query(APIKey).filter(
            APIKey.user_id == current_user.id,
            APIKey.is_active == True
        ).first()
        
        # 准备配置
        config = {
            "mode": request.mode,
            "symbols": request.symbols,
            "check_interval": request.check_interval,
            "max_positions": request.max_positions,
            "use_ai": request.use_ai,
        }
        
        # 如果有 API 密钥，添加到配置
        if user_api_keys:
            config["bybit_api_key"] = user_api_keys.bybit_api_key
            config["bybit_api_secret"] = user_api_keys.bybit_api_secret
            config["deepseek_api_key"] = user_api_keys.deepseek_api_key
        
        # 启动用户的交易系统
        result = multi_user_manager.start_for_user(
            user_id=str(current_user.id),
            username=current_user.username,
            config=config
        )
        
        if result["success"]:
            logger.info(f"✅ 用户 {current_user.username} 启动了自己的交易系统")
        
        return result
    
    except Exception as e:
        logger.error(f"❌ 启动用户交易系统失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trading/stop")
async def stop_user_trading_system(
    current_user: User = Depends(get_current_user)
):
    """
    停止当前用户的交易系统
    
    - 只停止自己的交易系统
    - 不影响其他用户
    """
    try:
        result = multi_user_manager.stop_for_user(str(current_user.id))
        
        if result["success"]:
            logger.info(f"✅ 用户 {current_user.username} 停止了自己的交易系统")
        
        return result
    
    except Exception as e:
        logger.error(f"❌ 停止用户交易系统失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trading/restart")
async def restart_user_trading_system(
    request: Optional[StartTradingRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    重启当前用户的交易系统
    
    - 可以更新配置
    - 只影响自己的系统
    """
    try:
        # 准备新配置（如果提供）
        config = None
        if request:
            user_api_keys = db.query(APIKey).filter(
                APIKey.user_id == current_user.id,
                APIKey.is_active == True
            ).first()
            
            config = {
                "mode": request.mode,
                "symbols": request.symbols,
                "check_interval": request.check_interval,
                "max_positions": request.max_positions,
                "use_ai": request.use_ai,
            }
            
            if user_api_keys:
                config["bybit_api_key"] = user_api_keys.bybit_api_key
                config["bybit_api_secret"] = user_api_keys.bybit_api_secret
                config["deepseek_api_key"] = user_api_keys.deepseek_api_key
        
        # 重启
        result = multi_user_manager.restart_for_user(
            str(current_user.id),
            config
        )
        
        if result["success"]:
            logger.info(f"✅ 用户 {current_user.username} 重启了自己的交易系统")
        
        return result
    
    except Exception as e:
        logger.error(f"❌ 重启用户交易系统失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trading/status", response_model=TradingSystemStatusResponse)
async def get_user_trading_status(
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户的交易系统状态
    
    - 只查看自己的状态
    """
    try:
        status = multi_user_manager.get_status_for_user(str(current_user.id))
        
        if status is None:
            # 用户还没有交易系统，返回默认状态
            return TradingSystemStatusResponse(
                user_id=str(current_user.id),
                username=current_user.username,
                state="stopped",
                is_running=False,
                config={"mode": "demo", "symbols": []},
                stats={
                    "total_trades": 0,
                    "successful_trades": 0,
                    "failed_trades": 0,
                    "total_pnl": 0.0,
                    "active_positions": 0
                },
                thread_alive=False
            )
        
        return TradingSystemStatusResponse(**status)
    
    except Exception as e:
        logger.error(f"❌ 获取用户交易系统状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# 用户数据查询端点
# ============================================================================

@router.get("/positions")
async def get_user_positions(
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户的持仓
    
    - 只查看自己的持仓
    """
    try:
        positions = multi_user_manager.get_positions_for_user(str(current_user.id))
        return {
            "success": True,
            "positions": positions,
            "count": len(positions)
        }
    
    except Exception as e:
        logger.error(f"❌ 获取用户持仓失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trades")
async def get_user_trades(
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户的交易记录
    
    - 只查看自己的交易
    """
    try:
        trades = multi_user_manager.get_trades_for_user(
            str(current_user.id),
            limit=limit
        )
        return {
            "success": True,
            "trades": trades,
            "count": len(trades)
        }
    
    except Exception as e:
        logger.error(f"❌ 获取用户交易记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/config")
async def get_user_trading_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取当前用户的交易配置状态
    
    - 检查 API 密钥是否配置
    - 返回当前配置（不包含敏感信息）
    """
    try:
        # 获取用户状态
        status = multi_user_manager.get_status_for_user(str(current_user.id))
        
        # 检查 API 密钥
        user_api_keys = db.query(APIKey).filter(
            APIKey.user_id == current_user.id,
            APIKey.is_active == True
        ).first()
        
        has_bybit = bool(user_api_keys and user_api_keys.bybit_api_key)
        has_deepseek = bool(user_api_keys and user_api_keys.deepseek_api_key)
        
        if status:
            config = status["config"]
            return UserTradingConfigResponse(
                has_bybit_key=has_bybit,
                has_deepseek_key=has_deepseek,
                mode=config.get("mode", "demo"),
                symbols=config.get("symbols", []),
                max_positions=config.get("max_positions", 3)
            )
        else:
            return UserTradingConfigResponse(
                has_bybit_key=has_bybit,
                has_deepseek_key=has_deepseek,
                mode="demo",
                symbols=[],
                max_positions=3
            )
    
    except Exception as e:
        logger.error(f"❌ 获取用户配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# 管理员端点（查看所有用户）
# ============================================================================

@router.get("/admin/all-users-status")
async def get_all_users_trading_status(
    current_user: User = Depends(get_current_admin_user)
):
    """
    获取所有用户的交易系统状态（仅管理员）
    
    - 查看所有用户的运行情况
    - 系统监控和管理
    """
    try:
        all_status = multi_user_manager.get_all_users_status()
        running_users = multi_user_manager.get_running_users()
        
        return {
            "success": True,
            "total_users": len(all_status),
            "running_users": len(running_users),
            "users": all_status
        }
    
    except Exception as e:
        logger.error(f"❌ 获取所有用户状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin/stop-user/{user_id}")
async def admin_stop_user_trading(
    user_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """
    管理员停止指定用户的交易系统
    
    - 用于紧急情况
    - 系统维护
    """
    try:
        result = multi_user_manager.stop_for_user(user_id)
        
        if result["success"]:
            logger.info(f"✅ 管理员 {current_user.username} 停止了用户 {user_id} 的交易系统")
        
        return result
    
    except Exception as e:
        logger.error(f"❌ 管理员停止用户交易系统失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# 健康检查
# ============================================================================

@router.get("/health")
async def user_trading_health():
    """多用户交易系统健康检查"""
    running_count = len(multi_user_manager.get_running_users())
    total_count = len(multi_user_manager.user_systems)
    
    return {
        "status": "healthy",
        "mode": "multi-user",
        "total_users": total_count,
        "running_users": running_count
    }


