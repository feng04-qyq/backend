"""
统一 API 桥接层（API Bridge）
=============================

定位：为前端提供稳定的接口外观，屏蔽后端多模块差异，便于对接。
核心职责：
  • 汇聚并标准化账户、交易、统计等常用数据
  • 自动适配单用户与多用户部署模式
  • 封装公共响应结构与错误处理（不改动核心交易逻辑）
  • 根据场景提供缓存、兜底数据（例如本地交易日志）
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
import logging
import asyncio
import time
import json
from pathlib import Path

# 导入认证
from api_auth import get_current_user, get_current_admin_user, User
# 导入数据库
from database_models import get_db, Trade, AIDecision, AccountSnapshot, APIKey

# 导入管理器（不修改核心文件，只导入）
try:
    from trading_system_multi_user_manager import get_multi_user_trading_manager
    MULTI_USER_MODE = True
except ImportError:
    from trading_system_manager import get_trading_system_manager
    MULTI_USER_MODE = False

logger = logging.getLogger(__name__)
# ============================================================================
# 辅助工具：交易日志与实时余额
# ============================================================================


def _journal_directory() -> Path:
    """返回交易日志目录，若不存在则由调用方处理。"""
    return Path("trade_journals")


def load_trades_from_journal(limit: int = 100) -> List[Dict[str, Any]]:
    """从本地 JSON 日志中加载交易（用于数据库缺失时兜底）。"""

    journal_dir = _journal_directory()
    if not journal_dir.exists():
        return []

    trades: List[Dict[str, Any]] = []

    journal_files = sorted(journal_dir.glob("trade_journal_*.json"), reverse=True)
    for file_path in journal_files:
        try:
            with file_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"无法解析交易日志 {file_path}: {exc}")
            continue

        for entry in data.get("trades", []):
            trades.append(entry)
            if len(trades) >= limit:
                break

        if len(trades) >= limit:
            break

    normalised: List[Dict[str, Any]] = []
    for entry in trades[:limit]:
        trade_id = entry.get("trade_id") or entry.get("id")
        status = entry.get("status", "OPEN").lower()
        side_raw = entry.get("action") or entry.get("side") or ""
        side = "Buy" if str(side_raw).upper() in {"LONG", "BUY"} else "Sell"

        open_time = entry.get("open_time") or entry.get("entry_time")
        close_time = entry.get("close_time")

        normalised.append({
            "trade_id": trade_id,
            "symbol": entry.get("symbol"),
            "side": side,
            "entry_price": entry.get("entry_price"),
            "close_price": entry.get("close_price"),
            "position_size": entry.get("quantity") or entry.get("size"),
            "pnl": entry.get("pnl"),
            "status": "closed" if status == "closed" else "open",
            "entry_time": open_time,
            "close_time": close_time,
        })

    return normalised


def _fetch_balance_from_trading_system(manager) -> Optional[Dict[str, float]]:
    """尝试从正在运行的交易系统直接获取余额。"""
    system = getattr(manager, "trading_system", None)
    if not system or not hasattr(system, "api"):
        return None

    try:
        wallet = system.api.get_wallet_balance()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"调用交易系统获取余额失败: {exc}")
        return None

    if not wallet:
        return None

    try:
        coins = wallet.get("list", [])[0].get("coin", [])
        balance = 0.0
        available = 0.0
        un_pnl = 0.0
        re_pnl = 0.0
        for coin in coins:
            if coin.get("coin") == "USDT":
                balance = float(coin.get("walletBalance", 0))
                available = float(coin.get("availableToWithdraw", 0))
                un_pnl = float(coin.get("unrealisedPnl", 0))
                re_pnl = float(coin.get("cumRealisedPnl", 0))
                break
        return {
            "balance": balance,
            "available_balance": available,
            "unrealized_pnl": un_pnl,
            "realized_pnl": re_pnl,
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"解析交易系统余额失败: {exc}")
        return None


# ============================================================================
# 路由定义与响应模型
# ============================================================================

router = APIRouter(tags=["统一API桥接"])

# ---------------------------------------------------------------------------
# 标准化响应模型
# ---------------------------------------------------------------------------

class StandardResponse(BaseModel):
    """标准响应格式"""
    success: bool
    message: str
    data: Optional[Any] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class TradingSystemStatus(BaseModel):
    """交易系统状态（统一字段，便于前端渲染）。"""
    is_running: bool
    mode: str
    symbols: List[str] = []
    total_trades: int = 0
    active_positions: int = 0
    total_pnl: float = 0.0

class PositionInfo(BaseModel):
    """持仓信息（兼容多种来源）。"""
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    leverage: int = 1

class TradeInfo(BaseModel):
    """交易信息（用于简化响应格式）。"""
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    close_price: Optional[float] = None
    position_size: float
    pnl: Optional[float] = None
    status: str
    entry_time: datetime
    close_time: Optional[datetime] = None

# ============================================================================
# 🔥 统一交易系统控制端点
# ============================================================================

@router.post("/api/trading/start")
async def start_trading_system(
    mode: str = Query(default="demo", description="运行模式"),
    symbols: Optional[List[str]] = Query(default=None, description="交易对"),
    current_user: User = Depends(get_current_user)
):
    """
    启动交易系统 - 统一端点
    
    支持多用户和单用户模式自动适配
    """
    try:
        if MULTI_USER_MODE:
            # 多用户模式
            manager = get_multi_user_trading_manager()
            config = {"mode": mode}
            if symbols:
                config["symbols"] = symbols
            
            result = manager.start_for_user(
                user_id=str(current_user.id),
                username=current_user.username,
                config=config
            )
        else:
            # 单用户模式
            manager = get_trading_system_manager()
            config = {"mode": mode}
            if symbols:
                config["symbols"] = symbols
            
            result = manager.start(config)
        
        return StandardResponse(
            success=result.get("success", False),
            message=result.get("message", "操作完成"),
            data=result
        )
        
    except Exception as e:
        logger.error(f"启动交易系统失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动失败: {str(e)}"
        )

@router.post("/api/trading/stop")
async def stop_trading_system(
    current_user: User = Depends(get_current_user)
):
    """
    停止交易系统 - 统一端点
    """
    try:
        if MULTI_USER_MODE:
            manager = get_multi_user_trading_manager()
            result = manager.stop_for_user(str(current_user.id))
        else:
            manager = get_trading_system_manager()
            result = manager.stop()
        
        return StandardResponse(
            success=result.get("success", False),
            message=result.get("message", "操作完成"),
            data=result
        )
        
    except Exception as e:
        logger.error(f"停止交易系统失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"停止失败: {str(e)}"
        )

@router.post("/api/trading/restart")
async def restart_trading_system(
    mode: str = Query(default="demo"),
    current_user: User = Depends(get_current_user)
):
    """
    重启交易系统 - 统一端点
    """
    try:
        if MULTI_USER_MODE:
            manager = get_multi_user_trading_manager()
            result = manager.restart_for_user(
                str(current_user.id),
                config={"mode": mode}
            )
        else:
            manager = get_trading_system_manager()
            result = manager.restart(config={"mode": mode})
        
        return StandardResponse(
            success=result.get("success", False),
            message=result.get("message", "操作完成"),
            data=result
        )
        
    except Exception as e:
        logger.error(f"重启交易系统失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重启失败: {str(e)}"
        )

@router.get("/api/trading/status")
async def get_trading_status(
    current_user: User = Depends(get_current_user)
):
    """
    获取交易系统状态 - 统一端点
    """
    try:
        if MULTI_USER_MODE:
            manager = get_multi_user_trading_manager()
            status_data = manager.get_status_for_user(str(current_user.id))
        else:
            manager = get_trading_system_manager()
            status_data = manager.get_status()
        
        if not status_data:
            # 未启动状态
            return StandardResponse(
                success=True,
                message="系统未启动",
                data=TradingSystemStatus(
                    is_running=False,
                    mode="demo",
                    symbols=[],
                    total_trades=0,
                    active_positions=0,
                    total_pnl=0.0
                ).dict()
            )
        
        # 标准化状态数据
        return StandardResponse(
            success=True,
            message="获取状态成功",
            data={
                "is_running": status_data.get("is_running", False),
                "mode": status_data.get("config", {}).get("mode", "demo"),
                "symbols": status_data.get("config", {}).get("symbols", []),
                "total_trades": status_data.get("stats", {}).get("total_trades", 0),
                "active_positions": status_data.get("stats", {}).get("active_positions", 0),
                "total_pnl": status_data.get("stats", {}).get("total_pnl", 0.0)
            }
        )
        
    except Exception as e:
        logger.error(f"获取状态失败: {e}")
        # 返回默认状态而不是抛出错误
        return StandardResponse(
            success=True,
            message="系统未启动",
            data=TradingSystemStatus(
                is_running=False,
                mode="demo",
                symbols=[],
                total_trades=0,
                active_positions=0,
                total_pnl=0.0
            ).dict()
        )

# ============================================================================
# 🔥 统一持仓查询端点
# ============================================================================

@router.get("/api/positions")
@router.get("/api/positions/live")
async def get_positions(
    current_user: User = Depends(get_current_user)
):
    """
    获取持仓 - 统一端点
    
    支持 /api/positions 和 /api/positions/live 两个路径
    """
    try:
        if MULTI_USER_MODE:
            manager = get_multi_user_trading_manager()
            positions = manager.get_positions_for_user(str(current_user.id))
        else:
            manager = get_trading_system_manager()
            # 尝试获取持仓
            system = getattr(manager, 'trading_system', None)
            if system and hasattr(system, 'get_positions'):
                positions = system.get_positions()
            else:
                positions = []
        
        return StandardResponse(
            success=True,
            message=f"获取到 {len(positions)} 个持仓",
            data={"positions": positions}
        )
        
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        return StandardResponse(
            success=True,
            message="暂无持仓",
            data={"positions": []}
        )

# ============================================================================
# 🔥 统一交易记录查询端点
# ============================================================================

@router.get("/api/trades")
@router.get("/api/trades/live")
async def get_trades(
    limit: int = Query(default=100, le=1000),
    status: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取交易记录 - 统一端点
    
    支持 /api/trades 和 /api/trades/live 两个路径
    """
    try:
        # 从数据库查询（支持多用户）
        query = db.query(Trade)
        
        # 如果是多用户模式，过滤用户ID
        if MULTI_USER_MODE and hasattr(Trade, 'user_id'):
            query = query.filter(Trade.user_id == current_user.id)
        
        # 状态过滤
        if status:
            query = query.filter(Trade.status == status)
        
        # 排序和限制
        trades = query.order_by(Trade.created_at.desc()).limit(limit).all()
        
        # 转换为字典
        trades_data = []
        for trade in trades:
            trades_data.append({
                "trade_id": trade.trade_id,
                "symbol": trade.symbol,
                "side": trade.side,
                "entry_price": float(trade.entry_price),
                "close_price": float(trade.close_price) if trade.close_price else None,
                "position_size": float(trade.position_size),
                "pnl": float(trade.pnl) if trade.pnl else None,
                "status": trade.status,
                "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
                "close_time": trade.close_time.isoformat() if trade.close_time else None
            })
        
        if not trades_data:
            trades_data = load_trades_from_journal(limit)
        
        return StandardResponse(
            success=True,
            message=f"获取到 {len(trades_data)} 条交易记录",
            data={"trades": trades_data}
        )
        
    except Exception as e:
        logger.error(f"获取交易记录失败: {e}")
        return StandardResponse(
            success=True,
            message="暂无交易记录",
            data={"trades": []}
        )


