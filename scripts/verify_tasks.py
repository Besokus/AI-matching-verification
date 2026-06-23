"""任务验收验证脚本

检查每个任务的验收标准是否达标。
运行: python scripts/verify_tasks.py
"""

import importlib
import sys
from pathlib import Path
from dataclasses import dataclass

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class CheckResult:
    """检查结果"""
    task: str
    check: str
    passed: bool
    message: str


def check_t0_1() -> list[CheckResult]:
    """T0.1: AKShare 分钟线数据接入"""
    results = []

    # 检查文件存在
    files = [
        "agent/data/providers/akshare_provider.py",
        "agent/data/models/market.py",
        "agent/tests/test_data/test_akshare_provider.py",
    ]
    for f in files:
        path = project_root / f
        results.append(CheckResult(
            task="T0.1",
            check=f"文件 {f} 存在",
            passed=path.exists(),
            message="" if path.exists() else f"缺少文件: {f}",
        ))

    # 检查模块可导入
    try:
        from agent.data.providers.akshare_provider import AKShareProvider
        from agent.data.models.market import KLine, DailyKLine
        results.append(CheckResult(
            task="T0.1",
            check="模块可导入",
            passed=True,
            message="AKShareProvider, KLine, DailyKLine",
        ))
    except ImportError as e:
        results.append(CheckResult(
            task="T0.1",
            check="模块可导入",
            passed=False,
            message=str(e),
        ))

    # 检查 AKShareProvider 有必要的方法
    try:
        from agent.data.providers.akshare_provider import AKShareProvider
        provider = AKShareProvider.__new__(AKShareProvider)
        has_minute = hasattr(provider, "get_minute_klines")
        has_daily = hasattr(provider, "get_daily_klines")
        results.append(CheckResult(
            task="T0.1",
            check="AKShareProvider 接口完整",
            passed=has_minute and has_daily,
            message=f"get_minute_klines={has_minute}, get_daily_klines={has_daily}",
        ))
    except Exception as e:
        results.append(CheckResult(
            task="T0.1",
            check="AKShareProvider 接口完整",
            passed=False,
            message=str(e),
        ))

    return results


def check_t0_2() -> list[CheckResult]:
    """T0.2: 价格路径生成算法"""
    results = []

    files = [
        "agent/synthesizer/price_path.py",
        "agent/synthesizer/tick_synthesizer.py",
        "agent/synthesizer/validator.py",
    ]
    for f in files:
        path = project_root / f
        results.append(CheckResult(
            task="T0.2",
            check=f"文件 {f} 存在",
            passed=path.exists(),
            message="" if path.exists() else f"缺少文件: {f}",
        ))

    # 检查价格路径生成
    try:
        from agent.synthesizer.price_path import PricePathGenerator
        gen = PricePathGenerator()
        prices = gen.generate(
            open_price=100.0, high_price=105.0,
            low_price=98.0, close_price=103.0,
            volume=1000, n_points=60,
        )
        # 验证约束
        start_ok = abs(prices[0] - 100.0) < 2.0
        end_ok = abs(prices[-1] - 103.0) < 2.0
        bounds_ok = all(98.0 <= p <= 105.0 for p in prices)
        results.append(CheckResult(
            task="T0.2",
            check="价格路径 OHLCV 约束",
            passed=start_ok and end_ok and bounds_ok,
            message=f"start={start_ok}, end={end_ok}, bounds={bounds_ok}",
        ))
    except Exception as e:
        results.append(CheckResult(
            task="T0.2",
            check="价格路径 OHLCV 约束",
            passed=False,
            message=str(e),
        ))

    return results


def check_t0_3() -> list[CheckResult]:
    """T0.3: 订单/成交事件生成"""
    results = []

    try:
        from agent.synthesizer.tick_synthesizer import TickSynthesizer
        from agent.data.models.market import KLine
        from datetime import datetime

        synth = TickSynthesizer()
        klines = [KLine(
            security_id="600519",
            timestamp=datetime(2026, 6, 20, 9, 30),
            open=100.0, high=105.0, low=98.0,
            close=103.0, volume=1000,
        )]
        events = synth.synthesize(klines)

        has_order = any(e.event_type == "ORDER_ADD" for e in events)
        has_trade = any(e.event_type == "TRADE" for e in events)
        has_cancel = any(e.event_type == "ORDER_CANCEL" for e in events)
        time_ordered = all(
            events[i].timestamp <= events[i + 1].timestamp
            for i in range(len(events) - 1)
        )
        results.append(CheckResult(
            task="T0.3",
            check="事件类型完整",
            passed=has_order and has_trade,
            message=f"ORDER_ADD={has_order}, TRADE={has_trade}, CANCEL={has_cancel}",
        ))
        results.append(CheckResult(
            task="T0.3",
            check="时间因果性",
            passed=time_ordered,
            message="事件时间戳严格递增" if time_ordered else "时间戳乱序",
        ))
    except Exception as e:
        results.append(CheckResult(
            task="T0.3",
            check="事件生成",
            passed=False,
            message=str(e),
        ))

    return results


def check_t1_1() -> list[CheckResult]:
    """T1.1: Proto 文件定义"""
    results = []

    proto_file = project_root / "agent/bridge/proto/matching_engine.proto"
    results.append(CheckResult(
        task="T1.1",
        check="proto 文件存在",
        passed=proto_file.exists(),
        message="" if proto_file.exists() else "缺少 matching_engine.proto",
    ))

    if proto_file.exists():
        content = proto_file.read_text(encoding="utf-8")
        has_service = "service MatchingEngineService" in content
        has_order = "message OrderEvent" in content
        has_trade = "message TradeEvent" in content
        has_snapshot = "message MarketSnapshotProto" in content
        results.append(CheckResult(
            task="T1.1",
            check="Proto 定义完整",
            passed=has_service and has_order and has_trade and has_snapshot,
            message=f"service={has_service}, order={has_order}, trade={has_trade}, snapshot={has_snapshot}",
        ))

    return results


