"""
Bybit API实盘自动合约交易系统 (基于DeepSeek AI决策)

功能：
1. 实时多资产数据获取（BTC/ETH/SOL永续合约）
2. AI自主交易决策（集成回测系统的AI引擎）
3. 自动订单管理（开仓/平仓/止盈止损）
4. 持仓监控和风险控制
5. 极端行情保护
6. 完整的日志记录

安全特性：
- 最大仓位30%限制
- 极端行情保护（5种机制）
- API密钥加密存储
- 错误重试机制
- 紧急停止开关

参考文档：https://bybit-exchange.github.io/docs/v5/intro
"""

import json
import os
import time
import hmac
import hashlib
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import logging
from logging.handlers import RotatingFileHandler
import pandas as pd
import numpy as np
from threading import Thread, Event
import sys

# 时区处理
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python 3.8 及更早版本，使用pytz
    try:
        import pytz
        # 创建兼容的ZoneInfo类
        class ZoneInfo:
            def __init__(self, key):
                self.key = key
                self.tz = pytz.timezone(key)
            def __repr__(self):
                return f"ZoneInfo({self.key})"
    except ImportError:
        logging.warning("⚠️ 未安装时区库，将使用系统时区")

# 自动检测系统时区
def get_local_timezone():
    """
    自动检测系统时区
    
    Returns:
        时区名称字符串（如'Asia/Shanghai'）
    """
    try:
        # 方法1：使用datetime的本地时区偏移
        local_offset = datetime.now(timezone.utc).astimezone().utcoffset()
        offset_hours = local_offset.total_seconds() / 3600
        
        # 常见时区映射
        timezone_map = {
            8: 'Asia/Shanghai',      # UTC+8 中国
            9: 'Asia/Tokyo',          # UTC+9 日本
            7: 'Asia/Bangkok',        # UTC+7 泰国
            -5: 'America/New_York',   # UTC-5 美国东部
            -8: 'America/Los_Angeles',# UTC-8 美国西部
            0: 'UTC',                 # UTC
            1: 'Europe/London',       # UTC+1 英国（夏令时）
        }
        
        tz_name = timezone_map.get(int(offset_hours), f'Etc/GMT{int(-offset_hours):+d}')
        
        logging.info(f"🌍 检测到系统时区: {tz_name} (UTC{offset_hours:+.1f})")
        return tz_name
        
    except Exception as e:
        logging.warning(f"⚠️ 时区检测失败: {e}，使用默认UTC+8")
        return 'Asia/Shanghai'

# 全局时区设置
SYSTEM_TIMEZONE = get_local_timezone()

# 导入AI提示词管理器和交易组件
try:
    from ai_prompts_manager import (
        MultiAssetDeepSeekTrader,  # AI决策引擎（LiveTradingAIEngine的别名）
        ExtremeMarketProtection,   # 极端市场保护
        setup_logging              # 日志系统
    )
    from trade_journal import TradeJournal, get_trade_journal
    from candlestick_patterns import get_pattern_recognizer
    from ai_interaction_logger import get_ai_interaction_logger, log_ai_decision
    from enhanced_indicators import EnhancedIndicators  # 增强版技术指标
except ImportError as e:
    print(f"错误：无法导入系统组件: {e}")
    print("请确保ai_prompts_manager.py和trade_journal.py在同一目录")
    exit(1)


# ==================== Bybit API客户端 ====================

