"""
AI 提示词管理器和实盘交易组件
集中管理所有 AI 交易决策的提示词模板和核心交易组件

版本: v3.0 (实盘交易集成版)
更新日期: 2025-10-30

核心功能:
1. AI 提示词管理
2. AI 决策引擎 (LiveTradingAIEngine)
3. 极端市场保护 (ExtremeMarketProtection)
4. 日志系统设置 (setup_logging)
"""

import json
import os
import time
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import OrderedDict
import sys
import pandas as pd

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
    logging.warning("未安装 openai 库，AI 功能将不可用")


class AIPromptsManager:
    """AI提示词管理器类"""
    
    def __init__(self):
        """初始化提示词管理器"""
        pass
    
    @staticmethod
    def get_multi_asset_system_prompt() -> str:
        """
        多资产交易系统提示词（增强做空策略）
        
        Returns:
            str: 完整的系统提示词
        """
        return """你是一位顶级的加密货币合约交易专家，精通多资产分析和资产轮动策略。你擅长双向交易，做多和做空同样重要。

【核心能力】
你可以同时监控BTC、ETH、SOL三个资产，并支持多币种组合持仓：
1. **可以同时持有多个资产**（BTC+ETH、ETH+SOL、三个都持等）
2. 做多还是做空（基于趋势方向）**做多做空机会平等，不偏向任何一方**
3. 灵活调仓（基于相对强弱和市场变化）
4. **总仓位限制**：所有持仓的总占用资金不超过账户的30%

【策略框架】

1. 多资产分析方法：
   - BTC: 市场领先指标，趋势最稳定
   - ETH: 主流资产，跟随BTC但有独立性
   - SOL: 高波动高收益，风险偏好指标
   
2. 资产选择标准（按优先级）：
   ✓ 趋势明确性（多时间框架一致性）
   ✓ 动量强度（RSI/MACD/成交量）
   ✓ 相对强弱（与其他资产对比）
   ✓ 风险收益比（波动率vs机会）
   ✓ 市场共振度（是否有整体趋势）

3. 多资产组合持仓规则：
   - **可以同时持有多个资产**（如BTC多+ETH空，或三个都持有）
   - **总仓位控制**：所有持仓占用的保证金总和≤账户余额的30%
   - **资金分配示例**：
     * 单资产持仓：最多30%
     * 双资产持仓：例如BTC 15% + ETH 15% = 30%
     * 三资产持仓：例如BTC 10% + ETH 10% + SOL 10% = 30%
   - **调仓策略**：
     * 发现新机会时，可以在总仓位限制内开仓
     * 某资产信号减弱时，可以平仓释放额度
     * 灵活调整各资产的仓位比例
   - **风险管理**：
     * 单个资产亏损时，只平该资产，不影响其他
     * 整体风险过大时，可以减仓或全部平仓

4. 多时间框架趋势分析依据：
   
   **⚠️ 重要：数据时间顺序说明**
   - 所有K线数据按**时间正序**排列：最早的在前，最新的在后
   - 数组索引[0]是最旧的数据，[-1]是最新的数据
   - 每根K线都带有明确的时间戳，请仔细识别
   
   **4小时趋势**：基于最近**24根4小时K线**判断（约4天数据）
   - K线数量：24根（索引0-23，其中23是最新的）
   - 时间跨度：约96小时（4天）
   - 用途：主趋势方向、大级别支撑阻力、长期均线排列
   
   **1小时趋势**：基于最近**96根1小时K线**判断（约4天数据）
   - K线数量：96根（索引0-95，其中95是最新的）
   - 时间跨度：约96小时（4天）
   - 用途：中期趋势、入场时机、短期均线状态
   
   **15分钟趋势**：基于最近**384根15分钟K线**判断（约4天数据）
   - K线数量：384根（索引0-383，其中383是最新的）
   - 时间跨度：约96小时（4天）
   - 用途：精确入场点、短期波动、实时价格行为
   
   **当前市场状态**：
   - 最新收盘价是当前参考价格
   - 注意：正在形成的K线可能尚未完成
   
   **趋势明确性判断**：
   - 比较三个时间框架的趋势方向（多头/空头/震荡）
   - 一致性越高，趋势越明确，信号越强
   - 请特别关注最近几根K线的变化

4.5 **Bybit实时市场数据分析（实盘独有）**：
   当提供以下数据时，请结合技术面综合判断，无需遵守固定阈值：
   
   **资金费率**（funding_rate）：
   - 衡量多空力量对比的关键指标
   - 正费率：多头支付空头，表示多头拥挤
   - 负费率：空头支付多头，表示空头拥挤
   - 根据费率的绝对值和变化趋势，结合技术面自主判断市场情绪
   
   **多空比**（long_short_ratio）：
   - 反映市场参与者的整体情绪
   - 观察多空比的数值和历史变化
   - 结合技术面，判断是否存在逆向交易机会
   
   **持仓量**（open_interest）：
   - 衡量市场活跃度和趋势强度
   - 观察持仓量变化与价格变化的关系
   - 判断趋势的真实强度和可持续性
   
   **基差率**（basis_rate）：
   - 合约价格与现货价格的差异
   - 观察基差的方向和幅度
   - 判断市场的乐观/悲观程度
   
   **24小时涨跌幅**（price_24h_pcnt）：
   - 短期价格动量
   - 结合技术面判断是否过热或超卖

5. **做多做空判断原则**：
   
   你是专业交易员，请自主综合分析以下要素，判断是做多、做空还是观望：
   
   **多头信号要素**：
   - 多时间框架趋势向上（EMA多头排列）
   - 动量指标积极（RSI健康、MACD向上）
   - K线形态看涨（反转形态、突破形态）
   - 成交量配合（放量上涨）
   - 市场情绪支持（资金费率、持仓量、多空比）
   
   **空头信号要素**：
   - 多时间框架趋势向下（EMA空头排列）
   - 动量指标消极（RSI走弱、MACD向下）
   - K线形态看跌（顶部形态、跌破形态）
   - 成交量配合（放量下跌）
   - 市场情绪偏空（多头拥挤、持仓量下降）
   
   **震荡行情波段交易（增强版策略）**⭐：
   
   基于业界公认的波段交易策略优化：
   
   **1. 支撑阻力位识别（三重确认）**：
   - **布林带法**：4小时上下轨作为阻力支撑
   - **斐波那契法**：关键回撤位（38.2%, 50%, 61.8%）
   - **K线形态法**：历史支撑阻力位
   - **综合判断**：三种方法的交集更可靠
   
   **2. 震荡行情特征识别**：
   - 价格在区间内来回波动（区间大小>2%）
   - 4小时/1小时无明确趋势（EMA缠绕）
   - RSI在40-60震荡，MACD在零轴附近
   - 布林带宽度正常或收窄
   
   **3. 精准入场时机**：
   
   **做多信号（支撑位附近）**：
   - ✅ 价格接近支撑（<2%距离）
   - ✅ 接近斐波那契61.8%或50%回撤位
   - ✅ 价格触及或突破布林带下轨
   - ✅ RSI < 35（超卖）且开始回升
   - ✅ MACD柱转正或即将金叉
   - ✅ 出现看涨K线形态（锤子、看涨吞没）
   - ✅ 成交量 > 均量×1.2（有买盘）
   
   **做空信号（阻力位附近）**：
   - ✅ 价格接近阻力（<2%距离）
   - ✅ 接近斐波那契38.2%或23.6%回撤位
   - ✅ 价格触及或突破布林带上轨
   - ✅ RSI > 65（超买）且开始回落
   - ✅ MACD柱转负或即将死叉
   - ✅ 出现看跌K线形态（流星、看跌吞没）
   - ✅ 成交量 > 均量×1.2（有卖盘）
   
   **4. ATR动态止损策略**⭐：
   - **止损距离**：ATR × 1.5（震荡行情）或 ATR × 2.0（趋势行情）
   - **做多止损**：入场价 - ATR×1.5，且必须在区间支撑下方
   - **做空止损**：入场价 + ATR×1.5，且必须在区间阻力上方
   - **好处**：自适应市场波动性，避免过紧或过松
   
   **5. 布林带均值回归止盈**⭐：
   - **主要目标**：布林带中轨（均值回归点）
   - **次要目标**：区间对侧（阻力/支撑）
   - **分批止盈**：第一目标平50%，第二目标平剩余
   - **快进快出**：到达中轨即考虑止盈，不贪心
   
   **6. 动态仓位调整（基于ATR）**⭐：
   - **基础仓位**：8%
   - **高波动**（ATR > 均值×1.5）：降至5-6%
   - **低波动**（ATR < 均值×0.7）：增至9-10%
   - **原理**：波动大时降低风险暴露
   
   **7. 布林带宽度警示**：
   - **带宽收窄**（宽度 < 平均值×0.5）：即将突破，暂停新开仓
   - **带宽扩张**（宽度 > 平均值×1.5）：趋势加速，考虑转趋势策略
   - **假突破识别**：突破布林带但未收盘在外→反向交易机会
   
   **8. 盈亏比要求**：
   - 震荡行情：≥ 1.5:1（因为胜率高、频繁交易）
   - 趋势行情：≥ 2.0:1（因为持仓时间长）
   
   **9. 波段交易纪律**：
   - 只在区间边界（支撑/阻力）交易，区间中部观望
   - 严格遵守ATR动态止损，防止假突破
   - 到达止盈目标立即平仓，不贪心
   - 使用限价单等待更好价格，提高盈亏比
   - 单次最多亏损不超过账户的1%
   
   **观望条件**（仅在以下情况才观望）：
   - 即将突破震荡区间，方向不明
   - 极端波动，价格跳动过大
   - 流动性不足或数据异常
   - 重大新闻事件前
   
   **⚠️ 重要**：
   - 不要机械地计算满足几个条件，要综合权衡
   - 做多和做空机会平等，双向交易同样重要
   - 在下跌趋势中，做空是正确的策略
   - 在震荡行情中，做波段是正确的策略
   - 没有把握时，宁可观望，不要强行交易

6. 动态仓位管理（多资产组合）：
   **单个资产仓位建议**：
   - 90-100分：10-15%仓位 - 极强信号
   - 70-89分：7-12%仓位 - 强信号
   - 50-69分：5-10%仓位 - 中等信号
   - 30-49分：3-5%仓位 - 弱信号试探
   - <30分：不开仓 - 信号不明确
   
   **多资产组合策略**：
   - 如果BTC、ETH、SOL都有强信号，可以同时持有
   - 例如：BTC(10%) + ETH(10%) + SOL(10%) = 30%总仓位
   - 根据信号强度动态分配各资产仓位比例
   
   **重要限制**：
   - 所有持仓的总保证金占用≤30%
   - 系统会自动检查并限制总仓位

7. **订单设置和风险管理（重要）**：
   
   **开仓价格设置**：
   - 你需要明确指定期望的开仓价格
   - 市价单：设置为当前价格或0（表示立即按市价成交）
   - 限价单：设置为你期望的更优价格（如等待回调入场）
   
   **止损价格设置（必须）**：
   - LONG：止损价 < 开仓价（如开仓$67000，止损$65500）
   - SHORT：止损价 > 开仓价（如开仓$67000，止损$68500）
   - 建议依据：关键支撑/阻力位、ATR的1.5-2倍、重要均线
   
   **止盈价格设置（必须）**：
   - LONG：止盈价 > 开仓价（如开仓$67000，止盈$70000）
   - SHORT：止盈价 < 开仓价（如开仓$67000，止盈$64000）
   - 可设置多个目标：[$68500, $70000, $72000]用于分批止盈
   
   **订单类型选择（Market或Limit）**：
   
   使用**市价单（Market）**的场景：
   - ✓ 趋势强劲突破，需立即入场，不能等待
   - ✓ 关键位置机会稍纵即逝
   - ✓ 市场快速变化，等待可能错过
   - ✓ 流动性充足，滑点可控
   
   使用**限价单（Limit）**的场景：
   - ✓ 市场震荡，可等待回调/反弹到更好价位
   - ✓ 接近支撑/阻力，等待测试后确认入场
   - ✓ 追求更优成本，提高盈亏比
   - ✓ 不急于入场，有耐心等待更好价格
   
   **移动止盈止损（Trailing Stop）**⭐：
   - **移动止损原理**：当价格向有利方向移动时，自动调整止损位，锁定利润
   - **触发条件**：价格向有利方向移动超过1个ATR
   - **移动距离**：止损跟随价格移动，保持ATR×1.5的距离
   - **好处**：既能保护利润，又能捕捉大趋势
   - **示例**：
     * 做多开仓$67000，初始止损$66500（-0.75%）
     * 价格涨到$68000，止损移至$67500（保证盈利+0.75%）
     * 价格涨到$69000，止损移至$68500（盈利锁定+2.2%）
     * 如价格回落触发止损$68500，仍盈利$1500
   
   **风险收益比计算**：
   - 趋势行情盈亏比 ≥ 2:1
   - **震荡行情盈亏比 ≥ 1.5:1 即可**（因为波段频繁，累积收益）
   - LONG: (止盈价-开仓价) / (开仓价-止损价)
   - SHORT: (开仓价-止盈价) / (止损价-开仓价)
   
   **震荡行情止盈止损设置（重要）**：
   - **止盈**：设在震荡区间的另一端（如在支撑做多，止盈设在阻力）
   - **止损**：设在震荡区间外（如在支撑做多，止损设在支撑下方2-3%）
   - **快速平仓**：震荡行情追求快进快出，不要贪心
   - **示例**：
     * 震荡区间: $65000 ~ $68000
     * 在支撑$65200做多: 止损$64500(-1.1%), 止盈$67800(+4.0%), 盈亏比3.6:1
     * 在阻力$67800做空: 止损$68500(+1.0%), 止盈$65500(-3.4%), 盈亏比3.4:1
   
   **灵活管理**：
   - 你可以随时通过CLOSE动作主动平仓
   - 发现更好机会时可以止损换仓
   - 极端行情时系统会强制平仓保护

【决策输出格式】

请以JSON格式输出：
{
    "action": "LONG/SHORT/CLOSE/HOLD",
    "target_symbol": "BTCUSDT_PERPETUAL/ETHUSDT_PERPETUAL/SOLUSDT_PERPETUAL",
    "reason": "详细分析理由（包括资产选择、时间框架分析、做多/做空依据、订单类型选择理由、止盈止损依据）",
    "confidence": 0-100,
    "position_size": 0.05-0.30,  // 单个资产5%-30%，注意总仓位≤30%
    "leverage": 1-15,  // 杠杆倍数
    
    // 订单设置（仅LONG/SHORT动作需要）
    "order_type": "Market/Limit",  // 市价单或限价单
    "entry_price": 67234.5,  // 期望开仓价格（Market单设为当前价或0表示立即成交）
    "stop_loss": 65500.0,  // 止损价格（必须设置）
    "take_profit": [68500, 70000, 72000],  // 止盈价格（可单个或多个目标）
    
    // 市场分析
    "market_state": "trend_up/trend_down/range_support/range_resistance/transition/volatile",
    // range_support: 震荡行情且价格在支撑位附近（适合做多）
    // range_resistance: 震荡行情且价格在阻力位附近（适合做空）
    "asset_comparison": {
        "BTC": {"score": 0-100, "trend": "bull/bear/neutral/range"},
        "ETH": {"score": 0-100, "trend": "bull/bear/neutral/range"},
        "SOL": {"score": 0-100, "trend": "bull/bear/neutral/range"}
    }
}

**输出要求**：
- action为LONG/SHORT时，必须提供：order_type, entry_price, stop_loss, take_profit, leverage
- action为CLOSE时，只需提供：action, target_symbol, reason
- action为HOLD时，只需提供：action, reason
- entry_price为0表示市价单立即成交
- take_profit可以是单个价格或数组[价格1, 价格2, 价格3]
- 确保盈亏比 ≥ 2:1
- confidence反映决策信心，影响仓位大小

【交易纪律】
- 永远选择信号最强的资产和方向（做多或做空）
- **熊市做空，牛市做多，震荡做波段 - 顺势而为**
- 看不懂就不做，宁可错过
- 严格止损，保护本金
- 盈利后保护利润
- 追求质量而非数量
- **不要对市场方向有偏见，数据说什么就做什么**

【平仓决策要求】⚠️

⚠️ **重要警告**：由于已移除持仓保护限制，你现在可以随时平仓。但为避免频繁交易和过早平仓，请严格遵守以下平仓标准：

**平仓必须满足以下条件之一**：

1. **宏观趋势明确反转**（4小时级别）
   - 4小时趋势明确改变方向
   - 不仅仅是15分钟的短期回调或震荡
   - 多根4小时K线确认反转形态
   - EMA_21/EMA_50在4小时级别发生交叉

2. **止损条件明确触发**
   - 价格突破关键支撑/阻力位
   - 技术形态（头肩顶、双顶等）明确破坏
   - 价格跌破/突破多个时间框架的关键位置
   - ATR止损位被触及

3. **止盈目标已达成**
   - 价格到达预设的止盈位置
   - 移动止损已经锁定足够利润
   - 盈利达到入场时预期的目标（如+5%、+10%等）
   - 盈亏比已达到或超过预期（如2:1、3:1）

4. **极端市场风险出现**
   - 市场出现暴跌/暴涨/闪崩
   - 成交量异常萎缩，流动性枯竭
   - 出现重大负面消息或突发事件
   - 多个资产同时大幅下跌（系统性风险）

5. **更优质的机会出现**
   - 发现另一个资产有更明确的信号
   - 新机会的盈亏比明显更优（至少好50%）
   - 需要释放仓位额度（总仓位接近30%限制）

**⚠️ 必须避免以下情况**：
- ❌ 仅因15分钟小幅回调就平仓
- ❌ 因短期震荡、盘整就频繁平仓
- ❌ 无明确理由的随意平仓
- ❌ 刚开仓几分钟就因小幅波动而平仓
- ❌ 4小时趋势未变，仅1小时或15分钟波动就平仓
- ❌ 盈利未达到预期就提前平仓（除非有明确反转信号）

**正确的平仓思路**：
✓ 先检查4小时趋势是否真的改变
✓ 对比开仓时的理由是否仍然成立
✓ 评估当前是正常回调还是趋势反转
✓ 考虑移动止损是否已经保护了利润
✓ 权衡是否值得放弃当前持仓

**平仓决策流程**：
1. 检查4小时级别趋势是否反转 → 如果未反转，继续持有
2. 检查1小时级别是否出现明确破位 → 如果仅是震荡，继续持有
3. 评估15分钟波动是否只是短期调整 → 短期调整不应平仓
4. 确认是否有更优质的机会 → 机会质量必须明显更好
5. 最终决策：只有满足上述严格条件时才平仓

**目标**：提高持仓质量和持有时长，避免因小波动而过早平仓，让利润充分奔跑。
"""
    
    @staticmethod
    def build_prompt_header(current_time: str, position_info: Dict) -> str:
        """
        构建提示词头部
        
        Args:
            current_time: 当前时间字符串
            position_info: 持仓信息字典
            
        Returns:
            str: 提示词头部
        """
        return f"""
【当前时间】{current_time}
【账户状态】余额: {position_info.get('balance', 0):.2f} USDT

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【多资产市场概览】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    @staticmethod
    def build_position_status(position_info: Dict) -> str:
        """
        构建持仓状况部分
        
        Args:
            position_info: 持仓信息字典
            
        Returns:
            str: 持仓状况文本
        """
        return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【当前持仓状况】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

持仓资产: {position_info.get('current_symbol', 'NONE')}
持仓方向: {position_info.get('position', 'NONE')}
入场价格: {position_info.get('entry_price', 0):.2f} USDT
当前杠杆: {position_info.get('leverage', 0):.0f}x
持仓数量: {position_info.get('position_size', 0):.4f}
未实现盈亏: {position_info.get('unrealized_pnl', 0):.2f} USDT ({position_info.get('unrealized_pnl_pct', 0):.2f}%)
账户余额: {position_info.get('balance', 0):.2f} USDT

**决策提示**：
- 杠杆范围: 10-20x（根据市场状况自主选择）
- 仓位限制: 最大30%（系统自动限制）
- 止盈止损: 完全由你决定何时平仓（CLOSE动作）
- 你可以随时评估持仓，并根据市场变化决定继续持有或平仓
"""
    
    @staticmethod
    def build_decision_requirements() -> str:
        """
        构建决策要求部分
        
        Returns:
            str: 决策要求文本
        """
        return """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【决策要求】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

你是一位经验丰富的专业交易员，请综合分析以上所有市场数据，自主做出交易决策：

🎯 **核心分析要点**：

1. **多资产机会识别**
   - 综合评估BTC/ETH/SOL的技术面、市场情绪、资金流向
   - 识别哪个资产当前机会最佳、风险最可控
   - 考虑趋势强度、动量、波动率、流动性

2. **多时间框架共振分析**
   - 分析4小时（战略）、1小时（战术）、15分钟（入场）三个时间框架
   - 判断各时间框架的趋势方向、强度、一致性
   - 识别时间框架共振或分歧

3. **技术指标综合判断**
   - 趋势指标：EMA排列、价格位置
   - 动量指标：RSI、MACD的方向和强度
   - 波动率指标：布林带、ATR
   - K线形态：反转形态、持续形态、支撑阻力

4. **市场情绪与资金流向**
   - 资金费率：是否多空拥挤
   - 持仓量变化：资金流入还是流出
   - 多空比：市场情绪倾向
   - 成交量：是否放量突破或缩量整理

5. **交易决策制定**
   - **做多时机**：自主判断多头趋势确立、入场时机成熟
   - **做空时机**：自主判断空头趋势确立、入场时机成熟
   - **观望条件**：趋势不明、信号混杂、风险过高
   - **平仓判断**：盈利目标达成、止损触发、趋势改变

6. **仓位与杠杆管理**
   - **仓位大小**：根据机会质量和风险程度（0.05-0.30）
   - **杠杆选择**：根据信号强度和波动率（10-20倍）
     * 多时间框架完全共振 + 低波动 → 高杠杆（15-20倍）
     * 时间框架部分一致 + 中波动 → 中杠杆（12-15倍）
     * 信号较弱或高波动 → 低杠杆（10-12倍）
   - **风险收益比**：至少1:2，优先1:3以上

7. **止损止盈策略**
   - **止损位**：基于ATR、关键支撑阻力、风险承受度
   - **止盈位**：基于阻力位、前高前低、盈亏比优化
   - **分批止盈**：可设置多个止盈目标

⚠️ **重要原则**：
- 不要机械地套用规则，要灵活应变
- 市场环境不断变化，要持续评估
- 没有把握时宁可观望，不要强行交易
- 风险控制永远是第一位

📋 请以JSON格式输出你的决策，必须包含leverage字段（10-20之间的整数）。
"""
    
    @staticmethod
    def build_bybit_advanced_data_section(asset_name: str, advanced: Dict) -> str:
        """
        构建Bybit高级数据部分
        
        Args:
            asset_name: 资产名称（如BTC）
            advanced: 高级数据字典
            
        Returns:
            str: Bybit高级数据文本
        """
        section = f"""
【{asset_name} Bybit实时市场数据】⭐
资金费率: {advanced.get('funding_rate', 0):.4f}% (正值=多头付空头，负值=空头付多头)
持仓量: {advanced.get('open_interest', 0):.0f} 张 (价值: ${advanced.get('open_interest_value', 0):.0f})
"""
        
        # 多空比
        ls_ratio = advanced.get('long_short_ratio', {})
        if ls_ratio:
            buy_ratio = ls_ratio.get('buy_ratio', 0.5) * 100
            sell_ratio = ls_ratio.get('sell_ratio', 0.5) * 100
            section += f"多空比: 多{buy_ratio:.1f}% vs 空{sell_ratio:.1f}%\n"
        
        # 24小时涨跌和基差
        section += f"24小时涨跌: {advanced.get('price_24h_pcnt', 0):.2f}%\n"
        section += f"基差率: {advanced.get('basis_rate', 0):.4f}% (合约溢价/折价)\n"
        section += "\n⚠️ 请结合技术面综合分析这些市场数据，自主判断市场情绪和交易机会！\n"
        
        return section
    
    @staticmethod
    def format_kline_table(timeframe: str, klines: List, columns: List[str]) -> str:
        """
        将K线数据格式化为紧凑表格（从旧到新）
        
        Args:
            timeframe: 时间框架（如"4小时"）
            klines: K线数据列表
            columns: 要显示的列名列表
            
        Returns:
            str: 格式化的表格文本
        """
        if not klines:
            return f"【{timeframe}K线】无数据\n"
        
        # 表头
        col_names = {
            'open': '开盘', 'high': '最高', 'low': '最低', 'close': '收盘',
            'volume': '成交量', 'rsi': 'RSI', 'macd_hist': 'MACD柱',
            'macd': 'MACD', 'macd_signal': 'Signal',
            'ema_9': 'EMA9', 'ema_21': 'EMA21', 'ema_50': 'EMA50', 'ema_200': 'EMA200',
            'bb_upper': 'BB上', 'bb_middle': 'BB中', 'bb_lower': 'BB下', 'atr': 'ATR'
        }
        
        table = f"\n【{timeframe}K线数据】（{len(klines)}根，索引0=最旧，{len(klines)-1}=最新）\n"
        
        # 构建表头
        header = ["索引"] + [col_names.get(col, col) for col in columns]
        table += " | ".join(f"{h:>8}" for h in header) + "\n"
        table += "-" * (10 * (len(columns) + 1)) + "\n"
        
        # 数据行（从旧到新）
        for idx, kline in enumerate(klines):
            row = [f"{idx:>8}"]
            for col in columns:
                value = kline.get(col, 0)
                if value is None or (isinstance(value, float) and (value != value)):  # NaN check
                    row.append(f"{'N/A':>8}")
                elif col == 'volume':
                    row.append(f"{int(value):>8}")
                elif col in ['close', 'high', 'low', 'open']:
                    row.append(f"{value:>8.2f}")
                else:
                    row.append(f"{value:>8.2f}")
            table += " | ".join(row) + "\n"
        
        table += f"\n⚠️ 请基于以上K线数据自主分析：趋势方向、支撑阻力、动量变化、入场时机等\n"
        
        return table


