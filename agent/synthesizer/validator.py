"""合成质量验证器 - 验证合成 tick 数据的质量

验证标准：
1. OHLCV 一致性：合成 tick 经引擎回放后产生的 K 线应与原始分钟 K 线一致
2. 价格边界：所有价格在 [Low, High] 范围内
3. 成交量守恒：所有成交总量 = 该分钟 Volume
4. 时间因果：事件时间戳严格递增
5. 方向合理性：上涨分钟主动买 > 主动卖，下跌分钟相反
"""

from dataclasses import dataclass
from ..data.models.market import KLine, TickEvent


@dataclass
class ValidationResult:
    """验证结果"""
    passed: bool
    checks: dict[str, bool]  # {"check_name": passed}
    errors: list[str]  # 错误信息列表
    warnings: list[str]  # 警告信息列表


class SynthesisValidator:
    """合成质量验证器"""

    def __init__(self, price_tolerance: float = 0.001, volume_tolerance: float = 0.01):
        """
        Args:
            price_tolerance: 价格误差容忍度（相对误差）
            volume_tolerance: 成交量误差容忍度（相对误差）
        """
        self.price_tolerance = price_tolerance
        self.volume_tolerance = volume_tolerance

    def validate(
        self,
        original_klines: list[KLine],
        synthesized_events: list[TickEvent],
    ) -> ValidationResult:
        """验证合成 tick 数据质量

        Args:
            original_klines: 原始分钟 K 线
            synthesized_events: 合成逐笔事件

        Returns:
            验证结果
        """
        checks: dict[str, bool] = {}
        errors: list[str] = []
        warnings: list[str] = []

        # 按分钟分组事件
        events_by_minute = self._group_events_by_minute(synthesized_events)

        # 检查 1: 时间因果性
        checks["time_causality"] = self._check_time_causality(synthesized_events, errors)

        # 检查 2: 价格边界
        checks["price_bounds"] = self._check_price_bounds(original_klines, events_by_minute, errors)

        # 检查 3: 成交量守恒
        checks["volume_conservation"] = self._check_volume_conservation(
            original_klines, events_by_minute, errors
        )

        # 检查 4: OHLCV 一致性
        checks["ohlcv_consistency"] = self._check_ohlcv_consistency(
            original_klines, events_by_minute, errors
        )

        # 检查 5: 方向合理性
        checks["direction_reasonability"] = self._check_direction_reasonability(
            original_klines, events_by_minute, warnings
        )

        # 检查 6: 事件完整性
        checks["event_completeness"] = self._check_event_completeness(
            synthesized_events, errors
        )

        all_passed = all(checks.values())
        return ValidationResult(
            passed=all_passed,
            checks=checks,
            errors=errors,
            warnings=warnings,
        )

    def _group_events_by_minute(self, events: list[TickEvent]) -> dict[str, list[TickEvent]]:
        """将事件按分钟分组"""
        groups: dict[str, list[TickEvent]] = {}
        for event in events:
            key = event.timestamp.strftime("%Y-%m-%d %H:%M")
            if key not in groups:
                groups[key] = []
            groups[key].append(event)
        return groups

    def _check_time_causality(self, events: list[TickEvent], errors: list[str]) -> bool:
        """检查时间因果性：事件时间戳严格递增"""
        if len(events) < 2:
            return True

        for i in range(1, len(events)):
            if events[i].timestamp < events[i - 1].timestamp:
                errors.append(
                    f"时间因果性错误: 事件 {i} 的时间戳 ({events[i].timestamp}) "
                    f"早于事件 {i-1} ({events[i-1].timestamp})"
                )
                return False

        return True

    def _check_price_bounds(
        self,
        original_klines: list[KLine],
        events_by_minute: dict[str, list[TickEvent]],
        errors: list[str],
    ) -> bool:
        """检查价格边界：所有价格在 [Low, High] 范围内"""
        passed = True

        for kline in original_klines:
            key = kline.timestamp.strftime("%Y-%m-%d %H:%M")
            events = events_by_minute.get(key, [])

            for event in events:
                if event.event_type == "TRADE":
                    if event.price < kline.low or event.price > kline.high:
                        errors.append(
                            f"价格越界: {event.timestamp} 价格 {event.price} "
                            f"不在 [{kline.low}, {kline.high}] 范围内"
                        )
                        passed = False

        return passed

    def _check_volume_conservation(
        self,
        original_klines: list[KLine],
        events_by_minute: dict[str, list[TickEvent]],
        errors: list[str],
    ) -> bool:
        """检查成交量守恒：所有成交总量 = 该分钟 Volume"""
        passed = True

        for kline in original_klines:
            key = kline.timestamp.strftime("%Y-%m-%d %H:%M")
            events = events_by_minute.get(key, [])

            trade_volume = sum(e.volume for e in events if e.event_type == "TRADE")

            if kline.volume > 0:
                relative_error = abs(trade_volume - kline.volume) / kline.volume
                if relative_error > self.volume_tolerance:
                    errors.append(
                        f"成交量不守恒: {key} 原始 {kline.volume}, "
                        f"合成 {trade_volume}, 误差 {relative_error:.2%}"
                    )
                    passed = False

        return passed

    def _check_ohlcv_consistency(
        self,
        original_klines: list[KLine],
        events_by_minute: dict[str, list[TickEvent]],
        errors: list[str],
    ) -> bool:
        """检查 OHLCV 一致性：合成事件的 OHLCV 与原始 K 线一致"""
        passed = True

        for kline in original_klines:
            key = kline.timestamp.strftime("%Y-%m-%d %H:%M")
            events = events_by_minute.get(key, [])

            trade_prices = [e.price for e in events if e.event_type == "TRADE"]
            if not trade_prices:
                continue

            # 计算合成的 OHLCV
            synth_open = trade_prices[0]
            synth_high = max(trade_prices)
            synth_low = min(trade_prices)
            synth_close = trade_prices[-1]

            # 检查 OHLC 误差
            for name, orig, synth in [
                ("Open", kline.open, synth_open),
                ("High", kline.high, synth_high),
                ("Low", kline.low, synth_low),
                ("Close", kline.close, synth_close),
            ]:
                if orig > 0:
                    rel_error = abs(synth - orig) / orig
                    if rel_error > self.price_tolerance:
                        errors.append(
                            f"OHLCV 不一致: {key} {name} 原始 {orig}, "
                            f"合成 {synth}, 误差 {rel_error:.2%}"
                        )
                        passed = False

        return passed

    def _check_direction_reasonability(
        self,
        original_klines: list[KLine],
        events_by_minute: dict[str, list[TickEvent]],
        warnings: list[str],
    ) -> bool:
        """检查方向合理性：上涨分钟主动买 > 主动卖，下跌分钟相反"""
        passed = True

        for kline in original_klines:
            key = kline.timestamp.strftime("%Y-%m-%d %H:%M")
            events = events_by_minute.get(key, [])

            buy_volume = sum(e.volume for e in events if e.side == "BUY" and e.event_type == "ORDER_ADD")
            sell_volume = sum(e.volume for e in events if e.side == "SELL" and e.event_type == "ORDER_ADD")

            if kline.close > kline.open:
                # 上涨分钟：买方应更多
                if sell_volume > buy_volume * 1.2:  # 允许 20% 误差
                    warnings.append(
                        f"方向异常: {key} 上涨但卖方量 ({sell_volume}) > 买方量 ({buy_volume})"
                    )
            elif kline.close < kline.open:
                # 下跌分钟：卖方应更多
                if buy_volume > sell_volume * 1.2:
                    warnings.append(
                        f"方向异常: {key} 下跌但买方量 ({buy_volume}) > 卖方量 ({sell_volume})"
                    )

        return passed

    def _check_event_completeness(self, events: list[TickEvent], errors: list[str]) -> bool:
        """检查事件完整性：每个事件都有必要的字段"""
        passed = True

        for i, event in enumerate(events):
            if not event.security_id:
                errors.append(f"事件 {i}: 缺少 security_id")
                passed = False
            if not event.timestamp:
                errors.append(f"事件 {i}: 缺少 timestamp")
                passed = False
            if event.price <= 0:
                errors.append(f"事件 {i}: 价格无效 ({event.price})")
                passed = False
            if event.volume <= 0:
                errors.append(f"事件 {i}: 成交量无效 ({event.volume})")
                passed = False

        return passed
