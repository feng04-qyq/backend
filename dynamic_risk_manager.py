"""
动态风险管理模块

核心功能：
1. 动态风险预算 - 根据账户状态调整风险敞口
2. 波动率自适应仓位 - 高波动降仓位，低波动加仓位
3. 回撤控制 - 连续亏损时降低风险
4. 压力测试 - 模拟极端场景
5. Kelly公式优化 - 最优仓位计算
6. 风险价值(VaR)计算
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from collections import deque


class DynamicRiskManager:
    """动态风险管理器"""
    
    def __init__(self, 
                 initial_capital: float = 100.0,
                 max_drawdown_limit: float = 20.0,
                 var_confidence: float = 0.95):
        """
        初始化风险管理器
        
        Args:
            initial_capital: 初始资金
            max_drawdown_limit: 最大回撤限制（%）
            var_confidence: VaR置信度
        """
        self.initial_capital = initial_capital
        self.max_drawdown_limit = max_drawdown_limit
        self.var_confidence = var_confidence
        
        # 账户历史
        self.equity_history = deque(maxlen=1000)
        self.trade_history = []
        
        # 风险状态
        self.current_risk_level = 1.0  # 风险乘数 (0.0-1.0)
        self.consecutive_losses = 0
        self.peak_equity = initial_capital
        
    def update_equity(self, current_equity: float):
        """更新账户权益"""
        self.equity_history.append(current_equity)
        
        # 更新峰值
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
    
    def record_trade(self, pnl: float, pnl_pct: float):
        """记录交易结果"""
        self.trade_history.append({
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'timestamp': len(self.trade_history)
        })
        
        # 更新连续亏损计数
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
    
    def calculate_current_drawdown(self) -> float:
        """
        计算当前回撤
        
        Returns:
            当前回撤百分比
        """
        if len(self.equity_history) == 0:
            return 0.0
        
        current_equity = self.equity_history[-1]
        drawdown = (self.peak_equity - current_equity) / self.peak_equity * 100
        
        return max(0, drawdown)
    
    def calculate_max_drawdown(self) -> float:
        """
        计算历史最大回撤
        
        Returns:
            最大回撤百分比
        """
        if len(self.equity_history) < 2:
            return 0.0
        
        equity_array = np.array(self.equity_history)
        cummax = np.maximum.accumulate(equity_array)
        drawdowns = (cummax - equity_array) / cummax * 100
        
        return drawdowns.max()
    
    def calculate_volatility(self, lookback: int = 50) -> float:
        """
        计算账户波动率
        
        Args:
            lookback: 回看期数
            
        Returns:
            年化波动率
        """
        if len(self.equity_history) < 2:
            return 0.0
        
        equity_array = np.array(list(self.equity_history)[-lookback:])
        returns = np.diff(equity_array) / equity_array[:-1]
        
        if len(returns) < 2:
            return 0.0
        
        volatility = np.std(returns) * np.sqrt(252)  # 年化
        
        return volatility
    
    def calculate_var(self, lookback: int = 100) -> float:
        """
        计算风险价值(Value at Risk)
        
        Args:
            lookback: 回看期数
            
        Returns:
            VaR值（在置信度下的最大可能损失%）
        """
        if len(self.equity_history) < 2:
            return 0.0
        
        equity_array = np.array(list(self.equity_history)[-lookback:])
        returns = np.diff(equity_array) / equity_array[:-1]
        
        if len(returns) < 2:
            return 0.0
        
        var = np.percentile(returns, (1 - self.var_confidence) * 100)
        
        return abs(var * 100)  # 转为百分比
    
    def calculate_kelly_fraction(self, 
                                 win_rate: float,
                                 avg_win: float,
                                 avg_loss: float) -> float:
        """
        Kelly公式计算最优仓位比例
        
        Kelly% = W - (1-W)/R
        其中：
        - W = 胜率
        - R = 盈亏比 (平均盈利/平均亏损)
        
        Args:
            win_rate: 胜率 (0-1)
            avg_win: 平均盈利
            avg_loss: 平均亏损（正数）
            
        Returns:
            Kelly建议仓位比例 (0-1)
        """
        if avg_loss == 0 or win_rate == 0:
            return 0.0
        
        profit_loss_ratio = avg_win / avg_loss
        kelly = win_rate - (1 - win_rate) / profit_loss_ratio
        
        # Kelly值可能为负（不利系统），限制在0-1之间
        # 保守起见，使用Half-Kelly或Quarter-Kelly
        kelly = np.clip(kelly * 0.5, 0, 1)  # Half-Kelly
        
        return kelly
    
    def get_dynamic_risk_multiplier(self) -> float:
        """
        计算动态风险乘数
        
        基于多个因素综合计算：
        1. 当前回撤 (30%)
        2. 账户波动率 (25%)
        3. 连续亏损 (20%)
        4. VaR风险值 (15%)
        5. 历史胜率 (10%)
        
        Returns:
            风险乘数 (0.0-1.5)
            - 1.0 = 正常
            - <1.0 = 降低风险
            - >1.0 = 可加风险（账户状态良好）
        """
        multiplier = 1.0
        
        # 1. 回撤因素 (30%)
        current_dd = self.calculate_current_drawdown()
        if current_dd > self.max_drawdown_limit * 0.8:
            multiplier *= 0.3  # 接近最大回撤，大幅降低
        elif current_dd > self.max_drawdown_limit * 0.5:
            multiplier *= 0.6  # 回撤较大，降低风险
        elif current_dd < 5:
            multiplier *= 1.1  # 回撤很小，可适当加风险
        
        # 2. 波动率因素 (25%)
        volatility = self.calculate_volatility()
        if volatility > 0.5:  # 高波动
            multiplier *= 0.7
        elif volatility > 0.3:
            multiplier *= 0.85
        elif volatility < 0.15:  # 低波动
            multiplier *= 1.15
        
        # 3. 连续亏损因素 (20%)
        if self.consecutive_losses >= 5:
            multiplier *= 0.4  # 严重连损，大幅减仓
        elif self.consecutive_losses >= 3:
            multiplier *= 0.7
        elif self.consecutive_losses == 0 and len(self.trade_history) > 0:
            if self.trade_history[-1]['pnl'] > 0:
                multiplier *= 1.05  # 刚盈利，略加风险
        
        # 4. VaR因素 (15%)
        var = self.calculate_var()
        if var > 5:  # VaR > 5%
            multiplier *= 0.8
        elif var < 2:
            multiplier *= 1.1
        
        # 5. 胜率因素 (10%)
        if len(self.trade_history) >= 10:
            recent_trades = self.trade_history[-20:]
            wins = sum(1 for t in recent_trades if t['pnl'] > 0)
            win_rate = wins / len(recent_trades)
            
            if win_rate > 0.6:
                multiplier *= 1.1
            elif win_rate < 0.35:
                multiplier *= 0.8
        
        # 限制范围
        multiplier = np.clip(multiplier, 0.1, 1.5)
        
        self.current_risk_level = multiplier
        
        return multiplier
    
    def adjust_position_size(self, 
                            base_position_size: float,
                            market_volatility: float = 0.0) -> float:
        """
        调整仓位大小
        
        Args:
            base_position_size: AI建议的基础仓位 (0-1)
            market_volatility: 市场波动率
            
        Returns:
            调整后的仓位 (0-1)
        """
        # 获取动态风险乘数
        risk_multiplier = self.get_dynamic_risk_multiplier()
        
        # 根据市场波动率调整
        if market_volatility > 0:
            # 波动率百分位
            if market_volatility > 0.6:  # 高波动
                vol_adjustment = 0.7
            elif market_volatility > 0.4:
                vol_adjustment = 0.85
            else:
                vol_adjustment = 1.0
        else:
            vol_adjustment = 1.0
        
        # 综合调整
        adjusted_size = base_position_size * risk_multiplier * vol_adjustment
        
        # 限制范围
        adjusted_size = np.clip(adjusted_size, 0.0, 1.0)
        
        return adjusted_size
    
    def adjust_leverage(self, 
                       base_leverage: int,
                       market_volatility: float = 0.0) -> int:
        """
        调整杠杆倍数
        
        Args:
            base_leverage: AI建议的基础杠杆
            market_volatility: 市场波动率
            
        Returns:
            调整后的杠杆 (10-20)
        """
        risk_multiplier = self.get_dynamic_risk_multiplier()
        
        # 杠杆调整更保守
        if risk_multiplier < 0.5:
            # 风险状态差，降到最低杠杆
            adjusted_leverage = 10
        elif risk_multiplier < 0.8:
            # 风险状态一般，降低杠杆
            adjusted_leverage = max(10, int(base_leverage * 0.8))
        elif risk_multiplier > 1.2:
            # 风险状态好，可适当提高
            adjusted_leverage = min(20, int(base_leverage * 1.1))
        else:
            adjusted_leverage = base_leverage
        
        # 市场波动率调整
        if market_volatility > 0.6:
            adjusted_leverage = max(10, int(adjusted_leverage * 0.7))
        elif market_volatility > 0.4:
            adjusted_leverage = max(10, int(adjusted_leverage * 0.85))
        
        return np.clip(adjusted_leverage, 10, 20)
    
    def should_stop_trading(self) -> Tuple[bool, str]:
        """
        判断是否应该停止交易（熔断机制）
        
        Returns:
            (是否停止, 原因)
        """
        # 1. 回撤超限
        current_dd = self.calculate_current_drawdown()
        if current_dd >= self.max_drawdown_limit:
            return True, f"回撤超限: {current_dd:.1f}% >= {self.max_drawdown_limit}%"
        
        # 2. 连续大额亏损
        if self.consecutive_losses >= 8:
            return True, f"连续亏损{self.consecutive_losses}次"
        
        # 3. 极端VaR
        var = self.calculate_var()
        if var > 10:
            return True, f"风险价值过高: VaR={var:.1f}%"
        
        # 4. 账户权益过低
        if len(self.equity_history) > 0:
            current_equity = self.equity_history[-1]
            if current_equity < self.initial_capital * 0.5:
                return True, f"账户权益过低: {current_equity:.2f} < {self.initial_capital*0.5:.2f}"
        
        return False, ""
    
    def get_risk_report(self) -> Dict:
        """
        生成风险报告
        
        Returns:
            风险指标字典
        """
        report = {
            '当前风险乘数': round(self.current_risk_level, 2),
            '当前回撤(%)': round(self.calculate_current_drawdown(), 2),
            '最大回撤(%)': round(self.calculate_max_drawdown(), 2),
            '账户波动率': round(self.calculate_volatility(), 3),
            f'VaR({self.var_confidence*100:.0f}%)': round(self.calculate_var(), 2),
            '连续亏损次数': self.consecutive_losses,
            '峰值权益': round(self.peak_equity, 2)
        }
        
        if len(self.equity_history) > 0:
            report['当前权益'] = round(self.equity_history[-1], 2)
        
        if len(self.trade_history) >= 5:
            recent = self.trade_history[-20:] if len(self.trade_history) >= 20 else self.trade_history
            wins = [t for t in recent if t['pnl'] > 0]
            losses = [t for t in recent if t['pnl'] <= 0]
            
            win_rate = len(wins) / len(recent) * 100 if recent else 0
            avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
            avg_loss = abs(np.mean([t['pnl'] for t in losses])) if losses else 0
            
            report['近期胜率(%)'] = round(win_rate, 1)
            report['平均盈利'] = round(avg_win, 2)
            report['平均亏损'] = round(avg_loss, 2)
            report['盈亏比'] = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0
            
            # Kelly建议
            if avg_loss > 0:
                kelly = self.calculate_kelly_fraction(
                    win_rate / 100, avg_win, avg_loss
                )
                report['Kelly建议仓位'] = f"{kelly*100:.1f}%"
        
        return report


class StressTester:
    """压力测试模块"""
    
    @staticmethod
    def simulate_flash_crash(current_price: float, 
                            crash_pct: float = 20.0) -> Dict:
        """
        模拟闪崩场景
        
        Args:
            current_price: 当前价格
            crash_pct: 崩盘幅度（%）
            
        Returns:
            压力测试结果
        """
        crash_price = current_price * (1 - crash_pct / 100)
        
        return {
            'scenario': 'flash_crash',
            'crash_pct': crash_pct,
            'original_price': current_price,
            'crash_price': crash_price,
            'description': f'{crash_pct}%闪崩'
        }
    
    @staticmethod
    def simulate_extreme_volatility(base_volatility: float) -> Dict:
        """
        模拟极端波动场景
        
        Args:
            base_volatility: 基准波动率
            
        Returns:
            压力测试结果
        """
        extreme_vol = base_volatility * 3  # 3倍波动率
        
        return {
            'scenario': 'extreme_volatility',
            'base_volatility': base_volatility,
            'extreme_volatility': extreme_vol,
            'description': '极端波动（3倍正常波动率）'
        }
    
    @staticmethod
    def calculate_worst_case_loss(position_size: float,
                                  leverage: int,
                                  crash_pct: float,
                                  balance: float) -> Dict:
        """
        计算最坏情况损失
        
        Args:
            position_size: 仓位比例
            leverage: 杠杆倍数
            crash_pct: 价格下跌幅度
            balance: 账户余额
            
        Returns:
            最坏情况分析
        """
        # 持仓价值
        position_value = balance * position_size * leverage
        
        # 损失
        loss = position_value * (crash_pct / 100)
        loss_pct = (loss / balance) * 100
        
        # 剩余权益
        remaining_equity = balance - loss
        
        return {
            '持仓价值': round(position_value, 2),
            '最大损失': round(loss, 2),
            '损失比例(%)': round(loss_pct, 2),
            '剩余权益': round(remaining_equity, 2),
            '是否爆仓': remaining_equity <= 0
        }


if __name__ == "__main__":
    print("动态风险管理模块已加载")
    print("\n核心功能:")
    print("  - 动态风险预算")
    print("  - 波动率自适应仓位")
    print("  - 回撤控制")
    print("  - Kelly公式优化")
    print("  - VaR计算")
    print("  - 压力测试")