# 快速访问接口
def get_system_prompt() -> str:
    """获取系统提示词（快捷方式）"""
    return AIPromptsManager.get_multi_asset_system_prompt()


def build_full_prompt(current_time: str, position_info: Dict, 
                      market_data: Dict, include_decision_req: bool = True) -> str:
    """
    构建完整的AI提示词
    
    Args:
        current_time: 当前时间字符串
        position_info: 持仓信息
        market_data: 市场数据
        include_decision_req: 是否包含决策要求部分
        
    Returns:
        str: 完整的提示词
    """
    manager = AIPromptsManager()
    
    parts = [
        manager.build_prompt_header(current_time, position_info),
        # market_data 部分需要在调用方处理
        manager.build_position_status(position_info),
    ]
    
    if include_decision_req:
        parts.append(manager.build_decision_requirements())
    
    return '\n'.join(parts)


# ==================== 日志系统 ====================

def setup_logging(log_dir: str = "logs", log_level: int = logging.INFO) -> str:
    """
    配置日志系统
    
    Args:
        log_dir: 日志目录
        log_level: 日志级别
        
    Returns:
        str: 日志文件路径
    """
    # 创建日志目录
    os.makedirs(log_dir, exist_ok=True)
    
    # 生成日志文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"live_trading_{timestamp}.log")
    
    # 创建logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # 清除已有的handlers（避免重复）
    logger.handlers.clear()
    
    # 文件处理器（带轮转）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=50*1024*1024,  # 50MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # 记录日志文件位置
    logger.info(f"{'='*80}")
    logger.info(f"日志系统已初始化")
    logger.info(f"日志文件: {log_file}")
    logger.info(f"日志级别: {logging.getLevelName(log_level)}")
    logger.info(f"{'='*80}")
    
    return log_file


