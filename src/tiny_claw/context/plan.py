"""
plan.py —— Plan 模式：TODO.md 任务规划 + 断点续传

Plan 模式下，System Prompt 中注入：
  "请先用 write_file 创建 TODO.md 规划步骤，逐步执行并标记完成"
"""

import logging
from pathlib import Path
from typing import Optional

from ..schema import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT + """

CRITICAL: This is a multi-step task in Plan Mode.
1. FIRST: use write_file to create TODO.md with a checklist of steps
2. Execute steps one by one, using edit_file to mark each as [x] done
3. If interrupted, TODO.md persists on disk — resume by reading it"""


class PlanManager:
    """管理 TODO.md：读取当前状态，注入 Plan System Prompt"""

    def __init__(self, work_dir: str) -> None:
        self.work_dir = Path(work_dir)

    @property
    def todo_path(self) -> str:
        return str(self.work_dir / "TODO.md")

    def load(self) -> Optional[str]:
        """读取当前 TODO.md，不存在返回 None"""
        path = self.work_dir / "TODO.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            logger.info("[Plan] 加载 TODO.md (%d 字节)", len(content))
            return content
        return None

    def inject_plan_prompt(self) -> str:
        """生成 Plan 模式的 System Prompt"""
        todo = self.load()
        if todo:
            return (
                PLAN_SYSTEM_PROMPT +
                f"\n\nCurrent TODO.md status:\n{todo}\n"
                "Continue from where you left off."
            )
        return PLAN_SYSTEM_PROMPT
