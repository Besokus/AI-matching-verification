"""TradeAgent-Veritas 主入口

回测主循环：
1. 获取 AKShare 分钟线数据
2. Tick 合成器生成逐笔事件
3. 喂入双引擎（A: 历史回放, B: Agent 仿真）
4. 每分钟触发 Agent 决策
5. 风控通过后注入引擎 B
6. 输出绩效报告
"""

import asyncio
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .config import AppConfig
from .data.providers.akshare_provider import AKShareProvider
from .synthesizer.tick_synthesizer import TickSynthesizer, SynthesizerConfig
from .bridge.engine_client import EngineClient, EngineConfig
from .graph.trading_graph import TradingGraph
from .graph.state import AgentState
from .performance.calculator import PerformanceCalculator, TradeRecord
from .performance.reporter import PerformanceReporter


class BacktestRunner:
    """回测运行器"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.provider = AKShareProvider(cache_dir=config.cache_dir)
        self.synthesizer = TickSynthesizer(SynthesizerConfig(
            volatility=config.synthesizer.volatility,
            points_per_minute=config.synthesizer.points_per_minute,
            cancel_ratio=config.synthesizer.cancel_ratio,
            seed=config.synthesizer.seed,
        ))
        self.engine_a = EngineClient(EngineConfig(
            host=config.engine_a_host,
            port=config.engine_a_port,
        ))
        self.engine_b = EngineClient(EngineConfig(
            host=config.engine_b_host,
            port=config.engine_b_port,
        ))
        self.graph = TradingGraph(
            risk_config=config.risk,
            max_debate_rounds=config.backtest.max_debate_rounds,
            data_provider=self.provider,
        )
        self.calculator = PerformanceCalculator(
            initial_capital=config.backtest.initial_capital,
        )
        self.position = {"volume": 0, "avg_price": 0.0, "pnl": 0.0}
        self.agent_trades: list[TradeRecord] = []

    async def run(self):
        """运行回测"""
        security_id = self.config.backtest.security_id
        start_date = self.config.backtest.start_date
        end_date = self.config.backtest.end_date

        print(f"=" * 60)
        print(f"TradeAgent-Veritas 回测启动")
        print(f"标的: {security_id}")
        print(f"时间: {start_date} ~ {end_date}")
        print(f"初始资金: {self.config.backtest.initial_capital:,.2f}")
        print(f"=" * 60)

        # Step 1: 获取分钟线数据
        print("\n[1/5] 获取分钟线数据...")
        klines = self.provider.get_minute_klines(
            security_id=security_id,
            start_date=start_date,
            end_date=end_date,
        )
        if not klines:
            print("错误: 无法获取分钟线数据")
            return
        print(f"  获取到 {len(klines)} 根分钟线")

        # Step 2: Tick 合成
        print("\n[2/5] 合成逐笔事件...")
        tick_events = self.synthesizer.synthesize(klines)
        print(f"  生成 {len(tick_events)} 个逐笔事件")

        # Step 3: 连接引擎
        print("\n[3/5] 连接撮合引擎...")
        engine_a_ok = self.engine_a.connect()
        engine_b_ok = self.engine_b.connect()

        if not engine_a_ok or not engine_b_ok:
            print("警告: 无法连接撮合引擎，使用模拟模式")
            # 模拟模式：不使用真实引擎
            await self._run_simulation(klines, tick_events)
            return

        # Step 4: 回放主循环
        print("\n[4/5] 开始回放...")
        await self._run_replay(klines, tick_events)

        # Step 5: 绩效统计
        print("\n[5/5] 生成绩效报告...")
        self._generate_report(security_id)

        # 断开引擎
        self.engine_a.disconnect()
        self.engine_b.disconnect()

    async def _run_replay(self, klines, tick_events):
        """使用真实引擎回放"""
        current_minute = None
        events_processed = 0

        for event in tick_events:
            # 喂事件到两个引擎
            if event.event_type == "TRADE":
                self.engine_a.feed_trade_event(event)
                self.engine_b.feed_trade_event(event)
            else:
                self.engine_a.feed_order_event(event)
                self.engine_b.feed_order_event(event)

            events_processed += 1

            # 每分钟边界触发 Agent 决策
            event_minute = event.timestamp.strftime("%Y-%m-%d %H:%M")
            if event_minute != current_minute:
                current_minute = event_minute

                # 等引擎排空
                self.engine_a.wait_for_drain()
                self.engine_b.wait_for_drain()

                # 从引擎 A 获取快照
                snapshot = self.engine_a.get_snapshot(self.config.backtest.security_id)
                if snapshot is None:
                    continue

                # 构建 Agent 输入状态
                recent_klines = self._get_recent_klines(klines, event.timestamp, 10)
                state = self._build_agent_state(snapshot, recent_klines)

                # 运行 Agent
                result = await self.graph.run(state)

                # 如果决策通过风控，注入引擎 B
                if result["final_decision"] == "EXECUTE":
                    order = result["order_decision"]
                    if result["risk_decision"].adjusted_order:
                        order = result["risk_decision"].adjusted_order

                    order_result = self.engine_b.submit_agent_order(
                        security_id=order.security_id,
                        price=order.price,
                        volume=order.volume,
                        side=order.action,
                        agent_id="trader_01",
                        reason=order.reason,
                    )

                    if order_result.get("success"):
                        # 记录交易
                        self._update_position(order)
                        print(f"  [{current_minute}] {order.action} {order.volume} @ {order.price:.2f}")

        print(f"  处理事件: {events_processed}")

    async def _run_simulation(self, klines, tick_events):
        """模拟模式（不使用真实引擎）"""
        current_minute = None

        # 按分钟分组事件
        for kline in klines:
            minute_key = kline.timestamp.strftime("%Y-%m-%d %H:%M")

            # 构建模拟快照
            snapshot = {
                "security_id": kline.security_id,
                "last_price": kline.close,
                "bids": [(kline.close - i * 0.01, 1000) for i in range(10)],
                "asks": [(kline.close + i * 0.01, 1000) for i in range(10)],
                "total_volume": kline.volume,
                "total_amount": kline.amount,
            }

            # 构建 Agent 输入状态
            recent_klines = self._get_recent_klines(klines, kline.timestamp, 10)
            state = self._build_agent_state(snapshot, recent_klines)

            # 运行 Agent
            result = await self.graph.run(state)

            # 如果决策通过风控，模拟成交
            if result["final_decision"] == "EXECUTE":
                order = result["order_decision"]
                if result["risk_decision"].adjusted_order:
                    order = result["risk_decision"].adjusted_order

                # 模拟成交
                trade = TradeRecord(
                    trade_id=len(self.agent_trades) + 1,
                    security_id=order.security_id,
                    price=order.price,
                    volume=order.volume,
                    side=order.action,
                    timestamp=kline.timestamp,
                    agent_id="trader_01",
                )
                self.agent_trades.append(trade)
                self._update_position(order)
                print(f"  [{minute_key}] {order.action} {order.volume} @ {order.price:.2f}")

    def _build_agent_state(self, snapshot: dict, recent_klines: list) -> AgentState:
        """构建 Agent 输入状态"""
        return {
            "security_id": self.config.backtest.security_id,
            "security_name": "",
            "trade_date": datetime.now().strftime("%Y-%m-%d"),
            "market_snapshot": snapshot,
            "recent_klines": [
                {
                    "timestamp": k.timestamp.isoformat(),
                    "open": k.open,
                    "high": k.high,
                    "low": k.low,
                    "close": k.close,
                    "volume": k.volume,
                }
                for k in recent_klines
            ],
            "daily_klines": [],
            "technical_report": None,
            "fundamental_report": None,
            "sentiment_report": None,
            "news_report": None,
            "debate_state": None,
            "order_decision": None,
            "risk_decision": None,
            "position": self.position.copy(),
            "final_decision": "",
            "node_timings": {},
        }

    def _get_recent_klines(self, klines, current_time, n: int) -> list:
        """获取最近 N 根 K 线"""
        recent = [k for k in klines if k.timestamp <= current_time]
        return recent[-n:] if len(recent) > n else recent

    def _update_position(self, order):
        """更新持仓状态"""
        if order.action == "BUY":
            # 买入
            total_cost = self.position["volume"] * self.position["avg_price"]
            new_cost = order.volume * order.price
            self.position["volume"] += order.volume
            if self.position["volume"] > 0:
                self.position["avg_price"] = (total_cost + new_cost) / self.position["volume"]
        elif order.action == "SELL":
            # 卖出
            if self.position["volume"] > 0:
                pnl = (order.price - self.position["avg_price"]) * order.volume
                self.position["pnl"] += pnl
            self.position["volume"] -= order.volume
            if self.position["volume"] <= 0:
                self.position["volume"] = 0
                self.position["avg_price"] = 0.0

    def _generate_report(self, security_id: str):
        """生成绩效报告"""
        # 从引擎 B 获取交易记录
        if self.engine_b.is_connected():
            engine_trades = self.engine_b.get_agent_trades(security_id=security_id)
            for t in engine_trades:
                self.agent_trades.append(TradeRecord(
                    trade_id=t.get("trade_id", 0),
                    security_id=t.get("security_id", ""),
                    price=t.get("price", 0.0),
                    volume=t.get("volume", 0),
                    side=t.get("side", "BUY"),
                    timestamp=datetime.fromtimestamp(t.get("timestamp", 0)),
                    agent_id=t.get("agent_id", ""),
                    commission=t.get("commission", 0.0),
                ))

        # 计算绩效
        metrics = self.calculator.calculate(self.agent_trades)

        # 打印摘要
        PerformanceReporter.print_summary(metrics)

        # 生成 Markdown 报告
        report = PerformanceReporter.generate_markdown(
            metrics, self.agent_trades, security_id=security_id
        )

        # 保存报告
        report_dir = Path(self.config.log_dir).expanduser()
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"backtest_{security_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_file.write_text(report, encoding="utf-8")
        print(f"\n报告已保存: {report_file}")


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(description="TradeAgent-Veritas 回测")
    parser.add_argument("--security-id", default="600519", help="股票代码")
    parser.add_argument("--start-date", required=True, help="开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--initial-capital", type=float, default=1_000_000, help="初始资金")
    parser.add_argument("--engine-a-port", type=int, default=50051, help="引擎 A 端口")
    parser.add_argument("--engine-b-port", type=int, default=50052, help="引擎 B 端口")

    args = parser.parse_args()

    config = AppConfig()
    config.backtest.security_id = args.security_id
    config.backtest.start_date = args.start_date
    config.backtest.end_date = args.end_date
    config.backtest.initial_capital = args.initial_capital
    config.engine_a_port = args.engine_a_port
    config.engine_b_port = args.engine_b_port

    runner = BacktestRunner(config)
    asyncio.run(runner.run())


if __name__ == "__main__":
    main()
