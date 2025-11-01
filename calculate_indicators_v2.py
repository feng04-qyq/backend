"""
技术指标计算脚本 V2
支持使用清洗后的数据
计算多种技术指标：EMA云带、SuperTrend、Ichimoku、ADX、RSI、StochRSI、
MACD、AO、Momentum、Pivot Points、OBV、VWAP等
"""

import pandas as pd
import numpy as np
import os
import json
from datetime import datetime

class TechnicalIndicators:
    """技术指标计算类"""
    
    def __init__(self, df):
        """
        初始化
        df: DataFrame，需要包含列：开盘价, 最高价, 最低价, 收盘价, 成交量
        """
        self.df = df.copy()
        self._prepare_data()
    
    def _prepare_data(self):
        """准备数据，转换为英文列名"""
        column_mapping = {
            '开盘价': 'open',
            '最高价': 'high',
            '最低价': 'low',
            '收盘价': 'close',
            '成交量': 'volume',
            # 支持清洗后的列名
            'open_time': 'open_time',
            'close_time': 'close_time'
        }
        
        # 重命名列
        for old_name, new_name in column_mapping.items():
            if old_name in self.df.columns and old_name != new_name:
                self.df.rename(columns={old_name: new_name}, inplace=True)
        
        # 确保数值类型
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
    
    # ==================== EMA相关 ====================
    
    def calculate_ema(self, period):
        """计算EMA（指数移动平均）"""
        return self.df['close'].ewm(span=period, adjust=False).mean()
    
    def calculate_ema_cloud(self, periods=[8, 13, 21, 34, 55, 89]):
        """计算多周期EMA云带"""
        for period in periods:
            self.df[f'EMA_{period}'] = self.calculate_ema(period)
        return self.df
    
    # ==================== SuperTrend ====================
    
    def calculate_atr(self, period=10):
        """计算ATR（平均真实波幅）"""
        high = self.df['high']
        low = self.df['low']
        close = self.df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(span=period, adjust=False).mean()
        
        return atr
    
    def calculate_supertrend(self, period=10, multiplier=3):
        """计算SuperTrend指标 - 优化版"""
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
        dir = direction.values
        
        # 优化循环（使用numpy数组访问更快）
        for i in range(1, len(self.df)):
            # 确定方向
            if close[i] > st[i-1]:
                dir[i] = 1
            elif close[i] < st[i-1]:
                dir[i] = -1
            else:
                dir[i] = dir[i-1]
            
            # 计算SuperTrend值
            if dir[i] == 1:
                st[i] = max(lower[i], st[i-1]) if dir[i-1] == 1 else lower[i]
            else:
                st[i] = min(upper[i], st[i-1]) if dir[i-1] == -1 else upper[i]
        
        self.df['SuperTrend'] = st
        self.df['SuperTrend_Direction'] = dir
        self.df['SuperTrend_Upper'] = upper_band
        self.df['SuperTrend_Lower'] = lower_band
        
        return self.df
    
    # ==================== Ichimoku云 ====================
    
    def calculate_ichimoku(self):
        """计算Ichimoku云指标"""
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
    
    def calculate_adx(self, period=14):
        """计算ADX（平均趋向指数）- 修正版"""
        high = self.df['high']
        low = self.df['low']
        close = self.df['close']
        
        # 计算+DM和-DM（修正逻辑）
        high_diff = high.diff()
        low_diff = -low.diff()
        
        # +DM: 当前高点-前高点 > 前低点-当前低点 且 > 0
        plus_dm = pd.Series(0.0, index=self.df.index)
        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
        
        # -DM: 前低点-当前低点 > 当前高点-前高点 且 > 0
        minus_dm = pd.Series(0.0, index=self.df.index)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)
        
        # 计算TR（真实波幅）
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
        
        # Wilder平滑（更准确的平滑方法）
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
        
        # 避免除以0
        di_sum = plus_di + minus_di
        di_sum = di_sum.replace(0, np.nan)
        
        # 计算DX
        dx = 100 * abs(plus_di - minus_di) / di_sum
        
        # 平滑DX得到ADX
        adx = pd.Series(0.0, index=self.df.index)
        adx.iloc[period-1] = dx.iloc[period:period*2].mean()
        for i in range(period*2, len(self.df)):
            adx.iloc[i] = adx.iloc[i-1] * (1 - alpha) + dx.iloc[i] * alpha
        
        self.df['ADX'] = adx
        self.df['ADX_PlusDI'] = plus_di
        self.df['ADX_MinusDI'] = minus_di
        
        return self.df
    
    # ==================== RSI ====================
    
    def calculate_rsi(self, period=14):
        """计算RSI（相对强弱指数）"""
        delta = self.df['close'].diff()
        
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        self.df['RSI'] = rsi
        
        return self.df
    
    # ==================== StochRSI ====================
    
    def calculate_stoch_rsi(self, rsi_period=14, stoch_period=14, k_period=3, d_period=3):
        """
        计算StochRSI - 修正版
        rsi_period: RSI计算周期
        stoch_period: Stochastic计算周期
        k_period: K线平滑周期
        d_period: D线平滑周期
        """
        if 'RSI' not in self.df.columns:
            self.calculate_rsi(rsi_period)
        
        rsi = self.df['RSI']
        
        # 计算RSI的最高最低
        rsi_min = rsi.rolling(window=stoch_period, min_periods=1).min()
        rsi_max = rsi.rolling(window=stoch_period, min_periods=1).max()
        
        # 避免除以0
        rsi_range = rsi_max - rsi_min
        rsi_range = rsi_range.replace(0, np.nan)
        
        # 计算StochRSI原始值
        stoch_rsi_raw = (rsi - rsi_min) / rsi_range
        
        # K线：对StochRSI进行简单移动平均（SMA）平滑
        stoch_rsi_k = stoch_rsi_raw.rolling(window=k_period, min_periods=1).mean() * 100
        
        # D线：对K线进行简单移动平均（SMA）平滑
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=1).mean()
        
        self.df['StochRSI'] = stoch_rsi_raw * 100  # 原始StochRSI值
        self.df['StochRSI_K'] = stoch_rsi_k  # K线（%K）
        self.df['StochRSI_D'] = stoch_rsi_d  # D线（%D）
        
        return self.df
    
    # ==================== MACD ====================
    
    def calculate_macd(self, fast=12, slow=26, signal=9):
        """计算MACD"""
        ema_fast = self.df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = self.df['close'].ewm(span=slow, adjust=False).mean()
        
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        histogram = (macd - signal_line) * 2
        
        self.df['MACD'] = macd
        self.df['MACD_Signal'] = signal_line
        self.df['MACD_Histogram'] = histogram
        
        return self.df
    
    # ==================== Awesome Oscillator ====================
    
    def calculate_ao(self, fast=5, slow=34):
        """计算Awesome Oscillator（AO）"""
        median_price = (self.df['high'] + self.df['low']) / 2
        
        ao = median_price.rolling(window=fast).mean() - median_price.rolling(window=slow).mean()
        
        self.df['AO'] = ao
        
        return self.df
    
    # ==================== Momentum ====================
    
    def calculate_momentum(self, period=10):
        """计算动量指标"""
        momentum = self.df['close'] - self.df['close'].shift(period)
        
        self.df['Momentum'] = momentum
        
        return self.df
    
    # ==================== Pivot Points ====================
    
    def calculate_pivot_points(self):
        """计算枢轴点"""
        # 使用前一根K线的高低收
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
    
    def calculate_obv(self):
        """计算OBV（能量潮）- 向量化优化版"""
        # 计算价格变化方向
        close_diff = self.df['close'].diff()
        
        # 根据价格变化决定成交量的符号
        # 上涨: +volume, 下跌: -volume, 持平: 0
        volume_signed = np.where(close_diff > 0, self.df['volume'],
                                np.where(close_diff < 0, -self.df['volume'], 0))
        
        # 累加得到OBV
        obv = pd.Series(volume_signed, index=self.df.index).cumsum()
        
        self.df['OBV'] = obv
        
        return self.df
    
    # ==================== VWAP ====================
    
    def calculate_vwap(self, period=None):
        """
        计算VWAP（成交量加权平均价）- 改进版
        period: 如果指定，计算滚动VWAP；如果为None，计算累积VWAP
        """
        # 典型价格（HLC/3是最常用的，也可以用OHLC/4或HL/2）
        # HLC/3: 更重视收盘价
        typical_price = (self.df['high'] + self.df['low'] + self.df['close']) / 3.0
        
        # 计算价格*成交量
        pv = typical_price * self.df['volume']
        
        if period is None:
            # 累积VWAP（从开始累积）
            vwap = pv.cumsum() / self.df['volume'].cumsum()
        else:
            # 滚动VWAP（指定周期）
            vwap = pv.rolling(window=period, min_periods=1).sum() / \
                   self.df['volume'].rolling(window=period, min_periods=1).sum()
        
        # 处理成交量为0的情况
        vwap = vwap.replace([np.inf, -np.inf], np.nan)
        
        self.df['VWAP'] = vwap
        self.df['Typical_Price'] = typical_price  # 也保存典型价格供参考
        
        # 如果有日期索引，可以计算每日VWAP
        if isinstance(self.df.index, pd.DatetimeIndex):
            daily_pv = pv.groupby(self.df.index.date).cumsum()
            daily_volume = self.df['volume'].groupby(self.df.index.date).cumsum()
            self.df['VWAP_Daily'] = daily_pv / daily_volume
        
        return self.df
    
    # ==================== 供需区域识别 ====================
    
    def identify_supply_demand_zones(self, lookback=20, volume_threshold=1.5):
        """
        识别供给和需求区域
        lookback: 回溯周期
        volume_threshold: 成交量阈值（相对于平均成交量的倍数）
        """
        avg_volume = self.df['volume'].rolling(window=lookback).mean()
        
        # 识别大成交量K线
        high_volume = self.df['volume'] > (avg_volume * volume_threshold)
        
        # 识别价格大幅上涨（需求区）
        price_rise = (self.df['close'] - self.df['open']) / self.df['open'] > 0.02
        
        # 识别价格大幅下跌（供给区）
        price_fall = (self.df['open'] - self.df['close']) / self.df['open'] > 0.02
        
        # 需求区域
        demand_zone = high_volume & price_rise
        
        # 供给区域
        supply_zone = high_volume & price_fall
        
        self.df['Demand_Zone'] = demand_zone.astype(int)
        self.df['Supply_Zone'] = supply_zone.astype(int)
        
        # 标记区域价格范围
        self.df['Demand_Zone_Low'] = np.where(demand_zone, self.df['low'], np.nan)
        self.df['Demand_Zone_High'] = np.where(demand_zone, self.df['high'], np.nan)
        self.df['Supply_Zone_Low'] = np.where(supply_zone, self.df['low'], np.nan)
        self.df['Supply_Zone_High'] = np.where(supply_zone, self.df['high'], np.nan)
        
        return self.df
    
    # ==================== 综合计算 ====================
    
    def calculate_all_indicators(self):
        """计算所有技术指标"""
        print("  计算EMA云带...")
        self.calculate_ema_cloud([8, 13, 21, 34, 55, 89])
        
        print("  计算SuperTrend...")
        self.calculate_supertrend()
        
        print("  计算Ichimoku云...")
        self.calculate_ichimoku()
        
        print("  计算ADX...")
        self.calculate_adx()
        
        print("  计算RSI...")
        self.calculate_rsi()
        
        print("  计算StochRSI...")
        self.calculate_stoch_rsi()
        
        print("  计算MACD...")
        self.calculate_macd()
        
        print("  计算AO...")
        self.calculate_ao()
        
        print("  计算Momentum...")
        self.calculate_momentum()
        
        print("  计算Pivot Points...")
        self.calculate_pivot_points()
        
        print("  计算OBV...")
        self.calculate_obv()
        
        print("  计算VWAP...")
        self.calculate_vwap()
        
        print("  识别供需区域...")
        self.identify_supply_demand_zones()
        
        return self.df


