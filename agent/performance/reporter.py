"""绩效报告生成器

生成 Markdown 格式的绩效报告。
"""

from datetime import datetime

from .calculator import PerformanceMetrics, TradeRecord


class PerformanceReporter:
    """绩效报告生成器"""

    @staticmethod
    def generate_markdown(
        metrics: PerformanceMetrics,
        trades: list[TradeRecord],
        security_id: str = "",
        title: str = "回测绩效报告",
    ) -> str:
        """生成 Markdown 格式的绩效报告

        Args:
            metrics: 绩效指标
            trades: 交易记录
            security_id: 股票代码
            title: 报告标题

        Returns:
            Markdown 格式的报告字符串
        """
        lines = []

        # 标题
        lines.append(f"# {title}")
        lines.append("")
        if security_id:
            lines.append(f"**标的:** {security_id}")
        if metrics.start_time and metrics.end_time:
            lines.append(f"**时间:** {metrics.start_time.strftime('%Y-%m-%d %H:%M')} ~ {metrics.end_time.strftime('%Y-%m-%d %H:%M')}")
            lines.append(f"**周期:** {metrics.duration_days:.1f} 天")
        lines.append("")

        # 核心指标
        lines.append("## 核心指标")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| 总盈亏 | {metrics.total_pnl:,.2f} |")
        lines.append(f"| 已实现盈亏 | {metrics.realized_pnl:,.2f} |")
        lines.append(f"| 未实现盈亏 | {metrics.unrealized_pnl:,.2f} |")
        lines.append(f"| 总收益率 | {metrics.total_return:.2%} |")
        lines.append(f"| 夏普比率 | {metrics.sharpe_ratio:.4f} |")
        lines.append(f"| 最大回撤 | {metrics.max_drawdown:,.2f} |")
        lines.append(f"| 最大回撤率 | {metrics.max_drawdown_pct:.2%} |")
        lines.append("")

        # 交易统计
        lines.append("## 交易统计")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| 总交易次数 | {metrics.total_trades} |")
        lines.append(f"| 盈利交易 | {metrics.winning_trades} |")
        lines.append(f"| 亏损交易 | {metrics.losing_trades} |")
        lines.append(f"| 胜率 | {metrics.win_rate:.2%} |")
        lines.append(f"| 盈亏比 | {metrics.profit_factor:.2f} |")
        lines.append("")

        # 持仓信息
        if metrics.final_position > 0:
            lines.append("## 当前持仓")
            lines.append("")
            lines.append(f"- 持仓数量: {metrics.final_position}")
            lines.append(f"- 平均入场价: {metrics.avg_entry_price:.2f}")
            lines.append("")

        # 交易明细
        if trades:
            lines.append("## 交易明细")
            lines.append("")
            lines.append("| 时间 | 方向 | 价格 | 数量 | 金额 |")
            lines.append("|------|------|------|------|------|")
            for trade in trades[:50]:  # 最多显示 50 笔
                direction = "买入" if trade.side == "BUY" else "卖出"
                amount = trade.price * trade.volume
                lines.append(
                    f"| {trade.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                    f"{direction} | {trade.price:.2f} | {trade.volume} | {amount:,.2f} |"
                )
            if len(trades) > 50:
                lines.append(f"| ... | ... | ... | ... | (共 {len(trades)} 笔) |")
            lines.append("")

        # 生成时间
        lines.append("---")
        lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(lines)

    @staticmethod
    def print_summary(metrics: PerformanceMetrics):
        """打印摘要到控制台"""
        print("=" * 50)
        print("回测绩效摘要")
        print("=" * 50)
        print(f"总盈亏:     {metrics.total_pnl:>12,.2f}")
        print(f"总收益率:   {metrics.total_return:>12.2%}")
        print(f"夏普比率:   {metrics.sharpe_ratio:>12.4f}")
        print(f"最大回撤:   {metrics.max_drawdown:>12,.2f}")
        print(f"最大回撤率: {metrics.max_drawdown_pct:>12.2%}")
        print(f"胜率:       {metrics.win_rate:>12.2%}")
        print(f"交易次数:   {metrics.total_trades:>12}")
        print("=" * 50)
