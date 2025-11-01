"""
交易日志系统 - 记录每笔交易的完整信息以供AI分析
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import logging
import pandas as pd
import numpy as np

class CustomJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理pandas和numpy类型"""
    def default(self, obj):
        if isinstance(obj, (pd.Timestamp, datetime)):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif pd.isna(obj):
            return None
        return super().default(obj)

class TradeJournal:
    """
    交易日志系统
    
    功能：
    1. 记录每笔交易的开仓详情、理由、市场数据
    2. 跟踪交易结果和盈亏
    3. 生成分析报告供AI学习
    """
    
    def __init__(self, journal_dir: str = "trade_journals"):
        """
        初始化交易日志
        
        Args:
            journal_dir: 日志目录
        """
        self.journal_dir = journal_dir
        self.current_journal_file = None
        self.trades = []
        
        # 创建日志目录
        os.makedirs(journal_dir, exist_ok=True)
        
        # 创建今日日志文件
        self._init_today_journal()
        
        logging.info(f"✓ 交易日志系统已初始化: {self.current_journal_file}")
    
    def _init_today_journal(self):
        """初始化今日日志文件"""
        today = datetime.now().strftime("%Y-%m-%d")
        self.current_journal_file = os.path.join(self.journal_dir, f"trade_journal_{today}.json")
        
        # 如果文件存在，加载已有交易
        if os.path.exists(self.current_journal_file):
            try:
                with open(self.current_journal_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.trades = data.get('trades', [])
                logging.info(f"加载今日已有交易记录: {len(self.trades)}笔")
            except Exception as e:
                logging.error(f"加载日志文件失败: {e}")
                self.trades = []
    
    def log_trade_open(self, trade_data: Dict) -> str:
        """
        记录开仓交易
        
        Args:
            trade_data: {
                'symbol': 交易对,
                'action': LONG/SHORT,
                'entry_price': 开仓价格,
                'stop_loss': 止损价格,
                'take_profit': 止盈价格列表,
                'quantity': 数量,
                'leverage': 杠杆,
                'position_size_pct': 仓位比例,
                'order_type': Market/Limit,
                'reason': AI决策理由,
                'confidence': 信心度,
                'market_data': {
                    '15m': {完整15分钟数据},
                    '1h': {完整1小时数据},
                    '4h': {完整4小时数据},
                    'advanced_data': {Bybit高级数据},
                    'timestamp': 时间戳
                },
                'ai_analysis': {
                    'market_state': 市场状态,
                    'asset_comparison': 资产对比,
                    'decision': AI完整决策JSON
                }
            }
        
        Returns:
            trade_id: 交易ID
        """
        trade_id = f"TRADE_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{trade_data['symbol']}"
        
        trade_record = {
            'trade_id': trade_id,
            'status': 'OPEN',
            'open_time': datetime.now().isoformat(),
            'close_time': None,
            
            # 交易基本信息
            'symbol': trade_data['symbol'],
            'action': trade_data['action'],
            'order_type': trade_data.get('order_type', 'Market'),
            
            # 价格信息
            'entry_price': trade_data['entry_price'],
            'stop_loss': trade_data.get('stop_loss', 0),
            'take_profit': trade_data.get('take_profit', []),
            'close_price': None,
            
            # 仓位信息
            'quantity': trade_data['quantity'],
            'leverage': trade_data['leverage'],
            'position_size_pct': trade_data['position_size_pct'],
            'position_value': trade_data['entry_price'] * trade_data['quantity'],
            
            # AI决策信息
            'reason': trade_data['reason'],
            'confidence': trade_data.get('confidence', 0),
            'ai_analysis': trade_data.get('ai_analysis', {}),
            
            # 完整市场数据（用于AI分析）
            'market_data_snapshot': trade_data.get('market_data', {}),
            
            # 交易结果（开仓时为None）
            'pnl': None,
            'pnl_pct': None,
            'duration_hours': None,
            'close_reason': None,
            
            # 风险收益比
            'risk_reward_ratio': self._calculate_risk_reward(
                trade_data['action'],
                trade_data['entry_price'],
                trade_data.get('stop_loss', 0),
                trade_data.get('take_profit', [])
            )
        }
        
        # 添加到交易列表
        self.trades.append(trade_record)
        
        # 立即保存
        self._save_journal()
        
        logging.info(f"✓ 交易已记录: {trade_id}")
        return trade_id
    
    def log_trade_close(self, trade_id: str, close_data: Dict):
        """
        记录平仓交易
        
        Args:
            close_data: {
                'close_price': 平仓价格,
                'close_reason': 平仓理由,
                'pnl': 盈亏金额,
                'pnl_pct': 盈亏百分比,
                'post_close_klines': 平仓后的3根15m K线（可选）
            }
        """
        # 查找交易记录
        trade = None
        for t in self.trades:
            if t['trade_id'] == trade_id and t['status'] == 'OPEN':
                trade = t
                break
        
        if not trade:
            logging.warning(f"未找到开仓记录: {trade_id}")
            return
        
        # 更新交易记录
        trade['status'] = 'CLOSED'
        trade['close_time'] = datetime.now().isoformat()
        trade['close_price'] = close_data['close_price']
        trade['close_reason'] = close_data.get('close_reason', '未知')
        trade['pnl'] = close_data['pnl']
        trade['pnl_pct'] = close_data['pnl_pct']
        
        # 计算持仓时长
        open_time = datetime.fromisoformat(trade['open_time'])
        close_time = datetime.now()
        duration = (close_time - open_time).total_seconds() / 3600
        trade['duration_hours'] = round(duration, 2)
        
        # 保存平仓后的K线数据（如果提供）
        if 'post_close_klines' in close_data:
            trade['post_close_klines'] = close_data['post_close_klines']
        
        # 保存
        self._save_journal()
        
        # 打印交易总结
        self._print_trade_summary(trade)
        
        logging.info(f"✓ 交易已平仓: {trade_id} | 盈亏: {trade['pnl']:.2f} USDT ({trade['pnl_pct']:.2f}%)")
    
    def _calculate_risk_reward(self, action: str, entry: float, stop_loss: float, take_profit: List) -> float:
        """计算盈亏比"""
        if stop_loss == 0 or not take_profit:
            return 0
        
        try:
            if action == "LONG":
                risk = abs(entry - stop_loss)
                reward = abs(take_profit[0] - entry)
            else:  # SHORT
                risk = abs(stop_loss - entry)
                reward = abs(entry - take_profit[0])
            
            if risk > 0:
                return round(reward / risk, 2)
        except:
            pass
        
        return 0
    
    def _save_journal(self):
        """保存日志到文件"""
        try:
            journal_data = {
                'date': datetime.now().strftime("%Y-%m-%d"),
                'total_trades': len(self.trades),
                'open_trades': len([t for t in self.trades if t['status'] == 'OPEN']),
                'closed_trades': len([t for t in self.trades if t['status'] == 'CLOSED']),
                'trades': self.trades
            }
            
            with open(self.current_journal_file, 'w', encoding='utf-8') as f:
                json.dump(journal_data, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
            
        except Exception as e:
            logging.error(f"保存日志失败: {e}")
    
    def add_post_close_klines(self, trade_id: str, post_close_klines: List[Dict]):
        """
        添加平仓后的K线数据到交易记录
        
        Args:
            trade_id: 交易ID
            post_close_klines: 平仓后的K线列表
        """
        # 查找交易记录
        for trade in self.trades:
            if trade['trade_id'] == trade_id:
                trade['post_close_klines'] = post_close_klines
                self._save_journal()
                logging.info(f"✓ 已添加{len(post_close_klines)}根平仓后K线到交易 {trade_id}")
                return
        
        logging.warning(f"未找到交易记录: {trade_id}")
    
    def _print_trade_summary(self, trade: Dict):
        """打印交易总结"""
        print("\n" + "="*80)
        print(f"📊 交易总结: {trade['trade_id']}")
        print("="*80)
        print(f"交易对: {trade['symbol']}")
        print(f"方向: {trade['action']}")
        print(f"开仓价: {trade['entry_price']:.2f} | 平仓价: {trade['close_price']:.2f}")
        print(f"止损价: {trade['stop_loss']:.2f} | 止盈价: {trade['take_profit']}")
        print(f"数量: {trade['quantity']} | 杠杆: {trade['leverage']}x")
        print(f"持仓时长: {trade['duration_hours']:.2f} 小时")
        print(f"盈亏: {trade['pnl']:.2f} USDT ({trade['pnl_pct']:.2f}%)")
        print(f"盈亏比: {trade['risk_reward_ratio']}:1")
        print(f"平仓原因: {trade['close_reason']}")
        print(f"AI理由: {trade['reason'][:100]}...")
        print("="*80 + "\n")
    
    def get_open_trades(self) -> List[Dict]:
        """获取所有未平仓交易"""
        return [t for t in self.trades if t['status'] == 'OPEN']
    
    def get_closed_trades(self, days: int = 7) -> List[Dict]:
        """获取最近N天的已平仓交易"""
        cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
        
        closed_trades = []
        for t in self.trades:
            if t['status'] == 'CLOSED' and t['close_time']:
                close_time = datetime.fromisoformat(t['close_time']).timestamp()
                if close_time >= cutoff_time:
                    closed_trades.append(t)
        
        return closed_trades
    
    def get_performance_stats(self, days: int = 7) -> Dict:
        """
        生成交易统计报告
        
        Returns:
            {
                'total_trades': 总交易数,
                'win_trades': 盈利交易数,
                'loss_trades': 亏损交易数,
                'win_rate': 胜率,
                'total_pnl': 总盈亏,
                'avg_pnl': 平均盈亏,
                'max_win': 最大盈利,
                'max_loss': 最大亏损,
                'avg_duration': 平均持仓时长
            }
        """
        closed_trades = self.get_closed_trades(days)
        
        if not closed_trades:
            return {
                'total_trades': 0,
                'win_trades': 0,
                'loss_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'avg_pnl': 0,
                'max_win': 0,
                'max_loss': 0,
                'avg_duration': 0
            }
        
        win_trades = [t for t in closed_trades if t['pnl'] > 0]
        loss_trades = [t for t in closed_trades if t['pnl'] <= 0]
        
        total_pnl = sum(t['pnl'] for t in closed_trades)
        avg_duration = sum(t['duration_hours'] for t in closed_trades) / len(closed_trades)
        
        return {
            'total_trades': len(closed_trades),
            'win_trades': len(win_trades),
            'loss_trades': len(loss_trades),
            'win_rate': round(len(win_trades) / len(closed_trades) * 100, 2),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl': round(total_pnl / len(closed_trades), 2),
            'max_win': round(max(t['pnl'] for t in closed_trades), 2),
            'max_loss': round(min(t['pnl'] for t in closed_trades), 2),
            'avg_duration': round(avg_duration, 2)
        }
    
    def generate_ai_analysis_report(self, days: int = 7) -> str:
        """
        生成供AI分析的报告
        
        包含：
        1. 所有失败交易的详细信息
        2. 市场数据快照
        3. AI的决策理由
        """
        closed_trades = self.get_closed_trades(days)
        loss_trades = [t for t in closed_trades if t['pnl'] < 0]
        
        report = f"""
# AI交易分析报告
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
分析周期: 最近{days}天

## 交易统计
总交易数: {len(closed_trades)}
盈利交易: {len([t for t in closed_trades if t['pnl'] > 0])}
亏损交易: {len(loss_trades)}
胜率: {(len([t for t in closed_trades if t['pnl'] > 0]) / len(closed_trades) * 100) if closed_trades else 0:.2f}%

## 需要分析的失败交易

"""
        
        for i, trade in enumerate(loss_trades, 1):
            report += f"""
### 失败交易 #{i}: {trade['trade_id']}

**基本信息:**
- 交易对: {trade['symbol']}
- 方向: {trade['action']}
- 开仓时间: {trade['open_time']}
- 平仓时间: {trade['close_time']}
- 持仓时长: {trade['duration_hours']:.2f}小时

**价格信息:**
- 开仓价: {trade['entry_price']:.2f}
- 止损价: {trade['stop_loss']:.2f}
- 止盈价: {trade['take_profit']}
- 平仓价: {trade['close_price']:.2f}
- 盈亏比: {trade['risk_reward_ratio']}:1

**交易结果:**
- 盈亏: {trade['pnl']:.2f} USDT ({trade['pnl_pct']:.2f}%)
- 平仓原因: {trade['close_reason']}

**AI决策信息:**
- 信心度: {trade['confidence']}%
- 决策理由: {trade['reason']}

**市场数据快照:**
- 15分钟趋势: {trade['market_data_snapshot'].get('15m', {}).get('close', 'N/A')}
- 1小时趋势: {trade['market_data_snapshot'].get('1h', {}).get('close', 'N/A')}
- 4小时趋势: {trade['market_data_snapshot'].get('4h', {}).get('close', 'N/A')}

**问题分析:**
请分析以下几个方面:
1. 入场时机是否合适？
2. 止损设置是否合理？
3. 趋势判断是否正确？
4. 是否忽略了关键信号？
5. 下次如何改进？

---
"""
        
        return report
    
    def save_analysis_report(self, days: int = 7):
        """保存分析报告到文件"""
        report = self.generate_ai_analysis_report(days)
        filename = os.path.join(
            self.journal_dir,
            f"ai_analysis_report_{datetime.now().strftime('%Y-%m-%d')}.md"
        )
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report)
            logging.info(f"✓ AI分析报告已保存: {filename}")
            return filename
        except Exception as e:
            logging.error(f"保存分析报告失败: {e}")
            return None


# 单例模式
_journal_instance = None

def get_trade_journal() -> TradeJournal:
    """获取交易日志单例"""
    global _journal_instance
    if _journal_instance is None:
        _journal_instance = TradeJournal()
    return _journal_instance

