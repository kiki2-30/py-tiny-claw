"""
recovery.py —— 错误自愈 + 死循环检测

TODO: 优化方向
  - [ ] 结构化错误码匹配（当前是字符串模式匹配）
  - [ ] 自适应重试策略（指数退避 vs 立即重试）
  - [ ] 错误分类统计（Dashboard 展示高频失败工具）
"""

import hashlib
import logging
from typing import Optional

from ..schema import ToolCall, ToolResult

logger = logging.getLogger(__name__)


class RecoveryManager:
    """工具失败时注入恢复建议"""

    def analyze(self, tool_name: str, error: str) -> str:
        lower = error.lower()
        hint = ""

        if tool_name == "edit_file":
            if "未找到 old_text" in error or "找不到该代码片段" in error:
                hint = "请先用 read_file 重读文件获取最新内容，再重新编辑。"
            elif "匹配到了" in error and "处" in error:
                hint = "old_text 不够唯一，请增加上下文行数确保匹配唯一。"
        elif tool_name in ("read_file", "write_file"):
            if "no such file" in lower or "文件不存在" in error:
                hint = "路径不对。请用 bash 执行 ls 或 find 查找正确路径。"
            elif "permission denied" in lower:
                hint = "没有权限操作该文件，请检查工作区限制。"
        elif tool_name == "bash":
            if "command not found" in lower:
                hint = "系统中未安装该命令，请换替代命令或先安装。"
            elif "超时" in error or "timeout" in lower:
                hint = "命令超时。如果是常驻服务，请用 nohup ... & 后台执行。"
            elif "syntax error" in lower:
                hint = "Bash 语法错误，检查引号转义。"
        elif "not found" in lower or "未找到" in error:
            hint = f"工具 '{tool_name}' 不存在，检查拼写。"

        if hint:
            return f"{error}\n\n[恢复建议] {hint}"
        return error


class ReminderInjector:
    """连续 3 次相同参数失败 → 注入提醒打破死循环"""

    def __init__(self) -> None:
        self._failures: dict[str, int] = {}

    def check(self, call: ToolCall, result: ToolResult) -> Optional[str]:
        if not result.is_error:
            self._failures.clear()
            return None

        fp = _fingerprint(call)
        self._failures[fp] = self._failures.get(fp, 0) + 1
        count = self._failures[fp]

        if count >= 3:
            logger.warning("⚠️ 死循环检测: %s 连续失败 %d 次", call.name, count)
            return (
                f"[SYSTEM REMINDER] 你已连续 {count} 次用相同参数调用 "
                f"'{call.name}' 且全部失败。请立即改变策略，或向用户求助。"
            )
        return None


def _fingerprint(call: ToolCall) -> str:
    return hashlib.md5(f"{call.name}{call.arguments}".encode()).hexdigest()