def check_t1_3() -> list[CheckResult]:
    """T1.3: Python gRPC client"""
    results = []

    files = [
        "agent/bridge/engine_client.py",
        "agent/bridge/generate_proto.py",
    ]
    for f in files:
        path = project_root / f
        results.append(CheckResult(
            task="T1.3",
            check=f"文件 {f} 存在",
            passed=path.exists(),
            message="" if path.exists() else f"缺少文件: {f}",
        ))

    try:
        from agent.bridge.engine_client import EngineClient, EngineConfig
        client = EngineClient.__new__(EngineClient)
        methods = ["connect", "disconnect", "feed_order_event", "submit_agent_order",
                    "get_snapshot", "wait_for_drain", "get_agent_trades"]
        missing = [m for m in methods if not hasattr(client, m)]
        results.append(CheckResult(
            task="T1.3",
            check="EngineClient 接口完整",
            passed=len(missing) == 0,
            message=f"缺少方法: {missing}" if missing else "所有方法存在",
        ))
    except Exception as e:
        results.append(CheckResult(
            task="T1.3",
            check="EngineClient 可导入",
            passed=False,
            message=str(e),
        ))

    return results


def check_t2_1() -> list[CheckResult]:
    """T2.1: LangGraph StateGraph 定义"""
    results = []

    files = [
        "agent/graph/state.py",
        "agent/graph/trading_graph.py",
        "agent/config.py",
    ]
    for f in files:
        path = project_root / f
        results.append(CheckResult(
            task="T2.1",
            check=f"文件 {f} 存在",
            passed=path.exists(),
            message="" if path.exists() else f"缺少文件: {f}",
        ))

    try:
        from agent.graph.state import AgentState, DebateState, OrderDecision, RiskDecision
        from agent.graph.trading_graph import TradingGraph
        results.append(CheckResult(
            task="T2.1",
            check="状态类可导入",
            passed=True,
            message="AgentState, DebateState, OrderDecision, RiskDecision",
        ))
    except Exception as e:
        results.append(CheckResult(
            task="T2.1",
            check="状态类可导入",
            passed=False,
            message=str(e),
        ))

    return results


def check_t2_2() -> list[CheckResult]:
    """T2.2: 技术面分析师 Agent"""
    results = []

    try:
        from agent.agents.analyst import TechnicalAnalystAgent
        agent = TechnicalAnalystAgent()
        has_run = hasattr(agent, "run")
        has_indicators = hasattr(agent, "_calculate_indicators")
        results.append(CheckResult(
            task="T2.2",
            check="TechnicalAnalystAgent 接口",
            passed=has_run and has_indicators,
            message=f"run={has_run}, _calculate_indicators={has_indicators}",
        ))
    except Exception as e:
        results.append(CheckResult(
            task="T2.2",
            check="TechnicalAnalystAgent 可导入",
            passed=False,
            message=str(e),
        ))

    return results


def check_t2_4() -> list[CheckResult]:
    """T2.4: 风控规则引擎"""
    results = []

    try:
        from agent.risk.engine import RiskEngine, RiskConfig
        from agent.risk.rules import (
            MaxPositionRule, ConcentrationRule, LimitPriceRule,
            MinVolumeRule, FrequencyRule,
            DailyLossRule, ConsecutiveLossRule, ConfidenceRule, DataAnomalyRule,
        )
        engine = RiskEngine()
        rule_count = len(engine.rules)
        results.append(CheckResult(
            task="T2.4",
            check="风控规则数量",
            passed=rule_count >= 9,
            message=f"规则数: {rule_count} (需要 >= 9)",
        ))
    except Exception as e:
        results.append(CheckResult(
            task="T2.4",
            check="风控引擎可导入",
            passed=False,
            message=str(e),
        ))

    return results


def run_all_checks() -> list[CheckResult]:
    """运行所有检查"""
    all_results = []
    all_results.extend(check_t0_1())
    all_results.extend(check_t0_2())
    all_results.extend(check_t0_3())
    all_results.extend(check_t1_1())
    all_results.extend(check_t1_3())
    all_results.extend(check_t2_1())
    all_results.extend(check_t2_2())
    all_results.extend(check_t2_4())
    return all_results


def main():
    """主函数"""
    print("=" * 60)
    print("TradeAgent-Veritas Task Verification")
    print("=" * 60)
    print()

    results = run_all_checks()

    # 按任务分组
    tasks: dict[str, list[CheckResult]] = {}
    for r in results:
        if r.task not in tasks:
            tasks[r.task] = []
        tasks[r.task].append(r)

    # 输出结果
    total_passed = 0
    total_failed = 0

    for task, checks in sorted(tasks.items()):
        passed = all(c.passed for c in checks)
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {task}")
        for c in checks:
            icon = "  [ok]" if c.passed else "  [NG]"
            msg = f" - {c.message}" if c.message else ""
            print(f"  {icon} {c.check}{msg}")
            if c.passed:
                total_passed += 1
            else:
                total_failed += 1
        print()

    # 汇总
    print("=" * 60)
    print(f"Total: {total_passed} passed, {total_failed} failed")
    if total_failed > 0:
        print("WARNING: Some checks failed. Please continue implementation.")
        sys.exit(1)
    else:
        print("All checks passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
