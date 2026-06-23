"""全局配置管理"""

from dataclasses import dataclass, field
from pathlib import Path

from .risk.engine import RiskConfig


@dataclass
class LLMConfig:
    """LLM 配置"""
    provider: str = "deepseek"
    deep_think_model: str = "deepseek-reasoner"
    quick_think_model: str = "deepseek-chat"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class SynthesizerConfig:
    """合成器配置"""
    volatility: float = 0.02
    points_per_minute: int = 60
    cancel_ratio: float = 0.15
    seed: int | None = None


@dataclass
class BacktestConfig:
    """回测配置"""
    security_id: str = "600519"
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 1_000_000.0
    max_debate_rounds: int = 2
    decision_interval: str = "1m"


@dataclass
class AppConfig:
    """应用配置"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    synthesizer: SynthesizerConfig = field(default_factory=SynthesizerConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    engine_a_host: str = "localhost"
    engine_a_port: int = 50051
    engine_b_host: str = "localhost"
    engine_b_port: int = 50052
    cache_dir: str = "~/.tradeagent/cache"
    log_dir: str = "~/.tradeagent/logs"