# ============================================================================
# 🔥 仪表盘汇总端点
# ============================================================================

DASHBOARD_OVERVIEW_TTL = 5.0
_dashboard_cache: Dict[str, Dict[str, Any]] = {}


@router.get("/api/dashboard/overview")
async def get_dashboard_overview(
    limit: int = Query(default=30, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """聚合仪表盘所需的核心数据，减少前端多次请求。"""

    cache_key = f"overview:{current_user.id}:{limit}"
    cached = _dashboard_cache.get(cache_key)
    now = time.time()
    if cached and now - cached["timestamp"] < DASHBOARD_OVERVIEW_TTL:
        return cached["response"]

    try:
        balance_resp, status_resp, stats_resp, trades_resp = await asyncio.gather(
            get_balance(current_user=current_user, db=db),
            get_trading_status(current_user=current_user),
            get_statistics(period="30d", current_user=current_user, db=db),
            get_trades(limit=limit, status=None, current_user=current_user, db=db),
        )

        balance_data = balance_resp.get("data", {}) if isinstance(balance_resp, dict) else {}
        status_data = status_resp.get("data", {}) if isinstance(status_resp, dict) else {}
        analytics_data = stats_resp.get("data", {}) if isinstance(stats_resp, dict) else {}
        trades_data = (
            trades_resp.get("data", {}).get("trades", [])
            if isinstance(trades_resp, dict)
            else []
        )

        overview = {
            "balance": balance_data,
            "status": status_data,
            "analytics": analytics_data,
            "trades": trades_data,
        }

        response = StandardResponse(
            success=True,
            message="仪表盘数据加载成功",
            data=overview,
        )
        _dashboard_cache[cache_key] = {"timestamp": now, "response": response}
        return response
    except Exception as exc:
        logger.error(f"组装仪表盘数据失败: {exc}")
        return StandardResponse(
            success=False,
            message="仪表盘数据加载失败",
            data={
                "balance": {},
                "status": {},
                "analytics": {},
                "trades": [],
            },
        )


# ============================================================================
# 🔥 统一余额查询端点
# ============================================================================

@router.get("/api/balance")
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取账户余额 - 统一端点
    """
    try:
        # 查询最新的账户快照
        query = db.query(AccountSnapshot)
        
        if MULTI_USER_MODE and hasattr(AccountSnapshot, 'user_id'):
            query = query.filter(AccountSnapshot.user_id == current_user.id)
        
        snapshot = query.order_by(AccountSnapshot.timestamp.desc()).first()
        
        if snapshot:
            return StandardResponse(
                success=True,
                message="获取余额成功",
                data={
                    "balance": float(snapshot.balance),
                    "available_balance": float(snapshot.available_balance),
                    "unrealized_pnl": float(snapshot.unrealized_pnl),
                    "realized_pnl": float(snapshot.realized_pnl)
                }
            )

        # 尝试实时获取（交易系统正在运行时不会有快照）
        manager = get_multi_user_trading_manager() if MULTI_USER_MODE else get_trading_system_manager()
        runtime_balance = _fetch_balance_from_trading_system(manager)
        if runtime_balance:
            return StandardResponse(
                success=True,
                message="实时余额",
                data=runtime_balance,
            )

            # 返回默认值
            return StandardResponse(
                success=True,
                message="暂无余额数据",
                data={
                    "balance": 0.0,
                    "available_balance": 0.0,
                    "unrealized_pnl": 0.0,
                    "realized_pnl": 0.0
                }
            )
        
    except Exception as e:
        logger.error(f"获取余额失败: {e}")
        return StandardResponse(
            success=True,
            message="暂无余额数据",
            data={
                "balance": 0.0,
                "available_balance": 0.0,
                "unrealized_pnl": 0.0,
                "realized_pnl": 0.0
            }
        )

# ============================================================================
# 🔥 统一AI决策查询端点
# ============================================================================

@router.get("/api/ai/decisions")
async def get_ai_decisions(
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取AI决策记录 - 统一端点
    """
    try:
        query = db.query(AIDecision)
        
        if MULTI_USER_MODE and hasattr(AIDecision, 'user_id'):
            query = query.filter(AIDecision.user_id == current_user.id)
        
        decisions = query.order_by(AIDecision.created_at.desc()).limit(limit).all()
        
        decisions_data = []
        for decision in decisions:
            decisions_data.append({
                "decision_id": decision.decision_id,
                "action": decision.action,
                "target_symbol": decision.target_symbol,
                "confidence": decision.confidence,
                "reason": decision.reason if hasattr(decision, 'reason') else decision.reasoning,
                "created_at": decision.created_at.isoformat()
            })
        
        return StandardResponse(
            success=True,
            message=f"获取到 {len(decisions_data)} 条AI决策",
            data={"decisions": decisions_data}
        )
        
    except Exception as e:
        logger.error(f"获取AI决策失败: {e}")
        return StandardResponse(
            success=True,
            message="暂无AI决策",
            data={"decisions": []}
        )

# ============================================================================
# 🔥 统一统计数据端点
# ============================================================================

@router.get("/api/statistics/summary")
@router.get("/api/analytics/statistics")
async def get_statistics(
    period: str = Query(default="30d"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取统计摘要 - 统一端点
    
    支持 /api/statistics/summary 和 /api/analytics/statistics 两个路径
    """
    try:
        # 查询交易记录
        query = db.query(Trade).filter(Trade.status == "closed")
        
        if MULTI_USER_MODE and hasattr(Trade, 'user_id'):
            query = query.filter(Trade.user_id == current_user.id)
        
        trades = query.all()
        
        # 计算统计
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t.pnl and t.pnl > 0])
        losing_trades = len([t for t in trades if t.pnl and t.pnl < 0])
        total_pnl = sum(t.pnl for t in trades if t.pnl)
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        return StandardResponse(
            success=True,
            message="获取统计成功",
            data={
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": round(win_rate, 2),
                "total_pnl": round(total_pnl, 2),
                "avg_pnl": round(total_pnl / total_trades, 2) if total_trades > 0 else 0
            }
        )
        
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return StandardResponse(
            success=True,
            message="暂无统计数据",
            data={
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_pnl": 0
            }
        )

# ============================================================================
# 🔥 用户管理代理端点（兼容前端路径）
# ============================================================================

@router.get("/api/users")
async def list_users_proxy(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    获取所有用户列表 - 代理到 /api/auth/users
    仅管理员可用
    
    返回格式：直接返回用户数组，兼容前端期望
    """
    try:
        from api_auth import DBUser
        db_users = db.query(DBUser).all()
        
        users = []
        for db_user in db_users:
            scopes = ["read", "write", "admin"] if db_user.is_admin else ["read", "write"]
            users.append({
                "id": db_user.id,
                "username": db_user.username,
                "is_admin": db_user.is_admin,
                "is_active": not db_user.account_locked,
                "scopes": scopes,
                "created_at": db_user.created_at.isoformat() if db_user.created_at else "unknown"
            })
        
        # 前端期望直接返回数组，而不是 StandardResponse 格式
        return users
    except Exception as e:
        logger.error(f"获取用户列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户列表失败: {str(e)}"
        )

@router.post("/api/users")
async def create_user_proxy(
    user_data: Dict[str, Any],
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    创建新用户 - 代理到 /api/auth/register
    仅管理员可用
    """
    try:
        from api_auth import DBUser
        import hashlib
        from datetime import datetime
        
        # 验证必需字段
        if "username" not in user_data or "password" not in user_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="username 和 password 是必需的"
            )
        
        username = user_data["username"]
        password = user_data["password"]
        is_admin = user_data.get("is_admin", False)
        
        # 检查用户是否已存在
        existing_user = db.query(DBUser).filter(DBUser.username == username).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"用户 '{username}' 已存在"
            )
        
        # 创建用户
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        db_user = DBUser(
            username=username,
            password_hash=password_hash,
            is_admin=is_admin,
            account_locked=False
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        return StandardResponse(
            success=True,
            message=f"用户 '{db_user.username}' 创建成功",
            data={
                "id": db_user.id,
                "username": db_user.username,
                "is_admin": db_user.is_admin,
                "created_at": db_user.created_at.isoformat() if db_user.created_at else None
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建用户失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建用户失败: {str(e)}"
        )

# ============================================================================
# 🔥 配置管理代理端点（确保前端路径可用）
# ============================================================================

@router.get("/api/config")
async def get_config_proxy(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取所有配置 - 代理到 /api/config/all
    
    返回格式：与 config_manager_api 兼容，直接返回配置对象
    """
    try:
        from database_models import Configuration
        
        # 查询当前用户的配置
        configs = db.query(Configuration).filter(
            Configuration.user_id == current_user.id
        ).all()
        
        result = {
            "deepseek": {},
            "bybit": {},
            "trading": {},
            "risk": {}
        }
        
        for config in configs:
            category = config.category
            key = config.key
            value = config.value
            
            # 脱敏处理
            if category in ["deepseek", "bybit"] and "key" in key.lower():
                if isinstance(value, str) and len(value) > 8:
                    value = f"{value[:4]}...{value[-4:]}"
            
            if category not in result:
                result[category] = {}
            
            result[category][key] = {
                "value": value,
                "description": config.description,
                "updated_at": config.updated_at.isoformat() if config.updated_at else None
            }
        
        # 返回与 config_manager_api 兼容的格式
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取配置失败: {str(e)}"
        )

@router.put("/api/config/trading")
async def update_trading_config_proxy(
    config_data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    更新交易配置 - 代理到 /api/config/trading
    """
    try:
        from database_models import Configuration
        
        # 保存配置到数据库（交易配置不需要验证）
        for key, value in config_data.items():
            config = db.query(Configuration).filter(
                Configuration.user_id == current_user.id,
                Configuration.category == "trading",
                Configuration.key == key
            ).first()
            
            if config:
                config.value = str(value) if value is not None else ""
                config.updated_at = datetime.now()
            else:
                config = Configuration(
                    user_id=current_user.id,
                    category="trading",
                    key=key,
                    value=str(value) if value is not None else "",
                    description=f"交易配置: {key}"
                )
                db.add(config)
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message="交易配置更新成功",
            data=config_data
        )
    except Exception as e:
        logger.error(f"更新交易配置失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新交易配置失败: {str(e)}"
        )

@router.put("/api/config/risk")
async def update_risk_config_proxy(
    config_data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    更新风险配置 - 代理到 /api/config/risk
    """
    try:
        from database_models import Configuration
        
        # 保存配置到数据库
        for key, value in config_data.items():
            config = db.query(Configuration).filter(
                Configuration.user_id == current_user.id,
                Configuration.category == "risk",
                Configuration.key == key
            ).first()
            
            if config:
                config.value = str(value) if value is not None else ""
                config.updated_at = datetime.now()
            else:
                config = Configuration(
                    user_id=current_user.id,
                    category="risk",
                    key=key,
                    value=str(value) if value is not None else "",
                    description=f"风险配置: {key}"
                )
                db.add(config)
        
        db.commit()
        
        return StandardResponse(
            success=True,
            message="风险配置更新成功",
            data=config_data
        )
    except Exception as e:
        logger.error(f"更新风险配置失败: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新风险配置失败: {str(e)}"
        )

@router.post("/api/config/validate/deepseek")
async def validate_deepseek_proxy(
    config_data: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    验证 DeepSeek 配置 - 代理到 /api/config/validate/deepseek
    """
    try:
        from config_manager_api import DeepSeekConfig, ConfigValidator
        
        config = DeepSeekConfig(**config_data)
        validator = ConfigValidator()
        result = await validator.validate_deepseek(config)
        
        return StandardResponse(
            success=result.valid,
            message=result.message,
            data=result.dict()
        )
    except Exception as e:
        logger.error(f"验证 DeepSeek 配置失败: {e}")
        return StandardResponse(
            success=False,
            message=f"验证失败: {str(e)}",
            data={"valid": False}
        )

@router.post("/api/config/validate/bybit")
async def validate_bybit_proxy(
    config_data: Dict[str, Any],
    current_user: User = Depends(get_current_user)
):
    """
    验证 Bybit 配置 - 代理到 /api/config/validate/bybit
    """
    try:
        from config_manager_api import BybitConfig, ConfigValidator
        
        config = BybitConfig(**config_data)
        validator = ConfigValidator()
        result = await validator.validate_bybit(config)
        
        return StandardResponse(
            success=result.valid,
            message=result.message,
            data=result.dict()
        )
    except Exception as e:
        logger.error(f"验证 Bybit 配置失败: {e}")
        return StandardResponse(
            success=False,
            message=f"验证失败: {str(e)}",
            data={"valid": False}
        )

# ============================================================================
# 🔥 健康检查端点
# ============================================================================

@router.get("/health")
@router.get("/api/health")
async def health_check():
    """
    健康检查 - 无需认证
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "v3.3",
        "bridge": "unified"
    }

# ============================================================================
# 日志
# ============================================================================

logger.info("=" * 60)
logger.info("🌉 统一API桥接层已加载")
logger.info(f"   模式: {'多用户' if MULTI_USER_MODE else '单用户'}")
logger.info(f"   端点数量: 21+ (包括用户管理和配置管理代理)")
logger.info("=" * 60)