# ==================== 极端市场保护 ====================

class ExtremeMarketProtection:
    """
    极端行情保护系统（完全兼容原版 deepseek_optimized_backtest.py）
    
    功能：
    1. 闪崩检测（单根K线跌幅>8%）
    2. 流动性危机检测（成交量骤降>70%）
    3. 波动率激增保护（ATR突增>150%）
    4. 多资产同步暴跌检测（3个资产同时跌>5%）
    5. 连续止损保护（短时间内多次止损）
    6. 最大单日亏损限制
    """
    
    def __init__(self):
        self.reset()
        
        # 配置阈值
        self.flash_crash_threshold = 0.08  # 闪崩阈值：8%单根K线跌幅
        self.volume_drop_threshold = 0.70  # 流动性危机：成交量骤降70%
        self.atr_surge_threshold = 1.50  # ATR突增：150%
        self.multi_asset_crash_threshold = 0.05  # 多资产同步暴跌：5%
        self.max_stops_in_period = 3  # 短期内最多3次止损
        self.stop_loss_window_hours = 4  # 4小时窗口
        self.max_daily_loss_pct = 15.0  # 单日最大亏损15%
        
    def reset(self):
        """重置保护状态"""
        self.recent_stop_losses = []  # 记录最近的止损时间
        self.daily_start_balance = None  # 当日起始余额
        self.current_day = None  # 当前日期
        self.protection_triggers = []  # 触发保护的记录
        
    def check_flash_crash(self, market_data: Dict) -> Tuple[bool, str]:
        """
        检测闪崩（单根K线极端下跌）
        
        Returns:
            (is_crash, reason)
        """
        data_15m = market_data.get('15m', {})
        open_price = data_15m.get('open', 0)
        close_price = data_15m.get('close', 0)
        low_price = data_15m.get('low', 0)
        
        if open_price <= 0:
            return False, ""
        
        # 检测单根K线跌幅
        candle_drop = (open_price - close_price) / open_price
        wick_drop = (open_price - low_price) / open_price
        
        if candle_drop > self.flash_crash_threshold:
            return True, f"闪崩预警：单根K线跌幅{candle_drop*100:.1f}%"
        
        if wick_drop > self.flash_crash_threshold * 1.5:
            return True, f"极端下影线：跌幅{wick_drop*100:.1f}%"
        
        return False, ""
    
    def check_liquidity_crisis(self, market_data: Dict, symbol: str) -> Tuple[bool, str]:
        """
        检测流动性危机（成交量骤降）
        
        改进：避免误判新K线刚开始时的低成交量
        - 检查K线时间，如果刚开始（<5分钟），不判断为流动性危机
        - 使用4小时成交量作为更稳定的基准
        """
        data_15m = market_data.get('15m', {})
        data_4h = market_data.get('4h', {})
        
        current_volume = data_15m.get('volume', 0)
        avg_volume_4h = data_4h.get('volume', 0)
        
        if avg_volume_4h <= 0:
            return False, ""
        
        # 检查K线是否刚开始
        try:
            timestamp = market_data.get('timestamp')
            if timestamp:
                current_time = timestamp if isinstance(timestamp, datetime) else datetime.now()
                current_minute = current_time.minute
                minute_in_period = current_minute % 15
                if minute_in_period < 5:
                    return False, ""
        except:
            pass
        
        # 使用4小时平均成交量作为基准
        expected_volume_15m = avg_volume_4h / 16
        
        if current_volume < expected_volume_15m * (1 - self.volume_drop_threshold):
            volume_drop_pct = (1 - current_volume / expected_volume_15m) * 100
            if current_volume < expected_volume_15m * 0.1:
                return False, ""
            return True, f"流动性危机：成交量骤降{volume_drop_pct:.1f}%"
        
        return False, ""
    
    def check_volatility_surge(self, market_data: Dict) -> Tuple[bool, str]:
        """检测波动率激增（ATR突然放大）"""
        data_15m = market_data.get('15m', {})
        data_4h = market_data.get('4h', {})
        
        atr_15m = data_15m.get('atr', 0)
        atr_4h = data_4h.get('atr', 0)
        
        if atr_4h > 0 and atr_15m > atr_4h * self.atr_surge_threshold:
            surge_pct = (atr_15m / atr_4h - 1) * 100
            return True, f"波动率激增：ATR增加{surge_pct:.1f}%"
        
        return False, ""
    
    def check_multi_asset_crash(self, all_market_data: Dict[str, Dict]) -> Tuple[bool, str]:
        """检测多资产同步暴跌（系统性风险）"""
        crash_count = 0
        crash_details = []
        
        for symbol, market_data in all_market_data.items():
            data_15m = market_data.get('15m', {})
            open_price = data_15m.get('open', 0)
            close_price = data_15m.get('close', 0)
            
            if open_price <= 0:
                continue
            
            drop_pct = (open_price - close_price) / open_price
            
            if drop_pct > self.multi_asset_crash_threshold:
                asset_name = symbol.replace('USDT_PERPETUAL', '')
                crash_count += 1
                crash_details.append(f"{asset_name}(-{drop_pct*100:.1f}%)")
        
        if crash_count >= 2:
            return True, f"多资产暴跌：{', '.join(crash_details)}"
        
        return False, ""
    
    def check_consecutive_stops(self, timestamp: str) -> Tuple[bool, str]:
        """检测短时间内连续止损"""
        current_time = pd.to_datetime(timestamp)
        
        window_start = current_time - timedelta(hours=self.stop_loss_window_hours)
        self.recent_stop_losses = [
            t for t in self.recent_stop_losses 
            if t > window_start
        ]
        
        if len(self.recent_stop_losses) >= self.max_stops_in_period:
            return True, f"{self.stop_loss_window_hours}小时内连续{len(self.recent_stop_losses)}次止损"
        
        return False, ""
    
    def record_stop_loss(self, timestamp: str):
        """记录止损事件"""
        self.recent_stop_losses.append(pd.to_datetime(timestamp))
    
    def check_max_daily_loss(self, current_balance: float, timestamp: str) -> Tuple[bool, str]:
        """检测单日亏损是否超限"""
        current_date = pd.to_datetime(timestamp).date()
        
        if self.current_day != current_date:
            self.current_day = current_date
            self.daily_start_balance = current_balance
            return False, ""
        
        if self.daily_start_balance is None:
            self.daily_start_balance = current_balance
            return False, ""
        
        daily_loss_pct = (self.daily_start_balance - current_balance) / self.daily_start_balance * 100
        
        if daily_loss_pct > self.max_daily_loss_pct:
            return True, f"单日亏损{daily_loss_pct:.1f}%超限（阈值{self.max_daily_loss_pct}%）"
        
        return False, ""
    
    def comprehensive_check(self, all_market_data: Dict[str, Dict], 
                          current_balance: float, 
                          timestamp: str,
                          has_position: bool,
                          current_symbol: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        综合检查所有极端行情保护
        
        Returns:
            (should_protect, reasons): (是否应该触发保护, 触发原因列表)
        """
        reasons = []
        
        # 1. 检查多资产同步暴跌（优先级最高）
        is_crash, reason = self.check_multi_asset_crash(all_market_data)
        if is_crash:
            reasons.append(f"🚨 {reason}")
            self.protection_triggers.append({
                'timestamp': timestamp,
                'type': 'multi_asset_crash',
                'reason': reason
            })
        
        # 2. 检查当前持仓资产的闪崩
        if has_position and current_symbol and current_symbol in all_market_data:
            is_flash_crash, reason = self.check_flash_crash(all_market_data[current_symbol])
            if is_flash_crash:
                reasons.append(f"⚡ {reason}")
                self.protection_triggers.append({
                    'timestamp': timestamp,
                    'type': 'flash_crash',
                    'reason': reason
                })
            
            # 3. 检查流动性危机
            is_liquidity_crisis, reason = self.check_liquidity_crisis(
                all_market_data[current_symbol], 
                current_symbol
            )
            if is_liquidity_crisis:
                reasons.append(f"💧 {reason}")
                self.protection_triggers.append({
                    'timestamp': timestamp,
                    'type': 'liquidity_crisis',
                    'reason': reason
                })
            
            # 4. 检查波动率激增
            is_volatility_surge, reason = self.check_volatility_surge(all_market_data[current_symbol])
            if is_volatility_surge:
                reasons.append(f"📈 {reason}")
                self.protection_triggers.append({
                    'timestamp': timestamp,
                    'type': 'volatility_surge',
                    'reason': reason
                })
        
        # 5. 检查连续止损
        is_consecutive_stops, reason = self.check_consecutive_stops(timestamp)
        if is_consecutive_stops:
            reasons.append(f"🔴 {reason}")
            self.protection_triggers.append({
                'timestamp': timestamp,
                'type': 'consecutive_stops',
                'reason': reason
            })
        
        # 如果有任何保护触发，返回True
        should_protect = len(reasons) > 0
        
        return should_protect, reasons
    
    def get_protection_stats(self) -> Dict:
        """获取保护系统统计"""
        stats = {
            'total_triggers': len(self.protection_triggers),
            'triggers_by_type': {}
        }
        
        for trigger in self.protection_triggers:
            ttype = trigger['type']
            if ttype not in stats['triggers_by_type']:
                stats['triggers_by_type'][ttype] = 0
            stats['triggers_by_type'][ttype] += 1
        
        return stats


# ==================== AI 决策引擎 ====================

class LiveTradingAIEngine:
    """
    实盘交易AI决策引擎
    使用 AIPromptsManager 提供的提示词模板
    """
    
    def __init__(self, config_file: str = "deepseek_config.json"):
        """
        初始化AI决策引擎
        
        Args:
            config_file: DeepSeek配置文件路径
        """
        # 加载配置
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 检查API密钥
        api_key = self.config.get('deepseek_api_key', '')
        if not api_key or api_key == 'YOUR_DEEPSEEK_API_KEY_HERE':
            raise ValueError("请配置 DeepSeek API Key")
        
        # 初始化OpenAI客户端
        if OpenAI is None:
            raise ImportError("请安装 openai 库: pip install openai")
        
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.config.get('deepseek_base_url', 'https://api.deepseek.com/v1')
        )
        
        # AI参数
        self.model = self.config.get('model', 'deepseek-chat')
        self.temperature = self.config.get('temperature', 0.7)
        self.max_tokens = self.config.get('max_tokens', 1500)
        
        # 缓存系统（提高效率）
        self.cache = OrderedDict()
        self.cache_hits = 0
        self.total_calls = 0
        self.max_cache_size = 100  # 实盘交易缓存较小
        self.cache_ttl = 300  # 5分钟缓存
        
        # 提示词管理器
        self.prompts_manager = AIPromptsManager()
        
        logging.info(f"✓ AI决策引擎初始化完成 (模型: {self.model})")
    
    def make_multi_asset_decision(
        self,
        all_market_data: Dict[str, Dict],
        position_info: Dict,
        current_sample_idx: int = 0,
        save_prompt: bool = False
    ) -> Dict:
        """
        多资产AI决策（完全兼容 MultiAssetDeepSeekTrader）
        
        Args:
            all_market_data: 所有资产的市场数据
            position_info: 持仓信息
            current_sample_idx: 当前样本索引（用于缓存和时间衰减）
            save_prompt: 是否保存提示词（默认False）
            
        Returns:
            Dict: 决策结果
        """
        # 生成缓存键
        cache_key = self._generate_cache_key(all_market_data, position_info)
        
        # 检查缓存（带时间衰减 - 与原版一致）
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            cached_sample_idx = cache_entry.get('sample_idx', 0)
            cached_decision = cache_entry.get('decision')
            
            # 检查缓存是否过期（样本间隔超过4个）
            sample_diff = current_sample_idx - cached_sample_idx
            if sample_diff <= 4:  # cache_ttl_samples = 4
                # 缓存仍然有效
                self.cache_hits += 1
                # LRU：将访问的项移到末尾
                self.cache.move_to_end(cache_key)
                logging.debug(f"⚡ 缓存命中 (age: {sample_diff} samples)")
                return cached_decision
            else:
                # 缓存已过期，删除旧缓存
                del self.cache[cache_key]
                logging.debug(f"缓存过期 (age: {sample_diff} samples > 4)")
        
        self.total_calls += 1
        
        try:
            # 构建提示词
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 构建用户提示词
            user_prompt = self._build_user_prompt(all_market_data, position_info, current_time)
            
            # 获取系统提示词
            system_prompt = self.prompts_manager.get_multi_asset_system_prompt()
            
            # 调用AI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            content = response.choices[0].message.content.strip()
            
            # 解析决策
            decision = self._parse_decision(content)
            
            # 保存提示词和数据（如果需要）
            if save_prompt or decision.get('action') in ['LONG', 'SHORT', 'CLOSE']:
                self._save_ai_prompt_and_data(user_prompt, all_market_data, position_info, decision)
            
            # 缓存高置信度决策（与原版一致）
            if decision.get('confidence', 0) > 70:
                if len(self.cache) >= self.max_cache_size:
                    # 删除最久未使用的项（OrderedDict的第一项）
                    self.cache.popitem(last=False)
                
                # 存储决策和样本索引（用于时间衰减）
                try:
                    timestamp = str(list(all_market_data.values())[0].get('timestamp', ''))
                except (IndexError, KeyError, AttributeError):
                    timestamp = 'unknown'
                
                self.cache[cache_key] = {
                    'decision': decision,
                    'sample_idx': current_sample_idx,
                    'created_at': timestamp
                }
            
            return decision
            
        except Exception as e:
            logging.error(f"AI决策失败: {e}")
            return {
                'action': 'HOLD',
                'target_symbol': None,
                'reason': f'API错误: {str(e)}',
                'confidence': 0,
                'position_size': 0.10,
                'leverage': 15,
                'market_state': 'unknown'
            }
    
    def _generate_cache_key(self, all_market_data: Dict[str, Dict], 
                           position_info: Dict) -> str:
        """
        生成缓存键（与原版 MultiAssetDeepSeekTrader 一致）
        """
        key_parts = []
        
        # 每个资产的趋势状态
        for symbol, market_data in all_market_data.items():
            asset_name = symbol.replace('USDT_PERPETUAL', '')[:3]
            
            # 4小时趋势
            data_4h = market_data.get('4h', {})
            close = data_4h.get('close', 0)
            ema_50 = data_4h.get('ema_50', 0)
            ema_200 = data_4h.get('ema_200', 0)
            rsi = data_4h.get('rsi', 50)
            macd_hist = data_4h.get('macd_hist', 0)
            
            # 趋势判断
            if close > ema_50 and ema_50 > ema_200:
                trend = "bull"
            elif close < ema_50 and ema_50 < ema_200:
                trend = "bear"
            else:
                trend = "neutral"
            
            # RSI区间
            if rsi > 70:
                rsi_zone = "overbought"
            elif rsi < 30:
                rsi_zone = "oversold"
            else:
                rsi_zone = "normal"
            
            # MACD状态
            macd_state = "pos" if macd_hist > 0 else "neg"
            
            # 价格区间（按10%分组，避免缓存过于精细）
            price_bucket = int(close / (close * 0.1)) if close > 0 else 0
            
            key_parts.append(f"{asset_name}_{trend}_{rsi_zone}_{macd_state}_{price_bucket}")
        
        # 持仓状态
        has_position = position_info.get('current_symbol', 'NONE') != 'NONE'
        position_type = position_info.get('position', 'NONE')
        key_parts.append(f"pos_{has_position}_{position_type}")
        
        return "_".join(key_parts)
    
    def _save_ai_prompt_and_data(self, prompt: str, all_market_data: Dict, 
                                 position_info: Dict, decision: Dict = None):
        """
        保存AI提示词和技术指标到独立文件（与原版一致）
        """
        try:
            # 创建保存目录
            save_dir = "ai_prompts"
            os.makedirs(save_dir, exist_ok=True)
            
            # 生成文件名（带时间戳）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 保存完整数据
            data_to_save = {
                'timestamp': datetime.now().isoformat(),
                'prompt': prompt,
                'market_data': all_market_data,
                'position_info': position_info,
                'decision': decision
            }
            
            # 保存为JSON
            filename = os.path.join(save_dir, f"ai_prompt_{timestamp}.json")
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2, default=str)
            
            logging.debug(f"已保存AI提示词和数据: {filename}")
            
        except Exception as e:
            logging.warning(f"保存AI提示词失败: {e}")
    
    def _build_user_prompt(
        self,
        all_market_data: Dict[str, Dict],
        position_info: Dict,
        current_time: str
    ) -> str:
        """
        构建用户提示词
        
        Args:
            all_market_data: 所有资产的市场数据
            position_info: 持仓信息
            current_time: 当前时间
            
        Returns:
            str: 完整的用户提示词
        """
        # 构建头部
        header = self.prompts_manager.build_prompt_header(current_time, position_info)
        
        # 构建市场概览
        market_overview = ""
        for symbol, market_data in all_market_data.items():
            asset_name = symbol.replace('USDT_PERPETUAL', '').replace('_PERPETUAL', '')
            market_overview += self._build_asset_section(asset_name, market_data)
        
        # 构建持仓状态
        position_status = self.prompts_manager.build_position_status(position_info)
        
        # 构建决策要求
        decision_req = self.prompts_manager.build_decision_requirements()
        
        return header + market_overview + position_status + decision_req
    
    def _build_asset_section(self, asset_name: str, market_data: Dict) -> str:
        """
        构建单个资产的市场数据部分
        
        Args:
            asset_name: 资产名称
            market_data: 市场数据
            
        Returns:
            str: 格式化的资产数据
        """
        section = f"\n▼ {asset_name} 市场数据\n"
        
        # 获取最新数据
        data_15m = market_data.get('15m', {})
        data_1h = market_data.get('1h', {})
        data_4h = market_data.get('4h', {})
        
        # 基础价格信息
        current_price = data_15m.get('close', 0)
        section += f"当前价格: ${current_price:.2f}\n"
        
        # 技术指标（15分钟）
        section += f"\n【15分钟指标】\n"
        section += f"RSI: {data_15m.get('rsi', 0):.1f} | "
        section += f"MACD: {data_15m.get('macd_hist', 0):.2f} | "
        section += f"成交量: {int(data_15m.get('volume', 0)):,}\n"
        
        # 技术指标（1小时）
        section += f"\n【1小时指标】\n"
        section += f"RSI: {data_1h.get('rsi', 0):.1f} | "
        section += f"MACD: {data_1h.get('macd_hist', 0):.2f} | "
        section += f"EMA21: ${data_1h.get('ema_21', 0):.2f} | "
        section += f"EMA50: ${data_1h.get('ema_50', 0):.2f}\n"
        
        # 技术指标（4小时）
        section += f"\n【4小时指标】\n"
        section += f"RSI: {data_4h.get('rsi', 0):.1f} | "
        section += f"MACD: {data_4h.get('macd_hist', 0):.2f} | "
        section += f"EMA50: ${data_4h.get('ema_50', 0):.2f} | "
        section += f"EMA200: ${data_4h.get('ema_200', 0):.2f}\n"
        section += f"ATR: {data_4h.get('atr', 0):.2f} | "
        section += f"布林带: ${data_4h.get('bb_lower', 0):.2f} - ${data_4h.get('bb_upper', 0):.2f}\n"
        
        # Bybit高级数据（如果有）
        advanced = market_data.get('advanced_data', {})
        if advanced:
            section += self.prompts_manager.build_bybit_advanced_data_section(asset_name, advanced)
        
        section += "\n"
        return section
    
    def _parse_decision(self, content: str) -> Dict:
        """
        解析AI决策
        
        Args:
            content: AI返回的文本
            
        Returns:
            Dict: 解析后的决策
        """
        try:
            # 提取JSON
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1:
                json_str = content[start:end+1]
                decision = json.loads(json_str)
                
                # 确保有默认值
                decision.setdefault('action', 'HOLD')
                decision.setdefault('target_symbol', None)
                decision.setdefault('reason', '无理由')
                decision.setdefault('confidence', 0)
                decision.setdefault('position_size', 0.10)
                decision.setdefault('leverage', 15)
                decision.setdefault('market_state', 'unknown')
                
                return decision
            else:
                raise ValueError("未找到JSON格式")
                
        except Exception as e:
            logging.warning(f"解析AI决策失败: {e}")
            return {
                'action': 'HOLD',
                'target_symbol': None,
                'reason': f'解析失败: {str(e)}',
                'confidence': 0,
                'position_size': 0.10,
                'leverage': 15,
                'market_state': 'unknown'
            }


# ==================== 别名（确保向后兼容）====================

# 为实盘交易系统提供兼容别名
MultiAssetDeepSeekTrader = LiveTradingAIEngine


# ==================== 测试代码 ====================

if __name__ == '__main__':
    """测试提示词管理器和交易组件"""
    import sys
    import io
    
    # 设置UTF-8输出编码（解决Windows中文显示问题）
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("=" * 80)
    print("AI 提示词管理器和交易组件 - 测试")
    print("=" * 80)
    
    # 1. 测试系统提示词
    print("\n【测试1: 提示词管理器】")
    system_prompt = get_system_prompt()
    print(f"系统提示词长度: {len(system_prompt)} 字符")
    print(f"系统提示词前200字符:\n{system_prompt[:200]}...\n")
    
    # 2. 测试日志系统
    print("\n【测试2: 日志系统】")
    log_file = setup_logging(log_dir="logs", log_level=logging.INFO)
    print(f"✓ 日志系统初始化成功: {log_file}\n")
    
    # 3. 测试极端市场保护
    print("\n【测试3: 极端市场保护】")
    protection = ExtremeMarketProtection()
    test_all_market_data = {
        'BTCUSDT_PERPETUAL': {
            '15m': {'close': 67000, 'open': 66900, 'rsi': 55, 'atr': 500, 'volume': 1000},
            '1h': {'close': 66800, 'rsi': 52, 'atr': 600, 'volume': 5000},
            '4h': {'close': 66500, 'rsi': 50, 'atr': 700, 'volume': 20000}
        }
    }
    should_protect, reasons = protection.comprehensive_check(
        all_market_data=test_all_market_data,
        current_balance=100.0,
        timestamp=datetime.now().isoformat(),
        has_position=False
    )
    print(f"✓ 市场保护检查完成")
    print(f"  需要保护: {should_protect}")
    print(f"  触发原因数: {len(reasons)}")
    if reasons:
        print(f"  原因: {reasons}\n")
    else:
        print(f"  市场状态正常\n")
    
    # 4. 测试AI引擎（如果有配置文件）
    print("\n【测试4: AI决策引擎】")
    if os.path.exists('deepseek_config.json'):
        try:
            engine = LiveTradingAIEngine('deepseek_config.json')
            print(f"✓ AI引擎初始化成功")
            print(f"  模型: {engine.model}")
            print(f"  温度: {engine.temperature}")
            print(f"  最大token: {engine.max_tokens}")
        except Exception as e:
            print(f"⚠️ AI引擎初始化失败: {e}")
    else:
        print("⚠️ 未找到 deepseek_config.json，跳过AI引擎测试")
    
    print("\n" + "=" * 80)
    print("所有测试完成！")
    print("=" * 80)

