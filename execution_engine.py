"""
改进的执行引擎

核心功能：
1. 真实滑点模型 - 基于成交量、波动率、订单大小
2. 订单执行策略 - 限价单、市价单、冰山单
3. 资金利用率优化 - 多级仓位管理
4. 部分平仓策略优化
5. 交易成本精确计算
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional, List
from enum import Enum


class OrderType(Enum):
    """订单类型"""
    MARKET = "market"  # 市价单
    LIMIT = "limit"    # 限价单
    ICEBERG = "iceberg"  # 冰山单（大额订单分批执行）


class SlippageModel:
    """滑点模型"""
    
    @staticmethod
    def calculate_slippage(
        order_size: float,
        current_price: float,
        volume_24h: float,
        volatility: float,
        order_type: OrderType = OrderType.MARKET,
        liquidity_score: float = 1.0
    ) -> Dict:
        """
        计算真实滑点
        
        滑点因素：
        1. 订单大小相对于成交量 (40%)
        2. 市场波动率 (30%)
        3. 订单类型 (20%)
        4. 流动性评分 (10%)
        
        Args:
            order_size: 订单规模（USDT）
            current_price: 当前价格
            volume_24h: 24小时成交量
            volatility: 波动率
            order_type: 订单类型
            liquidity_score: 流动性评分 (0-1)
            
        Returns:
            {
                'slippage_pct': 滑点百分比,
                'slippage_price': 滑点后的价格,
                'cost': 滑点成本
            }
        """
        # 1. 基础滑点（订单大小影响）
        # 订单占24小时成交量的比例
        volume_impact = order_size / (volume_24h * current_price + 1e-10)
        
        # 非线性影响：订单越大，滑点指数增长
        size_slippage = volume_impact ** 0.7 * 100  # 转为百分比
        size_slippage = min(size_slippage, 2.0)  # 最大2%
        
        # 2. 波动率滑点
        vol_slippage = volatility * 0.3  # 波动率越高，滑点越大
        vol_slippage = min(vol_slippage, 1.0)  # 最大1%
        
        # 3. 订单类型影响
        if order_type == OrderType.MARKET:
            type_multiplier = 1.0  # 市价单全额滑点
        elif order_type == OrderType.LIMIT:
            type_multiplier = 0.3  # 限价单降低70%滑点
        else:  # ICEBERG
            type_multiplier = 0.5  # 冰山单降低50%滑点
        
        # 4. 流动性影响
        liquidity_multiplier = 2.0 - liquidity_score  # 流动性差加倍滑点
        
        # 综合滑点
        total_slippage_pct = (
            (size_slippage * 0.4 + vol_slippage * 0.3) * 
            type_multiplier * 
            liquidity_multiplier
        )
        
        # 添加随机波动（模拟市场微观结构）
        random_noise = np.random.normal(0, total_slippage_pct * 0.2)
        total_slippage_pct += random_noise
        total_slippage_pct = max(0, total_slippage_pct)  # 不能为负
        
        # 计算滑点后价格和成本
        slippage_price = current_price * (1 + total_slippage_pct / 100)
        slippage_cost = order_size * (total_slippage_pct / 100)
        
        return {
            'slippage_pct': total_slippage_pct,
            'slippage_price': slippage_price,
            'cost': slippage_cost,
            'breakdown': {
                'size_impact': size_slippage * 0.4,
                'volatility_impact': vol_slippage * 0.3,
                'type_multiplier': type_multiplier,
                'liquidity_multiplier': liquidity_multiplier
            }
        }
    
    @staticmethod
    def calculate_spread_cost(
        current_price: float,
        spread_pct: float = 0.02
    ) -> Dict:
        """
        计算买卖价差成本
        
        Args:
            current_price: 当前价格
            spread_pct: 价差百分比（默认0.02%）
            
        Returns:
            {
                'bid': 买一价,
                'ask': 卖一价,
                'spread': 价差
            }
        """
        spread = current_price * spread_pct / 100
        
        return {
            'bid': current_price - spread / 2,
            'ask': current_price + spread / 2,
            'spread': spread,
            'spread_pct': spread_pct
        }


class PositionSizer:
    """仓位管理器"""
    
    @staticmethod
    def calculate_tiered_position(
        base_position_pct: float,
        confidence: float,
        risk_multiplier: float = 1.0
    ) -> List[Dict]:
        """
        计算分级仓位
        
        将仓位分为多个梯度，降低风险：
        - 高置信度：3级建仓 (50% + 30% + 20%)
        - 中置信度：2级建仓 (60% + 40%)
        - 低置信度：1级建仓 (100%)
        
        Args:
            base_position_pct: 基础仓位比例 (0-1)
            confidence: 信号置信度 (0-100)
            risk_multiplier: 风险乘数
            
        Returns:
            仓位梯度列表 [{ratio, entry_trigger}]
        """
        adjusted_position = base_position_pct * risk_multiplier
        adjusted_position = np.clip(adjusted_position, 0, 1)
        
        tiers = []
        
        if confidence >= 80:
            # 高置信度：3级
            tiers = [
                {'ratio': 0.50, 'entry_trigger': 'immediate'},
                {'ratio': 0.30, 'entry_trigger': 'confirmation'},
                {'ratio': 0.20, 'entry_trigger': 'breakout'}
            ]
        elif confidence >= 60:
            # 中置信度：2级
            tiers = [
                {'ratio': 0.60, 'entry_trigger': 'immediate'},
                {'ratio': 0.40, 'entry_trigger': 'confirmation'}
            ]
        else:
            # 低置信度：1级
            tiers = [
                {'ratio': 1.0, 'entry_trigger': 'immediate'}
            ]
        
        # 应用调整后的总仓位
        for tier in tiers:
            tier['size'] = adjusted_position * tier['ratio']
        
        return tiers
    
    @staticmethod
    def calculate_pyramid_entries(
        entry_price: float,
        direction: str,
        num_entries: int = 3,
        spacing_pct: float = 1.0
    ) -> List[float]:
        """
        计算金字塔加仓点位
        
        Args:
            entry_price: 初始入场价
            direction: LONG/SHORT
            num_entries: 加仓次数
            spacing_pct: 间距百分比
            
        Returns:
            加仓价格列表
        """
        prices = [entry_price]
        
        for i in range(1, num_entries):
            if direction == 'LONG':
                # 做多：价格下跌时加仓（抄底）
                next_price = entry_price * (1 - spacing_pct * i / 100)
            else:
                # 做空：价格上涨时加仓
                next_price = entry_price * (1 + spacing_pct * i / 100)
            
            prices.append(next_price)
        
        return prices


class PartialCloseManager:
    """部分平仓管理器"""
    
    @staticmethod
    def calculate_optimal_partial_close(
        unrealized_pnl_pct: float,
        take_profit_targets: List[float],
        current_volatility: float
    ) -> Optional[Dict]:
        """
        计算最优部分平仓策略
        
        动态调整平仓比例：
        - 低波动：小比例平仓，让利润奔跑
        - 高波动：大比例平仓，锁定利润
        
        Args:
            unrealized_pnl_pct: 未实现盈亏百分比
            take_profit_targets: 止盈目标列表
            current_volatility: 当前波动率
            
        Returns:
            None 或 {'close_ratio', 'reason'}
        """
        for target in sorted(take_profit_targets):
            if unrealized_pnl_pct >= target:
                # 根据波动率调整平仓比例
                if current_volatility > 0.5:
                    # 高波动：激进平仓
                    close_ratio = 0.5
                    reason = f"高波动环境，达到{target}%止盈，平仓50%"
                elif current_volatility > 0.3:
                    # 中波动：正常平仓
                    close_ratio = 0.33
                    reason = f"达到{target}%止盈，平仓33%"
                else:
                    # 低波动：保守平仓
                    close_ratio = 0.25
                    reason = f"低波动环境，达到{target}%止盈，平仓25%"
                
                return {
                    'target': target,
                    'close_ratio': close_ratio,
                    'reason': reason
                }
        
        return None
    
    @staticmethod
    def calculate_trailing_stop(
        entry_price: float,
        current_price: float,
        highest_price: float,  # 持仓以来的最高价
        direction: str,
        trailing_pct: float = 2.0
    ) -> Optional[float]:
        """
        计算移动止损价格
        
        Args:
            entry_price: 入场价
            current_price: 当前价
            highest_price: 最高价（做多）或最低价（做空）
            direction: LONG/SHORT
            trailing_pct: 回撤百分比触发止损
            
        Returns:
            止损价格或None
        """
        if direction == 'LONG':
            # 做多：从最高点回撤trailing_pct%触发
            profit_pct = (highest_price - entry_price) / entry_price * 100
            
            if profit_pct > 2:  # 盈利超过2%才启动移动止损
                trailing_stop = highest_price * (1 - trailing_pct / 100)
                return trailing_stop
        
        else:  # SHORT
            # 做空：从最低点反弹trailing_pct%触发
            profit_pct = (entry_price - highest_price) / entry_price * 100
            
            if profit_pct > 2:
                trailing_stop = highest_price * (1 + trailing_pct / 100)
                return trailing_stop
        
        return None


class ExecutionEngine:
    """执行引擎（集成所有执行功能）"""
    
    def __init__(self, trading_fee: float = 0.0006):
        """
        初始化执行引擎
        
        Args:
            trading_fee: 交易手续费率
        """
        self.trading_fee = trading_fee
        self.slippage_model = SlippageModel()
        self.position_sizer = PositionSizer()
        self.partial_close_mgr = PartialCloseManager()
    
    def calculate_entry_execution(
        self,
        direction: str,
        entry_price: float,
        position_size_pct: float,
        balance: float,
        leverage: int,
        market_data: Dict,
        order_type: OrderType = OrderType.MARKET
    ) -> Dict:
        """
        计算入场执行细节
        
        Args:
            direction: LONG/SHORT
            entry_price: 入场价格
            position_size_pct: 仓位比例
            balance: 账户余额
            leverage: 杠杆
            market_data: 市场数据（需包含volume, volatility）
            order_type: 订单类型
            
        Returns:
            执行细节字典
        """
        # 计算订单规模
        order_value = balance * position_size_pct * leverage
        
        # 计算滑点
        volume_24h = market_data.get('volume', 0) * 96  # 15分钟*96=24小时
        volatility = market_data.get('volatility', 0.3)
        
        slippage = self.slippage_model.calculate_slippage(
            order_size=order_value,
            current_price=entry_price,
            volume_24h=volume_24h,
            volatility=volatility,
            order_type=order_type
        )
        
        # 实际执行价格
        if direction == 'LONG':
            actual_price = slippage['slippage_price']  # 做多买入价更高
        else:
            actual_price = entry_price * (1 - slippage['slippage_pct'] / 100)  # 做空卖出价更低
        
        # 实际持仓数量
        actual_size = order_value / actual_price
        
        # 手续费
        fee = order_value * self.trading_fee
        
        # 总成本
        total_cost = slippage['cost'] + fee
        
        return {
            'actual_price': actual_price,
            'actual_size': actual_size,
            'order_value': order_value,
            'slippage': slippage,
            'fee': fee,
            'total_cost': total_cost,
            'cost_pct': (total_cost / order_value) * 100
        }
    
    def calculate_exit_execution(
        self,
        direction: str,
        exit_price: float,
        position_size: float,
        market_data: Dict,
        order_type: OrderType = OrderType.MARKET
    ) -> Dict:
        """
        计算出场执行细节
        
        Args:
            direction: LONG/SHORT
            exit_price: 出场价格
            position_size: 持仓数量
            market_data: 市场数据
            order_type: 订单类型
            
        Returns:
            执行细节字典
        """
        order_value = position_size * exit_price
        
        volume_24h = market_data.get('volume', 0) * 96
        volatility = market_data.get('volatility', 0.3)
        
        slippage = self.slippage_model.calculate_slippage(
            order_size=order_value,
            current_price=exit_price,
            volume_24h=volume_24h,
            volatility=volatility,
            order_type=order_type
        )
        
        # 实际成交价
        if direction == 'LONG':
            actual_price = exit_price * (1 - slippage['slippage_pct'] / 100)  # 做多卖出价更低
        else:
            actual_price = slippage['slippage_price']  # 做空买回价更高
        
        # 手续费
        fee = order_value * self.trading_fee
        
        # 总成本
        total_cost = slippage['cost'] + fee
        
        return {
            'actual_price': actual_price,
            'order_value': order_value,
            'slippage': slippage,
            'fee': fee,
            'total_cost': total_cost,
            'cost_pct': (total_cost / order_value) * 100
        }
    
    def optimize_position_size(
        self,
        base_size: float,
        confidence: float,
        risk_multiplier: float,
        market_volatility: float
    ) -> float:
        """
        优化仓位大小
        
        综合考虑：
        - AI信号强度
        - 账户风险状态
        - 市场波动率
        
        Args:
            base_size: AI建议仓位
            confidence: 信号置信度
            risk_multiplier: 风险乘数
            market_volatility: 市场波动率
            
        Returns:
            优化后的仓位
        """
        # 信号强度调整
        if confidence >= 90:
            conf_multiplier = 1.2
        elif confidence >= 75:
            conf_multiplier = 1.0
        elif confidence >= 60:
            conf_multiplier = 0.8
        else:
            conf_multiplier = 0.5
        
        # 波动率调整
        if market_volatility > 0.6:
            vol_multiplier = 0.6
        elif market_volatility > 0.4:
            vol_multiplier = 0.8
        else:
            vol_multiplier = 1.0
        
        # 综合
        optimized = base_size * conf_multiplier * risk_multiplier * vol_multiplier
        
        return np.clip(optimized, 0.1, 1.0)


if __name__ == "__main__":
    print("执行引擎模块已加载")
    print("\n核心功能:")
    print("  - 真实滑点模型")
    print("  - 多种订单类型")
    print("  - 分级仓位管理")
    print("  - 金字塔加仓")
    print("  - 动态部分平仓")
    print("  - 移动止损")




