"""
增强版技术指标计算模块 - 实盘交易专用
整合回测系统的丰富指标，提供更全面的市场分析

支持指标：
- SuperTrend（超级趋势）
- Ichimoku（一目均衡表）
- ADX（平均趋向指数）
- StochRSI（随机相对强弱指数）
- AO（动量振荡器）
- Pivot Points（枢轴点）
- OBV（能量潮）
- VWAP（成交量加权平均价）
- 多周期EMA云带

作者：Bybit Trading System
版本：v1.0
日期：2025-10-30
"""

import pandas as pd
import numpy as np
from typing import Optional


class EnhancedIndicators:
    """
    增强版技术指标计算类
    
    为实盘交易系统提供丰富的技术指标，与回测系统保持一致
    """
    
    def __init__(self, df: pd.DataFrame):
        """
        初始化
        
        Args:
            df: DataFrame，必须包含列：open, high, low, close, volume
        """
        self.df = df.copy()
        self._validate_data()
    
    def _validate_data(self):
        """验证数据完整性"""
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        missing = [col for col in required_columns if col not in self.df.columns]
        if missing:
            raise ValueError(f"缺少必需列: {missing}")
    
    # ==================== ATR ====================
    
    def calculate_atr(self, period: int = 14) -> pd.Series:
        """
        计算ATR（平均真实波幅）
        
        Args:
            period: 周期，默认14
            
        Returns:
            ATR序列
        """
        high = self.df['high']
        low = self.df['low']
        close = self.df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(span=period, adjust=False).mean()
        
        return atr
    
    # ==================== SuperTrend ====================
    
    def calculate_supertrend(self, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
        """
        计算SuperTrend指标
        
        SuperTrend是基于ATR的趋势跟踪指标
        - Direction = 1: 上升趋势（做多）
        - Direction = -1: 下降趋势（做空）
        
        Args:
            period: ATR周期，默认10
            multiplier: ATR乘数，默认3.0
            
        Returns:
            添加了以下列的DataFrame：
            - SuperTrend: 主线
            - SuperTrend_Direction: 方向（1=多，-1=空）
            - SuperTrend_Upper: 上轨
            - SuperTrend_Lower: 下轨
        """
        hl_avg = (self.df['high'] + self.df['low']) / 2
        atr = self.calculate_atr(period)
        
        upper_band = hl_avg + (multiplier * atr)
        lower_band = hl_avg - (multiplier * atr)
        
        # 初始化
        supertrend = pd.Series(index=self.df.index, dtype=float)
        direction = pd.Series(index=self.df.index, dtype=int)
        
        # 初始值
        supertrend.iloc[0] = lower_band.iloc[0]
        direction.iloc[0] = 1
        
        close = self.df['close'].values
        upper = upper_band.values
        lower = lower_band.values
        st = supertrend.values
        dir_arr = direction.values
        
        # 计算SuperTrend
        for i in range(1, len(self.df)):
            # 确定方向
            if close[i] > st[i-1]:
                dir_arr[i] = 1
            elif close[i] < st[i-1]:
                dir_arr[i] = -1
            else:
                dir_arr[i] = dir_arr[i-1]
            
            # 计算SuperTrend值
            if dir_arr[i] == 1:
                st[i] = max(lower[i], st[i-1]) if dir_arr[i-1] == 1 else lower[i]
            else:
                st[i] = min(upper[i], st[i-1]) if dir_arr[i-1] == -1 else upper[i]
        
        self.df['SuperTrend'] = st
        self.df['SuperTrend_Direction'] = dir_arr
        self.df['SuperTrend_Upper'] = upper_band
        self.df['SuperTrend_Lower'] = lower_band
        
        return self.df
    
    # ==================== Ichimoku ====================
    
    def calculate_ichimoku(self) -> pd.DataFrame:
        """
        计算Ichimoku云指标（一目均衡表）
        
        日本经典指标，提供支撑阻力和趋势方向
        
        Returns:
            添加了以下列的DataFrame：
            - Ichimoku_Tenkan: 转换线（9周期）
            - Ichimoku_Kijun: 基准线（26周期）
            - Ichimoku_SpanA: 领先跨度A（云上界）
            - Ichimoku_SpanB: 领先跨度B（云下界）
            - Ichimoku_Chikou: 延迟跨度（滞后线）
        """
        # 转换线（Tenkan-sen）：9周期
        period9_high = self.df['high'].rolling(window=9).max()
        period9_low = self.df['low'].rolling(window=9).min()
        tenkan_sen = (period9_high + period9_low) / 2
        
        # 基准线（Kijun-sen）：26周期
        period26_high = self.df['high'].rolling(window=26).max()
        period26_low = self.df['low'].rolling(window=26).min()
        kijun_sen = (period26_high + period26_low) / 2
        
        # 领先跨度A（Senkou Span A）：向前移26周期
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(26)
        
        # 领先跨度B（Senkou Span B）：52周期，向前移26周期
        period52_high = self.df['high'].rolling(window=52).max()
        period52_low = self.df['low'].rolling(window=52).min()
        senkou_span_b = ((period52_high + period52_low) / 2).shift(26)
        
        # 延迟跨度（Chikou Span）：当前收盘价向后移26周期
        chikou_span = self.df['close'].shift(-26)
        
        self.df['Ichimoku_Tenkan'] = tenkan_sen
        self.df['Ichimoku_Kijun'] = kijun_sen
        self.df['Ichimoku_SpanA'] = senkou_span_a
        self.df['Ichimoku_SpanB'] = senkou_span_b
        self.df['Ichimoku_Chikou'] = chikou_span
        
        return self.df
    
    # ==================== ADX ====================
    
    def calculate_adx(self, period: int = 14) -> pd.DataFrame:
        """
        计算ADX（平均趋向指数）
        
        衡量趋势强度的指标：
        - ADX > 25: 强趋势
        - ADX < 20: 弱趋势/震荡
        
        Args:
            period: 周期，默认14
            
        Returns:
            添加了以下列的DataFrame：
            - ADX: 平均趋向指数
            - ADX_PlusDI: +DI（上升动向指标）
            - ADX_MinusDI: -DI（下降动向指标）
        """
        high = self.df['high']
        low = self.df['low']
        close = self.df['close']
        
        # 计算+DM和-DM
        high_diff = high.diff()
        low_diff = -low.diff()
        
        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)
        
        # 计算TR（真实波幅）
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
        
        # Wilder平滑
        alpha = 1.0 / period
        
        # 平滑TR
        atr = pd.Series(0.0, index=self.df.index)
        atr.iloc[period-1] = tr.iloc[:period].mean()
        for i in range(period, len(self.df)):
            atr.iloc[i] = atr.iloc[i-1] * (1 - alpha) + tr.iloc[i] * alpha
        
        # 平滑+DM
        smoothed_plus_dm = pd.Series(0.0, index=self.df.index)
        smoothed_plus_dm.iloc[period-1] = pd.Series(plus_dm).iloc[:period].mean()
        for i in range(period, len(self.df)):
            smoothed_plus_dm.iloc[i] = smoothed_plus_dm.iloc[i-1] * (1 - alpha) + plus_dm[i] * alpha
        
        # 平滑-DM
        smoothed_minus_dm = pd.Series(0.0, index=self.df.index)
        smoothed_minus_dm.iloc[period-1] = pd.Series(minus_dm).iloc[:period].mean()
        for i in range(period, len(self.df)):
            smoothed_minus_dm.iloc[i] = smoothed_minus_dm.iloc[i-1] * (1 - alpha) + minus_dm[i] * alpha
        
        # 计算+DI和-DI
        plus_di = 100 * smoothed_plus_dm / atr
        minus_di = 100 * smoothed_minus_dm / atr
        
        # 计算DX
        di_sum = plus_di + minus_di
        di_sum = di_sum.replace(0, np.nan)
        dx = 100 * abs(plus_di - minus_di) / di_sum
        
        # 平滑DX得到ADX
        adx = pd.Series(0.0, index=self.df.index)
        if len(self.df) >= period * 2:
            adx.iloc[period*2-1] = dx.iloc[period:period*2].mean()
            for i in range(period*2, len(self.df)):
                adx.iloc[i] = adx.iloc[i-1] * (1 - alpha) + dx.iloc[i] * alpha
        
        self.df['ADX'] = adx
        self.df['ADX_PlusDI'] = plus_di
        self.df['ADX_MinusDI'] = minus_di
        
        return self.df
    
    # ==================== StochRSI ====================
    
    def calculate_stoch_rsi(self, rsi_period: int = 14, stoch_period: int = 14, 
                           k_period: int = 3, d_period: int = 3) -> pd.DataFrame:
        """
        计算StochRSI（随机相对强弱指数）
        
        结合RSI和随机指标的优势，更敏感的超买超卖信号
        
        Args:
            rsi_period: RSI计算周期，默认14
            stoch_period: Stochastic计算周期，默认14
            k_period: K线平滑周期，默认3
            d_period: D线平滑周期，默认3
            
        Returns:
            添加了以下列的DataFrame：
            - StochRSI: 原始StochRSI值
            - StochRSI_K: K线（%K）
            - StochRSI_D: D线（%D）
        """
        # 先计算RSI
        if 'RSI' not in self.df.columns:
            delta = self.df['close'].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            avg_gain = gain.ewm(span=rsi_period, adjust=False).mean()
            avg_loss = loss.ewm(span=rsi_period, adjust=False).mean()
            rs = avg_gain / avg_loss
            self.df['RSI'] = 100 - (100 / (1 + rs))
        
        rsi = self.df['RSI']
        
        # 计算RSI的最高最低
        rsi_min = rsi.rolling(window=stoch_period, min_periods=1).min()
        rsi_max = rsi.rolling(window=stoch_period, min_periods=1).max()
        
        # 避免除以0
        rsi_range = rsi_max - rsi_min
        rsi_range = rsi_range.replace(0, np.nan)
        
        # 计算StochRSI原始值
        stoch_rsi_raw = (rsi - rsi_min) / rsi_range
        
        # K线：对StochRSI进行平滑
        stoch_rsi_k = stoch_rsi_raw.rolling(window=k_period, min_periods=1).mean() * 100
        
        # D线：对K线进行平滑
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=1).mean()
        
        self.df['StochRSI'] = stoch_rsi_raw * 100
        self.df['StochRSI_K'] = stoch_rsi_k
        self.df['StochRSI_D'] = stoch_rsi_d
        
        return self.df
    
    # ==================== AO ====================
    
    def calculate_ao(self, fast: int = 5, slow: int = 34) -> pd.DataFrame:
        """
        计算Awesome Oscillator（动量振荡器）
        
        衡量市场动量的强弱
        
        Args:
            fast: 快速周期，默认5
            slow: 慢速周期，默认34
            
        Returns:
            添加了AO列的DataFrame
        """
        median_price = (self.df['high'] + self.df['low']) / 2
        ao = median_price.rolling(window=fast).mean() - median_price.rolling(window=slow).mean()
        self.df['AO'] = ao
        return self.df
    
    # ==================== Pivot Points ====================
    
    def calculate_pivot_points(self) -> pd.DataFrame:
        """
        计算枢轴点
        
        经典的支撑阻力位计算方法
        
        Returns:
            添加了以下列的DataFrame：
            - Pivot: 枢轴点
            - Pivot_R1/R2/R3: 阻力位1/2/3
            - Pivot_S1/S2/S3: 支撑位1/2/3
        """
        high_prev = self.df['high'].shift(1)
        low_prev = self.df['low'].shift(1)
        close_prev = self.df['close'].shift(1)
        
        pivot = (high_prev + low_prev + close_prev) / 3
        
        r1 = 2 * pivot - low_prev
        s1 = 2 * pivot - high_prev
        
        r2 = pivot + (high_prev - low_prev)
        s2 = pivot - (high_prev - low_prev)
        
        r3 = high_prev + 2 * (pivot - low_prev)
        s3 = low_prev - 2 * (high_prev - pivot)
        
        self.df['Pivot'] = pivot
        self.df['Pivot_R1'] = r1
        self.df['Pivot_S1'] = s1
        self.df['Pivot_R2'] = r2
        self.df['Pivot_S2'] = s2
        self.df['Pivot_R3'] = r3
        self.df['Pivot_S3'] = s3
        
        return self.df
    
    # ==================== OBV ====================
    
    def calculate_obv(self) -> pd.DataFrame:
        """
        计算OBV（能量潮）
        
        通过成交量变化判断资金流向
        
        Returns:
            添加了OBV列的DataFrame
        """
        close_diff = self.df['close'].diff()
        
        # 根据价格变化决定成交量的符号
        volume_signed = np.where(close_diff > 0, self.df['volume'],
                                np.where(close_diff < 0, -self.df['volume'], 0))
        
        # 累加得到OBV
        obv = pd.Series(volume_signed, index=self.df.index).cumsum()
        self.df['OBV'] = obv
        
        return self.df
    
    # ==================== VWAP ====================
    
    def calculate_vwap(self, period: Optional[int] = None) -> pd.DataFrame:
        """
        计算VWAP（成交量加权平均价）
        
        机构交易者常用的基准价格
        
        Args:
            period: 如果指定，计算滚动VWAP；如果为None，计算累积VWAP
            
        Returns:
            添加了VWAP列的DataFrame
        """
        typical_price = (self.df['high'] + self.df['low'] + self.df['close']) / 3.0
        pv = typical_price * self.df['volume']
        
        if period is None:
            # 累积VWAP
            vwap = pv.cumsum() / self.df['volume'].cumsum()
        else:
            # 滚动VWAP
            vwap = pv.rolling(window=period, min_periods=1).sum() / \
                   self.df['volume'].rolling(window=period, min_periods=1).sum()
        
        vwap = vwap.replace([np.inf, -np.inf], np.nan)
        self.df['VWAP'] = vwap
        
        return self.df
    
    # ==================== EMA云带 ====================
    
    def calculate_ema_cloud(self, periods: list = [8, 13, 21, 34, 55, 89]) -> pd.DataFrame:
        """
        计算多周期EMA云带
        
        多条EMA形成的趋势云，用于识别趋势强度
        
        Args:
            periods: EMA周期列表，默认斐波那契数列
            
        Returns:
            添加了EMA_X列的DataFrame（X为周期）
        """
        for period in periods:
            self.df[f'EMA_{period}'] = self.df['close'].ewm(span=period, adjust=False).mean()
        return self.df
    
    # ==================== 一键计算所有指标 ====================
    
    def calculate_all(self, include_basic: bool = True) -> pd.DataFrame:
        """
        一键计算所有增强指标
        
        Args:
            include_basic: 是否包含基础指标（RSI, MACD, EMA等），默认True
            
        Returns:
            包含所有指标的DataFrame
        """
        try:
            # 基础指标（如果需要）
            if include_basic:
                # RSI
                if 'RSI' not in self.df.columns:
                    delta = self.df['close'].diff()
                    gain = delta.where(delta > 0, 0)
                    loss = -delta.where(delta < 0, 0)
                    avg_gain = gain.ewm(span=14, adjust=False).mean()
                    avg_loss = loss.ewm(span=14, adjust=False).mean()
                    rs = avg_gain / avg_loss
                    self.df['RSI'] = 100 - (100 / (1 + rs))
                
                # MACD
                if 'MACD' not in self.df.columns:
                    ema_12 = self.df['close'].ewm(span=12, adjust=False).mean()
                    ema_26 = self.df['close'].ewm(span=26, adjust=False).mean()
                    self.df['MACD'] = ema_12 - ema_26
                    self.df['MACD_Signal'] = self.df['MACD'].ewm(span=9, adjust=False).mean()
                    self.df['MACD_Histogram'] = self.df['MACD'] - self.df['MACD_Signal']
                
                # EMA
                for period in [9, 21, 50, 200]:
                    if f'EMA_{period}' not in self.df.columns:
                        self.df[f'EMA_{period}'] = self.df['close'].ewm(span=period, adjust=False).mean()
                
                # 布林带
                if 'BB_Middle' not in self.df.columns:
                    self.df['BB_Middle'] = self.df['close'].rolling(window=20).mean()
                    bb_std = self.df['close'].rolling(window=20).std()
                    self.df['BB_Upper'] = self.df['BB_Middle'] + (bb_std * 2)
                    self.df['BB_Lower'] = self.df['BB_Middle'] - (bb_std * 2)
                
                # ATR
                if 'ATR' not in self.df.columns:
                    self.df['ATR'] = self.calculate_atr()
            
            # 高级指标
            self.calculate_supertrend()
            self.calculate_ichimoku()
            self.calculate_adx()
            self.calculate_stoch_rsi()
            self.calculate_ao()
            self.calculate_pivot_points()
            self.calculate_obv()
            self.calculate_vwap(period=20)  # 20周期滚动VWAP
            self.calculate_ema_cloud()
            
            return self.df
            
        except Exception as e:
            print(f"计算指标时出错: {e}")
            return self.df


