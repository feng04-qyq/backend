"""
启动脚本：同时运行交易系统和API服务器

使用方法:
python run_with_api.py
"""

import threading
import uvicorn
import logging
import time
from api_server import app, attach_trading_engine
from bybit_live_trading_system import LiveTradingEngine

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def run_api_server():
    """启动API服务器"""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )

def run_trading_engine():
    """启动交易引擎"""
    time.sleep(2)  # 等待API服务器启动
    
    try:
        # 初始化交易引擎
        engine = LiveTradingEngine()
        
        # 附加到API服务器
        attach_trading_engine(engine)
        
        # 启动交易
        engine.run()
        
    except KeyboardInterrupt:
        logging.info("接收到停止信号，正在关闭...")
        engine.stop()
    except Exception as e:
        logging.error(f"交易引擎错误: {e}", exc_info=True)

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 Bybit AI交易系统 - 启动中...")
    print("="*70)
    print()
    print("📡 API服务器: http://localhost:8000")
    print("📚 API文档: http://localhost:8000/docs")
    print("🔌 WebSocket: ws://localhost:8000/ws")
    print()
    print("="*70 + "\n")
    
    # 创建线程
    api_thread = threading.Thread(target=run_api_server, daemon=True)
    trading_thread = threading.Thread(target=run_trading_engine, daemon=True)
    
    # 启动线程
    api_thread.start()
    trading_thread.start()
    
    try:
        # 保持主线程运行
        api_thread.join()
        trading_thread.join()
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("🛑 正在停止系统...")
        print("="*70 + "\n")