class BybitAPIClient:
    """
    Bybit V5 API客户端
    
    文档：https://bybit-exchange.github.io/docs/v5/intro
    """
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False, demo: bool = False):
        """
        初始化API客户端
        
        Args:
            api_key: Bybit API密钥
            api_secret: Bybit API密钥
            testnet: 是否使用测试网（默认False）
            demo: 是否使用主网模拟盘（默认False）
            
        环境说明：
            - testnet=True: 测试网（需要testnet.bybit.com的API密钥）
            - demo=True: 主网模拟盘（需要主网API密钥，在模拟交易创建）
            - 都为False: 主网实盘（需要主网API密钥）
        """
        self.api_key = api_key
        self.api_secret = api_secret
        
        # API端点
        if testnet:
            self.base_url = "https://api-testnet.bybit.com"
            logging.info("🧪 使用Bybit测试网")
        elif demo:
            self.base_url = "https://api-demo.bybit.com"
            logging.info("🎮 使用Bybit主网模拟盘（虚拟资金）")
        else:
            # 主网端点（官方提供两个地址，可根据网络情况选择）
            self.base_url = "https://api.bybit.com"
            self.backup_url = "https://api.bytick.com"  # 备用地址
            logging.info("🔴 使用Bybit主网（实盘）")
        
        self.recv_window = 5000  # 5秒接收窗口
        self.time_offset = 0  # 本地时间与服务器时间的偏移量（毫秒）
        
        # 初始化时同步服务器时间
        self._sync_server_time()
        
    def _sync_server_time(self):
        """
        同步服务器时间，计算本地时间偏移
        
        文档：https://bybit-exchange.github.io/docs/zh-TW/v5/market/time
        """
        try:
            response = requests.get(f"{self.base_url}/v5/market/time", timeout=5)
            if response.status_code == 200:
                result = response.json()
                if result.get('retCode') == 0:
                    server_time = int(result['result']['timeSecond']) * 1000  # 转为毫秒
                    local_time = int(time.time() * 1000)
                    self.time_offset = server_time - local_time
                    logging.info(f"✓ 服务器时间已同步，偏移量: {self.time_offset}ms")
                    return
            logging.warning("⚠️ 无法同步服务器时间，使用本地时间")
        except Exception as e:
            logging.warning(f"⚠️ 服务器时间同步失败: {e}，使用本地时间")
    
    def _get_timestamp(self) -> str:
        """
        获取当前时间戳（毫秒），考虑服务器时间偏移
        
        确保满足Bybit时间窗口要求：server_time - recv_window <= timestamp < server_time + 1000
        """
        return str(int(time.time() * 1000) + self.time_offset)
    
    def _generate_signature(self, params: str, timestamp: str) -> str:
        """
        生成API签名
        
        签名算法：HMAC SHA256
        签名格式：timestamp + api_key + recv_window + params
        
        文档：https://bybit-exchange.github.io/docs/zh-TW/v5/guide#authentication
        """
        param_str = f"{timestamp}{self.api_key}{self.recv_window}{params}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _send_request(self, method: str, endpoint: str, params: Dict = None, signed: bool = False) -> Dict:
        """
        发送HTTP请求（完全符合Bybit V5 API规范）
        
        Args:
            method: GET/POST
            endpoint: API端点（如/v5/market/tickers）
            params: 请求参数
            signed: 是否需要签名（私有接口需要）
        
        Returns:
            API响应JSON
            
        参考：https://bybit-exchange.github.io/docs/zh-TW/v5/guide#authentication
        """
        url = self.base_url + endpoint
        params = params or {}
        
        headers = {
            "Content-Type": "application/json",
        }
        
        # 用于POST请求的数据字符串
        post_data = None
        
        if signed:
            # 生成时间戳（使用服务器时间偏移）
            timestamp = self._get_timestamp()
            
            # 构建签名字符串
            if method == "POST":
                # POST请求：将参数序列化为JSON字符串
                params_str = json.dumps(params) if params else ""
                post_data = params_str  # 保存用于发送
            else:
                # GET请求：参数按key排序后拼接
                params_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())]) if params else ""
            
            # 生成签名
            signature = self._generate_signature(params_str, timestamp)
            
            # 添加认证头部
            headers.update({
                "X-BAPI-API-KEY": self.api_key,
                "X-BAPI-SIGN": signature,
                "X-BAPI-SIGN-TYPE": "2",  # 重要：HMAC SHA256签名类型
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": str(self.recv_window)
            })
        
        try:
            if method == "GET":
                response = requests.get(url, params=params, headers=headers, timeout=10)
            elif method == "POST":
                # POST请求：根据是否签名选择不同的发送方式
                if signed:
                    # 签名请求：发送JSON字符串作为data
                    response = requests.post(url, data=post_data, headers=headers, timeout=10)
                else:
                    # 非签名请求：使用json参数（自动序列化）
                    response = requests.post(url, json=params, headers=headers, timeout=10)
            else:
                raise ValueError(f"不支持的HTTP方法: {method}")
            
            response.raise_for_status()
            result = response.json()
            
            # 检查Bybit返回码
            if result.get('retCode') != 0:
                ret_code = result.get('retCode')
                ret_msg = result.get('retMsg', 'Unknown error')
                
                # 特殊错误码处理
                if ret_code == 10002:
                    logging.error(f"❌ 签名验证失败: {ret_msg}")
                    logging.error("   请检查：1) API密钥是否正确 2) 时间戳是否同步 3) 签名算法是否正确")
                elif ret_code == 10003:
                    logging.error(f"❌ API密钥无效: {ret_msg}")
                elif ret_code == 10004:
                    logging.error(f"❌ 时间戳错误: {ret_msg}")
                    logging.error(f"   当前时间戳: {timestamp if 'timestamp' in locals() else 'N/A'}")
                    logging.error(f"   时间偏移: {self.time_offset}ms")
                elif ret_code == 10006:
                    logging.error(f"❌ 缺少必需参数: {ret_msg}")
                elif ret_code == 110043:
                    # 杠杆未修改（已经是目标值）- 这不是错误
                    logging.info(f"ℹ️ {ret_msg}（杠杆已是目标值，无需修改）")
                    return result  # 返回成功
                elif ret_code == 10001 and "zero position" in ret_msg:
                    # 无法为零持仓设置止盈止损 - 这是预期的
                    logging.debug(f"ℹ️ {ret_msg}（当前无持仓）")
                    return None  # 这是正常情况，不是错误
                else:
                    logging.error(f"❌ Bybit API错误 [{ret_code}]: {ret_msg}")
                
                return None
            
            return result
            
        except requests.exceptions.Timeout:
            logging.error(f"⏱️ API请求超时: {endpoint}")
            return None
        except requests.exceptions.HTTPError as e:
            logging.error(f"🌐 HTTP错误: {endpoint}, 状态码: {e.response.status_code}")
            try:
                error_detail = e.response.json()
                logging.error(f"   详情: {error_detail}")
            except:
                logging.error(f"   详情: {e.response.text[:200]}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"🔌 网络请求失败: {endpoint}, 错误: {e}")
            return None
        except json.JSONDecodeError as e:
            logging.error(f"📄 JSON解析失败: {endpoint}, 错误: {e}")
            return None
        except Exception as e:
            logging.error(f"❓ 未知错误: {endpoint}, 错误: {e}", exc_info=True)
            return None
    
    def get_server_time(self) -> Optional[Dict]:
        """
        获取Bybit服务器时间（用于测试和同步）
        
        文档：https://bybit-exchange.github.io/docs/zh-TW/v5/market/time
        
        Returns:
            {
                'timeSecond': '1234567890',  # 服务器时间（秒）
                'timeNano': '1234567890123456789'  # 服务器时间（纳秒）
            }
        """
        endpoint = "/v5/market/time"
        result = self._send_request("GET", endpoint)
        if result and result.get('result'):
            return result['result']
        return None
    
    # ==================== 市场数据接口 ====================
    
    def get_kline(self, symbol: str, interval: str, limit: int = 200) -> Optional[List[Dict]]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对（如BTCUSDT）
            interval: 时间间隔（15/60/240=15分钟/1小时/4小时）
            limit: 返回数量（1-1000，默认200）
        
        Returns:
            K线数据列表
        """
        endpoint = "/v5/market/kline"
        params = {
            "category": "linear",  # 永续合约
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        
        result = self._send_request("GET", endpoint, params)
        if result and result.get('result'):
            return result['result'].get('list', [])
        return None
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """
        获取实时行情
        
        Returns:
            行情数据
        """
        endpoint = "/v5/market/tickers"
        params = {
            "category": "linear",
            "symbol": symbol
        }
        
        result = self._send_request("GET", endpoint, params)
        if result and result.get('result'):
            tickers = result['result'].get('list', [])
            return tickers[0] if tickers else None
        return None
    
    def get_orderbook(self, symbol: str, limit: int = 25) -> Optional[Dict]:
        """
        获取订单簿
        
        Args:
            limit: 深度（1/25/50）
        """
        endpoint = "/v5/market/orderbook"
        params = {
            "category": "linear",
            "symbol": symbol,
            "limit": limit
        }
        
        result = self._send_request("GET", endpoint, params)
        if result and result.get('result'):
            return result['result']
        return None
    
    def get_long_short_ratio(self, symbol: str, period: str = "5min") -> Optional[Dict]:
        """
        获取多空比（账户数比例）
        
        文档：https://bybit-exchange.github.io/docs/zh-TW/v5/market/long-short-ratio
        
        Args:
            symbol: 交易对
            period: 数据周期（5min/15min/30min/1h/4h/1d）
        
        Returns:
            {
                'buy_ratio': 多头账户占比,
                'sell_ratio': 空头账户占比
            }
        """
        endpoint = "/v5/market/account-ratio"
        params = {
            "category": "linear",
            "symbol": symbol,
            "period": period,
            "limit": 1  # 只获取最新一条
        }
        
        result = self._send_request("GET", endpoint, params)
        if result and result.get('result'):
            data_list = result['result'].get('list', [])
            if data_list:
                latest = data_list[0]
                return {
                    'buy_ratio': float(latest.get('buyRatio', 0)),
                    'sell_ratio': float(latest.get('sellRatio', 0)),
                    'timestamp': latest.get('timestamp', '')
                }
        return None
    
    def get_funding_rate_history(self, symbol: str, limit: int = 10) -> Optional[List[Dict]]:
        """
        获取历史资金费率
        
        文档：https://bybit-exchange.github.io/docs/zh-TW/v5/market/history-fund-rate
        
        Args:
            symbol: 交易对
            limit: 返回数量（1-200）
        
        Returns:
            资金费率历史列表
        """
        endpoint = "/v5/market/funding/history"
        params = {
            "category": "linear",
            "symbol": symbol,
            "limit": limit
        }
        
        result = self._send_request("GET", endpoint, params)
        if result and result.get('result'):
            funding_list = result['result'].get('list', [])
            return [
                {
                    'funding_rate': float(item.get('fundingRate', 0)) * 100,  # 转为百分比
                    'funding_rate_timestamp': item.get('fundingRateTimestamp', '')
                }
                for item in funding_list
            ]
        return None
    
    def get_open_interest(self, symbol: str, interval: str = "5min") -> Optional[Dict]:
        """
        获取持仓量
        
        文档：https://bybit-exchange.github.io/docs/zh-TW/v5/market/open-interest
        
        Args:
            symbol: 交易对
            interval: 时间间隔（5min/15min/30min/1h/4h/1d）
        
        Returns:
            持仓量数据
        """
        endpoint = "/v5/market/open-interest"
        params = {
            "category": "linear",
            "symbol": symbol,
            "intervalTime": interval,
            "limit": 1
        }
        
        result = self._send_request("GET", endpoint, params)
        if result and result.get('result'):
            data_list = result['result'].get('list', [])
            if data_list:
                return {
                    'open_interest': float(data_list[0].get('openInterest', 0)),
                    'timestamp': data_list[0].get('timestamp', '')
                }
        return None
    
    def get_instruments_info(self, symbol: Optional[str] = None) -> Optional[Dict]:
        """
        获取交易规则信息
        
        文档：https://bybit-exchange.github.io/docs/zh-TW/v5/market/instrument
        
        Args:
            symbol: 交易对（可选，不传则返回所有）
        
        Returns:
            交易规则信息，包括：
            - lotSizeFilter: 数量精度规则
            - priceFilter: 价格精度规则
            - leverageFilter: 杠杆规则
            等
        """
        endpoint = "/v5/market/instruments-info"
        params = {
            "category": "linear"
        }
        
        if symbol:
            params["symbol"] = symbol
        
        result = self._send_request("GET", endpoint, params)
        if result and result.get('result'):
            instruments = result['result'].get('list', [])
            
            if symbol:
                # 返回指定交易对的规则
                for inst in instruments:
                    if inst.get('symbol') == symbol:
                        return inst
                return None
            else:
                # 返回所有交易对规则（字典格式）
                return {inst.get('symbol'): inst for inst in instruments}
        
        return None
    
    # ==================== 账户接口 ====================
    
    def get_wallet_balance(self, account_type: str = "UNIFIED") -> Optional[Dict]:
        """
        获取钱包余额
        
        Args:
            account_type: UNIFIED(统一账户)/CONTRACT(合约账户)
        """
        endpoint = "/v5/account/wallet-balance"
        params = {
            "accountType": account_type
        }
        
        result = self._send_request("GET", endpoint, params, signed=True)
        if result and result.get('result'):
            return result['result']
        return None
    
    # ==================== 交易接口 ====================
    
    def place_order(self, symbol: str, side: str, order_type: str, qty: str, 
                   price: Optional[str] = None, time_in_force: str = "GTC",
                   reduce_only: bool = False, close_on_trigger: bool = False,
                   stop_loss: Optional[str] = None, take_profit: Optional[str] = None) -> Optional[str]:
        """
        下单（Bybit V5 API）
        
        Args:
            symbol: 交易对（如BTCUSDT）
            side: Buy/Sell
            order_type: Market/Limit
            qty: 数量（字符串格式）
            price: 价格（限价单必需，字符串格式）
            time_in_force: GTC(成交为止)/IOC(立即成交否则取消)/FOK(全部成交否则取消)
            reduce_only: 只减仓
            close_on_trigger: 触发后平仓
            stop_loss: 止损价格（字符串格式）
            take_profit: 止盈价格（字符串格式）
        
        Returns:
            订单ID
        """
        endpoint = "/v5/order/create"
        
        params = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "positionIdx": 0  # 单向持仓模式（统一账户默认）
        }
        
        # 限价单必需价格和timeInForce
        if order_type == "Limit":
            if not price:
                logging.error("限价单必须提供价格")
                return None
            params["price"] = price
            params["timeInForce"] = time_in_force
        
        # 市价单timeInForce可选（但某些情况下需要）
        if order_type == "Market" and reduce_only:
            # 平仓市价单通常不需要timeInForce
            pass
        elif order_type == "Market":
            # 开仓市价单可能需要IOC
            params["timeInForce"] = "IOC"
        
        # 可选参数
        if reduce_only:
            params["reduceOnly"] = True
        if close_on_trigger:
            params["closeOnTrigger"] = True
        # 注意：price已在上面限价单部分设置，此处不重复
        if stop_loss:
            params["stopLoss"] = stop_loss
        if take_profit:
            params["takeProfit"] = take_profit
        
        result = self._send_request("POST", endpoint, params, signed=True)
        if result and result.get('result'):
            order_id = result['result'].get('orderId')
            logging.info(f"✓ 订单已提交: {order_id} | {side} {symbol} {qty}")
            return order_id
        return None
    
    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        取消订单
        """
        endpoint = "/v5/order/cancel"
        params = {
            "category": "linear",
            "symbol": symbol,
            "orderId": order_id
        }
        
        result = self._send_request("POST", endpoint, params, signed=True)
        return result is not None
    
    def get_order_history(self, symbol: str, order_id: str) -> Optional[Dict]:
        """
        获取历史订单详情
        
        Args:
            symbol: 交易对
            order_id: 订单ID
        
        Returns:
            订单详情，包含avgPrice（成交均价）等信息
        """
        endpoint = "/v5/order/history"
        params = {
            "category": "linear",
            "symbol": symbol,
            "orderId": order_id
        }
        
        result = self._send_request("GET", endpoint, params, signed=True)
        if result and result.get('result'):
            orders = result['result'].get('list', [])
            return orders[0] if orders else None
        return None
    
    def cancel_all_orders(self, symbol: Optional[str] = None, settle_coin: Optional[str] = None) -> bool:
        """
        取消所有订单
        
        Args:
            symbol: 指定交易对（可选）
            settle_coin: 按结算币种取消（如USDT）
        """
        endpoint = "/v5/order/cancel-all"
        params = {
            "category": "linear"
        }
        
        if symbol:
            params["symbol"] = symbol
        if settle_coin:
            params["settleCoin"] = settle_coin
        
        result = self._send_request("POST", endpoint, params, signed=True)
        return result is not None
    
    def get_open_orders(self, symbol: Optional[str] = None) -> Optional[List[Dict]]:
        """
        获取活动订单
        """
        endpoint = "/v5/order/realtime"
        params = {
            "category": "linear"
        }
        
        if symbol:
            params["symbol"] = symbol
        
        result = self._send_request("GET", endpoint, params, signed=True)
        if result and result.get('result'):
            return result['result'].get('list', [])
        return None
    
    # ==================== 持仓接口 ====================
    
    def get_positions(self, symbol: Optional[str] = None, settle_coin: Optional[str] = "USDT") -> Optional[List[Dict]]:
        """
        获取持仓信息
        
        Args:
            symbol: 指定交易对
            settle_coin: 结算币种（USDT/USDC）
        """
        endpoint = "/v5/position/list"
        params = {
            "category": "linear",
            "settleCoin": settle_coin
        }
        
        if symbol:
            params["symbol"] = symbol
        
        result = self._send_request("GET", endpoint, params, signed=True)
        if result and result.get('result'):
            return result['result'].get('list', [])
        return None
    
    def set_position_mode(self, symbol: str, mode: int = 3) -> bool:
        """
        设置持仓模式（重要：必须在交易前设置）
        
        Args:
            symbol: 交易对
            mode: 0=单向持仓, 3=双向持仓（Bybit V5默认建议3）
        
        Returns:
            是否成功
        """
        endpoint = "/v5/position/switch-mode"
        params = {
            "category": "linear",
            "symbol": symbol,
            "mode": mode
        }
        
        result = self._send_request("POST", endpoint, params, signed=True)
        if result:
            logging.info(f"✓ {symbol} 持仓模式已设置为: {mode}")
            return True
        return False
    
    def set_leverage(self, symbol: str, buy_leverage: str, sell_leverage: str) -> bool:
        """
        设置杠杆（Bybit V5 API）
        
        Args:
            symbol: 交易对
            buy_leverage: 买入杠杆（字符串格式，1-100）
            sell_leverage: 卖出杠杆（字符串格式，1-100）
        
        Returns:
            是否成功（包括杠杆已经是目标值的情况）
        """
        endpoint = "/v5/position/set-leverage"
        params = {
            "category": "linear",
            "symbol": symbol,
            "buyLeverage": buy_leverage,
            "sellLeverage": sell_leverage
        }
        
        result = self._send_request("POST", endpoint, params, signed=True)
        # result不为None表示成功（包括110043杠杆未修改的情况）
        return result is not None
    
    def set_trading_stop(self, symbol: str, stop_loss: Optional[str] = None, 
                        take_profit: Optional[str] = None, position_idx: int = 0) -> bool:
        """
        设置止盈止损（Bybit V5 API）
        
        Args:
            symbol: 交易对
            stop_loss: 止损价格（字符串格式）
            take_profit: 止盈价格（字符串格式）
            position_idx: 持仓方向（0=单向持仓, 1=买侧, 2=卖侧）
        
        Returns:
            是否成功
        """
        endpoint = "/v5/position/trading-stop"
        params = {
            "category": "linear",
            "symbol": symbol,
            "positionIdx": position_idx
        }
        
        if stop_loss:
            params["stopLoss"] = stop_loss
        if take_profit:
            params["takeProfit"] = take_profit
        
        # 至少需要设置一个
        if not stop_loss and not take_profit:
            logging.warning("至少需要设置止损或止盈中的一个")
            return False
        
        result = self._send_request("POST", endpoint, params, signed=True)
        if result:
            if stop_loss and take_profit:
                logging.info(f"✓ {symbol} 止损/止盈已设置: SL={stop_loss}, TP={take_profit}")
            elif stop_loss:
                logging.info(f"✓ {symbol} 止损已设置: {stop_loss}")
            else:
                logging.info(f"✓ {symbol} 止盈已设置: {take_profit}")
            return True
        return False


# ==================== 实时数据管理器 ====================

class LiveMarketDataManager:
    """
    实时市场数据管理器
    
    功能：
    - 实时获取多资产K线数据
    - 计算技术指标（RSI/MACD/EMA/ATR/布林带）
    - 多时间框架数据同步
    """
    
    def __init__(self, api_client: BybitAPIClient, symbols: List[str], use_enhanced_indicators: bool = False):
        self.api = api_client
        self.symbols = symbols
        self.data_cache = {}
        self.use_enhanced_indicators = use_enhanced_indicators  # 是否使用增强指标
        
        # 符号映射（AI使用的格式 → Bybit API格式）
        self.symbol_map = {
            'BTCUSDT_PERPETUAL': 'BTCUSDT',
            'ETHUSDT_PERPETUAL': 'ETHUSDT',
            'SOLUSDT_PERPETUAL': 'SOLUSDT'
        }
        
        indicator_type = "增强版指标（SuperTrend/Ichimoku/ADX等）" if use_enhanced_indicators else "基础指标（RSI/MACD/EMA等）"
        logging.info(f"初始化实时数据管理器: {symbols} | 指标类型: {indicator_type}")
    
    def get_realtime_data(self, symbol: str, timeframes: List[str] = ['15', '60', '240']) -> Optional[Dict]:
        """
        获取实时多时间框架数据（优化版：整合Bybit提供的多种市场数据）
        
        Args:
            symbol: AI格式符号（如BTCUSDT_PERPETUAL）
            timeframes: 时间框架列表（15=15分钟，60=1小时，240=4小时）
        
        Returns:
            {
                '15m': {...基础K线数据 + 计算指标...},
                '1h': {...},
                '4h': {...},
                'advanced_data': {
                    'funding_rate': 资金费率,
                    'open_interest': 持仓量,
                    'long_short_ratio': 多空比,
                    'mark_price': 标记价格,
                    'index_price': 指数价格
                },
                'timestamp': datetime
            }
        """
        # 转换符号格式
        bybit_symbol = self.symbol_map.get(symbol, symbol.replace('_PERPETUAL', ''))
        
        market_data = {}
        candlestick_patterns = {}  # 存储各时间框架的K线形态
        
        # 1. 获取基础K线数据和技术指标
        for tf in timeframes:
            klines = self.api.get_kline(bybit_symbol, tf, limit=200)
            
            if not klines:
                logging.warning(f"无法获取{bybit_symbol}的{tf}分钟K线数据")
                return None
            
            # 转换为DataFrame
            df = self._klines_to_dataframe(klines)
            
            # 计算技术指标（RSI/MACD/EMA等）
            df = self._calculate_indicators(df)
            
            # 获取最新数据（保留向后兼容）
            latest = df.iloc[-1].to_dict()
            
            # 时间框架映射
            tf_name = {'15': '15m', '60': '1h', '240': '4h'}.get(tf, f'{tf}m')
            market_data[tf_name] = latest
            
            # ✨ 新增：返回指定数量的K线历史数据（从旧到新）
            # 优化后的数量：减少50%，降低token消耗
            kline_counts = {'15m': 96, '1h': 24, '4h': 6}
            count = kline_counts.get(tf_name, 24)
            
            # 获取最近N根K线，确保从旧到新排列
            recent_klines = df.tail(count).to_dict('records')
            market_data[f'{tf_name}_klines'] = recent_klines
            
            # 识别K线形态（保存到patterns字典中）
            candlestick_patterns[tf_name] = df  # 保存DataFrame供后续识别
        
        # 2. 获取Bybit提供的高级市场数据（无需自己计算）
        advanced_data = self._get_bybit_advanced_data(bybit_symbol)
        if advanced_data:
            market_data['advanced_data'] = advanced_data
        
        # 3. 添加K线形态分析
        market_data['candlestick_patterns'] = {}
        for tf_name, df in candlestick_patterns.items():
            # 使用K线形态识别器
            from candlestick_patterns import get_pattern_recognizer
            pattern_recognizer = get_pattern_recognizer()
            patterns = pattern_recognizer.analyze_patterns(df)
            market_data['candlestick_patterns'][tf_name] = patterns
        
        market_data['timestamp'] = datetime.now()
        market_data['symbol'] = symbol
        
        return market_data
    
    def _get_bybit_advanced_data(self, symbol: str) -> Dict:
        """
        获取Bybit提供的高级市场数据
        
        参考：https://bybit-exchange.github.io/docs/zh-TW/v5/market
        
        包括：
        1. 实时行情（ticker）- 包含资金费率、持仓量等
        2. 多空比
        3. 标记价格、指数价格
        """
        advanced_data = {}
        
        try:
            # 1. 获取实时行情（包含大量有用信息）
            ticker = self.api.get_ticker(symbol)
            
            if ticker:
                advanced_data.update({
                    # 价格信息
                    'last_price': float(ticker.get('lastPrice', 0)),
                    'mark_price': float(ticker.get('markPrice', 0)),
                    'index_price': float(ticker.get('indexPrice', 0)),
                    
                    # 24小时统计
                    'price_24h_pcnt': float(ticker.get('price24hPcnt', 0)) * 100,  # 24小时涨跌幅%
                    'high_24h': float(ticker.get('highPrice24h', 0)),
                    'low_24h': float(ticker.get('lowPrice24h', 0)),
                    'volume_24h': float(ticker.get('volume24h', 0)),
                    'turnover_24h': float(ticker.get('turnover24h', 0)),
                    
                    # 资金费率（非常重要！）
                    'funding_rate': float(ticker.get('fundingRate', 0)) * 100,  # 转为百分比
                    'next_funding_time': ticker.get('nextFundingTime', ''),
                    
                    # 持仓量（市场热度指标）
                    'open_interest': float(ticker.get('openInterest', 0)),
                    'open_interest_value': float(ticker.get('openInterestValue', 0)),
                    
                    # 买卖盘压力
                    'bid1_price': float(ticker.get('bid1Price', 0)),
                    'bid1_size': float(ticker.get('bid1Size', 0)),
                    'ask1_price': float(ticker.get('ask1Price', 0)),
                    'ask1_size': float(ticker.get('ask1Size', 0)),
                    
                    # 基差（标记价格-现货价格，反映市场情绪）
                    'basis': float(ticker.get('markPrice', 0)) - float(ticker.get('indexPrice', 0)),
                    'basis_rate': (float(ticker.get('markPrice', 0)) - float(ticker.get('indexPrice', 0))) / float(ticker.get('indexPrice', 1)) * 100 if float(ticker.get('indexPrice', 0)) > 0 else 0
                })
            
            # 2. 获取多空比（市场情绪指标）
            long_short_ratio = self.api.get_long_short_ratio(symbol)
            if long_short_ratio:
                advanced_data['long_short_ratio'] = long_short_ratio
            
            # 3. 获取最近资金费率历史（趋势）
            funding_history = self.api.get_funding_rate_history(symbol, limit=3)
            if funding_history:
                advanced_data['funding_rate_trend'] = funding_history
            
        except Exception as e:
            logging.warning(f"获取高级市场数据失败: {e}")
        
        return advanced_data
    
    def _klines_to_dataframe(self, klines: List) -> pd.DataFrame:
        """
        将Bybit K线数据转换为DataFrame
        
        Bybit K线格式：[startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
        """
        df = pd.DataFrame(klines, columns=[
            'start_time', 'open', 'high', 'low', 'close', 'volume', 'turnover'
        ])
        
        # 数据类型转换
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 修复：先将start_time转换为整数，再转换为datetime
        df['start_time'] = pd.to_numeric(df['start_time'], errors='coerce')
        df['timestamp'] = pd.to_datetime(df['start_time'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        return df
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标
        
        根据配置选择：
        - 基础指标：RSI/MACD/EMA/布林带/ATR
        - 增强指标：以上 + SuperTrend/Ichimoku/ADX/StochRSI/AO/Pivot/OBV/VWAP/EMA云带
        """
        if self.use_enhanced_indicators:
            # 使用增强版指标计算
            try:
                calculator = EnhancedIndicators(df)
                df = calculator.calculate_all(include_basic=True)
                logging.debug("✓ 已计算增强版指标")
            except Exception as e:
                logging.warning(f"⚠️ 增强指标计算失败，回退到基础指标: {e}")
                df = self._calculate_basic_indicators(df)
        else:
            # 使用基础指标计算
            df = self._calculate_basic_indicators(df)
        
        return df
    
    def _calculate_basic_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算基础技术指标"""
        # RSI
        df['rsi'] = self._calculate_rsi(df['close'], period=14)
        
        # MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema_12 - ema_26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # EMA
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # 布林带
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        
        # ATR
        df['atr'] = self._calculate_atr(df)
        
        return df
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """计算RSI指标"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        计算ATR指标（使用Wilder平滑法）
        
        Wilder's ATR使用EMA平滑，而不是SMA
        参考：J. Welles Wilder (1978) - New Concepts in Technical Trading Systems
        """
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # 使用EMA平滑（Wilder原始方法）而不是SMA
        atr = tr.ewm(span=period, adjust=False).mean()
        return atr


# ==================== 实盘交易引擎 ====================

class LiveTradingEngine:
    """
    实盘交易引擎
    
    核心功能：
    1. AI决策执行
    2. 订单管理
    3. 持仓监控
    4. 风险控制
    5. 极端行情保护
    """
    
    @staticmethod
    def _normalise_symbols(symbols):
        """Ensure symbols use the *_PERPETUAL suffix expected by Bybit linear contracts."""
        normalised = []
        if not symbols:
            return normalised
        for symbol in symbols:
            if not isinstance(symbol, str):
                continue
            sym = symbol.strip().upper()
            if sym and not sym.endswith("_PERPETUAL"):
                if sym.endswith("USDT"):
                    sym = f"{sym}_PERPETUAL"
            if sym:
                normalised.append(sym)
        return normalised

    def __init__(self, config_file: str = "live_trading_config.json", **overrides):
        # 加载配置
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # 允许直接传入覆盖参数（用于API驱动场景）
        if overrides:
            inline_config = overrides.pop("config", None)
            if isinstance(inline_config, dict):
                self.config.update({k: v for k, v in inline_config.items() if v is not None})

            for key, value in list(overrides.items()):
                if value is None:
                    continue
                self.config[key] = value

        self.user_id = overrides.get("user_id")
        
        # 验证配置
        self._validate_config()
        
        # 初始化API客户端
        self.api = BybitAPIClient(
            api_key=self.config['bybit_api_key'],
            api_secret=self.config['bybit_api_secret'],
            testnet=self.config.get('use_testnet', False),
            demo=self.config.get('use_demo', False)
        )
        
        # 初始化数据管理器
        symbols_override = self.config.get('symbols')
        if symbols_override:
            normalised_symbols = self._normalise_symbols(symbols_override)
        else:
            normalised_symbols = [
            'BTCUSDT_PERPETUAL',
            'ETHUSDT_PERPETUAL',
            'SOLUSDT_PERPETUAL'
            ]
        self.symbols = normalised_symbols
        # 是否使用增强版指标（SuperTrend/Ichimoku/ADX等）
        use_enhanced = self.config.get('use_enhanced_indicators', False)
        self.data_manager = LiveMarketDataManager(self.api, self.symbols, use_enhanced_indicators=use_enhanced)
        
        # 初始化K线形态识别器
        self.pattern_recognizer = get_pattern_recognizer()
        logging.info("✓ K线形态识别器已加载")
        
        # 初始化AI交易器
        self.trader = MultiAssetDeepSeekTrader(self.config.get('deepseek_config', 'deepseek_config.json'))
        
        # 初始化极端行情保护
        self.extreme_protection = ExtremeMarketProtection()
        
        # 初始化交易日志系统
        self.trade_journal = get_trade_journal()
        self.current_trade_id = None  # 当前交易ID
        
        # 初始化AI交互记录器
        self.ai_logger = get_ai_interaction_logger()
        logging.info("✓ AI交互记录器已初始化")
        
        # 交易状态
        self.is_running = False
        self.stop_event = Event()
        self.current_position = None
        self.current_symbol = None
        self.entry_price = 0
        
        # 限价单监控
        self.pending_limit_orders = {}  # {order_id: {'symbol': '', 'create_time': timestamp, 'side': '', 'price': 0, 'qty': 0, 'decision': {}}}
        self.limit_order_timeout = self.config.get('limit_order_timeout', 300)  # 限价单超时时间（秒），默认5分钟
        
        # 持仓保护期（避免频繁止损）
        self.position_hold_time_min = self.config.get('position_hold_time_min', 1800)  # 持仓保护期（秒），默认30分钟
        self.position_entry_time = None  # 记录开仓时间
        self.position_entry_reason = ""  # 记录开仓理由
        
        # 风险控制
        max_position = self.config.get('max_position_pct', 0.30)
        try:
            max_position = float(max_position)
            if max_position > 1:
                max_position = max_position / 100
        except (TypeError, ValueError):
            max_position = 0.30
        self.max_position_pct = max_position  # 最大仓位百分比（0-1）
        self.min_balance = float(self.config.get('min_balance', 10.0))  # 最小余额10 USDT
        self.trading_interval = int(self.config.get('trading_interval', 180))  # 交易间隔（秒），默认3分钟
        
        # 移动止损配置
        self.use_trailing_stop = bool(self.config.get('use_trailing_stop', True))
        self.trailing_stop_distance_multiplier = self.config.get('trailing_stop_distance_atr_multiplier', 1.5)
        self.trailing_stop_trigger_multiplier = self.config.get('trailing_stop_trigger_atr_multiplier', 1.0)
        self.trailing_stop_check_interval = int(self.config.get('trailing_stop_check_interval', 60))
        self.last_trailing_stop_check = 0  # 上次检查时间
        
        # 统计
        self.total_trades = 0
        self.successful_trades = 0
        self.failed_trades = 0
        self.trailing_stop_updates = 0  # 移动止损更新次数
        
        # 资金回撤监控
        self.peak_balance = 0  # 历史最高余额
        self.max_drawdown_pct = 0  # 最大回撤百分比
        self.drawdown_analysis_triggered = False  # 是否已触发10%回撤分析
        
        # 交易规则缓存（从Bybit API获取）
        self.trading_rules = {}
        self._load_trading_rules()
        
        logging.info("✓ 实盘交易引擎初始化完成")
    
    def _validate_config(self):
        """验证配置文件"""
        required_keys = ['bybit_api_key', 'bybit_api_secret']
        
        for key in required_keys:
            if key not in self.config or not self.config[key]:
                raise ValueError(f"配置文件缺少必需项: {key}")
        
        # 检查API密钥格式
        if self.config['bybit_api_key'] == 'YOUR_BYBIT_API_KEY':
            raise ValueError("请配置有效的Bybit API密钥")
        
        logging.info("✓ 配置验证通过")
    
    def _load_trading_rules(self):
        """
        从Bybit API加载交易规则
        
        统一账户（全仓杠杆）支持的规则：
        - lotSizeFilter: 数量精度规则
        - priceFilter: 价格精度规则
        - leverageFilter: 杠杆规则
        """
        logging.info("正在加载交易规则...")
        
        try:
            # 获取所有监控资产的交易规则
            for symbol in self.symbols:
                bybit_symbol = symbol.replace('_PERPETUAL', '')
                
                rules = self.api.get_instruments_info(bybit_symbol)
                
                if rules:
                    # 解析交易规则
                    lot_size_filter = rules.get('lotSizeFilter', {})
                    price_filter = rules.get('priceFilter', {})
                    leverage_filter = rules.get('leverageFilter', {})
                    
                    self.trading_rules[bybit_symbol] = {
                        # 数量规则
                        'qty_step': float(lot_size_filter.get('qtyStep', 0.001)),
                        'min_order_qty': float(lot_size_filter.get('minOrderQty', 0.001)),
                        'max_order_qty': float(lot_size_filter.get('maxOrderQty', 100000)),
                        'min_order_amt': float(lot_size_filter.get('minOrderAmt', 0)),  # 最小订单金额
                        'max_order_amt': float(lot_size_filter.get('maxOrderAmt', 0)),  # 最大订单金额
                        
                        # 价格规则
                        'tick_size': float(price_filter.get('tickSize', 0.01)),
                        'min_price': float(price_filter.get('minPrice', 0)),
                        'max_price': float(price_filter.get('maxPrice', 999999)),
                        
                        # 杠杆规则
                        'min_leverage': float(leverage_filter.get('minLeverage', 1)),
                        'max_leverage': float(leverage_filter.get('maxLeverage', 100)),
                        'leverage_step': float(leverage_filter.get('leverageStep', 0.01)),
                        
                        # 其他信息
                        'status': rules.get('status', 'Trading'),
                        'unified_margin_trade': rules.get('unifiedMarginTrade', True),  # 是否支持统一账户
                        'contract_type': rules.get('contractType', 'LinearPerpetual')
                    }
                    
                    logging.info(f"  ✓ {bybit_symbol} 交易规则已加载")
                    logging.info(f"    - 数量精度: {self.trading_rules[bybit_symbol]['qty_step']}")
                    logging.info(f"    - 价格精度: {self.trading_rules[bybit_symbol]['tick_size']}")
                    logging.info(f"    - 杠杆范围: {self.trading_rules[bybit_symbol]['min_leverage']}-{self.trading_rules[bybit_symbol]['max_leverage']}x")
                    logging.info(f"    - 统一账户: {'✓' if self.trading_rules[bybit_symbol]['unified_margin_trade'] else '✗'}")
                else:
                    logging.error(f"  ✗ 无法获取{bybit_symbol}交易规则")
            
            if not self.trading_rules:
                raise ValueError("未能加载任何交易规则")
            
            logging.info("✓ 交易规则加载完成\n")
            
        except Exception as e:
            logging.error(f"加载交易规则失败: {e}")
            raise
    
    def start(self):
        """启动交易系统"""
        logging.info("\n" + "="*80)
        logging.info("🚀 启动实盘交易系统")
        logging.info("="*80)
        
        # 检查账户状态
        if not self._check_account_status():
            logging.error("账户检查失败，停止启动")
            return
        
        # 设置杠杆
        self._setup_leverage()
        
        # 启动主循环
        self.is_running = True
        logging.info(f"\n✓ 系统启动成功，交易间隔: {self.trading_interval}秒")
        logging.info(f"监控资产: {', '.join([s.replace('_PERPETUAL', '') for s in self.symbols])}")
        logging.info(f"按 Ctrl+C 停止交易\n")
        
        try:
            self._trading_loop()
        except KeyboardInterrupt:
            logging.warning("\n⚠️ 用户中断，正在安全停止...")
            self.stop()
        except Exception as e:
            logging.error(f"交易循环发生错误: {e}", exc_info=True)
            self.stop()
    
    def _check_account_status(self) -> bool:
        """检查账户状态"""
        logging.info("检查账户状态...")
        
        # 获取钱包余额
        wallet = self.api.get_wallet_balance()
        
        if not wallet:
            logging.error("❌ 无法获取账户余额")
            return False
        
        # 解析余额
        try:
            coins = wallet.get('list', [])[0].get('coin', [])
            usdt_balance = 0
            
            for coin in coins:
                if coin.get('coin') == 'USDT':
                    usdt_balance = float(coin.get('walletBalance', 0))
                    break
            
            logging.info(f"✓ USDT余额: {usdt_balance:.2f} USDT")
            
            if usdt_balance < self.min_balance:
                logging.error(f"❌ 余额不足，最小需要 {self.min_balance} USDT")
                return False
            
            return True
            
        except Exception as e:
            logging.error(f"解析账户信息失败: {e}")
            return False
    
    def _setup_leverage(self):
        """设置杠杆"""
        default_leverage = str(self.config.get('default_leverage', 15))
        
        logging.info(f"设置杠杆为 {default_leverage}x...")
        
        for symbol in self.symbols:
            bybit_symbol = symbol.replace('_PERPETUAL', '')
            
            result = self.api.set_leverage(
                symbol=bybit_symbol,
                buy_leverage=default_leverage,
                sell_leverage=default_leverage
            )
            
            # set_leverage在杠杆未修改时会返回result（不是None）
            if result:
                logging.info(f"✓ {bybit_symbol} 杠杆: {default_leverage}x")
            else:
                logging.warning(f"⚠️ {bybit_symbol} 杠杆设置失败")
    
    def _make_ai_decision_with_logging(self, all_market_data: Dict, position_info: Dict, current_sample_idx: int) -> Dict:
        """
        包装AI决策调用，记录完整的交互信息
        
        Args:
            all_market_data: 所有资产的市场数据
            position_info: 持仓信息
            current_sample_idx: 按交易间隔取整的样本索引（提高缓存命中率）
        
        优化：
        1. 不重复构建提示词（避免冗余计算）
        2. 只在实际调用AI时记录（缓存命中不记录）
        3. 使用按间隔取整的样本索引，提高缓存命中率
        """
        try:
            # 记录调用前的缓存统计
            cache_hits_before = self.trader.cache_hits
            total_calls_before = self.trader.total_calls
            
            # 调用AI决策（使用按间隔取整的样本索引，提高缓存命中率）
            decision = self.trader.make_multi_asset_decision(
                all_market_data=all_market_data,
                position_info=position_info,
                current_sample_idx=current_sample_idx
            )
            
            # 检查是否实际调用了AI（cache miss）
            cache_hit = (self.trader.cache_hits > cache_hits_before)
            actual_api_call = (self.trader.total_calls > total_calls_before)
            
            # 只在实际调用AI时记录（避免冗余存储）
            if actual_api_call and not cache_hit:
                try:
                    # 只记录简化的信息（避免重复构建提示词）
                    self.ai_logger.log_decision_making(
                        system_prompt="[系统提示词已内置于trader]",
                        user_prompt=f"市场分析: {len(all_market_data)}个资产, 持仓: {position_info.get('total_positions', 0)}",
                        market_data=all_market_data,  # 市场数据仍然保存（用于分析）
                        account_state={
                            "balance": position_info.get('balance', 0),
                            "equity": position_info.get('equity', 0),
                            "available_balance": position_info.get('available_balance', 0),
                            "unrealized_pnl": position_info.get('unrealized_pnl', 0),
                            "margin_used": position_info.get('margin_used', 0),
                            "total_positions": position_info.get('total_positions', 0),
                            "positions": position_info.get('positions', []),
                            "has_positions": self.current_position is not None
                        },
                        ai_response=f"决策: {decision.get('action', 'UNKNOWN')}, 置信度: {decision.get('confidence', 0)}%",
                        parsed_decision=decision,
                        execution_result=None
                    )
                    logging.debug("✓ AI交互已记录 (实际API调用)")
                except Exception as log_err:
                    logging.warning(f"记录AI交互失败（不影响交易）: {log_err}")
            else:
                if cache_hit:
                    logging.debug(f"⚡ 缓存命中 - 跳过记录 (命中率: {self.trader.cache_hits}/{self.trader.total_calls})")
            
            return decision
            
        except Exception as e:
            logging.error(f"AI决策失败: {e}", exc_info=True)
            return {
                'action': 'HOLD',
                'reason': f'AI决策失败: {str(e)}',
                'confidence': 0
            }
    
    def _trading_loop(self):
        """主交易循环"""
        while self.is_running and not self.stop_event.is_set():
            try:
                # 0. 检查待成交的限价单
                self._check_pending_limit_orders()
                
                # 1. 获取所有资产的实时数据
                all_market_data = {}
                
                for symbol in self.symbols:
                    market_data = self.data_manager.get_realtime_data(symbol)
                    
                    if market_data:
                        all_market_data[symbol] = market_data
                    else:
                        logging.warning(f"无法获取{symbol}数据")
                
                if not all_market_data:
                    logging.error("无法获取任何市场数据，等待下一轮")
                    time.sleep(self.trading_interval)
                    continue
                
                # 2. 获取当前持仓信息
                position_info = self._get_position_info()
                
                # 2.5. 检查资金回撤（10%触发AI分析）
                current_balance = position_info.get('balance', 0)
                if current_balance > 0:
                    self._check_drawdown_and_analyze(current_balance)
                
                # 3. 极端行情保护检查
                should_protect, reasons = self.extreme_protection.comprehensive_check(
                    all_market_data=all_market_data,
                    current_balance=position_info.get('balance', 0),
                    timestamp=str(datetime.now()),
                    has_position=(self.current_position is not None),
                    current_symbol=self.current_symbol
                )
                
                if should_protect:
                    logging.warning(f"\n{'='*80}")
                    logging.warning("⚠️ 极端行情保护触发！")
                    for reason in reasons:
                        logging.warning(f"  {reason}")
                    logging.warning(f"{'='*80}\n")
                    
                    # 如果有持仓，立即平仓
                    if self.current_position:
                        self._emergency_close_position("极端行情保护")
                    
                    # 暂停交易10分钟
                    logging.info("暂停交易10分钟...")
                    time.sleep(600)
                    continue
                
                # 4. AI决策
                logging.info(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] AI分析中...")
                
                # 计算按交易间隔取整的样本索引（提高缓存命中率）
                # 例如：180秒（3分钟）间隔内的所有调用使用相同的sample_idx
                current_sample_idx = int(time.time() / self.trading_interval)
                
                decision = self._make_ai_decision_with_logging(
                    all_market_data=all_market_data,
                    position_info=position_info,
                    current_sample_idx=current_sample_idx
                )
                
                # 5. 执行交易决策
                self._execute_decision(decision, all_market_data)
                
                # 5.5. 检查并更新移动止损（如果有持仓）
                if self.current_position:
                    self._check_and_update_trailing_stop()
                
                # 6. 等待下一轮
                logging.info(f"等待{self.trading_interval}秒...")
                time.sleep(self.trading_interval)
                
            except Exception as e:
                logging.error(f"交易循环错误: {e}", exc_info=True)
                time.sleep(60)  # 出错后等待1分钟
    
    def _check_pending_limit_orders(self):
        """
        检查待成交的限价单状态
        
        如果订单超时未成交，询问AI是否修改或取消
        """
        if not self.pending_limit_orders:
            return
        
        current_time = time.time()
        orders_to_remove = []
        
        for order_id, order_info in list(self.pending_limit_orders.items()):
            # 计算订单已等待时间
            wait_time = current_time - order_info['create_time']
            
            # 检查订单状态
            order_status = self._get_order_status(order_info['symbol'], order_id)
            
            if order_status is None:
                # 无法获取状态，跳过
                continue
            
            # 如果订单已成交或已取消，从监控列表移除
            if order_status in ['Filled', 'Cancelled', 'Rejected']:
                if order_status == 'Filled':
                    logging.info(f"✅ 限价单已成交: {order_id} | {order_info['symbol']}")
                orders_to_remove.append(order_id)
                continue
            
            # 如果订单超时未成交，询问AI
            if wait_time >= self.limit_order_timeout and order_status in ['New', 'PartiallyFilled']:
                logging.warning(f"\n{'='*80}")
                logging.warning(f"⏰ 限价单超时未成交")
                logging.warning(f"  订单ID: {order_id}")
                logging.warning(f"  交易对: {order_info['symbol']}")
                logging.warning(f"  方向: {order_info['side']}")
                logging.warning(f"  限价: {order_info['price']:.2f} USDT")
                logging.warning(f"  等待时间: {wait_time:.0f}秒 / {self.limit_order_timeout}秒")
                logging.warning(f"  订单状态: {order_status}")
                logging.warning(f"{'='*80}\n")
                
                # 询问AI如何处理
                ai_result = self._ask_ai_about_limit_order(order_id, order_info)
                ai_action = ai_result.get('action', 'continue_wait')
                
                if ai_action == 'cancel_and_market':
                    # 取消限价单，改用市价单
                    self._cancel_and_place_market_order(order_id, order_info)
                    orders_to_remove.append(order_id)
                    
                elif ai_action == 'modify':
                    # 修改订单价格（使用AI建议的新价格）
                    suggested_price = ai_result.get('new_price')
                    new_price = self._modify_limit_order_price(order_id, order_info, suggested_price)
                    if new_price:
                        order_info['price'] = new_price
                        order_info['create_time'] = time.time()  # 重置等待时间
                        logging.info(f"✓ 限价单价格已调整: {new_price:.2f}")
                    
                elif ai_action == 'cancel':
                    # 直接取消
                    self.api.cancel_order(order_info['symbol'], order_id)
                    logging.info(f"✓ 已取消限价单: {order_id}")
                    orders_to_remove.append(order_id)
                    
                # else: continue_wait - 继续等待
        
        # 移除已处理的订单
        for order_id in orders_to_remove:
            self.pending_limit_orders.pop(order_id, None)
    
    def _get_order_status(self, symbol: str, order_id: str) -> Optional[str]:
        """
        获取订单状态
        
        Returns:
            订单状态：New, PartiallyFilled, Filled, Cancelled, Rejected, 等
        """
        try:
            orders = self.api.get_open_orders(symbol)
            if orders:
                for order in orders:
                    if order.get('orderId') == order_id:
                        return order.get('orderStatus')
            
            # 如果不在活动订单中，可能已成交或取消
            # 查询历史订单（可选）
            return 'Filled'  # 假设已成交
            
        except Exception as e:
            logging.error(f"获取订单状态失败: {e}")
            return None
    
    def _format_candlestick_patterns(self, market_data: Dict) -> str:
        """格式化K线形态信息"""
        patterns_data = market_data.get('candlestick_patterns', {})
        if not patterns_data:
            return "无明显形态"
        
        result = []
        for tf_name, data in patterns_data.items():
            if not isinstance(data, dict):
                continue
            patterns = data.get('patterns', [])
            if patterns:
                bullish = [p for p in patterns if p.get('type') == 'bullish']
                bearish = [p for p in patterns if p.get('type') == 'bearish']
                if bullish or bearish:
                    result.append(f"{tf_name}: 看涨{len(bullish)}个, 看跌{len(bearish)}个")
        
        return " | ".join(result) if result else "无明显形态"
    
    def _ask_ai_about_limit_order(self, order_id: str, order_info: Dict) -> Dict:
        """
        询问AI如何处理超时未成交的限价单（增强版：对比下单时和当前的市场数据变化）
        
        Returns:
            Dict with:
                'action': 'cancel_and_market', 'modify', 'cancel', 'continue_wait'
                'new_price': float (如果action='modify')
                'reason': str
        """
        try:
            # 获取当前市场数据
            ai_symbol = order_info.get('ai_symbol', order_info['symbol'] + '_PERPETUAL')
            current_market_data = self.data_manager.get_realtime_data(ai_symbol)
            
            if not current_market_data:
                return {'action': 'continue_wait', 'reason': '无法获取市场数据'}
            
            # 获取下单时的市场数据
            original_market_data = order_info.get('market_data', {})
            original_decision = order_info.get('decision', {})
            
            # 构建对比数据
            def get_data_safely(data, *keys):
                """安全获取嵌套字典数据"""
                for key in keys:
                    if isinstance(data, dict):
                        data = data.get(key, {})
                    else:
                        return 0
                return data if data else 0
            
            # 下单时的数据
            original_4h = get_data_safely(original_market_data, '4h')
            original_1h = get_data_safely(original_market_data, '1h')
            original_15m = get_data_safely(original_market_data, '15m')
            original_adv = get_data_safely(original_market_data, 'advanced_data')
            
            # 当前数据
            current_4h = get_data_safely(current_market_data, '4h')
            current_1h = get_data_safely(current_market_data, '1h')
            current_15m = get_data_safely(current_market_data, '15m')
            current_adv = get_data_safely(current_market_data, 'advanced_data')
            
            # 构建AI提示（对比两个时间点的数据）
            prompt = f"""
【限价单超时重新评估 - 数据对比分析】

你在 {self.limit_order_timeout}秒前（约{self.limit_order_timeout/60:.0f}分钟前）下了一个限价单，现在需要重新评估。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【原始订单信息】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
交易对: {order_info['symbol']}
方向: {order_info['side']} (Buy=做多, Sell=做空)
限价: {order_info['price']:.2f} USDT
数量: {order_info['qty']}

原始开仓理由：
{original_decision.get('reason', '无')[:300]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【市场数据对比 - 下单时 vs 现在】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【价格变化】
下单时市价: {get_data_safely(original_adv, 'last_price'):.2f} USDT
当前市价:   {get_data_safely(current_adv, 'last_price'):.2f} USDT
变化幅度:   {((get_data_safely(current_adv, 'last_price') - get_data_safely(original_adv, 'last_price')) / get_data_safely(original_adv, 'last_price') * 100) if get_data_safely(original_adv, 'last_price') > 0 else 0:.2f}%
限价偏离:   {((order_info['price'] - get_data_safely(current_adv, 'last_price')) / get_data_safely(current_adv, 'last_price') * 100) if get_data_safely(current_adv, 'last_price') > 0 else 0:.2f}%

【4小时趋势对比】（宏观趋势）
下单时: 价格 {get_data_safely(original_4h, 'close'):.2f} | EMA50 {get_data_safely(original_4h, 'ema_50'):.2f} | RSI {get_data_safely(original_4h, 'rsi'):.1f} | MACD柱 {get_data_safely(original_4h, 'macd_hist'):.4f}
现在:   价格 {get_data_safely(current_4h, 'close'):.2f} | EMA50 {get_data_safely(current_4h, 'ema_50'):.2f} | RSI {get_data_safely(current_4h, 'rsi'):.1f} | MACD柱 {get_data_safely(current_4h, 'macd_hist'):.4f}
趋势变化: {'✅ 保持一致' if (get_data_safely(original_4h, 'rsi') > 50) == (get_data_safely(current_4h, 'rsi') > 50) else '⚠️ 可能反转'}

【1小时趋势对比】（中期趋势）
下单时: 价格 {get_data_safely(original_1h, 'close'):.2f} | EMA21 {get_data_safely(original_1h, 'ema_21'):.2f} | RSI {get_data_safely(original_1h, 'rsi'):.1f}
现在:   价格 {get_data_safely(current_1h, 'close'):.2f} | EMA21 {get_data_safely(current_1h, 'ema_21'):.2f} | RSI {get_data_safely(current_1h, 'rsi'):.1f}

【15分钟动量对比】（短期动量）
下单时: RSI {get_data_safely(original_15m, 'rsi'):.1f} | 成交量 {get_data_safely(original_15m, 'volume'):.0f}
现在:   RSI {get_data_safely(current_15m, 'rsi'):.1f} | 成交量 {get_data_safely(current_15m, 'volume'):.0f}

【市场情绪对比】
下单时: 资金费率 {get_data_safely(original_adv, 'funding_rate'):.4f}% | 持仓量 {get_data_safely(original_adv, 'open_interest'):.0f}
现在:   资金费率 {get_data_safely(current_adv, 'funding_rate'):.4f}% | 持仓量 {get_data_safely(current_adv, 'open_interest'):.0f}

【K线形态】
{self._format_candlestick_patterns(current_market_data)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【决策要求】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

请综合对比分析：
1. 4小时宏观趋势是否仍支持原方向？
2. 1小时中期趋势是否有变化？
3. 价格是否正在向限价靠近还是远离？
4. 市场情绪（资金费率、持仓量）是否有明显变化？
5. K线形态是否出现反转信号？

决策选项：
- continue_wait：趋势仍支持，价格向限价靠近，继续等待
- modify：趋势仍支持，但价格偏离，建议新价格（填写new_price）
- cancel：趋势已改变或机会窗口已过，取消订单
- cancel_and_market：趋势加速，急需入场，取消并市价成交

请以JSON格式返回：
{{
    "action": "continue_wait/modify/cancel/cancel_and_market",
    "new_price": 195.5,  # 仅modify时需要
    "reason": "详细理由（包括数据对比分析）"
}}
"""
            
            # 调用AI
            system_prompt_limit = "你是专业的加密货币数据分析师，基于市场数据你可以准确的推断出未来的价格走势、交易机会和隐藏的风险。"
            
            response = self.trader.client.chat.completions.create(
                model=self.trader.model,
                messages=[
                    {"role": "system", "content": system_prompt_limit},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,  # 增加token限制，确保完整分析
                temperature=0.3
            )
            
            content = response.choices[0].message.content.strip()
            
            # 记录AI交互
            try:
                self.ai_logger.log_interaction(
                    interaction_type="limit_order_review",
                    system_prompt=system_prompt_limit,
                    user_prompt=prompt,
                    market_data={
                        "original": original_market_data,
                        "current": current_market_data
                    },
                    account_state={
                        "pending_order": order_info,
                        "order_id": order_id
                    },
                    ai_response=content,
                    parsed_decision=None,  # 将在下面解析
                    metadata={
                        "order_symbol": order_info['symbol'],
                        "order_side": order_info['side'],
                        "order_price": order_info['price'],
                        "wait_time_seconds": self.limit_order_timeout
                    }
                )
                logging.debug("✓ 限价单AI决策已记录")
            except Exception as log_err:
                logging.warning(f"记录限价单AI交互失败（不影响交易）: {log_err}")
            
            # 解析JSON
            try:
                import json
                import re
                # 尝试提取JSON部分
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    logging.info(f"🤖 AI限价单决策: {result.get('action')}")
                    full_reason = result.get('reason', '')
                    logging.info(f"   完整理由:")
                    for i in range(0, len(full_reason), 100):
                        logging.info(f"     {full_reason[i:i+100]}")
                    if result.get('new_price'):
                        logging.info(f"   建议新价: {result.get('new_price'):.2f}")
                    return result
            except:
                pass
            
            # 如果JSON解析失败，使用关键词匹配
            content_lower = content.lower()
            if 'cancel_and_market' in content_lower or 'cancel and market' in content_lower:
                action = 'cancel_and_market'
            elif 'modify' in content_lower:
                action = 'modify'
            elif 'cancel' in content_lower:
                action = 'cancel'
            else:
                action = 'continue_wait'
            
            logging.info(f"🤖 AI限价单决策: {action}")
            logging.info(f"   完整理由:")
            for i in range(0, len(content), 100):
                logging.info(f"     {content[i:i+100]}")
            return {'action': action, 'reason': content}
            
        except Exception as e:
            logging.error(f"AI决策失败: {e}")
            # 默认策略：继续等待
            return {'action': 'continue_wait', 'reason': f'AI决策失败: {str(e)}'}
    
    def _cancel_and_place_market_order(self, order_id: str, order_info: Dict):
        """取消限价单并改用市价单"""
        try:
            # 取消限价单
            success = self.api.cancel_order(order_info['symbol'], order_id)
            if not success:
                logging.error(f"取消限价单失败: {order_id}")
                return
            
            logging.info(f"✓ 已取消限价单: {order_id}")
            
            # 下市价单
            logging.info(f"📊 改用市价单立即成交...")
            
            market_order_id = self.api.place_order(
                symbol=order_info['symbol'],
                side=order_info['side'],
                order_type='Market',
                qty=str(order_info['qty']),
                reduce_only=False
            )
            
            if market_order_id:
                logging.info(f"✅ 市价单已提交: {market_order_id}")
            else:
                logging.error(f"❌ 市价单提交失败")
                
        except Exception as e:
            logging.error(f"取消并改市价单失败: {e}")
    
    def _modify_limit_order_price(self, order_id: str, order_info: Dict, suggested_price: Optional[float] = None) -> Optional[float]:
        """
        修改限价单价格
        
        Args:
            order_id: 订单ID
            order_info: 订单信息
            suggested_price: AI建议的新价格（如果提供）
        """
        try:
            ticker = self.api.get_ticker(order_info['symbol'])
            if not ticker:
                return None
            
            current_price = float(ticker.get('lastPrice', 0))
            side = order_info['side']
            
            # 使用AI建议的价格，或自动计算
            if suggested_price:
                new_price = suggested_price
                logging.info(f"🤖 使用AI建议价格: {new_price:.2f} USDT")
            else:
                # 计算新价格（向市价靠拢）
                if side == 'Buy':
                    new_price = current_price * 0.98
                else:  # Sell
                    new_price = current_price * 1.02
                logging.info(f"📊 自动计算新价格: {new_price:.2f} USDT")
            
            # 格式化价格
            new_price_str = self._format_price(order_info['symbol'], new_price)
            old_price = order_info['price']
            
            logging.info(f"🔄 修改限价单价格: {old_price:.2f} → {new_price:.2f} USDT (当前市价: {current_price:.2f})")
            
            # 先取消旧订单
            cancel_result = self.api.cancel_order(order_info['symbol'], order_id)
            if not cancel_result:
                logging.warning(f"⚠️ 取消旧订单失败，可能已成交或已取消")
                # 检查是否已成交
                order_status = self._get_order_status(order_info['symbol'], order_id)
                if order_status == 'Filled':
                    logging.info(f"✓ 订单已成交: {order_id}")
                    return None
            
            # 等待一小段时间确保取消生效
            time.sleep(0.5)
            
            # 下新订单（包含止损止盈）
            order_params = {
                'symbol': order_info['symbol'],
                'side': order_info['side'],
                'order_type': 'Limit',
                'qty': str(order_info['qty']),
                'price': new_price_str,
                'reduce_only': False
            }
            
            # 从原订单信息中获取止损止盈（如果有）
            original_decision = order_info.get('decision', {})
            stop_loss = original_decision.get('stop_loss')
            take_profit = original_decision.get('take_profit')
            
            if stop_loss:
                order_params['stop_loss'] = str(self._format_price(order_info['symbol'], stop_loss))
            if take_profit and len(take_profit) > 0:
                order_params['take_profit'] = str(self._format_price(order_info['symbol'], take_profit[0]))
            
            new_order_id = self.api.place_order(**order_params)
            
            if new_order_id:
                # 先从监控列表移除旧订单（防止重复）
                self.pending_limit_orders.pop(order_id, None)
                
                # 添加新订单到监控列表
                new_order_info = order_info.copy()
                new_order_info['price'] = new_price
                new_order_info['create_time'] = time.time()
                self.pending_limit_orders[new_order_id] = new_order_info
                
                logging.info(f"✓ 新限价单已下达: {new_order_id}")
                return new_price
            
            return None
            
        except Exception as e:
            logging.error(f"修改限价单价格失败: {e}")
            return None
    
    def _get_position_info(self) -> Dict:
        """获取当前持仓信息"""
        # 获取Bybit持仓
        positions = self.api.get_positions(settle_coin="USDT")
        
        # 获取余额
        wallet = self.api.get_wallet_balance()
        balance = 0
        
        if wallet:
            try:
                coins = wallet.get('list', [])[0].get('coin', [])
                for coin in coins:
                    if coin.get('coin') == 'USDT':
                        balance = float(coin.get('walletBalance', 0))
                        break
            except:
                pass
        
        # 构建持仓信息（兼容AI接口）
        position_info = {
            'position': 'NONE',
            'current_symbol': 'NONE',
            'entry_price': 0,
            'position_size': 0,
            'leverage': 0,
            'unrealized_pnl': 0,
            'unrealized_pnl_pct': 0,
            'balance': balance
        }
        
        if positions:
            for pos in positions:
                size = float(pos.get('size', 0))
                if size > 0:
                    # 有持仓
                    symbol = pos.get('symbol', '') + '_PERPETUAL'
                    side = pos.get('side', '')
                    
                    position_info.update({
                        'position': 'LONG' if side == 'Buy' else 'SHORT',
                        'current_symbol': symbol,
                        'entry_price': float(pos.get('avgPrice', 0)),
                        'position_size': size,
                        'leverage': int(float(pos.get('leverage', 15))),
                        'unrealized_pnl': float(pos.get('unrealisedPnl', 0)),
                        'unrealized_pnl_pct': float(pos.get('unrealisedPnl', 0)) / balance * 100 if balance > 0 else 0
                    })
                    
                    # 更新内部状态
                    self.current_position = side
                    self.current_symbol = symbol
                    self.entry_price = float(pos.get('avgPrice', 0))
                    break
        else:
            # 无持仓，清空内部状态
            self.current_position = None
            self.current_symbol = None
            self.entry_price = 0
        
        return position_info
    
    def _execute_decision(self, decision: Dict, all_market_data: Dict):
        """
        执行AI决策
        
        决策类型：
        - LONG: 开多单（或换仓）
        - SHORT: 开空单（或换仓）
        - CLOSE: 平仓
        - HOLD: 持有/观望
        """
        action = decision.get('action', 'HOLD')
        target_symbol = decision.get('target_symbol')
        confidence = decision.get('confidence', 0)
        
        # 🔒 仓位限制：强制3%-30%范围
        min_position_pct = self.config.get('min_position_pct', 0.03)
        raw_position_size = decision.get('position_size', 0.15)
        position_size_pct = min(max(raw_position_size, min_position_pct), self.max_position_pct)
        
        # 🔒 杠杆限制：强制1-15倍（防止AI错误输出导致极高风险）
        max_leverage = self.config.get('max_leverage', 15)
        raw_leverage = decision.get('leverage', 15)
        leverage = min(max(raw_leverage, 1), max_leverage)
        
        # 记录限制情况
        if leverage != raw_leverage:
            logging.warning(f"⚠️ 杠杆已被限制: {raw_leverage}x → {leverage}x（最大{max_leverage}x）")
        if position_size_pct != raw_position_size:
            logging.warning(f"⚠️ 仓位已被限制: {raw_position_size*100:.1f}% → {position_size_pct*100:.1f}%（范围{min_position_pct*100:.0f}%-{self.max_position_pct*100:.0f}%）")
        
        logging.info(f"  AI决策: {action} {target_symbol}")
        logging.info(f"  信号强度: {confidence}%")
        logging.info(f"  仓位: {position_size_pct*100:.0f}% | 杠杆: {leverage}x")
        full_reason = decision.get('reason', '')
        logging.info(f"  完整理由:")
        for i in range(0, len(full_reason), 100):
            logging.info(f"    {full_reason[i:i+100]}")
        
        # HOLD - 无操作
        if action == 'HOLD':
            logging.info("  → 保持观望")
            return
        
        # CLOSE - 平仓
        if action == 'CLOSE':
            if self.current_position:
                # ✅ AI完全自主决策：直接执行平仓，不做任何限制
                # 记录持仓时长（仅用于日志，不影响决策）
                if self.position_entry_time:
                    hold_time = time.time() - self.position_entry_time
                    logging.info(f"📊 持仓信息：时长 {hold_time/60:.1f}分钟")
                    if self.position_entry_reason:
                        logging.info(f"   开仓理由: {self.position_entry_reason[:80]}...")
                
                # 执行平仓（完全信任AI决策）
                self._close_position("AI主动平仓")
            else:
                logging.info("  → 当前无持仓")
            return
        
        # LONG/SHORT - 开仓或换仓
        if action in ['LONG', 'SHORT']:
            # 检查是否有相同资产和方向的未成交限价单（防止重复下单）
            bybit_symbol = target_symbol.replace('_PERPETUAL', '')
            target_side = "Buy" if action == "LONG" else "Sell"
            
            has_pending_order = False
            for order_id, order_info in self.pending_limit_orders.items():
                if order_info['symbol'] == bybit_symbol and order_info['side'] == target_side:
                    has_pending_order = True
                    logging.warning(f"\n{'='*80}")
                    logging.warning(f"⚠️  防止重复下单")
                    logging.warning(f"   已有未成交的{action}订单: {order_id}")
                    logging.warning(f"   交易对: {bybit_symbol}")
                    logging.warning(f"   限价: {order_info['price']:.2f} USDT")
                    logging.warning(f"   → 跳过本次开仓，等待已有订单成交")
                    logging.warning(f"{'='*80}\n")
                    break
            
            if has_pending_order:
                return  # 跳过开仓
            
            # 如果有持仓且不是目标资产/方向，先平仓
            if self.current_position:
                need_switch = (
                    self.current_symbol != target_symbol or
                    (self.current_symbol == target_symbol and 
                     ((action == 'LONG' and self.current_position == 'Short') or
                      (action == 'SHORT' and self.current_position == 'Buy')))
                )
                
                if need_switch:
                    logging.info("  → 换仓：先平掉当前仓位")
                    self._close_position("换仓")
                    time.sleep(2)  # 等待平仓完成
            
            # 开新仓
            self._open_position(
                action=action,
                symbol=target_symbol,
                position_size_pct=position_size_pct,
                leverage=leverage,
                reason=decision.get('reason', ''),
                order_type=decision.get('order_type', 'Market'),
                entry_price=decision.get('entry_price', 0),
                stop_loss=decision.get('stop_loss', 0),
                take_profit=decision.get('take_profit', []),
                market_data=all_market_data.get(target_symbol, {}),
                decision=decision
            )
    
    def _check_and_update_trailing_stop(self):
        """
        检查并更新移动止损（Trailing Stop）
        
        功能：
        1. 检查当前持仓
        2. 获取当前价格和ATR
        3. 计算新的止损位置
        4. 如果满足条件，通过API更新止损
        
        移动规则：
        - LONG单：价格上涨时，止损也上移（只能上移不能下移）
        - SHORT单：价格下跌时，止损也下移（只能下移不能上移）
        - 触发条件：价格向有利方向移动超过 ATR × trigger_multiplier
        - 移动距离：当前价格 - ATR × distance_multiplier
        """
        if not self.use_trailing_stop:
            return
        
        # 检查时间间隔
        current_time = time.time()
        if current_time - self.last_trailing_stop_check < self.trailing_stop_check_interval:
            return
        
        self.last_trailing_stop_check = current_time
        
        # 必须有持仓
        if not self.current_position or not self.current_symbol:
            return
        
        try:
            bybit_symbol = self.current_symbol.replace('_PERPETUAL', '')
            
            # 获取持仓信息
            positions = self.api.get_positions(bybit_symbol)
            if not positions:
                return
            
            position = positions[0]
            side = position.get('side')
            size = float(position.get('size', 0))
            
            if size == 0:
                return  # 无持仓
            
            entry_price = float(position.get('avgPrice', 0))
            current_stop_loss = float(position.get('stopLoss', 0))
            
            # 获取当前价格
            ticker = self.api.get_ticker(bybit_symbol)
            if not ticker:
                return
            
            current_price = float(ticker.get('lastPrice', 0))
            
            # 获取ATR（从最新数据计算）
            market_data = self.data_manager.get_realtime_data(self.current_symbol)
            if not market_data:
                return
            
            # 优先使用15分钟数据计算ATR（更及时）
            df_15m = market_data.get('15m', {}).get('df')
            if df_15m is None or len(df_15m) < 14:
                # 如果15分钟数据不够，使用1小时数据
                df_1h = market_data.get('1h', {}).get('df')
                if df_1h is None or len(df_1h) < 14:
                    return
                atr = df_1h['atr'].iloc[-1]
            else:
                atr = df_15m['atr'].iloc[-1]
            
            if atr == 0 or pd.isna(atr):
                return
            
            # 计算移动止损
            trailing_distance = atr * self.trailing_stop_distance_multiplier
            trigger_distance = atr * self.trailing_stop_trigger_multiplier
            
            new_stop_loss = 0
            should_update = False
            reason = ""
            
            if side == "Buy":  # 多单
                # 检查是否盈利超过触发阈值
                profit = current_price - entry_price
                
                if profit >= trigger_distance:
                    # 计算新止损位置
                    potential_stop = current_price - trailing_distance
                    
                    # 止损只能上移不能下移
                    if current_stop_loss > 0:
                        if potential_stop > current_stop_loss:
                            new_stop_loss = potential_stop
                            should_update = True
                            reason = f"价格从${entry_price:.2f}涨到${current_price:.2f}，盈利${profit:.2f}（{profit/entry_price*100:.2f}%），止损上移锁定利润"
                    else:
                        # 第一次设置移动止损，至少保本
                        new_stop_loss = max(potential_stop, entry_price)
                        should_update = True
                        reason = f"价格盈利超过触发阈值（{trigger_distance:.2f}），启动移动止损保本"
            
            elif side == "Sell":  # 空单
                # 检查是否盈利超过触发阈值
                profit = entry_price - current_price
                
                if profit >= trigger_distance:
                    # 计算新止损位置
                    potential_stop = current_price + trailing_distance
                    
                    # 止损只能下移不能上移
                    if current_stop_loss > 0:
                        if potential_stop < current_stop_loss:
                            new_stop_loss = potential_stop
                            should_update = True
                            reason = f"价格从${entry_price:.2f}跌到${current_price:.2f}，盈利${profit:.2f}（{profit/entry_price*100:.2f}%），止损下移锁定利润"
                    else:
                        # 第一次设置移动止损，至少保本
                        new_stop_loss = min(potential_stop, entry_price)
                        should_update = True
                        reason = f"价格盈利超过触发阈值（{trigger_distance:.2f}），启动移动止损保本"
            
            # 执行更新
            if should_update and new_stop_loss > 0:
                # 格式化价格
                formatted_stop = self._format_price(bybit_symbol, new_stop_loss)
                
                logging.info(f"\n{'='*80}")
                logging.info(f"📈 移动止损更新: {bybit_symbol} ({side})")
                logging.info(f"  入场价格: ${entry_price:.2f}")
                logging.info(f"  当前价格: ${current_price:.2f}")
                logging.info(f"  旧止损位: ${current_stop_loss:.2f}" if current_stop_loss > 0 else "  旧止损位: 未设置")
                logging.info(f"  新止损位: ${new_stop_loss:.2f}")
                logging.info(f"  ATR: ${atr:.2f} | 距离: {trailing_distance:.2f} | 触发: {trigger_distance:.2f}")
                logging.info(f"  理由: {reason}")
                logging.info(f"{'='*80}\n")
                
                # 通过API更新止损
                result = self.api.set_trading_stop(
                    symbol=bybit_symbol,
                    stop_loss=str(formatted_stop),
                    position_idx=0  # 单向持仓模式
                )
                
                if result:
                    self.trailing_stop_updates += 1
                    logging.info(f"✓ 移动止损更新成功（累计更新{self.trailing_stop_updates}次）")
                else:
                    logging.warning(f"⚠️ 移动止损更新失败，将在下次检查时重试")
        
        except Exception as e:
            logging.error(f"移动止损检查失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _validate_stop_loss_take_profit(self, action: str, entry_price: float, 
                                        stop_loss: float, take_profit: list) -> Tuple[bool, str]:
        """
        验证止损止盈价格的合理性（防止AI设置错误导致立即触发或永远无法达到）
        
        Args:
            action: LONG/SHORT
            entry_price: 入场价格
            stop_loss: 止损价格
            take_profit: 止盈价格列表
            
        Returns:
            (is_valid, error_message)
        """
        min_stop_distance_pct = 0.3  # 最小止损距离0.3%
        max_stop_distance_pct = 20.0  # 最大止损距离20%
        
        if action == "LONG":
            # 🔒 做多验证
            if stop_loss > 0:
                if stop_loss >= entry_price:
                    return False, f"LONG单止损价格({stop_loss:.2f})必须低于入场价({entry_price:.2f})"
                
                stop_pct = abs(entry_price - stop_loss) / entry_price * 100
                if stop_pct < min_stop_distance_pct:
                    return False, f"止损距离过近({stop_pct:.2f}%)，建议≥{min_stop_distance_pct}%"
                if stop_pct > max_stop_distance_pct:
                    return False, f"止损距离过远({stop_pct:.2f}%)，建议≤{max_stop_distance_pct}%"
            
            if len(take_profit) > 0 and take_profit[0] > 0:
                if take_profit[0] <= entry_price:
                    return False, f"LONG单止盈价格({take_profit[0]:.2f})必须高于入场价({entry_price:.2f})"
        
        elif action == "SHORT":
            # 🔒 做空验证
            if stop_loss > 0:
                if stop_loss <= entry_price:
                    return False, f"SHORT单止损价格({stop_loss:.2f})必须高于入场价({entry_price:.2f})"
                
                stop_pct = abs(stop_loss - entry_price) / entry_price * 100
                if stop_pct < min_stop_distance_pct:
                    return False, f"止损距离过近({stop_pct:.2f}%)，建议≥{min_stop_distance_pct}%"
                if stop_pct > max_stop_distance_pct:
                    return False, f"止损距离过远({stop_pct:.2f}%)，建议≤{max_stop_distance_pct}%"
            
            if len(take_profit) > 0 and take_profit[0] > 0:
                if take_profit[0] >= entry_price:
                    return False, f"SHORT单止盈价格({take_profit[0]:.2f})必须低于入场价({entry_price:.2f})"
        
        return True, ""
    
    def _open_position(self, action: str, symbol: str, position_size_pct: float, 
                      leverage: int, reason: str, order_type: str = "Market",
                      entry_price: float = 0, stop_loss: float = 0, 
                      take_profit: list = None, market_data: Dict = None,
                      decision: Dict = None):
        """
        开仓
        
        Args:
            action: LONG/SHORT
            symbol: AI格式符号（如BTCUSDT_PERPETUAL）
            position_size_pct: 仓位比例（0.0-0.3）
            leverage: 杠杆（1-15）
            reason: 开仓理由
            order_type: Market/Limit（市价单或限价单）
            entry_price: 期望开仓价格（0表示市价）
            stop_loss: 止损价格
            take_profit: 止盈价格列表
            market_data: 开仓时的完整市场数据快照
            decision: AI的完整决策JSON
        """
        if take_profit is None:
            take_profit = []
        if market_data is None:
            market_data = {}
        if decision is None:
            decision = {}
        try:
            # 转换符号
            bybit_symbol = symbol.replace('_PERPETUAL', '')
            
            # 获取当前价格
            ticker = self.api.get_ticker(bybit_symbol)
            if not ticker:
                logging.error(f"无法获取{bybit_symbol}价格")
                return
            
            current_price = float(ticker.get('lastPrice', 0))
            
            # 计算下单数量
            position_info = self._get_position_info()
            balance = position_info.get('balance', 0)
            
            if balance < self.min_balance:
                logging.error(f"余额不足: {balance:.2f} USDT")
                return
            
            # 计算数量
            position_value = balance * position_size_pct * leverage
            qty = position_value / current_price
            
            # 根据Bybit API规则格式化数量
            qty_str = self._format_quantity(bybit_symbol, qty)
            qty = float(qty_str)
            
            # 验证订单是否符合规则
            is_valid, error_msg = self._validate_order(bybit_symbol, qty, current_price)
            if not is_valid:
                logging.error(f"订单验证失败: {error_msg}")
                return
            
            # 提交订单
            side = "Buy" if action == "LONG" else "Sell"
            
            # 确定订单价格
            if order_type == "Market" or entry_price == 0:
                order_price = current_price
                order_type = "Market"
            else:
                order_price = entry_price
                order_type = "Limit"
            
            # 🔒 验证止损止盈价格的合理性（防止AI设置错误）
            is_valid, error_msg = self._validate_stop_loss_take_profit(action, order_price, stop_loss, take_profit)
            if not is_valid:
                logging.error(f"❌ 止损止盈验证失败: {error_msg}")
                logging.error(f"   拒绝开仓以保护资金安全")
                return
            
            # 计算盈亏比
            risk_reward_ratio = 0
            if stop_loss > 0 and len(take_profit) > 0:
                if action == "LONG":
                    risk = abs(order_price - stop_loss)
                    reward = abs(take_profit[0] - order_price)
                else:  # SHORT
                    risk = abs(stop_loss - order_price)
                    reward = abs(order_price - take_profit[0])
                if risk > 0:
                    risk_reward_ratio = reward / risk
            
            logging.info(f"\n{'='*80}")
            logging.info(f"📈 开仓: {action} {bybit_symbol}")
            logging.info(f"  订单类型: {order_type}")
            logging.info(f"  当前价格: {current_price:.2f} USDT")
            logging.info(f"  开仓价格: {order_price:.2f} USDT")
            if stop_loss > 0:
                logging.info(f"  止损价格: {stop_loss:.2f} USDT (订单内置)")
            if len(take_profit) > 0:
                tp_str = ", ".join([f"{tp:.2f}" for tp in take_profit])
                logging.info(f"  止盈价格: [{tp_str}] USDT (订单内置)")
            if risk_reward_ratio > 0:
                logging.info(f"  盈亏比: {risk_reward_ratio:.2f}:1")
            logging.info(f"  数量: {qty_str} (符合规则: qty_step={self.trading_rules[bybit_symbol]['qty_step']})")
            logging.info(f"  订单价值: {qty * order_price:.2f} USDT")
            logging.info(f"  杠杆: {leverage}x")
            logging.info(f"  仓位: {position_size_pct*100:.0f}%")
            logging.info(f"  完整理由:")
            for i in range(0, len(reason), 100):
                logging.info(f"    {reason[i:i+100]}")
            logging.info(f"{'='*80}\n")
            
            # 下单（包含止盈止损）
            order_params = {
                'symbol': bybit_symbol,
                'side': side,
                'order_type': order_type,
                'qty': qty_str,
                'reduce_only': False
            }
            
            if order_type == "Limit":
                order_params['price'] = str(self._format_price(bybit_symbol, order_price))
            
            # 添加止损止盈到订单（Bybit支持在订单中直接设置）
            if stop_loss > 0:
                order_params['stop_loss'] = str(self._format_price(bybit_symbol, stop_loss))
            
            if len(take_profit) > 0 and take_profit[0] > 0:
                order_params['take_profit'] = str(self._format_price(bybit_symbol, take_profit[0]))
            
            order_id = self.api.place_order(**order_params)
            
            if order_id:
                self.total_trades += 1
                self.successful_trades += 1
                
                # 如果是限价单，添加到监控列表
                if order_type == "Limit":
                    self.pending_limit_orders[order_id] = {
                        'symbol': bybit_symbol,
                        'create_time': time.time(),
                        'side': side,
                        'price': order_price,
                        'qty': qty,
                        'order_type': order_type,
                        'decision': decision,
                        'market_data': market_data,
                        'ai_symbol': symbol  # 保存AI格式的符号
                    }
                    logging.info(f"⏳ 限价单已添加到监控列表，将在{self.limit_order_timeout}秒后检查状态")
                
                # 更新内部状态
                self.current_position = side
                self.current_symbol = symbol
                self.entry_price = order_price
                
                # 记录开仓时间和理由（用于持仓保护期）
                self.position_entry_time = time.time()
                self.position_entry_reason = reason
                
                # 记录交易到日志系统
                trade_data = {
                    'symbol': symbol,
                    'action': action,
                    'entry_price': order_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'quantity': qty,
                    'leverage': leverage,
                    'position_size_pct': position_size_pct,
                    'order_type': order_type,
                    'reason': reason,
                    'confidence': decision.get('confidence', 0),
                    'market_data': market_data,  # 完整的开仓时市场数据快照
                    'ai_analysis': {
                        'market_state': decision.get('market_state', 'unknown'),
                        'asset_comparison': decision.get('asset_comparison', {}),
                        'decision': decision  # 完整的AI决策
                    }
                }
                self.current_trade_id = self.trade_journal.log_trade_open(trade_data)
                
                logging.info(f"✅ 开仓成功！订单ID: {order_id} | 交易ID: {self.current_trade_id}")
            else:
                self.failed_trades += 1
                logging.error("❌ 开仓失败")
                
        except Exception as e:
            logging.error(f"开仓错误: {e}", exc_info=True)
            self.failed_trades += 1
    
    def _close_position(self, reason: str = ""):
        """平仓"""
        if not self.current_position or not self.current_symbol:
            logging.info("当前无持仓")
            return
        
        try:
            bybit_symbol = self.current_symbol.replace('_PERPETUAL', '')
            logging.info(f"开始平仓: {self.current_symbol} ({bybit_symbol}), 方向: {self.current_position}, 开仓价: {self.entry_price:.2f}")
            
            # 获取持仓信息
            positions = self.api.get_positions(symbol=bybit_symbol)
            
            if not positions or len(positions) == 0:
                logging.warning("无法获取持仓信息")
                self.current_position = None
                self.current_symbol = None
                return
            
            pos = positions[0]
            qty = pos.get('size', '0')
            
            if float(qty) == 0:
                logging.info("持仓数量为0")
                self.current_position = None
                self.current_symbol = None
                return
            
            # 平仓方向（与开仓相反）
            side = "Sell" if self.current_position == "Buy" else "Buy"
            
            logging.info(f"\n{'='*80}")
            logging.info(f"📉 平仓: {bybit_symbol}")
            logging.info(f"  数量: {qty}")
            logging.info(f"  理由: {reason}")
            logging.info(f"{'='*80}\n")
            
            order_id = self.api.place_order(
                symbol=bybit_symbol,
                side=side,
                order_type="Market",
                qty=qty,
                reduce_only=True
            )
            
            if order_id:
                self.total_trades += 1
                self.successful_trades += 1
                
                # 获取平仓价格 - 从实际成交信息中获取
                # 首先尝试从订单信息中获取成交价格
                order_details = self.api.get_order_history(bybit_symbol, order_id)
                close_price = 0
                
                if order_details:
                    # 从订单详情中获取实际成交价格
                    close_price = float(order_details.get('avgPrice', 0))
                    logging.debug(f"从订单详情获取平仓价: {close_price} ({bybit_symbol})")
                
                # 如果获取失败，从ticker获取当前价格
                if close_price == 0:
                    ticker = self.api.get_ticker(bybit_symbol)
                    close_price = float(ticker.get('lastPrice', 0)) if ticker else 0
                    logging.debug(f"从ticker获取平仓价: {close_price} ({bybit_symbol})")
                
                # 验证价格是否合理（与开仓价相差不应超过50%）
                if self.entry_price > 0 and close_price > 0:
                    price_diff_pct = abs(close_price - self.entry_price) / self.entry_price * 100
                    if price_diff_pct > 50:
                        logging.error(f"⚠️ 平仓价格异常！开仓价: {self.entry_price:.2f}, 平仓价: {close_price:.2f}, 差异: {price_diff_pct:.1f}%")
                        logging.error(f"   交易对: {bybit_symbol}, 当前symbol: {self.current_symbol}")
                        # 重新获取正确的价格
                        ticker = self.api.get_ticker(bybit_symbol)
                        if ticker:
                            close_price = float(ticker.get('lastPrice', 0))
                            logging.info(f"   重新获取价格: {close_price:.2f}")
                
                # 计算盈亏
                pnl = 0
                pnl_pct = 0
                if self.entry_price > 0 and close_price > 0:
                    qty_float = float(qty)
                    if self.current_position == "Buy":  # LONG平仓
                        pnl = (close_price - self.entry_price) * qty_float
                        pnl_pct = (close_price - self.entry_price) / self.entry_price * 100
                    else:  # SHORT平仓
                        pnl = (self.entry_price - close_price) * qty_float
                        pnl_pct = (self.entry_price - close_price) / self.entry_price * 100
                
                # 先不获取平仓后K线，等检查完回撤再决定
                # 记录平仓到日志系统（暂不包含post_close_klines）
                if self.current_trade_id:
                    close_data = {
                        'close_price': close_price,
                        'close_reason': reason,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct
                    }
                    self.trade_journal.log_trade_close(self.current_trade_id, close_data)
                
                # 获取最新余额信息
                latest_position_info = self._get_position_info()
                current_balance_after_close = latest_position_info.get('balance', 0)
                
                # 检查平仓后是否触发10%回撤
                # 如果触发，会等待获取3根15m K线后再进行AI分析
                triggered_drawdown = self._check_drawdown_after_close(
                    current_balance_after_close, 
                    bybit_symbol,
                    self.current_trade_id
                )
                
                # 如果没有触发回撤分析，正常获取平仓后K线
                if not triggered_drawdown:
                    logging.info(f"正在获取平仓后K线: {bybit_symbol}")
                    post_close_klines = self._get_post_close_klines(bybit_symbol, count=3)
                    if post_close_klines and self.current_trade_id:
                        # 验证K线价格是否合理
                        if post_close_klines and len(post_close_klines) > 0:
                            first_kline_price = post_close_klines[0].get('close', 0)
                            if self.entry_price > 0 and first_kline_price > 0:
                                kline_price_diff = abs(first_kline_price - self.entry_price) / self.entry_price * 100
                                if kline_price_diff > 50:
                                    logging.error(f"⚠️ 平仓后K线价格异常！开仓价: {self.entry_price:.2f}, K线价格: {first_kline_price:.2f}, 差异: {kline_price_diff:.1f}%")
                                    logging.error(f"   可能获取了错误交易对的K线数据！应为: {bybit_symbol}")
                                    post_close_klines = []  # 清空错误数据
                        
                        if post_close_klines:
                            # 更新交易记录，添加平仓后K线
                            self.trade_journal.add_post_close_klines(self.current_trade_id, post_close_klines)
                
                # 清空状态
                self.current_position = None
                self.current_symbol = None
                self.entry_price = 0
                self.current_trade_id = None
                
                # 清空持仓保护期记录
                self.position_entry_time = None
                self.position_entry_reason = ""
                
                logging.info(f"✅ 平仓成功！订单ID: {order_id} | 盈亏: {pnl:.2f} USDT ({pnl_pct:.2f}%)")
            else:
                self.failed_trades += 1
                logging.error("❌ 平仓失败")
                
        except Exception as e:
            logging.error(f"平仓错误: {e}", exc_info=True)
            self.failed_trades += 1
    
    def _emergency_close_position(self, reason: str):
        """紧急平仓（极端行情保护）"""
        logging.warning(f"🚨 紧急平仓: {reason}")
        self._close_position(reason)
    
    def _check_drawdown_and_analyze(self, current_balance: float):
        """
        检查资金回撤并在达到10%时触发AI自我分析
        （在交易循环中定期检查）
        
        Args:
            current_balance: 当前余额
        """
        # 更新历史最高余额
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
            self.drawdown_analysis_triggered = False  # 重置触发标志
        
        # 计算当前回撤
        if self.peak_balance > 0:
            current_drawdown = (self.peak_balance - current_balance) / self.peak_balance * 100
            
            # 更新最大回撤
            if current_drawdown > self.max_drawdown_pct:
                self.max_drawdown_pct = current_drawdown
            
            # 如果回撤达到10%且未触发过分析（非平仓触发的情况）
            if current_drawdown >= 10.0 and not self.drawdown_analysis_triggered:
                logging.warning(f"\n{'='*80}")
                logging.warning(f"⚠️ 资金回撤警告：当前回撤 {current_drawdown:.2f}%")
                logging.warning(f"   峰值余额: {self.peak_balance:.2f} USDT")
                logging.warning(f"   当前余额: {current_balance:.2f} USDT")
                logging.warning(f"   回撤金额: {self.peak_balance - current_balance:.2f} USDT")
                logging.warning(f"{'='*80}\n")
                
                # 触发AI自我分析（不等待K线）
                self._trigger_drawdown_analysis(current_drawdown)
                
                # 设置已触发标志，避免重复分析
                self.drawdown_analysis_triggered = True
    
    def _check_drawdown_after_close(self, current_balance: float, symbol: str, trade_id: str) -> bool:
        """
        平仓后检查回撤，如果触发10%则等待获取3根15m K线后再进行AI分析
        
        Args:
            current_balance: 平仓后的当前余额
            symbol: 交易对符号（Bybit格式）
            trade_id: 交易ID
        
        Returns:
            是否触发了回撤分析
        """
        # 更新历史最高余额
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
            self.drawdown_analysis_triggered = False
            return False
        
        # 计算当前回撤
        if self.peak_balance > 0:
            current_drawdown = (self.peak_balance - current_balance) / self.peak_balance * 100
            
            # 更新最大回撤
            if current_drawdown > self.max_drawdown_pct:
                self.max_drawdown_pct = current_drawdown
            
            # 如果回撤达到10%且未触发过分析
            if current_drawdown >= 10.0 and not self.drawdown_analysis_triggered:
                logging.warning(f"\n{'='*80}")
                logging.warning(f"⚠️ 平仓后回撤警告：当前回撤 {current_drawdown:.2f}%")
                logging.warning(f"   峰值余额: {self.peak_balance:.2f} USDT")
                logging.warning(f"   当前余额: {current_balance:.2f} USDT")
                logging.warning(f"   回撤金额: {self.peak_balance - current_balance:.2f} USDT")
                logging.warning(f"{'='*80}\n")
                
                # 先等待并获取平仓后的3根15m K线
                logging.warning("⏳ 等待获取平仓后的3根15m K线...")
                post_close_klines = self._get_post_close_klines(symbol, count=3)
                
                # 添加K线数据到交易记录
                if post_close_klines and trade_id:
                    self.trade_journal.add_post_close_klines(trade_id, post_close_klines)
                    logging.warning(f"✓ 已保存平仓后{len(post_close_klines)}根K线到交易日志")
                
                # 现在触发AI自我分析
                self._trigger_drawdown_analysis(current_drawdown)
                
                # 设置已触发标志
                self.drawdown_analysis_triggered = True
                
                return True
        
        return False
    
    def _trigger_drawdown_analysis(self, drawdown_pct: float):
        """
        触发回撤分析
        
        Args:
            drawdown_pct: 回撤百分比
        """
        try:
            logging.warning("🔍 触发AI自我分析（回撤达到10%）...")
            
            # 保存当前交易报告
            report_file = self.trade_journal.save_analysis_report(days=7)
            
            # 运行AI自我分析
            from ai_self_analysis import AISelfAnalysis
            
            analyzer = AISelfAnalysis(self.trader)
            analysis = analyzer.run_analysis(days=7)
            
            if analysis:
                logging.warning("✓ AI自我分析完成")
                analyzer.print_analysis_summary(analysis)
                
                # 发送警告通知（可选：邮件、短信等）
                logging.warning(f"\n🚨 回撤分析报告已生成，请及时查看并调整策略！")
                logging.warning(f"   当前回撤: {drawdown_pct:.2f}%")
                logging.warning(f"   分析报告: {report_file}")
            else:
                logging.error("❌ AI自我分析失败")
                
        except Exception as e:
            logging.error(f"触发回撤分析时出错: {e}", exc_info=True)
    
    def _get_post_close_klines(self, symbol: str, count: int = 3) -> List[Dict]:
        """
        获取平仓后的N根15分钟K线（用于事后分析）
        
        Args:
            symbol: Bybit符号（如BTCUSDT, ETHUSDT, SOLUSDT）
            count: 获取的K线数量（默认3根）
        
        Returns:
            K线列表，包含开盘价、最高价、最低价、收盘价、成交量等
        """
        try:
            # 等待15秒，确保第一根K线开始形成
            logging.info(f"等待15秒以获取平仓后的K线数据...")
            time.sleep(15)
            
            # 明确记录正在获取的交易对
            logging.info(f"获取 {symbol} 的平仓后K线数据（15分钟，{count}根）")
            
            # 获取最新的K线数据（稍多获取几根，确保有足够数据）
            klines = self.api.get_kline(symbol, '15', limit=count + 2)
            
            if not klines:
                logging.warning("无法获取平仓后的K线数据")
                return []
            
            # 提取最新的N根K线
            post_klines = []
            for i, kline in enumerate(klines[:count]):
                timestamp_ms = int(kline[0])
                
                # Bybit返回UTC时间戳，需要正确转换
                # 方法1：转换为UTC时间
                utc_time = datetime.fromtimestamp(timestamp_ms/1000, tz=timezone.utc)
                # 方法2：转换为本地时间
                local_time = utc_time.astimezone()
                
                post_klines.append({
                    'index': i,
                    'timestamp': timestamp_ms,
                    'timestamp_utc': utc_time.strftime('%Y-%m-%d %H:%M:%S UTC'),
                    'timestamp_local': local_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5])
                })
            
            logging.info(f"✓ 已获取平仓后{len(post_klines)}根15m K线")
            if post_klines:
                logging.info(f"   时间范围: {post_klines[0]['timestamp_local']} ~ {post_klines[-1]['timestamp_local']}")
            return post_klines
            
        except Exception as e:
            logging.error(f"获取平仓后K线失败: {e}")
            return []
    
    def _set_stop_loss_take_profit(self, symbol: str, action: str, stop_loss: float, 
                                   take_profit: list):
        """
        设置止损止盈
        
        Args:
            symbol: Bybit符号（如BTCUSDT）
            action: LONG/SHORT
            stop_loss: 止损价格
            take_profit: 止盈价格列表
        """
        try:
            # 格式化止损价格
            if stop_loss > 0:
                stop_loss_str = self._format_price(symbol, stop_loss)
                stop_loss_type = "StopLoss"
                
                # Bybit V5 API设置止损
                result = self.api.set_trading_stop(
                    symbol=symbol,
                    stop_loss=stop_loss_str,
                    position_idx=0  # 单向持仓模式
                )
                
                if result:
                    logging.info(f"✓ 止损已设置: {stop_loss_str} USDT")
                else:
                    logging.warning(f"✗ 止损设置失败")
            
            # 格式化止盈价格（只设置第一个目标）
            if len(take_profit) > 0:
                tp_price = take_profit[0]
                tp_price_str = self._format_price(symbol, tp_price)
                
                result = self.api.set_trading_stop(
                    symbol=symbol,
                    take_profit=tp_price_str,
                    position_idx=0
                )
                
                if result:
                    if len(take_profit) > 1:
                        logging.info(f"✓ 止盈已设置: {tp_price_str} USDT（第1个目标，共{len(take_profit)}个）")
                    else:
                        logging.info(f"✓ 止盈已设置: {tp_price_str} USDT")
                else:
                    logging.warning(f"✗ 止盈设置失败")
                    
        except Exception as e:
            logging.error(f"设置止损止盈错误: {e}", exc_info=True)
    
    def _format_price(self, symbol: str, price: float) -> str:
        """根据Bybit API规则格式化价格"""
        if symbol not in self.trading_rules:
            return str(round(price, 2))
        
        rules = self.trading_rules[symbol]
        tick_size = rules['tick_size']
        
        # 根据tick_size格式化价格
        if tick_size < 1:
            decimals = len(str(tick_size).split('.')[-1].rstrip('0'))
            formatted_price = round(price / tick_size) * tick_size
            formatted_price = round(formatted_price, decimals)
        else:
            formatted_price = int(price / tick_size) * tick_size
        
        return str(formatted_price)
    
    def _format_quantity(self, symbol: str, qty: float) -> str:
        """
        根据Bybit API交易规则格式化数量
        
        Args:
            symbol: 交易对（如BTCUSDT）
            qty: 原始数量
        
        Returns:
            格式化后的数量字符串
        """
        if symbol not in self.trading_rules:
            logging.warning(f"{symbol}交易规则未加载，使用默认精度")
            return str(round(qty, 3))
        
        rules = self.trading_rules[symbol]
        qty_step = rules['qty_step']
        min_qty = rules['min_order_qty']
        max_qty = rules['max_order_qty']
        
        # 1. 根据qtyStep调整精度
        # qtyStep可能是0.001, 0.01, 0.1, 1等
        if qty_step >= 1:
            # 整数精度
            formatted_qty = int(qty / qty_step) * qty_step
        else:
            # 小数精度
            decimals = len(str(qty_step).split('.')[-1].rstrip('0'))
            formatted_qty = round(qty / qty_step) * qty_step
            formatted_qty = round(formatted_qty, decimals)
        
        # 2. 检查最小/最大数量限制
        if formatted_qty < min_qty:
            logging.warning(f"{symbol}数量{formatted_qty}低于最小值{min_qty}，调整为最小值")
            formatted_qty = min_qty
        
        if formatted_qty > max_qty:
            logging.warning(f"{symbol}数量{formatted_qty}超过最大值{max_qty}，调整为最大值")
            formatted_qty = max_qty
        
        return str(formatted_qty)
    
    def _format_price(self, symbol: str, price: float) -> str:
        """
        根据Bybit API交易规则格式化价格
        
        Args:
            symbol: 交易对（如BTCUSDT）
            price: 原始价格
        
        Returns:
            格式化后的价格字符串
        """
        if symbol not in self.trading_rules:
            logging.warning(f"{symbol}交易规则未加载，使用默认精度")
            return str(round(price, 2))
        
        rules = self.trading_rules[symbol]
        tick_size = rules['tick_size']
        min_price = rules['min_price']
        max_price = rules['max_price']
        
        # 根据tickSize调整精度
        if tick_size >= 1:
            formatted_price = int(price / tick_size) * tick_size
        else:
            decimals = len(str(tick_size).split('.')[-1].rstrip('0'))
            formatted_price = round(price / tick_size) * tick_size
            formatted_price = round(formatted_price, decimals)
        
        # 检查价格范围
        if formatted_price < min_price:
            formatted_price = min_price
        if formatted_price > max_price:
            formatted_price = max_price
        
        return str(formatted_price)
    
    def _validate_order(self, symbol: str, qty: float, price: float) -> Tuple[bool, str]:
        """
        验证订单是否符合交易规则
        
        Args:
            symbol: 交易对
            qty: 数量
            price: 价格
        
        Returns:
            (is_valid, error_message)
        """
        if symbol not in self.trading_rules:
            return False, f"{symbol}交易规则未加载"
        
        rules = self.trading_rules[symbol]
        
        # 1. 检查交易状态
        if rules['status'] != 'Trading':
            return False, f"{symbol}当前状态为{rules['status']}，不可交易"
        
        # 2. 检查统一账户支持
        if not rules['unified_margin_trade']:
            return False, f"{symbol}不支持统一账户交易"
        
        # 3. 检查数量
        if qty < rules['min_order_qty']:
            return False, f"数量{qty}低于最小值{rules['min_order_qty']}"
        
        if qty > rules['max_order_qty']:
            return False, f"数量{qty}超过最大值{rules['max_order_qty']}"
        
        # 4. 检查订单金额
        order_value = qty * price
        if rules['min_order_amt'] > 0 and order_value < rules['min_order_amt']:
            return False, f"订单金额{order_value:.2f}低于最小值{rules['min_order_amt']}"
        
        if rules['max_order_amt'] > 0 and order_value > rules['max_order_amt']:
            return False, f"订单金额{order_value:.2f}超过最大值{rules['max_order_amt']}"
        
        # 5. 检查价格
        if price < rules['min_price']:
            return False, f"价格{price}低于最小值{rules['min_price']}"
        
        if price > rules['max_price']:
            return False, f"价格{price}超过最大值{rules['max_price']}"
        
        return True, ""
    
    def stop(self):
        """停止交易系统"""
        logging.info("\n正在停止交易系统...")
        
        self.is_running = False
        self.stop_event.set()
        
        # 显示统计
        logging.info(f"\n{'='*80}")
        logging.info("交易统计")
        logging.info(f"{'='*80}")
        logging.info(f"总交易次数: {self.total_trades}")
        logging.info(f"成功: {self.successful_trades}")
        logging.info(f"失败: {self.failed_trades}")
        logging.info(f"{'='*80}\n")
        
        # 显示AI缓存统计
        try:
            total_calls = self.trader.total_calls
            cache_hits = self.trader.cache_hits
            cache_expired = self.trader.cache_expired
            
            if total_calls > 0:
                cache_hit_rate = (cache_hits / total_calls) * 100
                actual_api_calls = total_calls - cache_hits
                
                logging.info(f"\n{'='*80}")
                logging.info("AI缓存统计")
                logging.info(f"{'='*80}")
                logging.info(f"总决策次数: {total_calls}")
                logging.info(f"缓存命中: {cache_hits} 次")
                logging.info(f"实际API调用: {actual_api_calls} 次")
                logging.info(f"缓存过期: {cache_expired} 次")
                logging.info(f"缓存命中率: {cache_hit_rate:.1f}%")
                
                # 成本估算（基于DeepSeek定价）
                tokens_per_call = 5500  # 估计：5000输入 + 500输出
                cost_per_1m_tokens = 0.14 + 0.28  # 输入+输出平均
                estimated_cost = (actual_api_calls * tokens_per_call * cost_per_1m_tokens) / 1000000
                saved_cost = (cache_hits * tokens_per_call * cost_per_1m_tokens) / 1000000
                
                logging.info(f"\n成本分析:")
                logging.info(f"  实际API成本: ${estimated_cost:.4f}")
                logging.info(f"  缓存节省: ${saved_cost:.4f}")
                logging.info(f"  总计节省: {(saved_cost/(estimated_cost+saved_cost)*100):.1f}%")
                
                # 健康度评估
                logging.info(f"\n缓存健康度:")
                if cache_hit_rate < 30:
                    logging.warning("  ⚠️ 缓存命中率过低 (<30%)，建议增加cache_ttl_samples")
                elif cache_hit_rate > 90:
                    logging.warning("  ⚠️ 缓存命中率过高 (>90%)，可能导致决策过时")
                else:
                    logging.info(f"  ✅ 缓存命中率健康 (30-90%)")
                
                logging.info(f"{'='*80}\n")
        except Exception as e:
            logging.warning(f"无法生成AI缓存统计: {e}")
        
        # 显示AI交互摘要
        try:
            self.ai_logger.print_session_summary()
            self.ai_logger.save_session_summary()
        except Exception as e:
            logging.warning(f"无法生成AI交互摘要: {e}")
        
        # 询问是否平仓
        if self.current_position:
            try:
                response = input("当前有持仓，是否平仓？(y/n): ").strip().lower()
                if response == 'y':
                    self._close_position("系统停止，用户确认平仓")
            except:
                logging.info("跳过平仓确认")
        
        logging.info("✓ 交易系统已停止")
    
    def get_status(self) -> Dict:
        """获取系统状态"""
        position_info = self._get_position_info()
        
        return {
            'is_running': self.is_running,
            'current_position': self.current_position,
            'current_symbol': self.current_symbol,
            'entry_price': self.entry_price,
            'balance': position_info.get('balance', 0),
            'unrealized_pnl': position_info.get('unrealized_pnl', 0),
            'total_trades': self.total_trades,
            'successful_trades': self.successful_trades,
            'failed_trades': self.failed_trades
        }


# ==================== 主程序 ====================

def create_default_config():
    """创建默认配置文件"""
    config = {
        "bybit_api_key": "YOUR_BYBIT_API_KEY",
        "bybit_api_secret": "YOUR_BYBIT_API_SECRET",
        "use_testnet": True,
        "symbols": [
            "BTCUSDT_PERPETUAL",
            "ETHUSDT_PERPETUAL",
            "SOLUSDT_PERPETUAL"
        ],
        "deepseek_config": "deepseek_config.json",
        "default_leverage": 10,  # 默认10倍杠杆（AI可选1-15倍）
        "trading_interval": 60,
        "max_position_pct": 0.30,
        "min_balance": 10.0
    }
    
    config_file = "live_trading_config.json"
    
    if not os.path.exists(config_file):
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"✓ 已创建配置文件: {config_file}")
        print(f"⚠️ 请编辑配置文件，填入Bybit API密钥")
        return False
    
    return True


if __name__ == "__main__":
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Bybit AI Trading System')
    parser.add_argument('--auto-confirm', action='store_true', 
                        help='Auto confirm startup without user input (for systemd service)')
    args = parser.parse_args()
    
    # 初始化日志
    log_file = setup_logging(log_dir="logs", log_level=logging.INFO)
    
    print("\n" + "="*80)
    print("🚀 Bybit实盘自动合约交易系统")
    print("="*80)
    print(f"基于DeepSeek AI决策 + 极端行情保护")
    print(f"参考文档: https://bybit-exchange.github.io/docs/v5/intro")
    print("="*80 + "\n")
    
    # 检查配置文件
    if not create_default_config():
        print("\n请完成以下步骤：")
        print("1. 打开 live_trading_config.json")
        print("2. 填入Bybit API密钥（从Bybit网站获取）")
        print("3. 建议先使用测试网（use_testnet: true）")
        print("4. 重新运行本程序\n")
        exit(0)
    
    try:
        # 创建交易引擎
        engine = LiveTradingEngine("live_trading_config.json")
        
        # 显示风险提示
        print("\n⚠️ 风险提示:")
        print("  - 本系统为自动交易，可能产生亏损")
        print("  - 请先在测试网充分测试")
        print("  - 建议小额资金试运行")
        print("  - 实盘交易风险自负\n")
        
        # 确认启动
        if args.auto_confirm:
            print("✓ 自动确认模式：系统启动中...")
            response = 'yes'
        else:
            response = input("确认启动交易系统？(yes/no): ").strip().lower()
        
        if response != 'yes':
            print("已取消启动")
            exit(0)
        
        # 启动交易
        engine.start()
        
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        logging.error(f"系统错误: {e}", exc_info=True)
        print(f"\n系统错误: {e}")
    
    print(f"\n日志文件: {log_file}")

