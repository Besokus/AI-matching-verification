"""风控规则定义

三层风控规则：
1. Agent 规则层：仓位、集中度、涨跌停、频率
2. 系统熔断层：日亏损、连续亏损、置信度
3. 人工审批层：大额交易（Phase 2）
"""

from dataclasses import dataclass
from abc import ABC, abstractmethod

from ..graph.state import OrderDecision, RiskDecision


@dataclass
class RuleResult:
    """规则检查结果"""
    passed: bool
    reason: str
    adjusted_order: OrderDecision | None = None


class BaseRule(ABC):
    """规则基类"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def evaluate(self, decision: OrderDecision, context: dict) -> RuleResult:
        """评估规则

        Args:
            decision: 订单决策
            context: 上下文（持仓、资金、历史交易等）

        Returns:
            RuleResult
        """
        pass


# ===== Layer 1: Agent 规则 =====


class MaxPositionRule(BaseRule):
    """单笔最大仓位限制"""

    def __init__(self, max_pct: float = 0.10):
        super().__init__("MaxPosition")
        self.max_pct = max_pct  # 默认 10%

    def evaluate(self, decision: OrderDecision, context: dict) -> RuleResult:
        if decision.action == "HOLD":
            return RuleResult(passed=True, reason="HOLD 无需检查")

        total_capital = context.get("total_capital", 1_000_000)
        order_value = decision.price * decision.volume

        if order_value > total_capital * self.max_pct:
            # 调整到最大允许值
            max_volume = int((total_capital * self.max_pct) / decision.price / 100) * 100
            if max_volume > 0:
                adjusted = OrderDecision(
                    action=decision.action,
                    security_id=decision.security_id,
                    price=decision.price,
                    volume=max_volume,
                    order_type=decision.order_type,
                    confidence=decision.confidence,
                    reason=decision.reason + f" [仓位调整: {decision.volume} → {max_volume}]",
                )
                return RuleResult(
                    passed=True,
                    reason=f"仓位超限，已调整: {decision.volume} → {max_volume}",
                    adjusted_order=adjusted,
                )
            else:
                return RuleResult(passed=False, reason=f"仓位超限且无法调整: {order_value:.0f} > {total_capital * self.max_pct:.0f}")

        return RuleResult(passed=True, reason="仓位检查通过")


class ConcentrationRule(BaseRule):
    """单股票集中度限制"""

    def __init__(self, max_pct: float = 0.30):
        super().__init__("Concentration")
        self.max_pct = max_pct  # 默认 30%

    def evaluate(self, decision: OrderDecision, context: dict) -> RuleResult:
        if decision.action == "HOLD":
            return RuleResult(passed=True, reason="HOLD 无需检查")

        total_capital = context.get("total_capital", 1_000_000)
        position = context.get("position", {})
        current_value = position.get("volume", 0) * position.get("avg_price", 0)
        order_value = decision.price * decision.volume

        if decision.action == "BUY":
            new_value = current_value + order_value
        else:
            new_value = current_value - order_value

        if new_value > total_capital * self.max_pct:
            return RuleResult(
                passed=False,
                reason=f"集中度超限: {new_value:.0f} > {total_capital * self.max_pct:.0f}",
            )

        return RuleResult(passed=True, reason="集中度检查通过")


class LimitPriceRule(BaseRule):
    """涨跌停限制"""

    def __init__(self, limit_pct: float = 0.10):
        super().__init__("LimitPrice")
        self.limit_pct = limit_pct  # A 股涨跌停 10%

    def evaluate(self, decision: OrderDecision, context: dict) -> RuleResult:
        if decision.action == "HOLD":
            return RuleResult(passed=True, reason="HOLD 无需检查")

        last_close = context.get("last_close", decision.price)
        upper_limit = last_close * (1 + self.limit_pct)
        lower_limit = last_close * (1 - self.limit_pct)

        if decision.action == "BUY" and decision.price >= upper_limit:
            return RuleResult(
                passed=False,
                reason=f"涨停追买禁止: {decision.price:.2f} >= {upper_limit:.2f}",
            )

        if decision.action == "SELL" and decision.price <= lower_limit:
            return RuleResult(
                passed=False,
                reason=f"跌停追卖禁止: {decision.price:.2f} <= {lower_limit:.2f}",
            )

        return RuleResult(passed=True, reason="涨跌停检查通过")


class MinVolumeRule(BaseRule):
    """最小交易量限制"""

    def __init__(self, min_volume: int = 100):
        super().__init__("MinVolume")
        self.min_volume = min_volume  # 1 手 = 100 股

    def evaluate(self, decision: OrderDecision, context: dict) -> RuleResult:
        if decision.action == "HOLD":
            return RuleResult(passed=True, reason="HOLD 无需检查")

        if decision.volume < self.min_volume:
            return RuleResult(
                passed=False,
                reason=f"交易量不足: {decision.volume} < {self.min_volume}",
            )

        return RuleResult(passed=True, reason="最小交易量检查通过")


class FrequencyRule(BaseRule):
    """交易频率限制"""

    def __init__(self, max_per_minute: int = 3):
        super().__init__("Frequency")
        self.max_per_minute = max_per_minute

    def evaluate(self, decision: OrderDecision, context: dict) -> RuleResult:
        if decision.action == "HOLD":
            return RuleResult(passed=True, reason="HOLD 无需检查")

        recent_trades = context.get("recent_trades_count", 0)
        if recent_trades >= self.max_per_minute:
            return RuleResult(
                passed=False,
                reason=f"交易频率超限: {recent_trades} >= {self.max_per_minute}/分钟",
            )

        return RuleResult(passed=True, reason="频率检查通过")


# ===== Layer 2: 系统熔断 =====


class DailyLossRule(BaseRule):
    """单日最大亏损限制"""

    def __init__(self, max_loss_pct: float = 0.05):
        super().__init__("DailyLoss")
        self.max_loss_pct = max_loss_pct  # 默认 -5%

    def evaluate(self, decision: OrderDecision, context: dict) -> RuleResult:
        if decision.action == "HOLD":
            return RuleResult(passed=True, reason="HOLD 无需检查")

        daily_pnl = context.get("daily_pnl", 0)
        total_capital = context.get("total_capital", 1_000_000)

        if daily_pnl < -total_capital * self.max_loss_pct:
            return RuleResult(
                passed=False,
                reason=f"单日亏损超限: {daily_pnl:.0f} < -{total_capital * self.max_loss_pct:.0f}",
            )

        return RuleResult(passed=True, reason="日亏损检查通过")


class ConsecutiveLossRule(BaseRule):
    """连续亏损限制"""

    def __init__(self, max_consecutive: int = 3):
        super().__init__("ConsecutiveLoss")
        self.max_consecutive = max_consecutive

    def evaluate(self, decision: OrderDecision, context: dict) -> RuleResult:
        if decision.action == "HOLD":
            return RuleResult(passed=True, reason="HOLD 无需检查")

        consecutive_losses = context.get("consecutive_losses", 0)
        if consecutive_losses >= self.max_consecutive:
            return RuleResult(
                passed=False,
                reason=f"连续亏损超限: {consecutive_losses} >= {self.max_consecutive}",
            )

        return RuleResult(passed=True, reason="连续亏损检查通过")


class ConfidenceRule(BaseRule):
    """置信度限制"""

    def __init__(self, min_confidence: float = 0.3):
        super().__init__("Confidence")
        self.min_confidence = min_confidence

    def evaluate(self, decision: OrderDecision, context: dict) -> RuleResult:
        if decision.action == "HOLD":
            return RuleResult(passed=True, reason="HOLD 无需检查")

        if decision.confidence < self.min_confidence:
            return RuleResult(
                passed=False,
                reason=f"置信度过低: {decision.confidence:.2f} < {self.min_confidence}",
            )

        return RuleResult(passed=True, reason="置信度检查通过")


class DataAnomalyRule(BaseRule):
    """数据异常检查"""

    def __init__(self):
        super().__init__("DataAnomaly")

    def evaluate(self, decision: OrderDecision, context: dict) -> RuleResult:
        if decision.action == "HOLD":
            return RuleResult(passed=True, reason="HOLD 无需检查")

        # 检查价格是否合理
        if decision.price <= 0:
            return RuleResult(passed=False, reason=f"价格异常: {decision.price}")

        # 检查成交量是否合理
        if decision.volume <= 0:
            return RuleResult(passed=False, reason=f"成交量异常: {decision.volume}")

        return RuleResult(passed=True, reason="数据异常检查通过")
