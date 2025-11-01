"""
K线形态识别模块

识别常见的K线形态，包括：
1. 单根K线形态（锤子线、吞没、十字星等）
2. 多根K线形态（双顶双底、头肩顶底等）
3. 趋势形态（通道、三角形等）
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional

class CandlestickPatternRecognizer:
    """K线形态识别器"""
    
    def __init__(self):
        """初始化"""
        pass
    
    def analyze_patterns(self, df: pd.DataFrame) -> Dict:
        """
        分析K线形态
        
        Args:
            df: 包含OHLC数据的DataFrame
        
        Returns:
            识别到的形态字典
        """
        if len(df) < 10:
            return {'patterns': [], 'description': '数据不足'}
        
        patterns = []
        
        # 1. 单根K线形态
        single_patterns = self._identify_single_candle_patterns(df)
        patterns.extend(single_patterns)
        
        # 2. 双根K线形态
        double_patterns = self._identify_double_candle_patterns(df)
        patterns.extend(double_patterns)
        
        # 3. 三根K线形态
        triple_patterns = self._identify_triple_candle_patterns(df)
        patterns.extend(triple_patterns)
        
        # 4. 趋势形态
        trend_patterns = self._identify_trend_patterns(df)
        patterns.extend(trend_patterns)
        
        # 5. 支撑阻力
        support_resistance = self._identify_support_resistance(df)
        
        return {
            'patterns': patterns,
            'support_resistance': support_resistance,
            'pattern_count': len(patterns),
            'bullish_count': sum(1 for p in patterns if p['type'] == 'bullish'),
            'bearish_count': sum(1 for p in patterns if p['type'] == 'bearish'),
            'description': self._generate_description(patterns)
        }
    
    def _identify_single_candle_patterns(self, df: pd.DataFrame) -> List[Dict]:
        """识别单根K线形态"""
        patterns = []
        
        if len(df) < 3:
            return patterns
        
        # 获取最近的K线
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        open_price = current['open']
        close_price = current['close']
        high_price = current['high']
        low_price = current['low']
        
        body = abs(close_price - open_price)
        total_range = high_price - low_price
        
        if total_range == 0:
            return patterns
        
        body_ratio = body / total_range if total_range > 0 else 0
        
        # 1. 十字星（Doji）
        if body_ratio < 0.1:
            upper_shadow = high_price - max(open_price, close_price)
            lower_shadow = min(open_price, close_price) - low_price
            
            if upper_shadow > body * 2 and lower_shadow > body * 2:
                patterns.append({
                    'name': '十字星',
                    'name_en': 'Doji',
                    'type': 'neutral',
                    'confidence': 0.7,
                    'description': '市场犹豫不决，可能反转'
                })
            elif upper_shadow > body * 3:
                patterns.append({
                    'name': '墓碑十字',
                    'name_en': 'Gravestone Doji',
                    'type': 'bearish',
                    'confidence': 0.75,
                    'description': '顶部反转信号，卖压强'
                })
            elif lower_shadow > body * 3:
                patterns.append({
                    'name': '蜻蜓十字',
                    'name_en': 'Dragonfly Doji',
                    'type': 'bullish',
                    'confidence': 0.75,
                    'description': '底部反转信号，买盘强'
                })
        
        # 2. 锤子线（Hammer）/ 吊颈线（Hanging Man）
        elif body_ratio < 0.3:
            upper_shadow = high_price - max(open_price, close_price)
            lower_shadow = min(open_price, close_price) - low_price
            
            if lower_shadow > body * 2 and upper_shadow < body * 0.3:
                is_bullish = close_price > open_price
                
                # 判断趋势
                prev_trend = self._get_trend(df.iloc[-10:-1])
                
                if prev_trend == 'down':
                    patterns.append({
                        'name': '锤子线',
                        'name_en': 'Hammer',
                        'type': 'bullish',
                        'confidence': 0.8,
                        'description': '下跌趋势中的看涨反转信号'
                    })
                elif prev_trend == 'up':
                    patterns.append({
                        'name': '吊颈线',
                        'name_en': 'Hanging Man',
                        'type': 'bearish',
                        'confidence': 0.75,
                        'description': '上涨趋势中的看跌反转警告'
                    })
        
        # 3. 倒锤子线（Inverted Hammer）/ 射击之星（Shooting Star）
        elif body_ratio < 0.3:
            upper_shadow = high_price - max(open_price, close_price)
            lower_shadow = min(open_price, close_price) - low_price
            
            if upper_shadow > body * 2 and lower_shadow < body * 0.3:
                prev_trend = self._get_trend(df.iloc[-10:-1])
                
                if prev_trend == 'down':
                    patterns.append({
                        'name': '倒锤子线',
                        'name_en': 'Inverted Hammer',
                        'type': 'bullish',
                        'confidence': 0.7,
                        'description': '下跌趋势中的潜在反转'
                    })
                elif prev_trend == 'up':
                    patterns.append({
                        'name': '射击之星',
                        'name_en': 'Shooting Star',
                        'type': 'bearish',
                        'confidence': 0.8,
                        'description': '上涨趋势中的看跌反转信号'
                    })
        
        # 4. 大阳线/大阴线（Marubozu）
        elif body_ratio > 0.9:
            if close_price > open_price:
                patterns.append({
                    'name': '大阳线',
                    'name_en': 'Bullish Marubozu',
                    'type': 'bullish',
                    'confidence': 0.85,
                    'description': '强劲买盘，持续看涨'
                })
            else:
                patterns.append({
                    'name': '大阴线',
                    'name_en': 'Bearish Marubozu',
                    'type': 'bearish',
                    'confidence': 0.85,
                    'description': '强劲卖盘，持续看跌'
                })
        
        # 5. 纺锤线（Spinning Top）
        elif 0.2 < body_ratio < 0.4:
            upper_shadow = high_price - max(open_price, close_price)
            lower_shadow = min(open_price, close_price) - low_price
            
            if upper_shadow > body and lower_shadow > body:
                patterns.append({
                    'name': '纺锤线',
                    'name_en': 'Spinning Top',
                    'type': 'neutral',
                    'confidence': 0.6,
                    'description': '市场不确定，买卖平衡'
                })
        
        return patterns
    
    def _identify_double_candle_patterns(self, df: pd.DataFrame) -> List[Dict]:
        """识别双根K线形态"""
        patterns = []
        
        if len(df) < 3:
            return patterns
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. 吞没形态（Engulfing）
        prev_body = abs(prev['close'] - prev['open'])
        current_body = abs(current['close'] - current['open'])
        
        # 看涨吞没
        if (prev['close'] < prev['open'] and  # 前一根是阴线
            current['close'] > current['open'] and  # 当前是阳线
            current['open'] <= prev['close'] and  # 当前开盘低于前收盘
            current['close'] > prev['open'] and  # 当前收盘高于前开盘
            current_body > prev_body * 1.2):  # 实体更大
            
            patterns.append({
                'name': '看涨吞没',
                'name_en': 'Bullish Engulfing',
                'type': 'bullish',
                'confidence': 0.85,
                'description': '强烈的反转信号，多头力量强'
            })
        
        # 看跌吞没
        elif (prev['close'] > prev['open'] and  # 前一根是阳线
              current['close'] < current['open'] and  # 当前是阴线
              current['open'] >= prev['close'] and  # 当前开盘高于前收盘
              current['close'] < prev['open'] and  # 当前收盘低于前开盘
              current_body > prev_body * 1.2):  # 实体更大
            
            patterns.append({
                'name': '看跌吞没',
                'name_en': 'Bearish Engulfing',
                'type': 'bearish',
                'confidence': 0.85,
                'description': '强烈的反转信号，空头力量强'
            })
        
        # 2. 刺透形态（Piercing）/ 乌云盖顶（Dark Cloud Cover）
        prev_range = prev['high'] - prev['low']
        current_range = current['high'] - current['low']
        
        # 刺透形态
        if (prev['close'] < prev['open'] and  # 前一根是阴线
            current['close'] > current['open'] and  # 当前是阳线
            current['open'] < prev['low'] and  # 跳空低开
            current['close'] > (prev['open'] + prev['close']) / 2 and  # 收盘超过前K线实体一半
            current['close'] < prev['open']):  # 但未完全吞没
            
            patterns.append({
                'name': '刺透形态',
                'name_en': 'Piercing Pattern',
                'type': 'bullish',
                'confidence': 0.8,
                'description': '底部反转信号，买盘强劲'
            })
        
        # 乌云盖顶
        elif (prev['close'] > prev['open'] and  # 前一根是阳线
              current['close'] < current['open'] and  # 当前是阴线
              current['open'] > prev['high'] and  # 跳空高开
              current['close'] < (prev['open'] + prev['close']) / 2 and  # 收盘低于前K线实体一半
              current['close'] > prev['open']):  # 但未完全吞没
            
            patterns.append({
                'name': '乌云盖顶',
                'name_en': 'Dark Cloud Cover',
                'type': 'bearish',
                'confidence': 0.8,
                'description': '顶部反转信号，卖压强劲'
            })
        
        # 3. 孕线（Harami）
        # 看涨孕线
        if (prev['close'] < prev['open'] and  # 前一根是大阴线
            current['close'] > current['open'] and  # 当前是小阳线
            current['open'] > prev['close'] and
            current['close'] < prev['open'] and
            current_body < prev_body * 0.5):
            
            patterns.append({
                'name': '看涨孕线',
                'name_en': 'Bullish Harami',
                'type': 'bullish',
                'confidence': 0.7,
                'description': '可能的底部反转'
            })
        
        # 看跌孕线
        elif (prev['close'] > prev['open'] and  # 前一根是大阳线
              current['close'] < current['open'] and  # 当前是小阴线
              current['open'] < prev['close'] and
              current['close'] > prev['open'] and
              current_body < prev_body * 0.5):
            
            patterns.append({
                'name': '看跌孕线',
                'name_en': 'Bearish Harami',
                'type': 'bearish',
                'confidence': 0.7,
                'description': '可能的顶部反转'
            })
        
        return patterns
    
    def _identify_triple_candle_patterns(self, df: pd.DataFrame) -> List[Dict]:
        """识别三根K线形态"""
        patterns = []
        
        if len(df) < 4:
            return patterns
        
        k1 = df.iloc[-3]
        k2 = df.iloc[-2]
        k3 = df.iloc[-1]
        
        # 1. 三白兵（Three White Soldiers）
        if (k1['close'] > k1['open'] and
            k2['close'] > k2['open'] and
            k3['close'] > k3['open'] and
            k2['close'] > k1['close'] and
            k3['close'] > k2['close'] and
            k2['open'] > k1['open'] and k2['open'] < k1['close'] and
            k3['open'] > k2['open'] and k3['open'] < k2['close']):
            
            patterns.append({
                'name': '三白兵',
                'name_en': 'Three White Soldiers',
                'type': 'bullish',
                'confidence': 0.9,
                'description': '强劲上涨趋势，连续突破'
            })
        
        # 2. 三黑鸦（Three Black Crows）
        elif (k1['close'] < k1['open'] and
              k2['close'] < k2['open'] and
              k3['close'] < k3['open'] and
              k2['close'] < k1['close'] and
              k3['close'] < k2['close'] and
              k2['open'] < k1['open'] and k2['open'] > k1['close'] and
              k3['open'] < k2['open'] and k3['open'] > k2['close']):
            
            patterns.append({
                'name': '三黑鸦',
                'name_en': 'Three Black Crows',
                'type': 'bearish',
                'confidence': 0.9,
                'description': '强劲下跌趋势，连续跌破'
            })
        
        # 3. 晨星（Morning Star）
        k1_is_bearish = k1['close'] < k1['open']
        k2_body = abs(k2['close'] - k2['open'])
        k3_is_bullish = k3['close'] > k3['open']
        
        if (k1_is_bearish and
            k2_body < abs(k1['close'] - k1['open']) * 0.3 and  # 中间是小K线
            k3_is_bullish and
            k3['close'] > (k1['open'] + k1['close']) / 2):  # 收盘超过第一根K线实体一半
            
            patterns.append({
                'name': '晨星',
                'name_en': 'Morning Star',
                'type': 'bullish',
                'confidence': 0.85,
                'description': '底部反转信号，趋势可能转多'
            })
        
        # 4. 暮星（Evening Star）
        k1_is_bullish = k1['close'] > k1['open']
        
        if (k1_is_bullish and
            k2_body < abs(k1['close'] - k1['open']) * 0.3 and  # 中间是小K线
            k3['close'] < k3['open'] and
            k3['close'] < (k1['open'] + k1['close']) / 2):  # 收盘低于第一根K线实体一半
            
            patterns.append({
                'name': '暮星',
                'name_en': 'Evening Star',
                'type': 'bearish',
                'confidence': 0.85,
                'description': '顶部反转信号，趋势可能转空'
            })
        
        return patterns
    
    def _identify_trend_patterns(self, df: pd.DataFrame) -> List[Dict]:
        """识别趋势形态"""
        patterns = []
        
        if len(df) < 20:
            return patterns
        
        recent_data = df.iloc[-20:]
        
        # 1. 判断整体趋势
        trend = self._get_trend(recent_data)
        
        if trend == 'up':
            patterns.append({
                'name': '上升趋势',
                'name_en': 'Uptrend',
                'type': 'bullish',
                'confidence': 0.8,
                'description': '价格持续创新高，趋势向上'
            })
        elif trend == 'down':
            patterns.append({
                'name': '下降趋势',
                'name_en': 'Downtrend',
                'type': 'bearish',
                'confidence': 0.8,
                'description': '价格持续创新低，趋势向下'
            })
        
        # 2. 检测通道突破
        highs = recent_data['high'].values
        lows = recent_data['low'].values
        
        upper_channel = np.percentile(highs, 90)
        lower_channel = np.percentile(lows, 10)
        
        current_close = df.iloc[-1]['close']
        
        if current_close > upper_channel:
            patterns.append({
                'name': '突破上轨',
                'name_en': 'Upper Channel Breakout',
                'type': 'bullish',
                'confidence': 0.75,
                'description': '价格突破通道上轨，可能加速上涨'
            })
        elif current_close < lower_channel:
            patterns.append({
                'name': '跌破下轨',
                'name_en': 'Lower Channel Breakdown',
                'type': 'bearish',
                'confidence': 0.75,
                'description': '价格跌破通道下轨，可能加速下跌'
            })
        
        return patterns
    
    def _identify_support_resistance(self, df: pd.DataFrame) -> Dict:
        """识别支撑和阻力位"""
        if len(df) < 20:
            return {}
        
        recent_data = df.iloc[-50:] if len(df) >= 50 else df
        
        # 找出局部高点和低点
        highs = []
        lows = []
        
        for i in range(2, len(recent_data) - 2):
            # 局部高点
            if (recent_data.iloc[i]['high'] > recent_data.iloc[i-1]['high'] and
                recent_data.iloc[i]['high'] > recent_data.iloc[i-2]['high'] and
                recent_data.iloc[i]['high'] > recent_data.iloc[i+1]['high'] and
                recent_data.iloc[i]['high'] > recent_data.iloc[i+2]['high']):
                highs.append(recent_data.iloc[i]['high'])
            
            # 局部低点
            if (recent_data.iloc[i]['low'] < recent_data.iloc[i-1]['low'] and
                recent_data.iloc[i]['low'] < recent_data.iloc[i-2]['low'] and
                recent_data.iloc[i]['low'] < recent_data.iloc[i+1]['low'] and
                recent_data.iloc[i]['low'] < recent_data.iloc[i+2]['low']):
                lows.append(recent_data.iloc[i]['low'])
        
        current_price = df.iloc[-1]['close']
        
        # 聚类找出关键价位
        resistance_levels = self._cluster_price_levels(highs) if highs else []
        support_levels = self._cluster_price_levels(lows) if lows else []
        
        # 找出最近的支撑和阻力
        nearest_resistance = min([r for r in resistance_levels if r > current_price], default=None)
        nearest_support = max([s for s in support_levels if s < current_price], default=None)
        
        return {
            'support_levels': support_levels,
            'resistance_levels': resistance_levels,
            'nearest_support': nearest_support,
            'nearest_resistance': nearest_resistance,
            'current_price': current_price
        }
    
    def _cluster_price_levels(self, prices: List[float], threshold: float = 0.02) -> List[float]:
        """聚类价格水平"""
        if not prices:
            return []
        
        prices = sorted(prices)
        clusters = []
        current_cluster = [prices[0]]
        
        for price in prices[1:]:
            if abs(price - np.mean(current_cluster)) / np.mean(current_cluster) < threshold:
                current_cluster.append(price)
            else:
                if len(current_cluster) >= 2:  # 至少2个点才认为是有效支撑/阻力
                    clusters.append(np.mean(current_cluster))
                current_cluster = [price]
        
        if len(current_cluster) >= 2:
            clusters.append(np.mean(current_cluster))
        
        return clusters
    
    def _get_trend(self, df: pd.DataFrame) -> str:
        """判断趋势方向"""
        if len(df) < 5:
            return 'neutral'
        
        closes = df['close'].values
        
        # 使用线性回归判断趋势
        x = np.arange(len(closes))
        slope = np.polyfit(x, closes, 1)[0]
        
        # 计算斜率相对于价格的比例
        avg_price = np.mean(closes)
        slope_pct = (slope / avg_price) * 100
        
        if slope_pct > 0.1:
            return 'up'
        elif slope_pct < -0.1:
            return 'down'
        else:
            return 'neutral'
    
    def _generate_description(self, patterns: List[Dict]) -> str:
        """生成形态描述"""
        if not patterns:
            return '未识别到明显的K线形态'
        
        bullish_patterns = [p for p in patterns if p['type'] == 'bullish']
        bearish_patterns = [p for p in patterns if p['type'] == 'bearish']
        
        if bullish_patterns and not bearish_patterns:
            return f"识别到{len(bullish_patterns)}个看涨形态，市场倾向多头"
        elif bearish_patterns and not bullish_patterns:
            return f"识别到{len(bearish_patterns)}个看跌形态，市场倾向空头"
        elif bullish_patterns and bearish_patterns:
            return f"识别到{len(bullish_patterns)}个看涨和{len(bearish_patterns)}个看跌形态，市场信号混杂"
        else:
            return "识别到中性形态，市场方向不明确"


# 全局实例
_pattern_recognizer = None

def get_pattern_recognizer() -> CandlestickPatternRecognizer:
    """获取K线形态识别器单例"""
    global _pattern_recognizer
    if _pattern_recognizer is None:
        _pattern_recognizer = CandlestickPatternRecognizer()
    return _pattern_recognizer


