"""
交易API路由 - 提供交易系统的REST API接口
集成 bybit_live_trading_system.py 的功能
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
from sqlalchemy.orm import Session

# 导入认证依赖
from api_auth import get_current_user, get_current_admin_user
# 导入数据库
from database_models import get_db, Trade, User, APIKey
# 导入交易系统管理器（重构后的API调用模式）
from trading_system_manager import get_trading_system_manager, TradingSystemState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["交易"])

# ============================================================================
# Pydantic 模型
# ============================================================================

class TradeCreate(BaseModel):
    """创建交易请求"""
    symbol: str = Field(..., description="交易对", example="BTCUSDT")
    side: str = Field(..., description="方向", example="Buy")
    order_type: str = Field(default="Market", description="订单类型")
    position_size: float = Field(..., gt=0, description="仓位大小")
    leverage: int = Field(default=10, ge=1, le=100, description="杠杆")
    stop_loss: Optional[float] = Field(None, description="止损价格")
    take_profit: Optional[float] = Field(None, description="止盈价格")

class TradeResponse(BaseModel):
    """交易响应"""
    id: int
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    position_size: float
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class PositionResponse(BaseModel):
    """持仓响应"""
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: Optional[float]
    unrealized_pnl: Optional[float]
    leverage: int

class MarketDataResponse(BaseModel):
    """市场数据响应"""
    symbol: str
    price: float
    change_24h: Optional[float]
    volume_24h: Optional[float]
    high_24h: Optional[float]
    low_24h: Optional[float]
    timestamp: datetime

class TradingSystemStatus(BaseModel):
    """交易系统状态"""
    is_running: bool
    mode: str  # demo/live
    symbols: List[str]
    total_trades: int
    active_positions: int
    total_pnl: float

# ============================================================================
# 全局变量（交易系统管理器）
# ============================================================================

# 获取交易系统管理器单例
trading_manager = get_trading_system_manager()

# ============================================================================
# 交易记录端点
# ============================================================================

@router.get("/trades", response_model=List[TradeResponse])
async def get_trades(
    skip: int = 0,
    limit: int = 100,
    symbol: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取交易记录
    
    - **skip**: 跳过记录数
    - **limit**: 返回记录数（最多100）
    - **symbol**: 过滤交易对（可选）
    """
    try:
        query = db.query(Trade).filter(Trade.user_id == current_user.id)
        
        if symbol:
            query = query.filter(Trade.symbol == symbol)
        
        trades = query.order_by(Trade.created_at.desc()).offset(skip).limit(limit).all()
        
        return trades
    
    except Exception as e:
        logger.error(f"获取交易记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trades/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取单个交易详情"""
    try:
        trade = db.query(Trade).filter(
            Trade.trade_id == trade_id,
            Trade.user_id == current_user.id
        ).first()
        
        if not trade:
            raise HTTPException(status_code=404, detail="交易记录不存在")
        
        return trade
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取交易详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trades", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def create_trade(
    trade_data: TradeCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建新交易（手动下单）
    
    这个端点允许用户手动下单，绕过AI决策
    """
    try:
        # TODO: 实现实际的交易逻辑
        # 1. 验证API密钥
        # 2. 调用Bybit API下单
        # 3. 记录到数据库
        
        # 临时实现：仅创建数据库记录
        new_trade = Trade(
            trade_id=f"manual_{int(datetime.now().timestamp())}",
            user_id=current_user.id,
            symbol=trade_data.symbol,
            side=trade_data.side,
            order_type=trade_data.order_type,
            position_size=trade_data.position_size,
            leverage=trade_data.leverage,
            stop_loss=trade_data.stop_loss,
            status="pending",
            created_at=datetime.now()
        )
        
        db.add(new_trade)
        db.commit()
        db.refresh(new_trade)
        
        # 后台任务：执行实际交易
        # background_tasks.add_task(execute_trade, new_trade.id)
        
        return new_trade
    
    except Exception as e:
        logger.error(f"创建交易失败: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# 持仓管理端点
# ============================================================================

@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(
    current_user: User = Depends(get_current_user)
):
    """
    获取当前持仓
    
    从Bybit API获取实时持仓信息
    """
    try:
        # TODO: 实现Bybit API调用
        # 1. 获取用户的API密钥
        # 2. 调用Bybit获取持仓
        # 3. 返回格式化数据
        
        # 临时返回示例数据
        return []
    
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/positions/{symbol}")
async def close_position(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    """
    平仓
    
    - **symbol**: 要平仓的交易对
    """
    try:
        # TODO: 实现平仓逻辑
        # 1. 调用Bybit API平仓
        # 2. 更新数据库记录
        
        return {
            "success": True,
            "message": f"{symbol} 平仓指令已发送",
            "symbol": symbol
        }
    
    except Exception as e:
        logger.error(f"平仓失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# 市场数据端点
# ============================================================================

@router.get("/market/{symbol}", response_model=MarketDataResponse)
async def get_market_data(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取市场数据
    
    - **symbol**: 交易对（如 BTCUSDT）
    """
    try:
        # TODO: 调用Bybit API获取市场数据
        
        # 临时返回示例数据
        return MarketDataResponse(
            symbol=symbol,
            price=50000.0,
            change_24h=2.5,
            volume_24h=1000000.0,
            high_24h=51000.0,
            low_24h=49000.0,
            timestamp=datetime.now()
        )
    
    except Exception as e:
        logger.error(f"获取市场数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/market/{symbol}/kline")
async def get_kline_data(
    symbol: str,
    interval: str = "1h",
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """
    获取K线数据
    
    - **symbol**: 交易对
    - **interval**: 时间间隔（1m, 5m, 15m, 1h, 4h, 1d）
    - **limit**: 数据条数
    """
    try:
        # TODO: 调用Bybit API获取K线数据
        
        return {
            "symbol": symbol,
            "interval": interval,
            "data": []
        }
    
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# 交易系统控制端点（管理员）
# ============================================================================

@router.post("/trading/start")
async def start_trading_system(
    mode: Optional[str] = "demo",
    symbols: Optional[List[str]] = None,
    current_user: User = Depends(get_current_admin_user)
):
    """
    启动AI交易系统（仅管理员）
    
    - **mode**: 运行模式 (demo/testnet/live)
    - **symbols**: 交易对列表（默认: ["BTCUSDT"]）
    """
    try:
        # 准备配置
        config = {
            "mode": mode,
            "symbols": symbols or ["BTCUSDT"],
            "check_interval": 60,
            "use_ai": True
        }
        
        # 启动交易系统
        result = trading_manager.start(config)
        
        if result["success"]:
            logger.info(f"✅ 用户 {current_user.username} 启动了交易系统")
            return result
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动交易系统失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trading/stop")
async def stop_trading_system(
    current_user: User = Depends(get_current_admin_user)
):
    """
    停止AI交易系统（仅管理员）
    """
    try:
        # 停止交易系统
        result = trading_manager.stop()
        
        if result["success"]:
            logger.info(f"✅ 用户 {current_user.username} 停止了交易系统")
            return result
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止交易系统失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trading/restart")
async def restart_trading_system(
    mode: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    current_user: User = Depends(get_current_admin_user)
):
    """
    重启AI交易系统（仅管理员）
    
    - **mode**: 运行模式（可选）
    - **symbols**: 交易对列表（可选）
    """
    try:
        # 准备新配置
        config = {}
        if mode:
            config["mode"] = mode
        if symbols:
            config["symbols"] = symbols
        
        # 重启交易系统
        result = trading_manager.restart(config if config else None)
        
        if result["success"]:
            logger.info(f"✅ 用户 {current_user.username} 重启了交易系统")
            return result
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重启交易系统失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trading/status", response_model=TradingSystemStatus)
async def get_trading_status(
    current_user: User = Depends(get_current_user)
):
    """
    获取交易系统状态
    
    返回系统运行状态、统计数据等
    """
    try:
        # 获取状态
        status = trading_manager.get_status()
        
        return TradingSystemStatus(
            is_running=status["is_running"],
            mode=status["config"].get("mode", "unknown"),
            symbols=status["config"].get("symbols", []),
            total_trades=status["stats"].get("total_trades", 0),
            active_positions=status["stats"].get("active_positions", 0),
            total_pnl=status["stats"].get("total_pnl", 0.0)
        )
    
    except Exception as e:
        logger.error(f"获取交易系统状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# 持仓管理端点（通过交易系统管理器）
# ============================================================================

@router.get("/positions/live")
async def get_live_positions(
    current_user: User = Depends(get_current_user)
):
    """
    获取交易系统当前持仓（实时）
    
    从运行中的交易系统获取持仓信息
    """
    try:
        positions = trading_manager.get_positions()
        return {
            "success": True,
            "positions": positions,
            "count": len(positions)
        }
    except Exception as e:
        logger.error(f"获取实时持仓失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trades/live")
async def get_live_trades(
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """
    获取交易系统交易记录（实时）
    
    从运行中的交易系统获取交易历史
    """
    try:
        trades = trading_manager.get_trades(limit=limit)
        return {
            "success": True,
            "trades": trades,
            "count": len(trades)
        }
    except Exception as e:
        logger.error(f"获取实时交易记录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# 统计分析端点
# ============================================================================

@router.get("/statistics/summary")
async def get_trading_statistics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取交易统计摘要
    
    包括：总交易次数、胜率、总盈亏等
    """
    try:
        # 查询用户的所有已完成交易
        trades = db.query(Trade).filter(
            Trade.user_id == current_user.id,
            Trade.status == "closed"
        ).all()
        
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_pnl": 0,
                "best_trade": 0,
                "worst_trade": 0
            }
        
        # 计算统计数据
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0
        
        total_pnl = sum(t.pnl for t in trades if t.pnl)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        
        pnls = [t.pnl for t in trades if t.pnl]
        best_trade = max(pnls) if pnls else 0
        worst_trade = min(pnls) if pnls else 0
        
        return {
            "total_trades": total_trades,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(avg_pnl, 2),
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "winning_trades": len(winning_trades),
            "losing_trades": total_trades - len(winning_trades)
        }
    
    except Exception as e:
        logger.error(f"获取统计数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# AI决策端点
# ============================================================================

@router.get("/ai/decision/{symbol}")
async def get_ai_decision(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取AI对指定交易对的决策建议
    
    - **symbol**: 交易对（如 BTCUSDT）
    """
    try:
        # TODO: 调用AI决策引擎
        # 1. 获取市场数据
        # 2. 计算技术指标
        # 3. 调用DeepSeek API
        # 4. 返回决策结果
        
        return {
            "symbol": symbol,
            "decision": "HOLD",  # BUY/SELL/HOLD
            "confidence": 0.75,
            "reasoning": "市场处于震荡区间，暂时观望",
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"获取AI决策失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

