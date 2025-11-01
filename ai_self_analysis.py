"""
AI自我分析系统 - 让AI分析自己的交易错误并改进
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from trade_journal import get_trade_journal

class AISelfAnalysis:
    """
    AI自我分析系统
    
    功能：
    1. 分析失败交易的原因
    2. 识别常见错误模式
    3. 生成改进建议
    4. 学习历史教训
    """
    
    def __init__(self, trader):
        """
        初始化自我分析系统
        
        Args:
            trader: MultiAssetDeepSeekTrader实例
        """
        self.trader = trader
        self.journal = get_trade_journal()
        logging.info("✓ AI自我分析系统已初始化")
    
    def generate_analysis_prompt(self, days: int = 7) -> str:
        """
        生成AI自我分析提示词
        
        Args:
            days: 分析最近N天的交易
        
        Returns:
            AI分析提示词
        """
        # 获取统计数据
        stats = self.journal.get_performance_stats(days)
        closed_trades = self.journal.get_closed_trades(days)
        loss_trades = [t for t in closed_trades if t['pnl'] < 0]
        
        prompt = f"""
# AI交易自我分析任务

你需要分析自己过去{days}天的交易表现，识别错误模式并提出改进建议。

## 交易统计

- 总交易数: {stats['total_trades']}
- 盈利交易: {stats['win_trades']}笔
- 亏损交易: {stats['loss_trades']}笔
- 胜率: {stats['win_rate']:.2f}%
- 总盈亏: {stats['total_pnl']:.2f} USDT
- 平均盈亏: {stats['avg_pnl']:.2f} USDT
- 最大盈利: {stats['max_win']:.2f} USDT
- 最大亏损: {stats['max_loss']:.2f} USDT
- 平均持仓时长: {stats['avg_duration']:.2f}小时

## 需要分析的失败交易

"""
        
        # 添加每笔失败交易的详细信息
        for i, trade in enumerate(loss_trades[:10], 1):  # 只分析最近10笔亏损
            market_data = trade.get('market_data_snapshot', {})
            
            prompt += f"""
### 失败交易 #{i}

**基本信息:**
- 交易ID: {trade['trade_id']}
- 交易对: {trade['symbol']}
- 方向: {trade['action']}
- 开仓时间: {trade['open_time']}
- 平仓时间: {trade['close_time']}
- 持仓时长: {trade.get('duration_hours', 0):.2f}小时

**价格数据:**
- 开仓价: {trade['entry_price']:.2f}
- 止损价: {trade['stop_loss']:.2f}
- 止盈目标: {trade['take_profit']}
- 实际平仓价: {trade.get('close_price', 0):.2f}
- 预期盈亏比: {trade.get('risk_reward_ratio', 0)}:1

**交易结果:**
- 实际盈亏: {trade.get('pnl', 0):.2f} USDT ({trade.get('pnl_pct', 0):.2f}%)
- 平仓原因: {trade.get('close_reason', '未知')}

**你当时的决策:**
- 信心度: {trade.get('confidence', 0)}%
- 决策理由: {trade.get('reason', '无理由')}

**市场数据快照:**
"""
            
            # 添加技术指标数据
            if '15m' in market_data:
                data_15m = market_data['15m']
                prompt += f"""
- 15分钟数据:
  * 收盘价: {data_15m.get('close', 0):.2f}
  * RSI: {data_15m.get('rsi', 0):.1f}
  * MACD: {data_15m.get('macd', 0):.4f}
  * EMA9: {data_15m.get('ema_9', 0):.2f}
  * EMA21: {data_15m.get('ema_21', 0):.2f}
"""
            
            if '1h' in market_data:
                data_1h = market_data['1h']
                prompt += f"""
- 1小时数据:
  * 收盘价: {data_1h.get('close', 0):.2f}
  * RSI: {data_1h.get('rsi', 0):.1f}
  * MACD: {data_1h.get('macd', 0):.4f}
  * EMA21: {data_1h.get('ema_21', 0):.2f}
  * EMA50: {data_1h.get('ema_50', 0):.2f}
"""
            
            if '4h' in market_data:
                data_4h = market_data['4h']
                prompt += f"""
- 4小时数据:
  * 收盘价: {data_4h.get('close', 0):.2f}
  * RSI: {data_4h.get('rsi', 0):.1f}
  * MACD: {data_4h.get('macd', 0):.4f}
  * EMA50: {data_4h.get('ema_50', 0):.2f}
  * EMA200: {data_4h.get('ema_200', 0):.2f}
