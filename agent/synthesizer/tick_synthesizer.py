"""Tick 合成器 - 将分钟 K 线转换为合成逐笔事件

核心流程：
1. 从分钟 K 线获取 OHLCV
2. 使用布朗运动生成价格路径
3. 根据价格路径生成订单事件（ADD/CANCEL）
4. 生成成交事件（TRADE）
5. 输出格式兼容 RTAuction OrderData/TradeData
"""

import random
from datetime import datetime, timedelta
from dataclasses import dataclass, field

import numpy as np

from ..data.models.market import KLine, TickEvent
from .price_path import PricePathGenerator, PricePathConfig


@dataclass
class SynthesizerConfig:
    """合成器配置"""
    volatility: float = 0.02  # 价格波动率
    points_per_minute: int = 60  # 每分钟价格点数
    cancel_ratio: float = 0.15  # 撤单比例（15% 的订单会被撤单）
    order_arrival_lambda: float = 5.0  # 订单到达泊松分布参数
    seed: int | None = None  # 随机种子
    tick_size: float = 0.01  # 最小价格变动单位


class TickSynthesizer:
    """Tick 合成器

    将分钟 K 线转换为合成逐笔事件序列。
    输出格式兼容 RTAuction OrderData/TradeData。
    """

    def __init__(self, config: SynthesizerConfig | None = None):
        self.config = config or SynthesizerConfig()
        self.price_generator = PricePathGenerator(PricePathConfig(
            volatility=self.config.volatility,
            points_per_minute=self.config.points_per_minute,
            seed=self.config.seed,
        ))
        self._order_id_counter = 0
        self._trade_id_counter = 0

    def synthesize(self, klines: list[KLine]) -> list[TickEvent]:
        """将分钟 K 线列表转换为合成逐笔事件

        Args:
            klines: 分钟 K 线列表（按时间排序）

        Returns:
            合成逐笔事件列表（按时间排序）
        """
        all_events: list[TickEvent] = []

        for kline in klines:
            events = self._synthesize_one_minute(kline)
            all_events.extend(events)

        # 按时间戳排序
        all_events.sort(key=lambda e: e.timestamp)

        return all_events

    def _synthesize_one_minute(self, kline: KLine) -> list[TickEvent]:
        """合成单分钟的逐笔事件

        Args:
            kline: 分钟 K 线

        Returns:
            该分钟内的逐笔事件列表
        """
        events: list[TickEvent] = []

        # 1. 生成价格路径
        prices = self.price_generator.generate(
            open_price=kline.open,
            high_price=kline.high,
            low_price=kline.low,
            close_price=kline.close,
            volume=kline.volume,
        )

        # 2. 计算每个价格点的时间间隔
        n_points = len(prices)
        time_delta = timedelta(seconds=60 / n_points)

        # 3. 分配成交量到每个价格点
        volume_per_point = self._distribute_volume(kline.volume, n_points)

        # 4. 生成订单和成交事件
        for i in range(n_points):
            timestamp = kline.timestamp + time_delta * i
            price = self._round_price(prices[i])
            vol = volume_per_point[i]

            if vol <= 0:
                continue

            # 判断方向：上涨时主动买多，下跌时主动卖多
            if i > 0:
                price_change = prices[i] - prices[i - 1]
                if price_change > 0:
                    buy_ratio = 0.6  # 上涨时 60% 买方主动
                elif price_change < 0:
                    buy_ratio = 0.4  # 下跌时 40% 买方主动
                else:
                    buy_ratio = 0.5  # 平盘各半
            else:
                buy_ratio = 0.5

            # 生成挂单事件（ADD）
            buy_vol = int(vol * buy_ratio)
            sell_vol = vol - buy_vol

            if buy_vol > 0:
                events.append(self._create_order_event(
                    security_id=kline.security_id,
                    timestamp=timestamp,
                    side="BUY",
                    price=price,
                    volume=buy_vol,
                ))

            if sell_vol > 0:
                events.append(self._create_order_event(
                    security_id=kline.security_id,
                    timestamp=timestamp,
                    side="SELL",
                    price=price,
                    volume=sell_vol,
                ))

            # 随机生成撤单事件
            if self.config.cancel_ratio > 0 and len(events) > 2:
                if random.random() < self.config.cancel_ratio:
                    # 撤销一个之前的订单
                    cancel_idx = random.randint(0, len(events) - 2)
                    cancel_event = events[cancel_idx]
                    if cancel_event.event_type == "ORDER_ADD":
                        events.append(TickEvent(
                            security_id=kline.security_id,
                            timestamp=timestamp + timedelta(milliseconds=1),
                            event_type="ORDER_CANCEL",
                            side=cancel_event.side,
                            price=cancel_event.price,
                            volume=cancel_event.volume,
                            order_id=cancel_event.order_id,
                        ))

            # 生成成交事件（TRADE）
            events.append(self._create_trade_event(
                security_id=kline.security_id,
                timestamp=timestamp + timedelta(milliseconds=2),
                price=price,
                volume=vol,
            ))

        return events

    def _distribute_volume(self, total_volume: int, n_points: int) -> list[int]:
        """将总成交量分配到每个价格点

        使用正态分布随机分配，但保证总和等于 total_volume
        """
        if n_points <= 0:
            return []

        if n_points == 1:
            return [total_volume]

        # 生成随机权重
        weights = np.random.exponential(1.0, n_points)
        weights = weights / weights.sum()

        # 按权重分配
        volumes = (weights * total_volume).astype(int)

        # 修正总量（将差额分配到最大权重的位置）
        diff = total_volume - volumes.sum()
        if diff > 0:
            max_idx = np.argmax(weights)
            volumes[max_idx] += diff
        elif diff < 0:
            max_idx = np.argmax(weights)
            volumes[max_idx] += diff  # diff 是负数

        return volumes.tolist()

    def _round_price(self, price: float) -> float:
        """将价格四舍五入到最小变动单位"""
        tick = self.config.tick_size
        return round(round(price / tick) * tick, 2)

    def _create_order_event(
        self,
        security_id: str,
        timestamp: datetime,
        side: str,
        price: float,
        volume: int,
    ) -> TickEvent:
        """创建订单事件"""
        self._order_id_counter += 1
        return TickEvent(
            security_id=security_id,
            timestamp=timestamp,
            event_type="ORDER_ADD",
            side=side,
            price=price,
            volume=volume,
            order_id=self._order_id_counter,
        )

    def _create_trade_event(
        self,
        security_id: str,
        timestamp: datetime,
        price: float,
        volume: int,
    ) -> TickEvent:
        """创建成交事件"""
        self._trade_id_counter += 1
        return TickEvent(
            security_id=security_id,
            timestamp=timestamp,
            event_type="TRADE",
            side="BUY",  # 成交事件的方向由买卖双方决定
            price=price,
            volume=volume,
            trade_id=self._trade_id_counter,
        )