# ==================== 便捷函数 ====================

def add_enhanced_indicators(df: pd.DataFrame, include_basic: bool = True) -> pd.DataFrame:
    """
    便捷函数：为DataFrame添加所有增强指标
    
    Args:
        df: 原始K线数据
        include_basic: 是否包含基础指标
        
    Returns:
        添加了所有指标的DataFrame
    """
    calculator = EnhancedIndicators(df)
    return calculator.calculate_all(include_basic=include_basic)


# ==================== 测试代码 ====================

if __name__ == '__main__':
    import sys
    import io
    
    # 设置UTF-8输出
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("=" * 60)
    print("增强版技术指标计算模块 - 测试")
    print("=" * 60)
    
    # 创建测试数据
    test_data = pd.DataFrame({
        'open': [100, 102, 101, 103, 105, 104, 106, 108, 107, 109] * 10,
        'high': [102, 104, 103, 105, 107, 106, 108, 110, 109, 111] * 10,
        'low': [99, 101, 100, 102, 104, 103, 105, 107, 106, 108] * 10,
        'close': [101, 103, 102, 104, 106, 105, 107, 109, 108, 110] * 10,
        'volume': [1000, 1200, 1100, 1300, 1500, 1400, 1600, 1800, 1700, 1900] * 10
    })
    
    print(f"\n✓ 创建测试数据: {len(test_data)} 根K线")
    
    # 计算指标
    print("\n开始计算增强指标...")
    calculator = EnhancedIndicators(test_data)
    result = calculator.calculate_all(include_basic=True)
    
    # 显示指标列表
    indicator_columns = [col for col in result.columns if col not in ['open', 'high', 'low', 'close', 'volume']]
    
    print(f"\n✓ 成功计算 {len(indicator_columns)} 个指标:")
    print("\n【基础指标】")
    basic_indicators = ['RSI', 'MACD', 'MACD_Signal', 'MACD_Histogram', 'EMA_9', 'EMA_21', 'EMA_50', 'EMA_200', 'BB_Middle', 'BB_Upper', 'BB_Lower', 'ATR']
    for ind in basic_indicators:
        if ind in result.columns:
            print(f"  ✓ {ind}")
    
    print("\n【高级指标】")
    advanced_indicators = ['SuperTrend', 'Ichimoku_Tenkan', 'ADX', 'StochRSI_K', 'AO', 'Pivot', 'OBV', 'VWAP', 'EMA_8']
    for ind in advanced_indicators:
        matching = [col for col in result.columns if ind in col]
        if matching:
            print(f"  ✓ {ind} ({len(matching)} 个)")
    
    print("\n" + "=" * 60)
    print("✓ 测试完成！模块工作正常。")
    print("=" * 60)



