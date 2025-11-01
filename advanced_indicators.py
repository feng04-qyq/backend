"""
高级技术指标计算模块

包含更多专业技术指标：
- ADX (平均趋向指标) - 趋势强度
- Stochastic (随机指标) - 超买超卖
- OBV (能量潮) - 成交量指标
- Williams %R - 动量指标
- CCI (商品通道指标) - 价格偏离
- 波动率指标
- 价格形态识别
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple


class AdvancedIndicators:
    """高级技术指标计算器"""
    
    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        计算ADX (Average Directional Index) - 趋势强度指标
        
        ADX值解读：
        - >25: 强趋势
        - 20-25: 中等趋势
        - <20: 弱趋势/震荡
        
        Returns:
            添加了 adx, di_plus, di_minus 列的DataFrame
        """
        high = df['high']
        low = df['low']
        close = df['close']
        
        # 计算+DM和-DM
        high_diff = high.diff()
        low_diff = -low.diff()
        
        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)
        
        # 计算TR (True Range)
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
        
        # 平滑处理
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (pd.Series(plus_dm).rolling(window=period).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm).rolling(window=period).mean() / atr)
        
        # 计算DX和ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        df['adx'] = adx
        df['di_plus'] = plus_di
        df['di_minus'] = minus_di
        
        return df
    
    @staticmethod
    def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, 
                            d_period: int = 3) -> pd.DataFrame:
        """
        计算Stochastic (随机指标) - 超买超卖指标
        
        解读：
        - %K > 80: 超买
        - %K < 20: 超卖
        - %K上穿%D: 买入信号
        - %K下穿%D: 卖出信号
        
        Returns:
            添加了 stoch_k, stoch_d 列的DataFrame
        """
        high = df['high']
        low = df['low']
        close = df['close']
        
        # 计算%K
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        
        stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        
        # 计算%D (对%K的移动平均)
        stoch_d = stoch_k.rolling(window=d_period).mean()
        
        df['stoch_k'] = stoch_k
        df['stoch_d'] = stoch_d
        
        return df
    
    @staticmethod
    def calculate_obv(df: pd.DataFrame) -> pd.DataFrame:
        """
        计算OBV (On Balance Volume) - 能量潮指标
        
        OBV上升表示买盘积极，下降表示卖盘积极
        结合价格走势判断背离
        
        Returns:
            添加了 obv 列的DataFrame
        """
        close = df['close']
        volume = df['volume']
        
        obv = [0]
        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i-1]:
                obv.append(obv[-1] + volume.iloc[i])
            elif close.iloc[i] < close.iloc[i-1]:
                obv.append(obv[-1] - volume.iloc[i])
            else:
                obv.append(obv[-1])
        
        df['obv'] = obv
        
        return df
    
    @staticmethod
    def calculate_williams_r(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        计算Williams %R - 动量指标
        
        解读：
        - > -20: 超买
        - < -80: 超卖
        - 范围: -100 到 0
        
        Returns:
            添加了 williams_r 列的DataFrame
        """
        high = df['high']
        low = df['low']
        close = df['close']
        
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        
        williams_r = -100 * (highest_high - close) / (highest_high - lowest_low)
        
        df['williams_r'] = williams_r
        
        return df
    
    @staticmethod
    def calculate_cci(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """
        计算CCI (Commodity Channel Index) - 商品通道指标
        
        解读：
        - > +100: 超买
        - < -100: 超卖
        - 穿越±100: 趋势信号
        
        Returns:
            添加了 cci 列的DataFrame
        """
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        sma = typical_price.rolling(window=period).mean()
        mad = typical_price.rolling(window=period).apply(
            lambda x: np.abs(x - x.mean()).mean()
        )
        
        cci = (typical_price - sma) / (0.015 * mad)
        
        df['cci'] = cci
        
        return df
    
    @staticmethod
    def calculate_volatility_metrics(df: pd.DataFrame, 
                                     period: int = 20) -> pd.DataFrame:
        """
        计算波动率相关指标
        
        Returns:
            添加了以下列：
            - volatility: 历史波动率
            - volatility_percentile: 波动率百分位
            - price_range_pct: 价格振幅百分比
        """
        returns = df['close'].pct_change()
        
        # 历史波动率 (年化)
        volatility = returns.rolling(window=period).std() * np.sqrt(365 * 24 * 4)  # 15分钟K线
        
        # 波动率百分位 (过去100期)
        volatility_percentile = volatility.rolling(window=100).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100
        )
        
        # 价格振幅百分比
        price_range_pct = (df['high'] - df['low']) / df['close'] * 100
        
        df['volatility'] = volatility
        df['volatility_percentile'] = volatility_percentile
        df['price_range_pct'] = price_range_pct
        
        return df
    
    @staticmethod
    def identify_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
        """
        识别K线形态
        
        Returns:
            添加了 pattern 列，值为识别出的形态名称
        """
        open_price = df['open']
        high = df['high']
        low = df['low']
        close = df['close']
        
        body = abs(close - open_price)
        upper_shadow = high - pd.concat([close, open_price], axis=1).max(axis=1)
        lower_shadow = pd.concat([close, open_price], axis=1).min(axis=1) - low
        
        patterns = []
        
        for i in range(len(df)):
            pattern = 'none'
            
            if i > 0:
                # 锤子线 (看涨反转)
                if (lower_shadow.iloc[i] > body.iloc[i] * 2 and 
                    upper_shadow.iloc[i] < body.iloc[i] * 0.1):
                    pattern = 'hammer'
                
                # 射击之星 (看跌反转)
                elif (upper_shadow.iloc[i] > body.iloc[i] * 2 and 
                      lower_shadow.iloc[i] < body.iloc[i] * 0.1):
                    pattern = 'shooting_star'
                
                # 吞没形态
                elif (body.iloc[i] > body.iloc[i-1] * 1.5 and
                      close.iloc[i] > open_price.iloc[i] and
                      close.iloc[i-1] < open_price.iloc[i-1]):
                    pattern = 'bullish_engulfing'
                
                elif (body.iloc[i] > body.iloc[i-1] * 1.5 and
                      close.iloc[i] < open_price.iloc[i] and
                      close.iloc[i-1] > open_price.iloc[i-1]):
                    pattern = 'bearish_engulfing'
                
                # 十字星 (犹豫)
                elif body.iloc[i] < (high.iloc[i] - low.iloc[i]) * 0.1:
                    pattern = 'doji'
            
            patterns.append(pattern)
        
        df['candlestick_pattern'] = patterns
        
        return df
    
    @staticmethod
    def calculate_trend_strength(df: pd.DataFrame) -> pd.DataFrame:
        """
        计算综合趋势强度评分
        
        基于多个指标综合评估：
        - ADX (趋势强度)
        - 价格与均线关系
        - MACD方向
        - RSI动量
        
        Returns:
            添加了 trend_strength 列 (0-100)
        """
        score = pd.Series(0.0, index=df.index)
        
        # ADX贡献 (30分)
        if 'adx' in df.columns:
            adx_score = np.clip(df['adx'] / 50 * 30, 0, 30)
            score += adx_score
        
        # 价格与均线关系 (25分)
        if 'ema_50' in df.columns:
            price_above_ema = (df['close'] > df['ema_50']).astype(int) * 25
            score += price_above_ema
        
        # MACD方向 (25分)
        if 'macd_hist' in df.columns:
            macd_positive = (df['macd_hist'] > 0).astype(int) * 25
            score += macd_positive
        
        # RSI动量 (20分)
        if 'rsi' in df.columns:
            rsi_momentum = np.where(
                df['rsi'] > 50,
                (df['rsi'] - 50) / 50 * 20,
                (50 - df['rsi']) / 50 * 20
            )
            score += rsi_momentum
        
        df['trend_strength'] = np.clip(score, 0, 100)
        
        return df
    
    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有高级指标
        
        Args:
            df: 包含OHLCV数据的DataFrame
            
        Returns:
            添加了所有指标列的DataFrame
        """
        df = AdvancedIndicators.calculate_adx(df)
        df = AdvancedIndicators.calculate_stochastic(df)
        df = AdvancedIndicators.calculate_obv(df)
        df = AdvancedIndicators.calculate_williams_r(df)
        df = AdvancedIndicators.calculate_cci(df)
        df = AdvancedIndicators.calculate_volatility_metrics(df)
        df = AdvancedIndicators.identify_candlestick_patterns(df)
        df = AdvancedIndicators.calculate_trend_strength(df)
        
        return df


def enhance_market_data_with_advanced_indicators(market_data: Dict) -> Dict:
    """
    为市场数据添加高级指标的简化版本（用于回测）
    
    Args:
        market_data: 包含15m/1h/4h数据的字典
        
    Returns:
        增强后的market_data
    """
    for timeframe in ['15m', '1h', '4h']:
        if timeframe in market_data and market_data[timeframe]:
            data = market_data[timeframe]
            
            # 添加一些可以从单根K线计算的指标
            # 价格振幅
            if 'high' in data and 'low' in data and 'close' in data:
                data['price_range_pct'] = (data['high'] - data['low']) / data['close'] * 100
            
            # K线实体大小
            if 'open' in data and 'close' in data:
                data['body_pct'] = abs(data['close'] - data['open']) / data['open'] * 100
                data['is_bullish'] = 1 if data['close'] > data['open'] else 0
    
    return market_data


if __name__ == "__main__":
    # 测试示例
    print("高级技术指标模块已加载")
    print("\n支持的指标:")
    print("  - ADX (趋势强度)")
    print("  - Stochastic (超买超卖)")
    print("  - OBV (能量潮)")
    print("  - Williams %R (动量)")
    print("  - CCI (通道指标)")
    print("  - 波动率指标")
    print("  - K线形态识别")
    print("  - 综合趋势强度")




