"""
tools.py —— 工具注册表 + 具体工具实现
"""

from pathlib import Path
from typing import Any, Optional, Protocol

from ..schema import ToolCall, ToolDefinition, ToolResult


# ============================================================
# 单个工具接口
# ============================================================
class Tool(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def definition(self) -> ToolDefinition: ...
    def execute(self, arguments: dict[str, Any]) -> str: ...


# ============================================================
# 真实工具注册表：注册 → 查询 → 执行
# ============================================================
class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_definitions(self) -> list[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

    def execute(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                tool_call_id=call.id,
                output=f"未找到工具 '{call.name}'",
                is_error=True,
            )
        try:
            output = tool.execute(call.arguments)
            return ToolResult(tool_call_id=call.id, output=output)
        except Exception as e:
            return ToolResult(
                tool_call_id=call.id,
                output=f"工具异常: {e}",
                is_error=True,
            )


# ============================================================
# Mock 注册表：保留，ch02/ch03 demo 继续能用
# ============================================================
class MockRegistry:
    def get_definitions(self) -> list[ToolDefinition]:
        return []

    def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_call_id=call.id,
            output="-rw-r--r--  1 user group  234 Oct 24 10:00 main.py\n",
            is_error=False,
        )


# ============================================================
# ReadFile 工具 —— 读取工作区文件
# ============================================================
class ReadFileTool:
    def __init__(self, work_dir: str) -> None:
        self.work_dir = Path(work_dir)

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="读取指定路径的文件内容。请提供相对工作区的路径。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径，如 hello.txt",
                    },
                },
                "required": ["path"],
            },
        )

    def execute(self, arguments: dict[str, Any]) -> str:
        path = arguments.get("path", "")
        full_path = self.work_dir / path

        # 安全检查：禁止读取工作区外的文件
        try:
            full_path.resolve().relative_to(self.work_dir.resolve())
        except ValueError:
            raise ValueError(f"禁止访问工作区外的路径: {path}")

        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        content = full_path.read_text(encoding="utf-8")

        # 截断过长的内容（保护上下文不溢出）
        if len(content) > 8000:
            return content[:8000] + f"\n\n...[内容过长，已截断至前 8000 字节]..."

        return content


# ============================================================
# WriteFile 工具 —— 创建或覆盖写入文件
# ============================================================
class WriteFileTool:
    def __init__(self, work_dir: str) -> None:
        self.work_dir = Path(work_dir)

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_file",
            description="创建或覆盖写入一个文件。目录不存在会自动创建。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要写入的文件路径，如 src/main.py",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整文件内容",
                    },
                },
                "required": ["path", "content"],
            },
        )

    def execute(self, arguments: dict[str, Any]) -> str:
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        full_path = self.work_dir / path

        try:
            full_path.resolve().relative_to(self.work_dir.resolve())
        except ValueError:
            raise ValueError(f"禁止访问工作区外的路径: {path}")

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return f"文件已写入: {path} ({len(content)} 字节)"


# ============================================================
# Bash 工具 —— 执行 Shell 命令
# ============================================================
class BashTool:
    def __init__(self, work_dir: str) -> None:
        self.work_dir = Path(work_dir)

    @property
    def name(self) -> str:
        return "bash"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="bash",
            description="在终端中执行一条 Shell 命令，返回 stdout/stderr。超时 30 秒。",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 Shell 命令，如 ls -la",
                    },
                },
                "required": ["command"],
            },
        )

    def execute(self, arguments: dict[str, Any]) -> str:
        import subprocess

        command = arguments.get("command", "")
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.work_dir),
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if result.returncode != 0:
                output += f"\n[退出码: {result.returncode}]"
            return output.strip() or "(无输出)"
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"命令超时（30秒）: {command}")