"""
            
            # 添加Bybit高级数据
            advanced = market_data.get('advanced_data', {})
            if advanced:
                prompt += f"""
- Bybit市场数据:
  * 资金费率: {advanced.get('funding_rate', 0):.4f}%
  * 持仓量: {advanced.get('open_interest', 0):.0f}
  * 多空比: 多{advanced.get('long_short_ratio', {}).get('buy_ratio', 0.5)*100:.1f}% vs 空{advanced.get('long_short_ratio', {}).get('sell_ratio', 0.5)*100:.1f}%
  * 24h涨跌: {advanced.get('price_24h_pcnt', 0):.2f}%
"""
            
            prompt += "\n---\n"
        
        # 添加分析任务
        prompt += """
## 分析任务

请从以下角度分析上述失败交易：

### 1. 入场时机问题
- 是否在趋势开始时入场？还是趋势末端？
- 是否等待了合适的回调/反弹？
- 突破是否有成交量确认？
- 是否忽略了关键阻力/支撑？

### 2. 趋势判断错误
- 三个时间框架是否真的一致？
- 是否被短期波动误导？
- 主趋势是否真的明确？
- 是否逆势交易？

### 3. 止损设置问题
- 止损位置是否太近（容易被扫）？
- 止损位置是否太远（风险太大）？
- 是否基于技术位置设置止损？

### 4. 风险管理问题
- 盈亏比是否合理？
- 仓位是否过大？
- 杠杆是否过高？
- 是否在不确定时期重仓？

### 5. 市场情绪判断
- 资金费率是否显示过热？
- 多空比是否显示极端情绪？
- 是否忽略了市场情绪警告？

### 6. 常见错误模式
请识别你反复犯的错误：
- 是否总在同样的情况下失败？
- 是否有特定的资产更容易亏损？
- 是否在特定时间段表现较差？
- 是否有某些指标被误读？

## 输出格式

请以JSON格式输出你的分析结果：

```json
{
    "overall_assessment": "整体表现评价（100-200字）",
    "main_problems": [
        {
            "problem": "问题描述",
            "frequency": "发生频率（高/中/低）",
            "impact": "影响程度（严重/中等/轻微）",
            "examples": ["具体案例1", "具体案例2"]
        }
    ],
    "improvement_suggestions": [
        {
            "area": "改进领域",
            "current_issue": "当前问题",
            "improvement_action": "具体改进措施",
            "priority": "优先级（高/中/低）"
        }
    ],
    "lessons_learned": [
        "教训1：...",
        "教训2：...",
        "教训3：..."
    ],
    "action_plan": [
        "短期行动1（立即实施）",
        "短期行动2",
        "中期目标1（1-2周）",
        "中期目标2"
    ]
}
```

请诚实、客观地分析自己的错误，不要找借口。目标是通过学习改进未来的交易表现。
"""
        
        return prompt
    
    def run_analysis(self, days: int = 7) -> Optional[Dict]:
        """
        运行AI自我分析
        
        Args:
            days: 分析最近N天的交易
        
        Returns:
            AI的分析结果（JSON格式）
        """
        try:
            # 生成分析提示词
            prompt = self.generate_analysis_prompt(days)
            
            logging.info("🤔 AI正在分析自己的交易表现...")
            
            # 调用AI进行分析
            response = self.trader._call_deepseek_api(
                system_prompt="你是一个专业的交易分析师，需要客观分析AI交易员的表现并提供改进建议。",
                user_prompt=prompt
            )
            
            if not response:
                logging.error("AI分析失败：无响应")
                return None
            
            # 解析JSON响应
            try:
                start = response.find('{')
                end = response.rfind('}')
                if start != -1 and end != -1:
                    json_str = response[start:end+1]
                    analysis = json.loads(json_str)
                    
                    # 保存分析结果
                    self._save_analysis_result(analysis, days)
                    
                    return analysis
            except json.JSONDecodeError as e:
                logging.error(f"解析AI分析结果失败: {e}")
                # 至少保存原始响应
                self._save_raw_analysis(response, days)
                return None
                
        except Exception as e:
            logging.error(f"运行AI分析出错: {e}", exc_info=True)
            return None
    
    def _save_analysis_result(self, analysis: Dict, days: int):
        """保存分析结果"""
        filename = f"ai_self_analysis_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
        filepath = f"trade_journals/{filename}"
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({
                    'analysis_date': datetime.now().isoformat(),
                    'analysis_period_days': days,
                    'analysis': analysis
                }, f, indent=2, ensure_ascii=False)
            
            logging.info(f"✓ AI分析结果已保存: {filepath}")
            
            # 同时保存Markdown格式
            self._save_analysis_markdown(analysis, days)
            
        except Exception as e:
            logging.error(f"保存分析结果失败: {e}")
    
    def _save_analysis_markdown(self, analysis: Dict, days: int):
        """保存Markdown格式的分析报告"""
        filename = f"ai_self_analysis_{datetime.now().strftime('%Y-%m-%d')}.md"
        filepath = f"trade_journals/{filename}"
        
        content = f"""# AI交易自我分析报告

