"""绩效计算器

计算交易策略的核心绩效指标：
- PnL（盈亏）
- Sharpe Ratio（夏普比率）
- Max Drawdown（最大回撤）
- Win Rate（胜率）
- Profit Factor（盈亏比）
"""

import math
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np


@dataclass
class TradeRecord:
    """交易记录"""
    trade_id: int
    security_id: str
    price: float
    volume: int
    side: str  # "BUY" or "SELL"
    timestamp: datetime
    agent_id: str = ""
    commission: float = 0.0


@dataclass
class PerformanceMetrics:
    """绩效指标"""
    # 收益
    total_pnl: float = 0.0  # 总盈亏
    realized_pnl: float = 0.0  # 已实现盈亏
    unrealized_pnl: float = 0.0  # 未实现盈亏
    total_return: float = 0.0  # 总收益率

    # 风险
    sharpe_ratio: float = 0.0  # 夏普比率
    max_drawdown: float = 0.0  # 最大回撤
    max_drawdown_pct: float = 0.0  # 最大回撤百分比

    # 交易统计
    total_trades: int = 0  # 总交易次数
    winning_trades: int = 0  # 盈利交易次数
    losing_trades: int = 0  # 亏损交易次数
    win_rate: float = 0.0  # 胜率
    profit_factor: float = 0.0  # 盈亏比

    # 持仓
    final_position: int = 0  # 最终持仓
    avg_entry_price: float = 0.0  # 平均入场价

    # 时间
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_days: float = 0.0