def process_file(input_file, output_file):
    """处理单个文件，计算所有指标"""
    print(f"\n处理文件: {os.path.basename(input_file)}")
    
    try:
        # 读取数据
        df = pd.read_csv(input_file, encoding='utf-8')
        
        # 处理时间列（支持不同的列名）
        time_cols = ['开盘时间', 'open_time']
        for time_col in time_cols:
            if time_col in df.columns:
                if not isinstance(df.index, pd.DatetimeIndex):
                    df[time_col] = pd.to_datetime(df[time_col])
                    df.set_index(time_col, inplace=True)
                break
        
        print(f"  数据条数: {len(df)}")
        
        # 计算指标
        ti = TechnicalIndicators(df)
        result_df = ti.calculate_all_indicators()
        
        # 保存结果
        result_df.to_csv(output_file, encoding='utf-8')
        print(f"✓ 指标已保存到: {output_file}")
        
        # 返回统计信息
        indicator_count = len([col for col in result_df.columns if col not in ['open', 'high', 'low', 'close', 'volume', 'open_time', 'close_time', 'quote_volume', 'trades']])
        
        return {
            'file': os.path.basename(input_file),
            'records': int(len(result_df)),
            'indicators': int(indicator_count),
            'status': 'success'
        }
        
    except Exception as e:
        print(f"✗ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            'file': os.path.basename(input_file),
            'records': 0,
            'indicators': 0,
            'status': f'failed: {str(e)}'
        }


