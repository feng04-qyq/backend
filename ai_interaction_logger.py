"""
AI交互完整记录系统 - 保存发送给AI的所有信息和数据

功能：
1. 记录发送给AI的完整prompt（系统提示词 + 用户提示词）
2. 记录完整的市场数据和技术指标
3. 记录AI的原始响应
4. 记录决策结果和执行情况
5. 便于后续分析、调试和优化
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging


class CustomJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理各种Python类型"""
    def default(self, obj):
        try:
            import pandas as pd
            import numpy as np
            
            if isinstance(obj, (pd.Timestamp, datetime)):
                return obj.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float64, np.float32)):
                if np.isnan(obj) or np.isinf(obj):
                    return None
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif pd.isna(obj):
                return None
        except ImportError:
            pass
        
        # 处理datetime对象
        if isinstance(obj, datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        
        return super().default(obj)


class AIInteractionLogger:
    """
    AI交互完整记录系统
    
    保存每次AI交互的：
    - 完整输入（prompt + 数据）
    - 完整输出（AI响应）
    - 上下文信息（时间、账户状态等）
    - 执行结果
    """
    
    def __init__(self, log_dir: str = "ai_interactions"):
        """
        初始化AI交互记录器
        
        Args:
            log_dir: 日志保存目录
        """
        self.log_dir = log_dir
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.interaction_count = 0
        
        # 创建目录结构
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(os.path.join(log_dir, "daily"), exist_ok=True)
        os.makedirs(os.path.join(log_dir, "sessions"), exist_ok=True)
        
        # 当前会话记录
        self.current_session_file = os.path.join(
            log_dir, "sessions", f"session_{self.session_id}.json"
        )
        self.interactions = []
        
        logging.info(f"✓ AI交互记录系统已初始化: {self.current_session_file}")
    
    def log_interaction(
        self,
        interaction_type: str,
        system_prompt: str,
        user_prompt: str,
        market_data: Optional[Dict] = None,
        account_state: Optional[Dict] = None,
        ai_response: Optional[str] = None,
        parsed_decision: Optional[Dict] = None,
        execution_result: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        记录一次完整的AI交互
        
        Args:
            interaction_type: 交互类型（decision_making/self_analysis/risk_check等）
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            market_data: 完整市场数据
            account_state: 账户状态
            ai_response: AI的原始响应
            parsed_decision: 解析后的决策JSON
            execution_result: 执行结果
            metadata: 其他元数据
        
        Returns:
            interaction_id: 交互ID
        """
        self.interaction_count += 1
        
        interaction_id = f"AI_{self.session_id}_{self.interaction_count:04d}"
        timestamp = datetime.now()
        
        # 构建完整记录
        interaction_record = {
            # === 基本信息 ===
            "interaction_id": interaction_id,
            "session_id": self.session_id,
            "interaction_number": self.interaction_count,
            "timestamp": timestamp.isoformat(),
            "interaction_type": interaction_type,
            
            # === 输入信息 ===
            "input": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "prompt_length": {
                    "system": len(system_prompt),
                    "user": len(user_prompt),
                    "total": len(system_prompt) + len(user_prompt)
                }
            },
            
            # === 市场数据 ===
            "market_data": self._sanitize_data(market_data) if market_data else None,
            
            # === 账户状态 ===
            "account_state": self._sanitize_data(account_state) if account_state else None,
            
            # === AI响应 ===
            "output": {
                "raw_response": ai_response,
                "response_length": len(ai_response) if ai_response else 0,
                "parsed_decision": self._sanitize_data(parsed_decision) if parsed_decision else None
            },
            
            # === 执行结果 ===
            "execution": self._sanitize_data(execution_result) if execution_result else None,
            
            # === 元数据 ===
            "metadata": metadata or {}
        }
        
        # 添加到当前会话
        self.interactions.append(interaction_record)
        
        # 保存到文件
        self._save_interaction(interaction_record)
        self._save_session()
        
        logging.info(f"✓ AI交互已记录: {interaction_id} ({interaction_type})")
        
        return interaction_id
    
    def log_decision_making(
        self,
        system_prompt: str,
        user_prompt: str,
        market_data: Dict,
        account_state: Dict,
        ai_response: str,
        parsed_decision: Dict,
        execution_result: Optional[Dict] = None
    ) -> str:
        """
        记录决策类AI交互
        
        这是最常用的方法，用于记录AI做交易决策时的完整信息
        """
        return self.log_interaction(
            interaction_type="decision_making",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            market_data=market_data,
            account_state=account_state,
            ai_response=ai_response,
            parsed_decision=parsed_decision,
            execution_result=execution_result,
            metadata={
                "assets_analyzed": list(market_data.keys()) if market_data else [],
                "has_open_positions": account_state.get("has_positions", False) if account_state else False
            }
        )
    
    def log_self_analysis(
        self,
        analysis_prompt: str,
        ai_response: str,
        parsed_analysis: Optional[Dict] = None,
        trade_stats: Optional[Dict] = None
    ) -> str:
        """
        记录AI自我分析交互
        """
        return self.log_interaction(
            interaction_type="self_analysis",
            system_prompt="你是一个专业的交易分析师，需要客观分析AI交易员的表现并提供改进建议。",
            user_prompt=analysis_prompt,
            ai_response=ai_response,
            parsed_decision=parsed_analysis,
            metadata={
                "trade_stats": trade_stats
            }
        )
    
    def log_risk_check(
        self,
        risk_prompt: str,
        current_positions: Dict,
        ai_response: str,
        risk_decision: Dict
    ) -> str:
        """
        记录风险检查交互
        """
        return self.log_interaction(
            interaction_type="risk_check",
            system_prompt="你是一个严格的风险管理专家。",
            user_prompt=risk_prompt,
            account_state=current_positions,
            ai_response=ai_response,
            parsed_decision=risk_decision
        )
    
    def _sanitize_data(self, data: Any) -> Any:
        """
        清理数据，移除不可序列化的对象
        """
        if data is None:
            return None
        
        try:
            # 尝试直接序列化
            json.dumps(data, cls=CustomJSONEncoder)
            return data
        except (TypeError, ValueError):
            # 如果失败，转换为字符串
            return str(data)
    
    def _save_interaction(self, interaction: Dict):
        """
        保存单个交互到独立文件
        """
        try:
            # 保存到每日目录
            date_str = datetime.now().strftime("%Y-%m-%d")
            daily_dir = os.path.join(self.log_dir, "daily", date_str)
            os.makedirs(daily_dir, exist_ok=True)
            
            # 独立交互文件
            interaction_file = os.path.join(
                daily_dir,
                f"{interaction['interaction_id']}.json"
            )
            
            with open(interaction_file, 'w', encoding='utf-8') as f:
                json.dump(interaction, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
            
            # 同时保存Markdown格式（更易读）
            self._save_interaction_markdown(interaction, daily_dir)
            
        except Exception as e:
            logging.error(f"保存AI交互失败: {e}")
    
    def _save_interaction_markdown(self, interaction: Dict, output_dir: str):
        """
        保存Markdown格式的交互记录（更易阅读）
        """
        try:
            md_file = os.path.join(
                output_dir,
                f"{interaction['interaction_id']}.md"
            )
            
            content = f"""# AI交互记录

## 基本信息

- **交互ID**: {interaction['interaction_id']}
- **时间**: {interaction['timestamp']}
- **类型**: {interaction['interaction_type']}
- **会话ID**: {interaction['session_id']}

---

## 输入信息

### 系统提示词

```
{interaction['input']['system_prompt']}
```

### 用户提示词

```
{interaction['input']['user_prompt']}
```

### 提示词统计

- 系统提示词长度: {interaction['input']['prompt_length']['system']} 字符
- 用户提示词长度: {interaction['input']['prompt_length']['user']} 字符
- 总长度: {interaction['input']['prompt_length']['total']} 字符

---

## 市场数据

```json
{json.dumps(interaction['market_data'], indent=2, ensure_ascii=False, cls=CustomJSONEncoder) if interaction['market_data'] else 'null'}
```

---

## 账户状态

```json
{json.dumps(interaction['account_state'], indent=2, ensure_ascii=False, cls=CustomJSONEncoder) if interaction['account_state'] else 'null'}
```

---

## AI响应

### 原始响应

```
{interaction['output']['raw_response'] or '无响应'}
```

### 解析后的决策

```json
{json.dumps(interaction['output']['parsed_decision'], indent=2, ensure_ascii=False, cls=CustomJSONEncoder) if interaction['output']['parsed_decision'] else 'null'}
```

---

## 执行结果

```json
{json.dumps(interaction['execution'], indent=2, ensure_ascii=False, cls=CustomJSONEncoder) if interaction['execution'] else 'null'}
```

---

## 元数据

```json
{json.dumps(interaction['metadata'], indent=2, ensure_ascii=False, cls=CustomJSONEncoder)}
```

---

*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
            
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except Exception as e:
            logging.error(f"保存Markdown格式交互记录失败: {e}")
    
    def _save_session(self):
        """
        保存当前会话的所有交互
        """
        try:
            session_data = {
                "session_id": self.session_id,
                "start_time": self.interactions[0]['timestamp'] if self.interactions else None,
                "last_update": datetime.now().isoformat(),
                "total_interactions": self.interaction_count,
                "interactions": self.interactions
            }
            
            with open(self.current_session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
            
        except Exception as e:
            logging.error(f"保存会话记录失败: {e}")
    
    def get_session_summary(self) -> Dict:
        """
        获取当前会话摘要
        """
        if not self.interactions:
            return {
                "session_id": self.session_id,
                "total_interactions": 0,
                "interaction_types": {}
            }
        
        # 统计交互类型
        type_counts = {}
        for interaction in self.interactions:
            itype = interaction['interaction_type']
            type_counts[itype] = type_counts.get(itype, 0) + 1
        
        return {
            "session_id": self.session_id,
            "start_time": self.interactions[0]['timestamp'],
            "last_update": self.interactions[-1]['timestamp'],
            "total_interactions": self.interaction_count,
            "interaction_types": type_counts,
            "total_prompt_length": sum(
                i['input']['prompt_length']['total'] 
                for i in self.interactions
            ),
            "total_response_length": sum(
                i['output']['response_length'] 
                for i in self.interactions
            )
        }
    
    def save_session_summary(self):
        """
        保存会话摘要报告
        """
        summary = self.get_session_summary()
        
        summary_file = os.path.join(
            self.log_dir,
            f"session_summary_{self.session_id}.json"
        )
        
        try:
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            logging.info(f"✓ 会话摘要已保存: {summary_file}")
            
            # 打印摘要
            self.print_session_summary(summary)
            
        except Exception as e:
            logging.error(f"保存会话摘要失败: {e}")
    
    def print_session_summary(self, summary: Optional[Dict] = None):
        """
        打印会话摘要
        """
        if summary is None:
            summary = self.get_session_summary()
        
        print("\n" + "="*80)
        print("📊 AI交互会话摘要")
        print("="*80)
        print(f"\n会话ID: {summary['session_id']}")
        
        if summary['total_interactions'] > 0:
            print(f"开始时间: {summary['start_time']}")
            print(f"最后更新: {summary['last_update']}")
            print(f"总交互次数: {summary['total_interactions']}")
            
            print(f"\n交互类型分布:")
            for itype, count in summary['interaction_types'].items():
                print(f"  - {itype}: {count} 次")
            
            print(f"\n数据量统计:")
            print(f"  - 总提示词长度: {summary['total_prompt_length']:,} 字符")
            print(f"  - 总响应长度: {summary['total_response_length']:,} 字符")
            print(f"  - 平均提示词长度: {summary['total_prompt_length'] // summary['total_interactions']:,} 字符/次")
            print(f"  - 平均响应长度: {summary['total_response_length'] // summary['total_interactions']:,} 字符/次")
        else:
            print("暂无交互记录")
        
        print("\n" + "="*80 + "\n")
    
    def export_for_training(self, output_file: str):
        """
        导出为训练数据格式（可用于微调AI模型）
        
        导出格式：
        [
            {
                "input": "系统提示词 + 用户提示词",
                "output": "AI响应",
                "metadata": {...}
            }
        ]
        """
        training_data = []
        
        for interaction in self.interactions:
            training_data.append({
                "input": f"{interaction['input']['system_prompt']}\n\n{interaction['input']['user_prompt']}",
                "output": interaction['output']['raw_response'],
                "metadata": {
                    "interaction_id": interaction['interaction_id'],
                    "timestamp": interaction['timestamp'],
                    "type": interaction['interaction_type'],
                    "market_data_included": interaction['market_data'] is not None,
                    "decision_made": interaction['output']['parsed_decision'] is not None
                }
            })
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(training_data, f, indent=2, ensure_ascii=False)
            
            logging.info(f"✓ 训练数据已导出: {output_file}")
            print(f"\n✓ 已导出 {len(training_data)} 条训练数据到: {output_file}\n")
            
        except Exception as e:
            logging.error(f"导出训练数据失败: {e}")


# 单例模式
_logger_instance = None

def get_ai_interaction_logger() -> AIInteractionLogger:
    """获取AI交互记录器单例"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = AIInteractionLogger()
    return _logger_instance


# 便捷函数
def log_ai_decision(
    system_prompt: str,
    user_prompt: str,
    market_data: Dict,
    account_state: Dict,
    ai_response: str,
    parsed_decision: Dict,
    execution_result: Optional[Dict] = None
) -> str:
    """
    快速记录AI决策交互
    
    使用示例：
    ```python
    interaction_id = log_ai_decision(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        market_data=all_market_data,
        account_state={"balance": 1000, "positions": []},
        ai_response=raw_response,
        parsed_decision=decision_json,
        execution_result={"action": "LONG", "success": True}
    )
    ```
    """
    logger = get_ai_interaction_logger()
    return logger.log_decision_making(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        market_data=market_data,
        account_state=account_state,
        ai_response=ai_response,
        parsed_decision=parsed_decision,
        execution_result=execution_result
    )


if __name__ == "__main__":
    # 测试示例
    print("AI交互记录系统测试\n")
    
    logger = AIInteractionLogger()
    
    # 模拟记录一次AI决策
    interaction_id = logger.log_decision_making(
        system_prompt="你是一个专业的加密货币交易员。",
        user_prompt="分析当前BTC市场并给出交易建议。",
        market_data={
            "BTCUSDT": {
                "15m": {"close": 68000, "rsi": 65},
                "1h": {"close": 68000, "rsi": 62},
                "4h": {"close": 68000, "rsi": 58}
            }
        },
        account_state={
            "balance": 1000,
            "positions": []
        },
        ai_response='{"action": "LONG", "confidence": 75, "reason": "技术指标看涨"}',
        parsed_decision={
            "action": "LONG",
            "confidence": 75,
            "reason": "技术指标看涨"
        },
        execution_result={
            "success": True,
            "order_id": "ORDER123"
        }
    )
    
    print(f"✓ 测试交互已记录: {interaction_id}\n")
    
    # 保存会话摘要
    logger.save_session_summary()

