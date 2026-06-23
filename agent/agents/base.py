"""Agent 基类

所有 Agent 的基类，提供通用功能：
- LLM 调用
- Prompt 模板管理
- 错误处理
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Agent 基类"""

    def __init__(self, llm: Any, name: str = "BaseAgent"):
        """
        Args:
            llm: LLM 客户端实例
            name: Agent 名称
        """
        self.llm = llm
        self.name = name

    @abstractmethod
    async def run(self, **kwargs) -> Any:
        """运行 Agent

        Args:
            **kwargs: Agent 特定参数

        Returns:
            Agent 输出
        """
        pass

    async def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """调用 LLM

        Args:
            prompt: 用户 prompt
            system_prompt: 系统 prompt

        Returns:
            LLM 响应文本
        """
        if self.llm is None:
            raise RuntimeError(f"[{self.name}] LLM 未初始化")

        try:
            # 支持不同的 LLM 接口
            if hasattr(self.llm, "ainvoke"):
                # LangChain 接口
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                response = await self.llm.ainvoke(messages)
                return response.content if hasattr(response, "content") else str(response)
            elif hasattr(self.llm, "chat"):
                # OpenAI 兼容接口
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                response = self.llm.chat(messages)
                return response.choices[0].message.content
            else:
                raise ValueError(f"不支持的 LLM 接口: {type(self.llm)}")
        except Exception as e:
            print(f"[{self.name}] LLM 调用失败: {e}")
            raise

    def _format_klines(self, klines: list[dict]) -> str:
        """格式化 K 线数据为文本"""
        if not klines:
            return "无数据"

        lines = ["时间 | 开盘 | 最高 | 最低 | 收盘 | 成交量"]
        lines.append("-" * 50)
        for k in klines[-10:]:  # 只显示最近 10 根
            lines.append(
                f"{k.get('timestamp', '')} | "
                f"{k.get('open', 0):.2f} | "
                f"{k.get('high', 0):.2f} | "
                f"{k.get('low', 0):.2f} | "
                f"{k.get('close', 0):.2f} | "
                f"{k.get('volume', 0)}"
            )
        return "\n".join(lines)

    def _format_snapshot(self, snapshot: dict) -> str:
        """格式化市场快照为文本"""
        if not snapshot:
            return "无数据"

        lines = [f"股票: {snapshot.get('security_id', '未知')}"]
        lines.append(f"最新价: {snapshot.get('last_price', 0):.2f}")
        lines.append(f"总成交量: {snapshot.get('total_volume', 0)}")

        # 买盘
        bids = snapshot.get("bids", [])
        if bids:
            lines.append("\n买盘:")
            for i, (price, vol) in enumerate(bids[:5]):
                lines.append(f"  买{i+1}: {price:.2f} x {vol}")

        # 卖盘
        asks = snapshot.get("asks", [])
        if asks:
            lines.append("\n卖盘:")
            for i, (price, vol) in enumerate(asks[:5]):
                lines.append(f"  卖{i+1}: {price:.2f} x {vol}")

        return "\n".join(lines)
