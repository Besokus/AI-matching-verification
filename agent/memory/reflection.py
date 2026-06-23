"""反思生成器

分析历史决策结果，生成反思内容注入到后续决策中。
"""

from typing import Any

from .models import MemoryRecord
from .memory_store import MemoryStore


class ReflectionGenerator:
    """反思生成器

    分析近期决策结果，识别成功/失败模式，生成反思摘要。
    """

    def __init__(self, store: MemoryStore, llm: Any = None):
        """
        Args:
            store: 决策记录存储
            llm: LLM 客户端（可选）
        """
        self.store = store
        self.llm = llm

    def generate_reflection(
        self,
        security_id: str | None = None,
        recent_count: int = 10,
    ) -> str:
        """生成反思摘要

        Args:
            security_id: 股票代码（可选）
            recent_count: 分析最近 N 条记录

        Returns:
            反思摘要文本
        """
        # 查询最近的已完成决策
        records = self.store.query_history(
            security_id=security_id,
            limit=recent_count,
        )

        # 过滤有结果的记录
        completed = [r for r in records if r.result_pnl != 0]

        if not completed:
            return "暂无历史决策记录"

        # 统计分析
        stats = self.store.get_statistics(security_id)

        # 识别模式
        success_patterns = self._identify_patterns([r for r in completed if r.is_success])
        failure_patterns = self._identify_patterns([r for r in completed if not r.is_success])

        # 生成反思
        reflection_parts = []

        # 总体表现
        reflection_parts.append(f"近期{len(completed)}笔交易，胜率{stats['win_rate']:.1f}%")
        reflection_parts.append(f"总盈亏: {stats['total_pnl']:.2f}")

        # 成功模式
        if success_patterns:
            reflection_parts.append(f"成功模式: {'; '.join(success_patterns)}")

        # 失败模式
        if failure_patterns:
            reflection_parts.append(f"失败模式: {'; '.join(failure_patterns)}")

        # 建议
        suggestions = self._generate_suggestions(stats, success_patterns, failure_patterns)
        if suggestions:
            reflection_parts.append(f"建议: {'; '.join(suggestions)}")

        return " | ".join(reflection_parts)

    def generate_reflection_for_decision(
        self,
        security_id: str,
        action: str,
        technical_signal: str,
        fundamental_valuation: str,
        sentiment_flow: str,
    ) -> str:
        """为特定决策生成反思

        基于历史相似场景的决策结果，生成针对性反思。

        Args:
            security_id: 股票代码
            action: 拟执行操作
            technical_signal: 技术信号
            fundamental_valuation: 基本面估值
            sentiment_flow: 资金流向

        Returns:
            针对性反思文本
        """
        # 查询相似场景的历史记录
        all_records = self.store.query_history(security_id=security_id, limit=50)

        # 筛选相似场景
        similar_records = []
        for r in all_records:
            similarity_score = 0
            if r.action == action:
                similarity_score += 1
            if r.technical_signal == technical_signal:
                similarity_score += 1
            if r.fundamental_valuation == fundamental_valuation:
                similarity_score += 1
            if r.sentiment_flow == sentiment_flow:
                similarity_score += 1

            if similarity_score >= 2:  # 至少 2 个维度相似
                similar_records.append(r)

        if not similar_records:
            return self.generate_reflection(security_id)

        # 分析相似场景的结果
        completed = [r for r in similar_records if r.result_pnl != 0]
        if not completed:
            return f"历史上有{len(similar_records)}次相似场景，但无结果数据"

        win_count = sum(1 for r in completed if r.is_success)
        total_pnl = sum(r.result_pnl for r in completed)
        win_rate = win_count / len(completed) * 100

        reflection_parts = []
        reflection_parts.append(
            f"历史相似场景{len(completed)}次，胜率{win_rate:.1f}%，总盈亏{total_pnl:.2f}"
        )

        # 提取成功/失败案例的关键特征
        successes = [r for r in completed if r.is_success]
        failures = [r for r in completed if not r.is_success]

        if successes:
            avg_confidence = sum(r.confidence for r in successes) / len(successes)
            reflection_parts.append(f"成功案例平均置信度: {avg_confidence:.2f}")

        if failures:
            avg_confidence = sum(r.confidence for r in failures) / len(failures)
            reflection_parts.append(f"失败案例平均置信度: {avg_confidence:.2f}")

            # 常见失败原因
            reasons = [r.reason for r in failures if r.reason]
            if reasons:
                reflection_parts.append(f"常见失败原因: {reasons[0][:50]}")

        return " | ".join(reflection_parts)

    def _identify_patterns(self, records: list[MemoryRecord]) -> list[str]:
        """识别决策模式

        Args:
            records: 决策记录列表

        Returns:
            模式描述列表
        """
        if not records:
            return []

        patterns = []

        # 信号分布
        signal_counts = {}
        for r in records:
            signal = r.technical_signal or "unknown"
            signal_counts[signal] = signal_counts.get(signal, 0) + 1

        if signal_counts:
            most_common = max(signal_counts.items(), key=lambda x: x[1])
            if most_common[1] > len(records) * 0.5:
                patterns.append(f"技术信号'{most_common[0]}'成功率高")

        # 操作分布
        action_counts = {}
        for r in records:
            action = r.action
            action_counts[action] = action_counts.get(action, 0) + 1

        if action_counts:
            most_common = max(action_counts.items(), key=lambda x: x[1])
            patterns.append(f"操作'{most_common[0]}'占比{most_common[1]/len(records)*100:.0f}%")

        # 置信度分析
        avg_confidence = sum(r.confidence for r in records) / len(records)
        if avg_confidence > 0.7:
            patterns.append("高置信度决策")
        elif avg_confidence < 0.4:
            patterns.append("低置信度决策")

        return patterns

    def _generate_suggestions(
        self,
        stats: dict,
        success_patterns: list[str],
        failure_patterns: list[str],
    ) -> list[str]:
        """生成改进建议

        Args:
            stats: 统计信息
            success_patterns: 成功模式
            failure_patterns: 失败模式

        Returns:
            建议列表
        """
        suggestions = []

        # 胜率建议
        win_rate = stats.get("win_rate", 0)
        if win_rate < 40:
            suggestions.append("胜率偏低，建议提高入场标准")
        elif win_rate > 60:
            suggestions.append("胜率良好，可适当增加仓位")

        # 盈亏比建议
        max_win = stats.get("max_win", 0)
        max_loss = stats.get("max_loss", 0)
        if max_loss < 0 and max_win > 0:
            profit_factor = abs(max_win / max_loss)
            if profit_factor < 1:
                suggestions.append("盈亏比不佳，建议设置更严格止损")

        # 失败模式建议
        if "低置信度" in str(failure_patterns):
            suggestions.append("低置信度决策失败率高，建议只在高置信度时交易")

        return suggestions
