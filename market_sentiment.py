"""
市场情绪指标模块

包含：
- 资金费率 (Funding Rate) - 多空情绪
- 持仓量 (Open Interest) - 市场参与度
- 长短比 (Long/Short Ratio) - 散户情绪
- 恐慌贪婪指数 (Fear & Greed) - 市场情绪
- 巨鲸持仓变化 - 大户行为
- 交易所流入流出 - 抛压指标

注: 由于这是回测系统，部分数据使用技术指标模拟
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import datetime


class MarketSentiment:
    """市场情绪分析器"""
    
    @staticmethod
    def estimate_funding_rate(df: pd.DataFrame, lookback: int = 8) -> pd.DataFrame:
        """
        估算资金费率（基于价格动量和成交量）
        
        真实场景应从交易所API获取，这里用技术指标模拟：
        - 价格强势上涨 + 高成交量 → 正资金费率（多头付费）
        - 价格强势下跌 + 高成交量 → 负资金费率（空头付费）
        
        Returns:
            添加 funding_rate_estimate 列 (范围: -0.1% 到 +0.1%)
        """
        returns = df['close'].pct_change(lookback)
        
        # 成交量标准化
        volume_ma = df['volume'].rolling(window=24).mean()
        volume_ratio = df['volume'] / volume_ma
        
        # 估算资金费率
        funding_rate = returns * volume_ratio * 100  # 转为百分比
        funding_rate = np.clip(funding_rate, -0.1, 0.1)
        
        df['funding_rate_estimate'] = funding_rate
        
        # 资金费率累积 (长期偏向)
        funding_cumsum = funding_rate.rolling(window=48).sum()
        df['funding_cumulative'] = funding_cumsum
        
        return df
    
    @staticmethod
    def estimate_open_interest(df: pd.DataFrame) -> pd.DataFrame:
        """
        估算持仓量变化
        
        真实场景应从交易所获取，这里基于成交量和价格波动模拟：
        - 放量上涨/下跌 → 持仓量增加（新开仓）
        - 缩量 → 持仓量减少（平仓）
        
        Returns:
            添加 oi_estimate, oi_change_pct 列
        """
        volume_ma = df['volume'].rolling(window=24).mean()
        price_change = df['close'].pct_change().abs()
        
        # 模拟持仓量（基于成交量滚动累积）
        oi_estimate = df['volume'].rolling(window=48).mean() * 100
        
        # 持仓量变化百分比
        oi_change_pct = oi_estimate.pct_change(periods=24) * 100
        
        df['oi_estimate'] = oi_estimate
        df['oi_change_pct'] = oi_change_pct
        
        return df
    
    @staticmethod
    def estimate_long_short_ratio(df: pd.DataFrame) -> pd.DataFrame:
        """
        估算多空比（散户持仓比例）
        
        基于价格和RSI模拟：
        - RSI高 → 散户偏多
        - RSI低 → 散户偏空
        - 可用于反向指标
        
        Returns:
            添加 long_short_ratio 列 (>1多头多, <1空头多)
        """
        if 'rsi' in df.columns:
            # RSI越高，散户越偏多
            long_short_ratio = (df['rsi'] / (100 - df['rsi'])).clip(0.1, 10)
        else:
            # 使用价格动量替代
            momentum = df['close'].pct_change(14)
            long_short_ratio = (1 + momentum * 10).clip(0.1, 10)
        
        df['long_short_ratio'] = long_short_ratio
        
        # 极端多空比 (可能的反转信号)
        df['extreme_ratio'] = (
            (long_short_ratio > 3.0) | (long_short_ratio < 0.33)
        ).astype(int)
        
        return df
    
    @staticmethod
    def calculate_fear_greed_index(df: pd.DataFrame) -> pd.DataFrame:
        """
        计算恐慌贪婪指数 (0-100)
        
        综合多个因素：
        - 价格动量 (25%)
        - 波动率 (25%)
        - 成交量 (20%)
        - RSI (15%)
        - 资金费率 (15%)
        
        0-25: 极度恐慌
        25-45: 恐慌
        45-55: 中性
        55-75: 贪婪
        75-100: 极度贪婪
        
        Returns:
            添加 fear_greed_index 列 (0-100)
        """
        score = pd.Series(50.0, index=df.index)  # 基准50
        
        # 1. 价格动量 (25%)
        momentum_14 = df['close'].pct_change(14) * 100
        momentum_score = 50 + np.clip(momentum_14 * 2, -50, 50)
        score += (momentum_score - 50) * 0.25
        
        # 2. 波动率 (25% - 高波动=恐慌)
        if 'volatility' in df.columns:
            vol_percentile = df['volatility'].rolling(window=100).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100
            )
            volatility_score = 100 - vol_percentile  # 反转：波动越高分数越低
            score += (volatility_score - 50) * 0.25
        
        # 3. 成交量 (20% - 高成交量=贪婪)
        volume_ma = df['volume'].rolling(window=24).mean()
        volume_ratio = df['volume'] / volume_ma
        volume_score = 50 + np.clip((volume_ratio - 1) * 50, -50, 50)
        score += (volume_score - 50) * 0.20
        
        # 4. RSI (15%)
        if 'rsi' in df.columns:
            rsi_score = df['rsi']
            score += (rsi_score - 50) * 0.15
        
        # 5. 资金费率 (15%)
        if 'funding_rate_estimate' in df.columns:
            funding_score = 50 + df['funding_rate_estimate'] * 500  # 放大到0-100范围
            score += (funding_score - 50) * 0.15
        
        df['fear_greed_index'] = np.clip(score, 0, 100)
        
        # 情绪状态标签
        df['sentiment_label'] = pd.cut(
            df['fear_greed_index'],
            bins=[0, 25, 45, 55, 75, 100],
            labels=['极度恐慌', '恐慌', '中性', '贪婪', '极度贪婪']
        )
        
        return df
    
    @staticmethod
    def detect_whale_activity(df: pd.DataFrame, 
                             volume_threshold: float = 2.5) -> pd.DataFrame:
        """
        检测巨鲸活动（大额交易）
        
        基于异常成交量识别：
        - 成交量 > 均值的2.5倍 → 可能有大户参与
        
        Returns:
            添加 whale_activity 列 (0或1)
        """
        volume_ma = df['volume'].rolling(window=24).mean()
        volume_std = df['volume'].rolling(window=24).std()
        
        # Z-score检测异常
        z_score = (df['volume'] - volume_ma) / (volume_std + 1e-10)
        
        whale_activity = (z_score > volume_threshold).astype(int)
        
        df['whale_activity'] = whale_activity
        df['volume_z_score'] = z_score
        
        return df
    
    @staticmethod
    def estimate_exchange_flow(df: pd.DataFrame) -> pd.DataFrame:
        """
        估算交易所流入流出
        
        基于价格和成交量模拟：
        - 大幅下跌 + 放量 → 可能流入交易所（抛压）
        - 上涨 + 缩量 → 可能流出交易所（囤币）
        
        Returns:
            添加 exchange_flow_pressure 列 (-1到1，负=流入/抛压)
        """
        price_change = df['close'].pct_change(4)
        
        volume_ma = df['volume'].rolling(window=24).mean()
        volume_ratio = df['volume'] / volume_ma
        
        # 下跌+放量 → 负值（抛压）
        # 上涨+缩量 → 正值（囤币）
        flow_pressure = -price_change * volume_ratio
        flow_pressure = np.clip(flow_pressure, -1, 1)
        
        df['exchange_flow_pressure'] = flow_pressure
        
        # 累积流动压力
        cumulative_pressure = flow_pressure.rolling(window=48).sum()
        df['cumulative_flow_pressure'] = cumulative_pressure
        
        return df
    
    @staticmethod
    def calculate_market_regime(df: pd.DataFrame) -> pd.DataFrame:
        """
        识别市场状态
        
        基于波动率、趋势强度、成交量分类：
        - bull_trend: 牛市趋势
        - bear_trend: 熊市趋势
        - high_volatility: 高波动震荡
        - low_volatility: 低波动盘整
        
        Returns:
            添加 market_regime 列
        """
        # 趋势方向
        if 'ema_50' in df.columns:
            trend_up = df['close'] > df['ema_50']
        else:
            trend_up = df['close'] > df['close'].rolling(50).mean()
        
        # 波动率水平
        if 'volatility' in df.columns:
            vol_high = df['volatility'] > df['volatility'].rolling(100).quantile(0.7)
        else:
            returns = df['close'].pct_change()
            vol_high = returns.rolling(20).std() > returns.rolling(100).std().quantile(0.7)
        
        # 趋势强度
        if 'adx' in df.columns:
            strong_trend = df['adx'] > 25
        else:
            strong_trend = abs(df['close'].pct_change(20)) > 0.1
        
        # 状态分类
        regime = []
        for i in range(len(df)):
            if strong_trend.iloc[i]:
                if trend_up.iloc[i]:
                    regime.append('bull_trend')
                else:
                    regime.append('bear_trend')
            else:
                if vol_high.iloc[i]:
                    regime.append('high_volatility')
                else:
                    regime.append('low_volatility')
        
        df['market_regime'] = regime
        
        return df
    
    @staticmethod
    def calculate_all_sentiment_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有市场情绪指标
        
        Args:
            df: 包含OHLCV和技术指标的DataFrame
            
        Returns:
            添加了所有情绪指标的DataFrame
        """
        df = MarketSentiment.estimate_funding_rate(df)
        df = MarketSentiment.estimate_open_interest(df)
        df = MarketSentiment.estimate_long_short_ratio(df)
        df = MarketSentiment.calculate_fear_greed_index(df)
        df = MarketSentiment.detect_whale_activity(df)
        df = MarketSentiment.estimate_exchange_flow(df)
        df = MarketSentiment.calculate_market_regime(df)
        
        return df


