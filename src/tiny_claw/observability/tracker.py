"""
observability/tracker.py —— Token 计数 + 成本核算（装饰器模式）

TODO:
  - [ ] 多模型定价表（当前只 deepseek-chat）
  - [ ] 告警阈值（单次调用花费 > ¥1 时警告）
"""

import logging
import time
from typing import Optional

from ..provider import LLMProvider
from ..schema import Message, ToolDefinition

logger = logging.getLogger(__name__)

# 定价：元/百万 Token
PRICING = {
    "deepseek-chat": {"input": 0.15, "output": 0.15},
}


class CostTracker:
    """包装 LLMProvider，记录每次调用的 Token 和花费"""

    def __init__(self, provider: LLMProvider, model: str,
                 session: Optional["Session"] = None) -> None:
        self._provider = provider
        self._model = model
        self._session = session

    def generate(
        self, messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
    ) -> Message:
        t0 = time.perf_counter()
        resp = self._provider.generate(messages, tools)
        elapsed = time.perf_counter() - t0

        usage = getattr(resp, "usage", None)
        if usage:
            price = PRICING.get(self._model, {"input": 0, "output": 0})
            cost = (
                usage.prompt_tokens * price["input"]
                + usage.completion_tokens * price["output"]
            ) / 1_000_000

            logger.info(
                "💰 API: %.1fs | in=%d out=%d | ¥%.6f",
                elapsed, usage.prompt_tokens, usage.completion_tokens, cost,
            )

            if self._session:
                self._session.total_cost += cost
        else:
            logger.info("💰 API: %.1fs | usage=N/A", elapsed)

        return resp
