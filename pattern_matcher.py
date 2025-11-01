"""
历史模式匹配系统

核心功能：
1. K线形态识别
2. 趋势相似度计算
3. 历史情景匹配
4. 预测未来走势概率
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from scipy.spatial.distance import euclidean
from scipy.stats import pearsonr
import warnings
warnings.filterwarnings('ignore')


class PatternMatcher:
    """历史模式匹配器"""
    
    def __init__(self, lookback_window: int = 50):
        """
        初始化模式匹配器
        
        Args:
            lookback_window: 回看窗口大小
        """
        self.lookback_window = lookback_window
        self.pattern_library = {}  # 存储已知模式
    
    def calculate_price_pattern(self, prices: pd.Series) -> np.ndarray:
        """
        计算价格模式特征向量
        
        将价格序列标准化为特征向量：
        1. 归一化（去除绝对价格影响）
        2. 计算收益率序列
        3. 提取统计特征
        
        Args:
            prices: 价格序列
            
        Returns:
            特征向量
        """
        if len(prices) < 2:
            return np.array([])
        
        # 收益率序列
        returns = prices.pct_change().fillna(0)
        
        # 归一化价格（0-1范围）
        normalized_prices = (prices - prices.min()) / (prices.max() - prices.min() + 1e-10)
        
        return np.array(normalized_prices)
    
    def calculate_similarity(
        self,
        pattern1: np.ndarray,
        pattern2: np.ndarray,
        method: str = 'euclidean'
    ) -> float:
        """
        计算两个模式的相似度
        
        Args:
            pattern1: 模式1
            pattern2: 模式2
            method: 相似度方法 ('euclidean', 'correlation', 'dtw')
            
        Returns:
            相似度分数 (0-100，越高越相似)
        """
        if len(pattern1) != len(pattern2) or len(pattern1) == 0:
            return 0.0
        
        if method == 'euclidean':
            # 欧氏距离（越小越相似）
            distance = euclidean(pattern1, pattern2)
            # 转换为相似度分数
            similarity = 100 / (1 + distance)
        
        elif method == 'correlation':
            # 皮尔逊相关系数
            if np.std(pattern1) == 0 or np.std(pattern2) == 0:
                return 0.0
            correlation, _ = pearsonr(pattern1, pattern2)
            # 转换为0-100分数
            similarity = (correlation + 1) / 2 * 100
        
        elif method == 'dtw':
            # DTW (Dynamic Time Warping) 简化版
            similarity = self._dtw_similarity(pattern1, pattern2)
        
        else:
            similarity = 0.0
        
        return np.clip(similarity, 0, 100)
    
    def _dtw_similarity(self, pattern1: np.ndarray, pattern2: np.ndarray) -> float:
        """
        动态时间规整(DTW)相似度
        
        允许时间轴上的伸缩匹配
        """
        n, m = len(pattern1), len(pattern2)
        dtw_matrix = np.zeros((n + 1, m + 1))
        
        for i in range(n + 1):
            for j in range(m + 1):
                dtw_matrix[i, j] = np.inf
        dtw_matrix[0, 0] = 0
        
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = abs(pattern1[i-1] - pattern2[j-1])
                dtw_matrix[i, j] = cost + min(
                    dtw_matrix[i-1, j],    # 插入
                    dtw_matrix[i, j-1],    # 删除
                    dtw_matrix[i-1, j-1]   # 匹配
                )
        
        dtw_distance = dtw_matrix[n, m]
        similarity = 100 / (1 + dtw_distance)
        
        return similarity
    
    def find_similar_patterns(
        self,
        current_pattern: np.ndarray,
        historical_data: pd.DataFrame,
        window_size: int,
        top_k: int = 5,
        min_similarity: float = 70.0
    ) -> List[Dict]:
        """
        在历史数据中查找相似模式
        
        Args:
            current_pattern: 当前价格模式
            historical_data: 历史数据DataFrame
            window_size: 窗口大小
            top_k: 返回top K个最相似的
            min_similarity: 最小相似度阈值
            
        Returns:
            相似模式列表
        """
        matches = []
        
        # 滑动窗口搜索
        for i in range(len(historical_data) - window_size):
            window = historical_data['close'].iloc[i:i+window_size]
            
            if len(window) < window_size:
                continue
            
            # 计算模式特征
            historical_pattern = self.calculate_price_pattern(window)
            
            # 计算相似度
            similarity = self.calculate_similarity(
                current_pattern,
                historical_pattern,
                method='correlation'
            )
            
            if similarity >= min_similarity:
                # 获取后续走势
                future_window = 10  # 查看后续10根K线
                if i + window_size + future_window < len(historical_data):
                    future_prices = historical_data['close'].iloc[
                        i+window_size:i+window_size+future_window
                    ]
                    
                    # 计算后续收益
                    entry_price = historical_data['close'].iloc[i+window_size-1]
                    future_return = (future_prices.iloc[-1] - entry_price) / entry_price * 100
                    
                    matches.append({
                        'start_idx': i,
                        'end_idx': i + window_size,
                        'similarity': similarity,
                        'entry_price': entry_price,
                        'future_return': future_return,
                        'timestamp': historical_data['timestamp'].iloc[i] if 'timestamp' in historical_data else i
                    })
        
        # 按相似度排序
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        
        return matches[:top_k]
    
    def predict_next_move(
        self,
        similar_patterns: List[Dict]
    ) -> Dict:
        """
        基于相似模式预测下一步走势
        
        Args:
            similar_patterns: 相似模式列表
            
        Returns:
            预测结果 {direction, confidence, expected_return}
        """
        if not similar_patterns:
            return {
                'direction': 'NEUTRAL',
                'confidence': 0,
                'expected_return': 0,
                'sample_size': 0
            }
        
        # 收集所有相似情景的后续表现
        future_returns = [p['future_return'] for p in similar_patterns]
        similarities = [p['similarity'] for p in similar_patterns]
        
        # 加权平均收益（权重=相似度）
        weighted_return = np.average(future_returns, weights=similarities)
        
        # 计算一致性（标准差越小越一致）
        consistency = 1 - np.std(future_returns) / (np.mean(np.abs(future_returns)) + 1e-10)
        consistency = np.clip(consistency, 0, 1)
        
        # 方向判断
        bullish_count = sum(1 for r in future_returns if r > 0)
        bearish_count = len(future_returns) - bullish_count
        
        if bullish_count > bearish_count:
            direction = 'BULLISH'
            confidence = (bullish_count / len(future_returns)) * consistency * 100
        elif bearish_count > bullish_count:
            direction = 'BEARISH'
            confidence = (bearish_count / len(future_returns)) * consistency * 100
        else:
            direction = 'NEUTRAL'
            confidence = 50
        
        # 平均相似度作为额外权重
        avg_similarity = np.mean(similarities)
        confidence = confidence * (avg_similarity / 100)
        
        return {
            'direction': direction,
            'confidence': round(confidence, 1),
            'expected_return': round(weighted_return, 2),
            'sample_size': len(similar_patterns),
            'avg_similarity': round(avg_similarity, 1),
            'bullish_ratio': round(bullish_count / len(future_returns) * 100, 1)
        }
    
    def analyze_current_pattern(
        self,
        df: pd.DataFrame,
        current_idx: int,
        window_size: int = 20
    ) -> Dict:
        """
        分析当前价格模式
        
        Args:
            df: 完整数据DataFrame
            current_idx: 当前索引
            window_size: 模式窗口大小
            
        Returns:
            模式分析结果
        """
        if current_idx < window_size:
            return {
                'pattern_found': False,
                'reason': 'insufficient_data'
            }
        
        # 提取当前模式
        current_window = df['close'].iloc[current_idx-window_size:current_idx]
        current_pattern = self.calculate_price_pattern(current_window)
        
        # 在历史数据中查找相似模式
        historical_data = df.iloc[:current_idx-window_size]  # 排除当前窗口及之后
        
        if len(historical_data) < window_size * 3:
            return {
                'pattern_found': False,
                'reason': 'insufficient_history'
            }
        
        similar_patterns = self.find_similar_patterns(
            current_pattern,
            historical_data,
            window_size,
            top_k=10,
            min_similarity=65
        )
        
        if not similar_patterns:
            return {
                'pattern_found': False,
                'reason': 'no_similar_patterns'
            }
        
        # 预测
        prediction = self.predict_next_move(similar_patterns)
        
        return {
            'pattern_found': True,
            'window_size': window_size,
            'similar_count': len(similar_patterns),
            'best_match_similarity': similar_patterns[0]['similarity'],
            'prediction': prediction,
            'similar_patterns': similar_patterns[:3]  # 只返回前3个最相似的
        }


class TrendAnalyzer:
    """趋势分析器"""
    
    @staticmethod
    def identify_trend(prices: pd.Series, window: int = 20) -> Dict:
        """
        识别当前趋势
        
        Args:
            prices: 价格序列
            window: 窗口大小
            
        Returns:
            趋势信息
        """
        if len(prices) < window:
            return {'trend': 'UNKNOWN', 'strength': 0}
        
        recent_prices = prices.iloc[-window:]
        
        # 线性回归斜率
        x = np.arange(len(recent_prices))
        y = recent_prices.values
        
        # 拟合直线
        slope, intercept = np.polyfit(x, y, 1)
        
        # 斜率标准化
        avg_price = recent_prices.mean()
        slope_pct = (slope / avg_price) * 100
        
        # R²拟合优度
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r_squared = 1 - (ss_res / (ss_tot + 1e-10))
        
        # 判断趋势
        if abs(slope_pct) < 0.5:
            trend = 'SIDEWAYS'
            strength = 0
        elif slope_pct > 0:
            trend = 'UPTREND'
            strength = min(slope_pct * 10, 100) * r_squared
        else:
            trend = 'DOWNTREND'
            strength = min(abs(slope_pct) * 10, 100) * r_squared
        
        return {
            'trend': trend,
            'strength': round(strength, 1),
            'slope': round(slope, 2),
            'r_squared': round(r_squared, 3),
            'direction_pct': round(slope_pct, 2)
        }
    
    @staticmethod
    def detect_support_resistance(
        df: pd.DataFrame,
        lookback: int = 100,
        num_levels: int = 3
    ) -> Dict:
        """
        检测支撑位和阻力位
        
        使用价格聚类方法
        
        Args:
            df: 数据DataFrame
            lookback: 回看期数
            num_levels: 要识别的关键位数量
            
        Returns:
            支撑位和阻力位
        """
        if len(df) < lookback:
            lookback = len(df)
        
        recent_data = df.iloc[-lookback:]
        
        # 收集高点和低点
        highs = recent_data['high'].values
        lows = recent_data['low'].values
        
        # 聚类分析（简化版）
        all_levels = np.concatenate([highs, lows])
        
        # 找到价格密集区域
        hist, bin_edges = np.histogram(all_levels, bins=50)
        
        # 找到峰值（价格密集区）
        peaks = []
        for i in range(1, len(hist) - 1):
            if hist[i] > hist[i-1] and hist[i] > hist[i+1] and hist[i] > np.mean(hist):
                price_level = (bin_edges[i] + bin_edges[i+1]) / 2
                peaks.append((price_level, hist[i]))
        
        # 按重要性排序
        peaks.sort(key=lambda x: x[1], reverse=True)
        
        current_price = df['close'].iloc[-1]
        
        # 分离支撑位和阻力位
        supports = [p[0] for p in peaks if p[0] < current_price][:num_levels]
        resistances = [p[0] for p in peaks if p[0] > current_price][:num_levels]
        
        return {
            'supports': sorted(supports, reverse=True),
            'resistances': sorted(resistances),
            'current_price': current_price
        }


def get_pattern_analysis_summary(
    df: pd.DataFrame,
    current_idx: int
) -> Dict:
    """
    获取模式分析摘要（用于AI决策）
    
    Args:
        df: 数据DataFrame
        current_idx: 当前索引
        
    Returns:
        模式分析摘要
    """
    matcher = PatternMatcher()
    analyzer = TrendAnalyzer()
    
    # 模式匹配
    pattern_result = matcher.analyze_current_pattern(df, current_idx, window_size=20)
    
    # 趋势分析
    trend_info = analyzer.identify_trend(df['close'].iloc[:current_idx], window=20)
    
    # 支撑阻力
    sr_levels = analyzer.detect_support_resistance(df.iloc[:current_idx], lookback=100)
    
    summary = {
        'pattern_match': pattern_result,
        'trend': trend_info,
        'support_resistance': sr_levels
    }
    
    return summary


if __name__ == "__main__":
    print("历史模式匹配模块已加载")
    print("\n核心功能:")
    print("  - K线形态识别")
    print("  - 趋势相似度计算")
    print("  - 历史情景匹配")
    print("  - 未来走势预测")
    print("  - 支撑阻力位识别")