class PerformanceCalculator:
    """绩效计算器"""

    def __init__(self, initial_capital: float = 1_000_000.0, risk_free_rate: float = 0.03):
        """
        Args:
            initial_capital: 初始资金
            risk_free_rate: 无风险利率（年化）
        """
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate

    def calculate(
        self,
        trades: list[TradeRecord],
        current_price: float = 0.0,
    ) -> PerformanceMetrics:
        """计算绩效指标

        Args:
            trades: 交易记录列表
            current_price: 当前价格（用于计算未实现盈亏）

        Returns:
            PerformanceMetrics
        """
        if not trades:
            return PerformanceMetrics(
                start_time=None,
                end_time=None,
            )

        # 排序交易记录
        sorted_trades = sorted(trades, key=lambda t: t.timestamp)

        # 计算盈亏
        pnl_result = self._calculate_pnl(sorted_trades)

        # 计算收益率曲线
        equity_curve = self._calculate_equity_curve(sorted_trades)

        # 计算最大回撤
        max_dd, max_dd_pct = self._calculate_max_drawdown(equity_curve)

        # 计算夏普比率
        sharpe = self._calculate_sharpe(equity_curve)

        # 计算胜率和盈亏比
        win_rate, profit_factor = self._calculate_win_stats(sorted_trades, pnl_result)

        # 计算时间跨度
        start_time = sorted_trades[0].timestamp
        end_time = sorted_trades[-1].timestamp
        duration = (end_time - start_time).total_seconds() / 86400  # 天数

        return PerformanceMetrics(
            total_pnl=pnl_result["total_pnl"],
            realized_pnl=pnl_result["realized_pnl"],
            unrealized_pnl=pnl_result["unrealized_pnl"],
            total_return=pnl_result["total_pnl"] / self.initial_capital,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            total_trades=len(sorted_trades),
            winning_trades=pnl_result["winning_trades"],
            losing_trades=pnl_result["losing_trades"],
            win_rate=win_rate,
            profit_factor=profit_factor,
            final_position=pnl_result["final_position"],
            avg_entry_price=pnl_result["avg_entry_price"],
            start_time=start_time,
            end_time=end_time,
            duration_days=duration,
        )

    def _calculate_pnl(self, trades: list[TradeRecord]) -> dict:
        """计算盈亏

        使用 FIFO 方式计算已实现盈亏。
        """
        position = 0  # 当前持仓
        avg_price = 0.0  # 平均入场价
        realized_pnl = 0.0  # 已实现盈亏
        total_commission = 0.0
        winning_trades = 0
        losing_trades = 0

        # 用于 FIFO 的持仓队列
        position_queue: list[dict] = []  # [{"price": float, "volume": int}]

        for trade in trades:
            total_commission += trade.commission

            if trade.side == "BUY":
                # 买入
                position_queue.append({
                    "price": trade.price,
                    "volume": trade.volume,
                })
                position += trade.volume

            elif trade.side == "SELL":
                # 卖出
                sell_volume = trade.volume
                sell_price = trade.price

                while sell_volume > 0 and position_queue:
                    entry = position_queue[0]
                    match_volume = min(sell_volume, entry["volume"])

                    # 计算这笔的盈亏
                    pnl = (sell_price - entry["price"]) * match_volume
                    realized_pnl += pnl

                    if pnl > 0:
                        winning_trades += 1
                    elif pnl < 0:
                        losing_trades += 1

                    # 更新队列
                    entry["volume"] -= match_volume
                    sell_volume -= match_volume
                    position -= match_volume

                    if entry["volume"] <= 0:
                        position_queue.pop(0)

        # 计算平均入场价
        if position > 0 and position_queue:
            total_cost = sum(e["price"] * e["volume"] for e in position_queue)
            total_volume = sum(e["volume"] for e in position_queue)
            avg_price = total_cost / total_volume if total_volume > 0 else 0

        # 未实现盈亏（如果有持仓）
        unrealized_pnl = 0.0
        if position > 0 and trades:
            last_price = trades[-1].price
            unrealized_pnl = (last_price - avg_price) * position

        return {
            "total_pnl": realized_pnl + unrealized_pnl - total_commission,
            "realized_pnl": realized_pnl - total_commission,
            "unrealized_pnl": unrealized_pnl,
            "final_position": position,
            "avg_entry_price": avg_price,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
        }

    def _calculate_equity_curve(self, trades: list[TradeRecord]) -> list[float]:
        """计算权益曲线"""
        equity = self.initial_capital
        curve = [equity]

        position = 0
        position_queue: list[dict] = []

        for trade in trades:
            if trade.side == "BUY":
                equity -= trade.price * trade.volume + trade.commission
                position_queue.append({
                    "price": trade.price,
                    "volume": trade.volume,
                })
                position += trade.volume
            elif trade.side == "SELL":
                equity += trade.price * trade.volume - trade.commission
                sell_volume = trade.volume
                while sell_volume > 0 and position_queue:
                    entry = position_queue[0]
                    match_volume = min(sell_volume, entry["volume"])
                    entry["volume"] -= match_volume
                    sell_volume -= match_volume
                    position -= match_volume
                    if entry["volume"] <= 0:
                        position_queue.pop(0)

            curve.append(equity)

        return curve

    def _calculate_max_drawdown(self, equity_curve: list[float]) -> tuple[float, float]:
        """计算最大回撤

        Returns:
            (最大回撤金额, 最大回撤百分比)
        """
        if len(equity_curve) < 2:
            return 0.0, 0.0

        peak = equity_curve[0]
        max_dd = 0.0
        max_dd_pct = 0.0

        for equity in equity_curve:
            if equity > peak:
                peak = equity

            dd = peak - equity
            dd_pct = dd / peak if peak > 0 else 0

            if dd > max_dd:
                max_dd = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        return max_dd, max_dd_pct

    def _calculate_sharpe(self, equity_curve: list[float]) -> float:
        """计算夏普比率

        夏普比率 = (年化收益率 - 无风险利率) / 年化波动率
        """
        if len(equity_curve) < 2:
            return 0.0

        # 计算每日收益率
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] > 0:
                ret = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                returns.append(ret)

        if not returns:
            return 0.0

        # 计算平均收益率和标准差
        returns_arr = np.array(returns)
        avg_return = returns_arr.mean()
        std_return = returns_arr.std()

        if std_return == 0:
            return 0.0

        # 年化（假设 252 个交易日）
        annual_return = avg_return * 252
        annual_std = std_return * math.sqrt(252)

        # 夏普比率
        sharpe = (annual_return - self.risk_free_rate) / annual_std

        return sharpe

    def _calculate_win_stats(
        self, trades: list[TradeRecord], pnl_result: dict
    ) -> tuple[float, float]:
        """计算胜率和盈亏比"""
        winning = pnl_result["winning_trades"]
        losing = pnl_result["losing_trades"]
        total = winning + losing

        win_rate = winning / total if total > 0 else 0.0

        # 盈亏比 = 平均盈利 / 平均亏损
        # 简化计算
        if losing > 0 and winning > 0:
            profit_factor = winning / losing  # 简化版
        else:
            profit_factor = float("inf") if winning > 0 else 0.0

        return win_rate, profit_factor
