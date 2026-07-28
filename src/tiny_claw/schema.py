"""
schema.py —— Agent 引擎的数据类型定义
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# 默认 System Prompt（engine / a2a / plan 共用基底）
DEFAULT_SYSTEM_PROMPT = "You are an expert coding assistant with tool access."


# ============================================================
# 消息角色：system / user / assistant
# ============================================================
class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


# ============================================================
# AI 决定调用一个工具时的指令
# ID 用来匹配返回结果，支持并发
# ============================================================
@dataclass
class ToolCall:
    id: str                          # 唯一标识，如 "call_123"
    name: str                        # 工具名，如 "bash"
    arguments: dict[str, Any] = field(default_factory=dict)


# ============================================================
# 工具执行完的回执
# is_error 用于触发后续的自愈恢复逻辑
# ============================================================
@dataclass
class ToolResult:
    tool_call_id: str     # 对应 ToolCall.id
    output: str           # 工具的输出文本
    is_error: bool = False


# ============================================================
# 对话历史的一条消息
# tool_call_id 非空 → 这是一条工具执行结果
# ============================================================
@dataclass
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""
    usage: Optional["Usage"] = None  # ch16: Token 用量


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


# ============================================================
# 工具定义 —— 发给 AI 的「工具说明书」
# input_schema 用 JSON Schema 格式描述参数
# ============================================================
@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
