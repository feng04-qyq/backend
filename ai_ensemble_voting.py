"""
多模型集成投票系统

支持多个AI模型并行决策并通过投票机制得出最终结论。

核心理念：
- 多个独立AI模型同时分析市场
- 每个模型给出自己的决策和置信度
- 通过加权投票得出最终决策
- 降低单一模型的偏差和错误

支持的投票策略：
1. 简单多数投票 (Simple Majority)
2. 加权投票 (Weighted by Confidence)
3. 一致性投票 (Unanimous)
4. 质量加权投票 (Weighted by Historical Performance)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import Counter
import logging


class AIEnsemble:
    """AI模型集成系统"""
    
    def __init__(self, models: List[str], voting_strategy: str = 'weighted'):
        """
        初始化集成系统
        
        Args:
            models: 模型列表 (如 ['deepseek-chat', 'deepseek-coder', ...])
            voting_strategy: 投票策略
                - 'simple': 简单多数投票
                - 'weighted': 加权投票（基于置信度）
                - 'unanimous': 一致性投票
                - 'quality': 质量加权（基于历史表现）
        """
        self.models = models
        self.voting_strategy = voting_strategy
        
        # 记录各模型历史表现
        self.model_performance = {model: {'correct': 0, 'total': 0} for model in models}
        
    def collect_predictions(self, model_decisions: List[Dict]) -> Dict:
        """
        收集所有模型的预测
        
        Args:
            model_decisions: 各模型的决策列表
                [
                    {
                        'model': 'model_name',
                        'action': 'LONG/SHORT/HOLD',
                        'target_symbol': 'BTCUSDT_PERPETUAL',
                        'confidence': 0-100,
                        'position_size': 0-1,
                        'leverage': 10-20,
                        'reason': 'xxx'
                    },
                    ...
                ]
                
        Returns:
            集成后的决策
        """
        if not model_decisions:
            return self._get_default_decision()
        
        # 根据策略选择投票方法
        if self.voting_strategy == 'simple':
            final_decision = self._simple_majority_vote(model_decisions)
        elif self.voting_strategy == 'weighted':
            final_decision = self._weighted_vote(model_decisions)
        elif self.voting_strategy == 'unanimous':
            final_decision = self._unanimous_vote(model_decisions)
        elif self.voting_strategy == 'quality':
            final_decision = self._quality_weighted_vote(model_decisions)
        else:
            final_decision = self._weighted_vote(model_decisions)
        
        # 添加集成信息
        final_decision['ensemble_info'] = {
            'num_models': len(model_decisions),
            'voting_strategy': self.voting_strategy,
            'model_breakdown': self._get_model_breakdown(model_decisions)
        }
        
        return final_decision
    
    def _simple_majority_vote(self, decisions: List[Dict]) -> Dict:
        """简单多数投票"""
        actions = [d['action'] for d in decisions]
        symbols = [d.get('target_symbol') for d in decisions if d.get('target_symbol')]
        
        # 最常见的行动
        action_counter = Counter(actions)
        final_action = action_counter.most_common(1)[0][0]
        
        # 最常见的目标资产
        if symbols:
            symbol_counter = Counter(symbols)
            final_symbol = symbol_counter.most_common(1)[0][0]
        else:
            final_symbol = None
        
        # 平均参数
        avg_confidence = np.mean([d['confidence'] for d in decisions])
        avg_position_size = np.mean([d.get('position_size', 0.5) for d in decisions])
        avg_leverage = int(np.mean([d.get('leverage', 15) for d in decisions]))
        
        # 投票比例作为最终置信度
        vote_ratio = action_counter[final_action] / len(decisions) * 100
        final_confidence = (avg_confidence + vote_ratio) / 2
        
        return {
            'action': final_action,
            'target_symbol': final_symbol,
            'confidence': final_confidence,
            'position_size': avg_position_size,
            'leverage': avg_leverage,
            'reason': f"集成决策: {action_counter[final_action]}/{len(decisions)}个模型同意",
            'stop_loss_pct': 3.0,
            'take_profit_targets': [2, 4, 6],
            'market_state': 'ensemble'
        }
    
    def _weighted_vote(self, decisions: List[Dict]) -> Dict:
        """加权投票（基于置信度）"""
        # 按行动分组
        action_weights = {}
        symbol_weights = {}
        
        for d in decisions:
            action = d['action']
            confidence = d['confidence']
            symbol = d.get('target_symbol')
            
            # 累加权重
            action_weights[action] = action_weights.get(action, 0) + confidence
            
            if symbol:
                key = f"{action}_{symbol}"
                symbol_weights[key] = symbol_weights.get(key, 0) + confidence
        
        # 选择权重最高的行动
        final_action = max(action_weights.items(), key=lambda x: x[1])[0]
        
        # 选择权重最高的资产
        if symbol_weights:
            best_combo = max(symbol_weights.items(), key=lambda x: x[1])[0]
            final_symbol = best_combo.split('_', 1)[1]
        else:
            final_symbol = None
        
        # 只计算支持最终决策的模型的平均参数
        supporting_decisions = [d for d in decisions 
                               if d['action'] == final_action 
                               and d.get('target_symbol') == final_symbol]
        
        if supporting_decisions:
            avg_confidence = np.mean([d['confidence'] for d in supporting_decisions])
            avg_position_size = np.mean([d.get('position_size', 0.5) for d in supporting_decisions])
            avg_leverage = int(np.mean([d.get('leverage', 15) for d in supporting_decisions]))
        else:
            avg_confidence = 50
            avg_position_size = 0.5
            avg_leverage = 15
        
        # 权重比例作为信心加成
        total_weight = sum(action_weights.values())
        weight_ratio = action_weights[final_action] / total_weight * 100
        
        final_confidence = (avg_confidence * 0.6 + weight_ratio * 0.4)
        final_confidence = np.clip(final_confidence, 0, 100)
        
        return {
            'action': final_action,
            'target_symbol': final_symbol,
            'confidence': final_confidence,
            'position_size': avg_position_size,
            'leverage': avg_leverage,
            'reason': f"加权集成: {len(supporting_decisions)}/{len(decisions)}模型, 权重{weight_ratio:.0f}%",
            'stop_loss_pct': 3.0,
            'take_profit_targets': [2, 4, 6],
            'market_state': 'ensemble'
        }
    
    def _unanimous_vote(self, decisions: List[Dict]) -> Dict:
        """一致性投票（所有模型必须一致）"""
        actions = [d['action'] for d in decisions]
        symbols = [d.get('target_symbol') for d in decisions]
        
        # 检查是否所有模型一致
        if len(set(actions)) == 1 and len(set(symbols)) == 1:
            # 完全一致，高置信度
            avg_confidence = np.mean([d['confidence'] for d in decisions])
            final_confidence = min(avg_confidence * 1.2, 100)  # 提升20%置信度
            
            return {
                'action': actions[0],
                'target_symbol': symbols[0],
                'confidence': final_confidence,
                'position_size': np.mean([d.get('position_size', 0.5) for d in decisions]),
                'leverage': int(np.mean([d.get('leverage', 15) for d in decisions])),
                'reason': f"完全一致: 所有{len(decisions)}个模型达成共识",
                'stop_loss_pct': 3.0,
                'take_profit_targets': [2, 4, 6],
                'market_state': 'strong_consensus'
            }
        else:
            # 不一致，保守HOLD
            return {
                'action': 'HOLD',
                'target_symbol': None,
                'confidence': 0,
                'position_size': 0,
                'leverage': 15,
                'reason': f"模型分歧: {len(set(actions))}种不同意见，保持观望",
                'stop_loss_pct': 3.0,
                'take_profit_targets': [2, 4, 6],
                'market_state': 'divergence'
            }
    
    def _quality_weighted_vote(self, decisions: List[Dict]) -> Dict:
        """质量加权投票（基于历史表现）"""
        # 计算每个模型的质量权重
        quality_weights = {}
        for model in self.models:
            perf = self.model_performance[model]
            if perf['total'] > 0:
                accuracy = perf['correct'] / perf['total']
                quality_weights[model] = accuracy
            else:
                quality_weights[model] = 0.5  # 默认50%
        
        # 加权累加
        action_scores = {}
        symbol_scores = {}
        
        for d in decisions:
            model = d.get('model', 'unknown')
            quality = quality_weights.get(model, 0.5)
            confidence = d['confidence']
            
            # 综合权重 = 模型质量 * 置信度
            weight = quality * confidence
            
            action = d['action']
            symbol = d.get('target_symbol')
            
            action_scores[action] = action_scores.get(action, 0) + weight
            
            if symbol:
                key = f"{action}_{symbol}"
                symbol_scores[key] = symbol_scores.get(key, 0) + weight
        
        # 选择得分最高的
        final_action = max(action_scores.items(), key=lambda x: x[1])[0]
        
        if symbol_scores:
            best_combo = max(symbol_scores.items(), key=lambda x: x[1])[0]
            final_symbol = best_combo.split('_', 1)[1]
        else:
            final_symbol = None
        
        # 计算参数
        supporting = [d for d in decisions 
                     if d['action'] == final_action 
                     and d.get('target_symbol') == final_symbol]
        
        if supporting:
            # 质量加权平均
            weights = [quality_weights.get(d.get('model', 'unknown'), 0.5) for d in supporting]
            
            final_confidence = np.average([d['confidence'] for d in supporting], weights=weights)
            final_position_size = np.average([d.get('position_size', 0.5) for d in supporting], weights=weights)
            final_leverage = int(np.average([d.get('leverage', 15) for d in supporting], weights=weights))
        else:
            final_confidence = 50
            final_position_size = 0.5
            final_leverage = 15
        
        return {
            'action': final_action,
            'target_symbol': final_symbol,
            'confidence': final_confidence,
            'position_size': final_position_size,
            'leverage': final_leverage,
            'reason': f"质量加权: {len(supporting)}个高质量模型支持",
            'stop_loss_pct': 3.0,
            'take_profit_targets': [2, 4, 6],
            'market_state': 'quality_ensemble'
        }
    
    def _get_model_breakdown(self, decisions: List[Dict]) -> Dict:
        """获取模型分解信息"""
        breakdown = {}
        
        for d in decisions:
            model = d.get('model', 'unknown')
            breakdown[model] = {
                'action': d['action'],
                'symbol': d.get('target_symbol'),
                'confidence': d['confidence']
            }
        
        return breakdown
    
    def update_performance(self, model: str, correct: bool):
        """
        更新模型表现记录
        
        Args:
            model: 模型名称
            correct: 此次预测是否正确
        """
        if model in self.model_performance:
            self.model_performance[model]['total'] += 1
            if correct:
                self.model_performance[model]['correct'] += 1
    
    def get_performance_report(self) -> Dict:
        """获取模型表现报告"""
        report = {}
        
        for model, perf in self.model_performance.items():
            if perf['total'] > 0:
                accuracy = perf['correct'] / perf['total'] * 100
                report[model] = {
                    'accuracy': f"{accuracy:.1f}%",
                    'correct': perf['correct'],
                    'total': perf['total']
                }
            else:
                report[model] = {
                    'accuracy': 'N/A',
                    'correct': 0,
                    'total': 0
                }
        
        return report
    
    def _get_default_decision(self) -> Dict:
        """默认决策"""
        return {
            'action': 'HOLD',
            'target_symbol': None,
            'confidence': 0,
            'position_size': 0,
            'leverage': 15,
            'reason': '无模型决策',
            'stop_loss_pct': 3.0,
            'take_profit_targets': [2, 4, 6],
            'market_state': 'unknown'
        }


# ==================== 示例使用 ====================

def example_ensemble_usage():
    """示例：如何使用集成系统"""
    
    # 1. 创建集成系统
    ensemble = AIEnsemble(
        models=['deepseek-chat', 'deepseek-coder', 'gpt-4'],
        voting_strategy='weighted'
    )
    
    # 2. 模拟多个模型的决策
    model_decisions = [
        {
            'model': 'deepseek-chat',
            'action': 'LONG',
            'target_symbol': 'BTCUSDT_PERPETUAL',
            'confidence': 85,
            'position_size': 0.7,
            'leverage': 18
        },
        {
            'model': 'deepseek-coder',
            'action': 'LONG',
            'target_symbol': 'BTCUSDT_PERPETUAL',
            'confidence': 78,
            'position_size': 0.6,
            'leverage': 16
        },
        {
            'model': 'gpt-4',
            'action': 'LONG',
            'target_symbol': 'ETHUSDT_PERPETUAL',  # 不同资产
            'confidence': 70,
            'position_size': 0.5,
            'leverage': 15
        }
    ]
    
    # 3. 进行投票
    final_decision = ensemble.collect_predictions(model_decisions)
    
    print("=== 集成决策结果 ===")
    print(f"行动: {final_decision['action']}")
    print(f"资产: {final_decision['target_symbol']}")
    print(f"置信度: {final_decision['confidence']:.1f}%")
    print(f"仓位: {final_decision['position_size']:.1%}")
    print(f"杠杆: {final_decision['leverage']}x")
    print(f"理由: {final_decision['reason']}")
    
    print("\n=== 模型分解 ===")
    for model, info in final_decision['ensemble_info']['model_breakdown'].items():
        print(f"{model}: {info['action']} {info['symbol']} (信心{info['confidence']}%)")
    
    # 4. 更新表现
    ensemble.update_performance('deepseek-chat', correct=True)
    ensemble.update_performance('deepseek-coder', correct=True)
    ensemble.update_performance('gpt-4', correct=False)
    
    # 5. 查看表现报告
    print("\n=== 模型表现报告 ===")
    report = ensemble.get_performance_report()
    for model, stats in report.items():
        print(f"{model}: {stats['accuracy']} ({stats['correct']}/{stats['total']})")


if __name__ == "__main__":
    print("多模型集成投票系统已加载\n")
    print("支持的投票策略:")
    print("  - simple: 简单多数投票")
    print("  - weighted: 加权投票（基于置信度）")
    print("  - unanimous: 一致性投票（所有模型必须一致）")
    print("  - quality: 质量加权（基于历史表现）")
    print("\n运行示例:")
    example_ensemble_usage()