def main():
    """主函数"""
    print("="*70)
    print("技术指标计算工具 V2")
    print("="*70)
    
    # 检查可用的数据源
    original_dir = "klines_data"
    cleaned_dir = "klines_data_cleaned"
    
    has_original = os.path.exists(original_dir) and len([f for f in os.listdir(original_dir) if f.endswith('.csv') and 'PERPETUAL' in f]) > 0
    has_cleaned = os.path.exists(cleaned_dir) and len([f for f in os.listdir(cleaned_dir) if f.endswith('.csv') and 'PERPETUAL' in f]) > 0
    
    # 选择数据源
    if has_cleaned:
        print("\n✓ 检测到清洗后的数据！")
        print("  1. 使用清洗后的数据（推荐，质量更高）")
        if has_original:
            print("  2. 使用原始数据")
        
        choice = input("\n请选择数据源（直接回车使用清洗后的数据）: ").strip()
        
        if choice == '2' and has_original:
            data_dir = original_dir
            output_suffix = ""
            print(f"\n使用原始数据: {data_dir}")
        else:
            data_dir = cleaned_dir
            output_suffix = "_from_cleaned"
            print(f"\n✓ 使用清洗后的数据: {data_dir}")
    elif has_original:
        data_dir = original_dir
        output_suffix = ""
        print(f"\n使用原始数据: {data_dir}")
        print("💡 提示: 运行 clean_klines_data.py 可以清洗数据以获得更好的质量")
    else:
        print("\n错误: 没有找到数据文件")
        print("请先运行 fetch_klines_advanced.py 获取数据")
        return
    
    # 设置输出目录
    if output_suffix:
        output_dir = f"klines_data_with_indicators{output_suffix}"
    else:
        output_dir = "klines_data_with_indicators"
    
    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 查找所有CSV文件
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv') and 'PERPETUAL' in f]
    
    if not csv_files:
        print(f"错误: {data_dir} 中没有找到K线数据文件")
        return
    
    print(f"\n找到 {len(csv_files)} 个数据文件")
    print(f"输出目录: {output_dir}\n")
    
    results = []
    
    for i, csv_file in enumerate(csv_files, 1):
        print(f"\n[{i}/{len(csv_files)}]")
        input_path = os.path.join(data_dir, csv_file)
        output_path = os.path.join(output_dir, csv_file)
        
        result = process_file(input_path, output_path)
        results.append(result)
    
    # 保存处理报告
    report = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'data_source': data_dir,
        'total_files': len(csv_files),
        'successful': sum(1 for r in results if r['status'] == 'success'),
        'failed': sum(1 for r in results if r['status'] != 'success'),
        'results': results
    }
    
    report_file = os.path.join(output_dir, 'indicators_report.json')
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # 显示总结
    print("\n" + "="*70)
    print("处理完成！")
    print("="*70)
    print(f"数据源: {data_dir}")
    print(f"成功: {report['successful']}/{report['total_files']}")
    print(f"输出目录: {output_dir}")
    print(f"报告文件: {report_file}")
    print("="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()

