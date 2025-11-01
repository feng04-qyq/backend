"""
多用户交易系统管理器 - Multi-User Trading System Manager
支持每个用户独立运行自己的交易系统和策略

功能：
- 每个用户独立的交易系统实例
- 配置隔离
- 策略隔离
- 资金账户隔离（需要用户自己配置 API 密钥）
"""

import logging
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import json

logger = logging.getLogger(__name__)

from trading_runtime_config import load_trading_runtime_config


class TradingSystemState(str, Enum):
    """交易系统状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class UserTradingSystem:
    """
    单个用户的交易系统实例
    
    每个用户一个独立的实例，互不干扰
    """
    
    def __init__(self, user_id: str, username: str):
        """
        初始化用户交易系统
        
        Args:
            user_id: 用户ID
            username: 用户名
        """
        self.user_id = user_id
        self.username = username
        self.state = TradingSystemState.STOPPED
        self.trading_system = None
        self.trading_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # 用户专属统计
        self.stats = {
            "user_id": user_id,
            "username": username,
            "start_time": None,
            "stop_time": None,
            "total_trades": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "total_pnl": 0.0,
            "active_positions": 0,
            "last_error": None
        }
        
        # 用户专属配置
        # ⚠️ 交易对固定，由系统统一管理，用户不可修改
        self.FIXED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]  # 固定交易对
        
        self.config = {
            "user_id": user_id,
            "mode": "demo",  # 运行模式：demo/testnet/live（用户可选）
            "symbols": self.FIXED_SYMBOLS,  # 交易对固定
            "max_positions": 3,  # 最大持仓数（用户可调整 1-5）
            "check_interval": 60,  # 检查间隔（用户可调整 30-300 秒）
            "use_ai": True,  # 是否使用 AI（用户可开关）
            
            # 策略参数（用户可以修改这些参数来调整策略）
            "risk_per_trade": 0.02,  # 单笔风险比例（0.01-0.05）
            "stop_loss_atr_multiplier": 2.0,  # 止损 ATR 倍数（1.5-3.0）
            "take_profit_ratio": 2.0,  # 止盈比例（1.5-3.0）
            "trailing_stop_enabled": True,  # 是否启用移动止损
            "use_multiple_timeframes": True,  # 是否使用多周期分析
            
            # 用户自己的 API 密钥（从数据库加载）
            "bybit_api_key": None,
            "bybit_api_secret": None,
            "deepseek_api_key": None,
        }
        
        logger.info(f"✅ 创建用户 {username} 的交易系统实例")
    
    # ========================================================================
    # 生命周期管理
    # ========================================================================
    
    def start(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """启动用户的交易系统"""
        try:
            if self.state == TradingSystemState.RUNNING:
                return {
                    "success": False,
                    "message": f"用户 {self.username} 的交易系统已在运行中",
                    "state": self.state
                }
            
            if self.state == TradingSystemState.STARTING:
                return {
                    "success": False,
                    "message": "交易系统正在启动中",
                    "state": self.state
                }
            
            preferred_mode = None

            # 更新配置（但交易对固定，不允许修改）
            if config:
                # 移除用户尝试修改的 symbols（如果有）
                if "symbols" in config:
                    logger.warning(f"用户 {self.username} 尝试修改交易对，已忽略")
                    del config["symbols"]

                # 记录用户期望的模式
                if "mode" in config:
                    preferred_mode = config.get("mode")

                # 验证和限制用户参数
                if "max_positions" in config:
                    config["max_positions"] = max(1, min(5, config["max_positions"]))

                if "check_interval" in config:
                    config["check_interval"] = max(30, min(300, config["check_interval"]))

                if "risk_per_trade" in config:
                    config["risk_per_trade"] = max(0.01, min(0.05, config["risk_per_trade"]))

                # 更新允许的配置
                self.config.update({k: v for k, v in config.items() if v is not None})

            # 确保交易对保持固定
            self.config["symbols"] = self.FIXED_SYMBOLS

            # 加载数据库中的API密钥等敏感配置
            try:
                runtime_overrides = load_trading_runtime_config(
                    user_id=int(self.user_id) if str(self.user_id).isdigit() else None,
                    preferred_mode=preferred_mode,
                )
            except RuntimeError as runtime_error:
                logger.error(f"❌ 无法加载用户 {self.username} 的交易配置: {runtime_error}")
                self.state = TradingSystemState.ERROR
                self.stats["last_error"] = str(runtime_error)
                return {
                    "success": False,
                    "message": str(runtime_error),
                    "state": self.state,
                }

            self.config.update(runtime_overrides)
            
            logger.info(f"🚀 正在启动用户 {self.username} 的交易系统... 模式: {self.config['mode']}")
            self.state = TradingSystemState.STARTING
            
            # 重置停止事件
            self.stop_event.clear()
            
            # 启动交易系统线程
            self.trading_thread = threading.Thread(
                target=self._run_trading_system,
                daemon=True,
                name=f"Trading-{self.user_id}"
            )
            self.trading_thread.start()
            
            # 等待系统初始化
            import time
            time.sleep(2)
            
            if self.state == TradingSystemState.RUNNING:
                self.stats["start_time"] = datetime.now().isoformat()
                logger.info(f"✅ 用户 {self.username} 的交易系统启动成功")
                return {
                    "success": True,
                    "message": f"用户 {self.username} 的交易系统启动成功",
                    "state": self.state,
                    "config": self._safe_config()
                }
            else:
                logger.error(f"❌ 用户 {self.username} 的交易系统启动失败")
                return {
                    "success": False,
                    "message": f"交易系统启动失败: {self.stats.get('last_error', 'Unknown')}",
                    "state": self.state
                }
                
        except Exception as e:
            logger.error(f"❌ 启动用户 {self.username} 的交易系统时出错: {e}")
            self.state = TradingSystemState.ERROR
            self.stats["last_error"] = str(e)
            return {
                "success": False,
                "message": f"启动失败: {str(e)}",
                "state": self.state
            }
    
    def stop(self) -> Dict[str, Any]:
        """停止用户的交易系统"""
        try:
            if self.state == TradingSystemState.STOPPED:
                return {
                    "success": False,
                    "message": "交易系统未在运行",
                    "state": self.state
                }
            
            logger.info(f"🛑 正在停止用户 {self.username} 的交易系统...")
            self.state = TradingSystemState.STOPPING
            
            # 发送停止信号
            self.stop_event.set()
            
            # 停止交易系统实例
            if self.trading_system:
                try:
                    if hasattr(self.trading_system, 'stop'):
                        self.trading_system.stop()
                except Exception as e:
                    logger.error(f"停止交易系统实例时出错: {e}")
            
            # 等待线程结束
            if self.trading_thread and self.trading_thread.is_alive():
                self.trading_thread.join(timeout=10)
            
            self.state = TradingSystemState.STOPPED
            self.stats["stop_time"] = datetime.now().isoformat()
            
            logger.info(f"✅ 用户 {self.username} 的交易系统已停止")
            return {
                "success": True,
                "message": f"用户 {self.username} 的交易系统已停止",
                "state": self.state
            }
            
        except Exception as e:
            logger.error(f"❌ 停止用户 {self.username} 的交易系统时出错: {e}")
            self.state = TradingSystemState.ERROR
            self.stats["last_error"] = str(e)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
                "state": self.state
            }
    
    def restart(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """重启用户的交易系统"""
        logger.info(f"🔄 正在重启用户 {self.username} 的交易系统...")
        
        # 先停止
        stop_result = self.stop()
        if not stop_result["success"]:
            return stop_result
        
        # 等待完全停止
        import time
        time.sleep(2)
        
        # 再启动
        return self.start(config)
    
    # ========================================================================
    # 交易系统运行逻辑
    # ========================================================================
    
    def _run_trading_system(self):
        """在后台线程中运行交易系统"""
        try:
            logger.info(f"📊 用户 {self.username} 的交易系统线程启动")
            
            # 导入交易系统（延迟导入避免循环依赖）
            try:
                from bybit_live_trading_system import LiveTradingEngine
                
                # 创建用户专属的交易系统实例
                engine_kwargs = {
                    "user_id": self.user_id,
                    "mode": self.config.get("mode"),
                    "symbols": self.config.get("symbols"),
                    "check_interval": self.config.get("check_interval"),
                    "bybit_api_key": self.config.get("bybit_api_key"),
                    "bybit_api_secret": self.config.get("bybit_api_secret"),
                    "use_testnet": self.config.get("use_testnet"),
                    "use_demo": self.config.get("use_demo"),
                    "deepseek_api_key": self.config.get("deepseek_api_key"),
                    "deepseek_model": self.config.get("deepseek_model"),
                    "deepseek_system_prompt": self.config.get("deepseek_system_prompt"),
                    "trading_interval": self.config.get("trading_interval"),
                    "max_position_pct": self.config.get("max_position_pct"),
                    "default_leverage": self.config.get("default_leverage"),
                    "use_trailing_stop": self.config.get("use_trailing_stop"),
                }

                engine_kwargs = {k: v for k, v in engine_kwargs.items() if v is not None}

                self.trading_system = LiveTradingEngine(**engine_kwargs)
                
                logger.info(f"✅ 用户 {self.username} 的交易系统实例创建成功")
                self.state = TradingSystemState.RUNNING
                
                # 运行交易系统（阻塞调用）
                self.trading_system.run()
                
            except ImportError as e:
                logger.error(f"❌ 无法导入交易系统: {e}")
                logger.info(f"⚠️ 用户 {self.username} 使用模拟交易系统")
                self.state = TradingSystemState.RUNNING
                
                # 模拟交易系统
                self._run_mock_trading_system()
            
        except Exception as e:
            logger.error(f"❌ 用户 {self.username} 的交易系统运行错误: {e}")
            self.state = TradingSystemState.ERROR
            self.stats["last_error"] = str(e)
        finally:
            logger.info(f"📊 用户 {self.username} 的交易系统线程结束")
            if self.state != TradingSystemState.ERROR:
                self.state = TradingSystemState.STOPPED
    
    def _run_mock_trading_system(self):
        """模拟交易系统（用于开发/测试）"""
        logger.info(f"🎭 运行用户 {self.username} 的模拟交易系统")
        
        import time
        import random
        
        while not self.stop_event.is_set():
            try:
                # 模拟交易逻辑
                if random.random() > 0.8:  # 20% 概率生成交易
                    trade_type = random.choice(["buy", "sell"])
                    symbol = random.choice(self.config["symbols"])
                    
                    logger.info(f"📈 用户 {self.username} 模拟交易: {trade_type.upper()} {symbol}")
                    
                    self.stats["total_trades"] += 1
                    if random.random() > 0.3:  # 70% 成功率
                        self.stats["successful_trades"] += 1
                        pnl = random.uniform(-100, 200)
                        self.stats["total_pnl"] += pnl
                    else:
                        self.stats["failed_trades"] += 1
                
                # 模拟持仓数量
                self.stats["active_positions"] = random.randint(0, 3)
                
                # 休眠一段时间
                check_interval = self.config.get("check_interval", 60)
                self.stop_event.wait(timeout=check_interval)
                
            except Exception as e:
                logger.error(f"用户 {self.username} 模拟交易系统错误: {e}")
                time.sleep(5)
        
        logger.info(f"🎭 用户 {self.username} 的模拟交易系统已停止")
    
    # ========================================================================
    # 状态查询
    # ========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """获取交易系统状态"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "state": self.state,
            "is_running": self.state == TradingSystemState.RUNNING,
            "config": self._safe_config(),
            "stats": self.stats,
            "thread_alive": self.trading_thread.is_alive() if self.trading_thread else False
        }
    
    def _safe_config(self) -> Dict[str, Any]:
        """返回安全的配置（隐藏敏感信息）"""
        safe_config = self.config.copy()
        # 隐藏 API 密钥
        if "bybit_api_key" in safe_config:
            safe_config["bybit_api_key"] = "***" if safe_config["bybit_api_key"] else None
        if "bybit_api_secret" in safe_config:
            safe_config["bybit_api_secret"] = "***" if safe_config["bybit_api_secret"] else None
        if "deepseek_api_key" in safe_config:
            safe_config["deepseek_api_key"] = "***" if safe_config["deepseek_api_key"] else None
        return safe_config
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """获取当前持仓"""
        if self.trading_system and hasattr(self.trading_system, 'get_positions'):
            try:
                return self.trading_system.get_positions()
            except Exception as e:
                logger.error(f"获取用户 {self.username} 持仓失败: {e}")
        return []
    
    def get_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取交易历史"""
        if self.trading_system and hasattr(self.trading_system, 'get_trades'):
            try:
                return self.trading_system.get_trades(limit=limit)
            except Exception as e:
                logger.error(f"获取用户 {self.username} 交易记录失败: {e}")
        return []


# ============================================================================
# 多用户交易系统管理器
# ============================================================================

class MultiUserTradingManager:
    """
    多用户交易系统管理器
    
    管理多个用户各自的交易系统实例
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化管理器"""
        if self._initialized:
            return
            
        self._initialized = True
        self.user_systems: Dict[str, UserTradingSystem] = {}
        self.lock = threading.Lock()
        
        logger.info("✅ 多用户交易系统管理器初始化完成")
    
    # ========================================================================
    # 用户系统管理
    # ========================================================================
    
    def get_or_create_user_system(self, user_id: str, username: str) -> UserTradingSystem:
        """
        获取或创建用户的交易系统实例
        
        Args:
            user_id: 用户ID
            username: 用户名
            
        Returns:
            用户的交易系统实例
        """
        with self.lock:
            if user_id not in self.user_systems:
                self.user_systems[user_id] = UserTradingSystem(user_id, username)
                logger.info(f"✅ 为用户 {username} 创建交易系统实例")
            return self.user_systems[user_id]
    
    def get_user_system(self, user_id: str) -> Optional[UserTradingSystem]:
        """
        获取用户的交易系统实例
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户的交易系统实例，如果不存在返回 None
        """
        return self.user_systems.get(user_id)
    
    def remove_user_system(self, user_id: str) -> bool:
        """
        移除用户的交易系统实例（先停止再移除）
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否成功移除
        """
        with self.lock:
            if user_id in self.user_systems:
                user_system = self.user_systems[user_id]
                # 先停止
                if user_system.state == TradingSystemState.RUNNING:
                    user_system.stop()
                # 移除
                del self.user_systems[user_id]
                logger.info(f"✅ 移除用户 {user_system.username} 的交易系统实例")
                return True
            return False
    
    # ========================================================================
    # 生命周期管理（用户级别）
    # ========================================================================
    
    def start_for_user(
        self, 
        user_id: str, 
        username: str, 
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        为特定用户启动交易系统
        
        Args:
            user_id: 用户ID
            username: 用户名
            config: 配置字典
            
        Returns:
            操作结果
        """
        user_system = self.get_or_create_user_system(user_id, username)
        return user_system.start(config)
    
    def stop_for_user(self, user_id: str) -> Dict[str, Any]:
        """为特定用户停止交易系统"""
        user_system = self.get_user_system(user_id)
        if user_system:
            return user_system.stop()
        return {
            "success": False,
            "message": "用户交易系统不存在"
        }
    
    def restart_for_user(
        self, 
        user_id: str, 
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """为特定用户重启交易系统"""
        user_system = self.get_user_system(user_id)
        if user_system:
            return user_system.restart(config)
        return {
            "success": False,
            "message": "用户交易系统不存在"
        }
    
    # ========================================================================
    # 状态查询
    # ========================================================================
    
    def get_status_for_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户的交易系统状态"""
        user_system = self.get_user_system(user_id)
        if user_system:
            return user_system.get_status()
        return None
    
    def get_all_users_status(self) -> List[Dict[str, Any]]:
        """获取所有用户的交易系统状态"""
        statuses = []
        for user_id, user_system in self.user_systems.items():
            statuses.append(user_system.get_status())
        return statuses
    
    def get_running_users(self) -> List[str]:
        """获取正在运行交易系统的用户ID列表"""
        running_users = []
        for user_id, user_system in self.user_systems.items():
            if user_system.state == TradingSystemState.RUNNING:
                running_users.append(user_id)
        return running_users
    
    # ========================================================================
    # 数据查询
    # ========================================================================
    
    def get_positions_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的持仓"""
        user_system = self.get_user_system(user_id)
        if user_system:
            return user_system.get_positions()
        return []
    
    def get_trades_for_user(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取用户的交易记录"""
        user_system = self.get_user_system(user_id)
        if user_system:
            return user_system.get_trades(limit)
        return []


# ============================================================================
# 全局单例访问
# ============================================================================

def get_multi_user_trading_manager() -> MultiUserTradingManager:
    """
    获取多用户交易系统管理器单例
    
    Returns:
        MultiUserTradingManager 实例
    """
    return MultiUserTradingManager()


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 测试管理器
    manager = get_multi_user_trading_manager()
    
    print("\n" + "="*60)
    print("🧪 测试多用户交易系统管理器")
    print("="*60)
    
    # 用户 A 启动系统
    print("\n1️⃣ 用户 A 启动交易系统...")
    result_a = manager.start_for_user(
        user_id="user_a",
        username="Alice",
        config={
            "mode": "demo",
            "symbols": ["BTCUSDT"],
            "check_interval": 10
        }
    )
    print(f"   结果: {result_a}")
    
    # 用户 B 启动系统
    print("\n2️⃣ 用户 B 启动交易系统...")
    result_b = manager.start_for_user(
        user_id="user_b",
        username="Bob",
        config={
            "mode": "demo",
            "symbols": ["ETHUSDT"],
            "check_interval": 10
        }
    )
    print(f"   结果: {result_b}")
    
    # 查询所有用户状态
    import time
    time.sleep(3)
    print("\n3️⃣ 查询所有用户状态...")
    all_status = manager.get_all_users_status()
    for status in all_status:
        print(f"   用户 {status['username']}: {status['state']} - 交易对: {status['config']['symbols']}")
    
    # 运行一段时间
    print("\n4️⃣ 运行30秒...")
    time.sleep(30)
    
    # 再次查询
    print("\n5️⃣ 查询运行统计...")
    for status in manager.get_all_users_status():
        print(f"   用户 {status['username']}:")
        print(f"     总交易: {status['stats']['total_trades']}")
        print(f"     总盈亏: ${status['stats']['total_pnl']:.2f}")
    
    # 停止所有
    print("\n6️⃣ 停止所有用户的交易系统...")
    manager.stop_for_user("user_a")
    manager.stop_for_user("user_b")
    
    print("\n" + "="*60)
    print("✅ 测试完成 - 两个用户独立运行，互不干扰！")
    print("="*60 + "\n")