**分析日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**分析周期**: 最近{days}天

---

## 整体评价

{analysis.get('overall_assessment', '无评价')}

---

## 主要问题

"""
        
        for i, problem in enumerate(analysis.get('main_problems', []), 1):
            content += f"""
### {i}. {problem.get('problem', '未知问题')}

- **发生频率**: {problem.get('frequency', '未知')}
- **影响程度**: {problem.get('impact', '未知')}
- **具体案例**:
"""
            for example in problem.get('examples', []):
                content += f"  - {example}\n"
            content += "\n"
        
        content += """
---

## 改进建议

"""
        
        for i, suggestion in enumerate(analysis.get('improvement_suggestions', []), 1):
            content += f"""
### {i}. {suggestion.get('area', '未知领域')}

- **当前问题**: {suggestion.get('current_issue', '未知')}
- **改进措施**: {suggestion.get('improvement_action', '未知')}
- **优先级**: {suggestion.get('priority', '未知')}

"""
        
        content += """
---

## 学到的教训

"""
        
        for lesson in analysis.get('lessons_learned', []):
            content += f"- {lesson}\n"
        
        content += """
---

## 行动计划

"""
        
        for action in analysis.get('action_plan', []):
            content += f"- [ ] {action}\n"
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            logging.info(f"✓ AI分析报告（Markdown）已保存: {filepath}")
        except Exception as e:
            logging.error(f"保存Markdown报告失败: {e}")
    
    def _save_raw_analysis(self, response: str, days: int):
        """保存原始响应（当JSON解析失败时）"""
        filename = f"ai_self_analysis_raw_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt"
        filepath = f"trade_journals/{filename}"
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"AI分析原始响应 - {datetime.now().isoformat()}\n")
                f.write(f"分析周期: {days}天\n\n")
                f.write("="*80 + "\n\n")
                f.write(response)
            
            logging.info(f"✓ AI原始分析已保存: {filepath}")
        except Exception as e:
            logging.error(f"保存原始分析失败: {e}")
    
    def print_analysis_summary(self, analysis: Dict):
        """打印分析摘要"""
        print("\n" + "="*80)
        print("🧠 AI自我分析报告摘要")
        print("="*80)
        
        print(f"\n📊 整体评价:")
        print(f"{analysis.get('overall_assessment', '无评价')}\n")
        
        print(f"⚠️ 主要问题 ({len(analysis.get('main_problems', []))}个):")
        for i, problem in enumerate(analysis.get('main_problems', [])[:3], 1):
            print(f"  {i}. {problem.get('problem', '未知')} ({problem.get('frequency', '?')}频率, {problem.get('impact', '?')}影响)")
        
        print(f"\n💡 改进建议 ({len(analysis.get('improvement_suggestions', []))}个):")
        for i, suggestion in enumerate(analysis.get('improvement_suggestions', [])[:3], 1):
            print(f"  {i}. {suggestion.get('area', '未知')}: {suggestion.get('improvement_action', '未知')[:50]}...")
        
        print(f"\n📝 关键教训:")
        for i, lesson in enumerate(analysis.get('lessons_learned', [])[:3], 1):
            print(f"  {i}. {lesson[:80]}...")
        
        print("\n" + "="*80 + "\n")


# 便捷函数
def run_daily_self_analysis(trader, days: int = 7):
    """运行每日自我分析"""
    analyzer = AISelfAnalysis(trader)
    analysis = analyzer.run_analysis(days)
    
    if analysis:
        analyzer.print_analysis_summary(analysis)
        return analysis
    else:
        logging.error("AI自我分析失败")
        return None

