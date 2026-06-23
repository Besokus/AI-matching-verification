"""价格路径生成算法 - 从分钟 K 线生成合成逐笔价格序列

使用布朗运动 + OHLCV 约束生成价格路径：
1. 生成布朗运动随机路径
2. 缩放和偏移路径以匹配 OHLCV 约束
3. 确保路径经过 Open → High/Low → Close
"""

import numpy as np
from dataclasses import dataclass


@dataclass
class PricePathConfig:
    """价格路径配置"""
    volatility: float = 0.02  # 波动率（控制价格振幅）
    points_per_minute: int = 60  # 每分钟生成的价格点数
    seed: int | None = None  # 随机种子（可复现）


class PricePathGenerator:
    """价格路径生成器

    从分钟 K 线的 OHLCV 生成该分钟内的价格序列。
    约束：路径必须经过 Open → High/Low → Close，且所有价格在 [Low, High] 范围内。
    """

    def __init__(self, config: PricePathConfig | None = None):
        self.config = config or PricePathConfig()
        if self.config.seed is not None:
            np.random.seed(self.config.seed)

    def generate(
        self,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        volume: int,
        n_points: int | None = None,
    ) -> list[float]:
        """生成价格路径

        Args:
            open_price: 开盘价
            high_price: 最高价
            low_price: 最低价
            close_price: 收盘价
            volume: 成交量
            n_points: 价格点数（默认使用配置值）

        Returns:
            价格序列列表，长度为 n_points
        """
        if n_points is None:
            n_points = self.config.points_per_minute

        if n_points < 2:
            return [open_price, close_price]

        # 确定价格路径形状
        # 情况 1: 上涨 - Open → High → Close (High > Open, Close > Open)
        # 情况 2: 下跌 - Open → Low → Close (Low < Open, Close < Open)
        # 情况 3: 震荡 - Open → High → Low → Close 或 Open → Low → High → Close

        path_shape = self._determine_path_shape(open_price, high_price, low_price, close_price)

        # 生成布朗运动路径
        base_path = self._generate_brownian_path(n_points, self.config.volatility)

        # 根据路径形状进行约束
        if path_shape == "up":
            prices = self._constrain_up_path(base_path, open_price, high_price, close_price, n_points)
        elif path_shape == "down":
            prices = self._constrain_down_path(base_path, open_price, low_price, close_price, n_points)
        else:
            prices = self._constrain_volatile_path(base_path, open_price, high_price, low_price, close_price, n_points)

        # 最终裁剪：确保所有价格在 [Low, High] 范围内
        prices = [max(low_price, min(high_price, p)) for p in prices]

        return prices

    def _determine_path_shape(self, open_p: float, high_p: float, low_p: float, close_p: float) -> str:
        """判断价格路径形状"""
        if close_p > open_p and high_p >= max(open_p, close_p):
            return "up"
        elif close_p < open_p and low_p <= min(open_p, close_p):
            return "down"
        else:
            return "volatile"

    def _generate_brownian_path(self, n_points: int, volatility: float) -> np.ndarray:
        """生成布朗运动路径

        从 0 开始，每步随机游走，最终值为 0（归一化后使用）
        """
        # 生成随机增量
        increments = np.random.normal(0, volatility, n_points - 1)
        # 累加得到路径
        path = np.zeros(n_points)
        path[1:] = np.cumsum(increments)
        return path

    def _constrain_up_path(
        self, base_path: np.ndarray, open_p: float, high_p: float, close_p: float, n_points: int
    ) -> list[float]:
        """约束上涨路径：Open → High → Close

        策略：
        1. 找到路径中的最高点位置
        2. 将最高点映射到 High
        3. 前半段从 Open 到 High
        4. 后半段从 High 到 Close
        """
        # 找到路径中的最高点
        peak_idx = np.argmax(base_path)

        # 确保峰值不在首尾
        if peak_idx == 0:
            peak_idx = max(1, n_points // 3)
        elif peak_idx == n_points - 1:
            peak_idx = min(n_points - 2, 2 * n_points // 3)

        # 构建目标路径
        prices = np.zeros(n_points)

        # 前半段：Open → High
        for i in range(peak_idx + 1):
            t = i / peak_idx if peak_idx > 0 else 0
            # 使用平滑插值
            prices[i] = open_p + (high_p - open_p) * self._smooth_step(t)

        # 后半段：High → Close
        for i in range(peak_idx + 1, n_points):
            t = (i - peak_idx) / (n_points - 1 - peak_idx) if (n_points - 1 - peak_idx) > 0 else 0
            prices[i] = high_p + (close_p - high_p) * self._smooth_step(t)

        return prices.tolist()

    def _constrain_down_path(
        self, base_path: np.ndarray, open_p: float, low_p: float, close_p: float, n_points: int
    ) -> list[float]:
        """约束下跌路径：Open → Low → Close

        策略：
        1. 找到路径中的最低点位置
        2. 将最低点映射到 Low
        3. 前半段从 Open 到 Low
        4. 后半段从 Low 到 Close
        """
        # 找到路径中的最低点
        trough_idx = np.argmin(base_path)

        # 确保谷值不在首尾
        if trough_idx == 0:
            trough_idx = max(1, n_points // 3)
        elif trough_idx == n_points - 1:
            trough_idx = min(n_points - 2, 2 * n_points // 3)

        # 构建目标路径
        prices = np.zeros(n_points)

        # 前半段：Open → Low
        for i in range(trough_idx + 1):
            t = i / trough_idx if trough_idx > 0 else 0
            prices[i] = open_p + (low_p - open_p) * self._smooth_step(t)

        # 后半段：Low → Close
        for i in range(trough_idx + 1, n_points):
            t = (i - trough_idx) / (n_points - 1 - trough_idx) if (n_points - 1 - trough_idx) > 0 else 0
            prices[i] = low_p + (close_p - low_p) * self._smooth_step(t)

        return prices.tolist()

    def _constrain_volatile_path(
        self, base_path: np.ndarray, open_p: float, high_p: float, low_p: float, close_p: float, n_points: int
    ) -> list[float]:
        """约束震荡路径：Open → High → Low → Close 或 Open → Low → High → Close

        策略：
        1. 找到路径中的最高点和最低点
        2. 按顺序映射：Open → 极值1 → 极值2 → Close
        """
        peak_idx = np.argmax(base_path)
        trough_idx = np.argmin(base_path)

        # 确定顺序：先高后低 or 先低后高
        if peak_idx < trough_idx:
            # Open → High → Low → Close
            points = [
                (0, open_p),
                (peak_idx, high_p),
                (trough_idx, low_p),
                (n_points - 1, close_p),
            ]
        else:
            # Open → Low → High → Close
            points = [
                (0, open_p),
                (trough_idx, low_p),
                (peak_idx, high_p),
                (n_points - 1, close_p),
            ]

        # 确保关键点不重叠
        points = self._deduplicate_points(points)

        # 分段插值
        prices = np.zeros(n_points)
        for i in range(len(points) - 1):
            start_idx, start_price = points[i]
            end_idx, end_price = points[i + 1]

            for j in range(start_idx, end_idx + 1):
                t = (j - start_idx) / (end_idx - start_idx) if (end_idx - start_idx) > 0 else 0
                prices[j] = start_price + (end_price - start_price) * self._smooth_step(t)

        return prices.tolist()

    def _smooth_step(self, t: float) -> float:
        """平滑插值函数（Hermite 插值）

        使用 smoothstep 函数使价格变化更自然：
        - 在起点和终点速度为 0
        - 中间段加速/减速
        """
        t = max(0.0, min(1.0, t))
        return t * t * (3 - 2 * t)

    def _deduplicate_points(self, points: list[tuple[int, float]]) -> list[tuple[int, float]]:
        """去重关键点（避免索引重叠）"""
        if len(points) < 2:
            return points

        # 获取最大有效索引（从最后一点推断 n_points）
        max_idx = points[-1][0]

        result = [points[0]]
        for i in range(1, len(points)):
            idx, price = points[i]
            prev_idx, _ = result[-1]
            if idx <= prev_idx:
                # 移动到前一个点之后，但不超过最大索引
                idx = min(prev_idx + 1, max_idx)
            result.append((idx, price))

        return result