def get_sentiment_summary(market_data: Dict) -> Dict:
    """
    获取市场情绪摘要（用于AI决策）
    
    Args:
        market_data: 包含15m/1h/4h数据的字典
        
    Returns:
        情绪摘要字典
    """
    summary = {}
    
    # 从4小时数据提取主要情绪
    data_4h = market_data.get('4h', {})
    
    if data_4h:
        summary['fear_greed'] = data_4h.get('fear_greed_index', 50)
        summary['sentiment_label'] = data_4h.get('sentiment_label', '中性')
        summary['market_regime'] = data_4h.get('market_regime', 'unknown')
        summary['funding_rate'] = data_4h.get('funding_rate_estimate', 0)
        summary['oi_change'] = data_4h.get('oi_change_pct', 0)
        summary['long_short_ratio'] = data_4h.get('long_short_ratio', 1.0)
        summary['whale_activity'] = data_4h.get('whale_activity', 0)
        summary['flow_pressure'] = data_4h.get('exchange_flow_pressure', 0)
    
    return summary


if __name__ == "__main__":
    print("市场情绪指标模块已加载")
    print("\n支持的指标:")
    print("  - 资金费率估算")
    print("  - 持仓量变化")
    print("  - 多空比")
    print("  - 恐慌贪婪指数")
    print("  - 巨鲸活动检测")
    print("  - 交易所流入流出")
    print("  - 市场状态识别")




