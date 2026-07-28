"""
subagent.py —— 子智能体工具（探路者模式）

TODO:
  - [x] 单 Subagent
  - [x] 多 Subagent 并发 + 竞态修复（clone_with）
  - [ ] 流式返回 / 超时熔断
  - [ ] 持久化 Teammate（参考 Claude Code：独立线程 + JSONL inbox 通信）

竞态问题（ch15 发现并修复）:
  现象：两个 Subagent 并发时，第二个报「工具不存在」
  根因：多线程共享 engine.registry，A 跑完恢复 main_registry 后 B 的 registry 被篡改
  解决：clone_with(registry) → 每个 Subagent 独立引擎副本，零共享状态
"""

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine import AgentEngine

from ..context.session import Session
from ..schema import Message, Role, ToolDefinition
from . import ToolRegistry

logger = logging.getLogger(__name__)

SUBAGENT_SYSTEM = """You are an explorer subagent. Your task is to investigate
and report back. Use ONLY read-only tools (read_file, bash, glob).
When finished, return a concise summary. Do NOT modify any files."""


class SubagentTool:
    """派出子 Agent 探索。只读工具，最多 10 轮。"""

    def __init__(self, engine: "AgentEngine",
                 read_only_registry: ToolRegistry,
                 work_dir: str) -> None:
        self._engine = engine
        self._read_only = read_only_registry
        self._work_dir = work_dir

    @property
    def name(self) -> str:
        return "spawn_subagent"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="spawn_subagent",
            description="派子 Agent 去探索文件/代码/配置，返回摘要。"
                        "用于搜索、查找、跨文件分析。",
            input_schema={
                "type": "object",
                "properties": {
                    "task_prompt": {
                        "type": "string",
                        "description": "给子 Agent 的探索指令",
                    },
                },
                "required": ["task_prompt"],
            },
        )

    def execute(self, arguments: dict[str, Any]) -> str:
        task = arguments.get("task_prompt", "")
        logger.info("[Subagent] 出发！任务: %s", task[:80])

        session = Session(id=f"sub_{hash(task) & 0x7fffffff:x}",
                          work_dir=self._work_dir)
        session.history = [
            Message(role=Role.SYSTEM, content=SUBAGENT_SYSTEM),
            Message(role=Role.USER, content=task),
        ]

        # 独立引擎副本，多 Subagent 并发时不竞态
        sub = self._engine.clone_with(self._read_only)
        # 强制关闭 Plan 模式：Subagent 有自己的 SUBAGENT_SYSTEM，
        # 不能被 Plan 模式的 PLAN_SYSTEM_PROMPT 覆盖
        sub.plan_mode = False
        sub.plan = None
        sub.run(session, max_turns=10)

        # 提取最后一轮 AI 回复作为摘要
        for msg in reversed(session.history):
            if msg.role == Role.ASSISTANT and msg.content:
                return f"[子 Agent 报告]\n{msg.content}"
        return "[子 Agent] 未找到结果"
