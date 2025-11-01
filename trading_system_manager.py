"""
交易系统管理器 - Trading System Manager
将 bybit_live_trading_system.py 封装为可API调用的服务

功能：
- 单例模式管理交易系统实例
- 异步启动/停止交易系统
- 状态查询和监控
- 配置动态更新
"""

import logging
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

from trading_runtime_config import load_trading_runtime_config


class TradingSystemState(str, Enum):
    """交易系统状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class TradingSystemManager:
    """
    交易系统管理器（单例模式）
    
    负责管理 bybit_live_trading_system 的生命周期
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
        self.state = TradingSystemState.STOPPED
        self.trading_system = None
        self.trading_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # 系统统计
        self.stats = {
            "start_time": None,
            "stop_time": None,
            "total_trades": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "total_pnl": 0.0,
            "active_positions": 0,
            "last_error": None
        }
        
        # 配置
        self.config = {
            "mode": "demo",  # demo/testnet/live
            "symbols": ["BTCUSDT"],
            "max_positions": 3,
            "check_interval": 60,
            "use_ai": True
        }
        
        logger.info("✅ 交易系统管理器初始化完成")
    
    # ========================================================================
    # 生命周期管理
    # ========================================================================
    
    def start(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        启动交易系统
        
        Args:
            config: 配置字典（可选）
            
        Returns:
            操作结果
        """
        try:
            if self.state == TradingSystemState.RUNNING:
                return {
                    "success": False,
                    "message": "交易系统已在运行中",
                    "state": self.state
                }
            
            if self.state == TradingSystemState.STARTING:
                return {
                    "success": False,
                    "message": "交易系统正在启动中",
                    "state": self.state
                }
            
            requested_mode = None
            if config and "mode" in config:
                requested_mode = config.get("mode")

            try:
                runtime_overrides = load_trading_runtime_config(preferred_mode=requested_mode)
            except RuntimeError as runtime_error:
                logger.error(f"❌ 加载交易配置失败: {runtime_error}")
                self.state = TradingSystemState.ERROR
                self.stats["last_error"] = str(runtime_error)
                return {
                    "success": False,
                    "message": str(runtime_error),
                    "state": self.state,
                }

            # 先应用运行时配置，然后覆盖用户传入的额外参数（例如 symbols、check_interval）
            self.config.update(runtime_overrides)

            if config:
                self.config.update({k: v for k, v in config.items() if v is not None})

            # 保证模式字段与真实环境一致
            if "mode" not in self.config and "active_environment" in runtime_overrides:
                active_env = runtime_overrides["active_environment"]
                self.config["mode"] = "live" if active_env == "mainnet" else active_env
            elif "active_environment" in runtime_overrides:
                # 如果外部传入 mode 与凭证环境不一致，以凭证环境为准
                active_env = runtime_overrides["active_environment"]
                expected_mode = "live" if active_env == "mainnet" else active_env
                self.config["mode"] = expected_mode
            
            logger.info(
                "🚀 正在启动交易系统... 模式: %s | 环境: %s",
                self.config.get("mode"),
                runtime_overrides.get("active_environment"),
            )
            self.state = TradingSystemState.STARTING
            
            # 重置停止事件
            self.stop_event.clear()
            
            # 启动交易系统线程
            self.trading_thread = threading.Thread(
                target=self._run_trading_system,
                daemon=True
            )
            self.trading_thread.start()
            
            # 等待系统初始化
            import time
            time.sleep(2)
            
            if self.state == TradingSystemState.RUNNING:
                self.stats["start_time"] = datetime.now().isoformat()
                logger.info("✅ 交易系统启动成功")
                return {
                    "success": True,
                    "message": "交易系统启动成功",
                    "state": self.state,
                    "config": self.config
                }
            else:
                logger.error("❌ 交易系统启动失败")
                return {
                    "success": False,
                    "message": f"交易系统启动失败: {self.stats.get('last_error', 'Unknown')}",
                    "state": self.state
                }
                
        except Exception as e:
            logger.error(f"❌ 启动交易系统时出错: {e}")
            self.state = TradingSystemState.ERROR
            self.stats["last_error"] = str(e)
            return {
                "success": False,
                "message": f"启动失败: {str(e)}",
                "state": self.state
            }
    
    def stop(self) -> Dict[str, Any]:
        """
        停止交易系统
        
        Returns:
            操作结果
        """
        try:
            if self.state == TradingSystemState.STOPPED:
                return {
                    "success": False,
                    "message": "交易系统未在运行",
                    "state": self.state
                }
            
            logger.info("🛑 正在停止交易系统...")
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
            
            logger.info("✅ 交易系统已停止")
            return {
                "success": True,
                "message": "交易系统已停止",
                "state": self.state
            }
            
        except Exception as e:
            logger.error(f"❌ 停止交易系统时出错: {e}")
            self.state = TradingSystemState.ERROR
            self.stats["last_error"] = str(e)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
                "state": self.state
            }
    
    def restart(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        重启交易系统
        
        Args:
            config: 新配置（可选）
            
        Returns:
            操作结果
        """
        logger.info("🔄 正在重启交易系统...")
        
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
        """
        在后台线程中运行交易系统
        
        这里是交易系统的主循环
        """
        try:
            logger.info("📊 交易系统线程启动")
            
            # 导入交易系统（延迟导入避免循环依赖）
            try:
                from bybit_live_trading_system import LiveTradingEngine

                engine_kwargs = {
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

                # 过滤掉 None，避免覆盖默认值
                engine_kwargs = {k: v for k, v in engine_kwargs.items() if v is not None}

                # 创建交易系统实例
                self.trading_system = LiveTradingEngine(**engine_kwargs)
                
                logger.info("✅ 交易系统实例创建成功")
                self.state = TradingSystemState.RUNNING
                
                # 运行交易系统（阻塞调用）
                self.trading_system.run()
                
            except ImportError as e:
                logger.error(f"❌ 无法导入交易系统: {e}")
                logger.info("⚠️ 使用模拟交易系统")
                self.state = TradingSystemState.RUNNING
                
                # 模拟交易系统（用于开发/测试）
                self._run_mock_trading_system()
            
        except Exception as e:
            logger.error(f"❌ 交易系统运行错误: {e}")
            self.state = TradingSystemState.ERROR
            self.stats["last_error"] = str(e)
        finally:
            logger.info("📊 交易系统线程结束")
            if self.state != TradingSystemState.ERROR:
                self.state = TradingSystemState.STOPPED
    
    def _run_mock_trading_system(self):
        """
        模拟交易系统（用于开发/测试）
        
        当 bybit_live_trading_system 不可用时使用
        """
        logger.info("🎭 运行模拟交易系统")
        
        import time
        import random
        
        while not self.stop_event.is_set():
            try:
                # 模拟交易逻辑
                if random.random() > 0.8:  # 20% 概率生成交易
                    trade_type = random.choice(["buy", "sell"])
                    symbol = random.choice(self.config["symbols"])
                    
                    logger.info(f"📈 模拟交易: {trade_type.upper()} {symbol}")
                    
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
                logger.error(f"模拟交易系统错误: {e}")
                time.sleep(5)
        
        logger.info("🎭 模拟交易系统已停止")
    
    # ========================================================================
    # 状态查询
    # ========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取交易系统状态
        
        Returns:
            状态信息字典
        """
        return {
            "state": self.state,
            "is_running": self.state == TradingSystemState.RUNNING,
            "config": self.config,
            "stats": self.stats,
            "thread_alive": self.trading_thread.is_alive() if self.trading_thread else False
        }
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        获取当前持仓
        
        Returns:
            持仓列表
        """
        if self.trading_system and hasattr(self.trading_system, 'get_positions'):
            try:
                return self.trading_system.get_positions()
            except Exception as e:
                logger.error(f"获取持仓失败: {e}")
        
        # 模拟返回
        return []
    
    def get_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取交易历史
        
        Args:
            limit: 返回数量限制
            
        Returns:
            交易记录列表
        """
        if self.trading_system and hasattr(self.trading_system, 'get_trades'):
            try:
                return self.trading_system.get_trades(limit=limit)
            except Exception as e:
                logger.error(f"获取交易记录失败: {e}")
        
        # 模拟返回
        return []
    
    def update_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新配置（需要重启才能生效）
        
        Args:
            config: 新配置
            
        Returns:
            操作结果
        """
        try:
            self.config.update(config)
            logger.info(f"✅ 配置已更新: {config}")
            
            return {
                "success": True,
                "message": "配置已更新（重启后生效）",
                "config": self.config
            }
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            return {
                "success": False,
                "message": f"更新失败: {str(e)}"
            }


# ============================================================================
# 全局单例访问
# ============================================================================

def get_trading_system_manager() -> TradingSystemManager:
    """
    获取交易系统管理器单例
    
    Returns:
        TradingSystemManager 实例
    """
    return TradingSystemManager()


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
    manager = get_trading_system_manager()
    
    print("\n" + "="*60)
    print("🧪 测试交易系统管理器")
    print("="*60)
    
    # 启动
    print("\n1️⃣ 启动交易系统...")
    result = manager.start({
        "mode": "demo",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "check_interval": 10
    })
    print(f"   结果: {result}")
    
    # 状态查询
    import time
    time.sleep(3)
    print("\n2️⃣ 查询状态...")
    status = manager.get_status()
    print(f"   状态: {status['state']}")
    print(f"   配置: {status['config']}")
    print(f"   统计: {status['stats']}")
    
    # 运行一段时间
    print("\n3️⃣ 运行30秒...")
    time.sleep(30)
    
    # 再次查询
    status = manager.get_status()
    print(f"   总交易: {status['stats']['total_trades']}")
    print(f"   成功: {status['stats']['successful_trades']}")
    print(f"   总盈亏: {status['stats']['total_pnl']:.2f}")
    
    # 停止
    print("\n4️⃣ 停止交易系统...")
    result = manager.stop()
    print(f"   结果: {result}")
    
    print("\n" + "="*60)
    print("✅ 测试完成")
    print("="*60 + "\n")