# ============================================================
# DiffEngine — 可插拔 diff 后端（ch17 C++ 加速入口）
#
# 场景：Agent 通过 edit_file 编辑代码时，AI 提供 old_text（一小段代码），
#       需要在文件内容中定位这段代码的位置并替换。
#       本质是「在海里找珍珠」—— 5000 行文件中定位 10 行代码。
#
# 为什么不用标准 Myers Diff：
#   标准 Myers 计算两个文件之间的完整编辑脚本（给 git 用）。
#   我们的场景完全不同：一个文件 vs 一小段文本，只需要定位 + 替换。
#   滑动窗口 + 编辑距离才是正确算法。
#
# SimpleDiffEngine（当前）：Python 4 层退化匹配（精确 → 归一化 → strip → 逐行）
# MyersDiffEngine（ch17）：  C++ 滑动窗口 + 编辑距离 + 早停优化
# ============================================================
class DiffEngine(Protocol):
    def apply_edit(self, content: str, old_text: str, new_text: str) -> str:
        """在 content 中找到 old_text 并替换为 new_text，找不到抛异常"""
        ...


# ============================================================
# SimpleDiffEngine —— Python 版 fuzzyReplace（对标 Go 版）
# ============================================================
class SimpleDiffEngine:
    def apply_edit(self, content: str, old_text: str, new_text: str) -> str:
        # L1: 精确匹配
        count = content.count(old_text)
        if count == 1:
            return content.replace(old_text, new_text, 1)
        if count > 1:
            raise ValueError(f"old_text 匹配到 {count} 处，请提供更多上下文确保唯一性")

        # L2: 换行符归一化
        nc = content.replace("\r\n", "\n")
        no = old_text.replace("\r\n", "\n")
        count = nc.count(no)
        if count == 1:
            return nc.replace(no, new_text, 1)

        # L3: 去除首尾空白
        trimmed = no.strip()
        if trimmed:
            count = nc.count(trimmed)
            if count == 1:
                return nc.replace(trimmed, new_text, 1)

        # L4: 逐行去缩进
        return self._line_by_line(nc, no, new_text)

    def _line_by_line(self, content: str, old: str, new: str) -> str:
        c_lines = content.split("\n")
        o_lines = [l.strip() for l in old.strip().split("\n")]
        if not o_lines or len(c_lines) < len(o_lines):
            raise ValueError("在文件中未找到 old_text，请用 read_file 确认内容")

        for i in range(len(c_lines) - len(o_lines) + 1):
            match = all(
                c_lines[i + j].strip() == o_lines[j]
                for j in range(len(o_lines))
            )
            if match:
                c_lines[i : i + len(o_lines)] = [new]
                return "\n".join(c_lines)

        raise ValueError("在文件中未找到 old_text，请用 read_file 确认文件内容")


# ============================================================
# EditFile 工具 —— 精准代码编辑
# 通过 DiffEngine 接口注入，benchmark 时换 C++ 引擎零侵入
# ============================================================
class EditFileTool:
    def __init__(self, work_dir: str, diff_engine: Optional[DiffEngine] = None) -> None:
        self.work_dir = Path(work_dir)
        self.diff = diff_engine or SimpleDiffEngine()

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="edit_file",
            description="对现有文件进行局部替换。提供 old_text（原文本）和 new_text（新文本），"
                        "old_text 需要包含足够上下文确保唯一匹配。",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "old_text": {"type": "string", "description": "要替换的原文本"},
                    "new_text": {"type": "string", "description": "替换后的新文本"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        )

    def execute(self, arguments: dict[str, Any]) -> str:
        path = arguments.get("path", "")
        old_text = arguments.get("old_text", "")
        new_text = arguments.get("new_text", "")
        full_path = self.work_dir / path

        try:
            full_path.resolve().relative_to(self.work_dir.resolve())
        except ValueError:
            raise ValueError(f"禁止访问工作区外的路径: {path}")

        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        original = full_path.read_text(encoding="utf-8")
        updated = self.diff.apply_edit(original, old_text, new_text)
        full_path.write_text(updated, encoding="utf-8")
        return f"✅ 已修改: {path}"
