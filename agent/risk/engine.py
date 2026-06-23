"""风控规则引擎

确定性风控引擎，不使用 LLM。
三层风控：
1. Agent 规则层
2. 系统熔断层
3. 人工审批层（Phase 2）
"""

from dataclasses import dataclass, field

from ..graph.state import OrderDecision, RiskDecision
from .rules import (
    BaseRule, RuleResult,
    MaxPositionRule, ConcentrationRule, LimitPriceRule,
    MinVolumeRule, FrequencyRule,
    DailyLossRule, ConsecutiveLossRule, ConfidenceRule, DataAnomalyRule,
)


@dataclass
class RiskConfig:
    """风控配置"""
    # Layer 1: Agent 规则
    max_position_pct: float = 0.10  # 单笔最大仓位 10%
    max_concentration_pct: float = 0.30  # 单股集中度 30%
    limit_pct: float = 0.10  # 涨跌停 10%
    min_volume: int = 100  # 最小交易量（1 手）
    max_trades_per_minute: int = 3  # 每分钟最大交易次数

    # Layer 2: 系统熔断
    max_daily_loss_pct: float = 0.05  # 单日最大亏损 5%
    max_consecutive_losses: int = 3  # 连续亏损次数
    min_confidence: float = 0.3  # 最低置信度


class RiskEngine:
    """确定性风控引擎

    使用规则链检查订单决策，不依赖 LLM。
    """

    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()
        self.rules: list[BaseRule] = self._init_rules()

    def _init_rules(self) -> list[BaseRule]:
        """初始化规则链"""
        return [
            # Layer 1: Agent 规则
            DataAnomalyRule(),
            MaxPositionRule(self.config.max_position_pct),
            ConcentrationRule(self.config.max_concentration_pct),
            LimitPriceRule(self.config.limit_pct),
            MinVolumeRule(self.config.min_volume),
            FrequencyRule(self.config.max_trades_per_minute),

            # Layer 2: 系统熔断
            DailyLossRule(self.config.max_daily_loss_pct),
            ConsecutiveLossRule(self.config.max_consecutive_losses),
            ConfidenceRule(self.config.min_confidence),
        ]

    def check(self, decision: OrderDecision, context: dict) -> RiskDecision:
        """检查订单决策

        Args:
            decision: 订单决策
            context: 上下文信息
                - total_capital: 总资金
                - position: 当前持仓 {"volume": 0, "avg_price": 0}
                - daily_pnl: 当日盈亏
                - consecutive_losses: 连续亏损次数
                - recent_trades_count: 最近交易次数
                - last_close: 昨日收盘价

        Returns:
            RiskDecision
        """
        # HOLD 无需检查
        if decision.action == "HOLD":
            return RiskDecision(
                approved=True,
                reason="HOLD 无需风控检查",
            )

        # 逐条检查规则
        adjusted_order = decision
        for rule in self.rules:
            result = rule.evaluate(adjusted_order, context)
            if not result.passed:
                return RiskDecision(
                    approved=False,
                    reason=f"[{rule.name}] {result.reason}",
                )
            # 如果有调整后的订单，使用调整后的
            if result.adjusted_order:
                adjusted_order = result.adjusted_order

        # 检查是否有调整
        if adjusted_order != decision:
            return RiskDecision(
                approved=True,
                reason="风控通过（已调整）",
                adjusted_order=adjusted_order,
            )

        return RiskDecision(
            approved=True,
            reason="风控通过",
        )

    def add_rule(self, rule: BaseRule):
        """添加自定义规则"""
        self.rules.append(rule)

    def remove_rule(self, name: str):
        """移除规则"""
        self.rules = [r for r in self.rules if r.name != name]
