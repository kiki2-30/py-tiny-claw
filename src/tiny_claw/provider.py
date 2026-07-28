"""
provider.py —— 大模型调用接口 + Mock + DeepSeek 实现
"""

import json
import os
from typing import Any, Optional, Protocol

from openai import OpenAI

from .schema import Message, Role, ToolCall, ToolDefinition, Usage


class LLMProvider(Protocol):
    def generate(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
    ) -> Message: ...


# ============================================================
# DeepSeek Provider —— 对接 DeepSeek API（OpenAI 兼容）
# 环境变量: DEEPSEEK_API_KEY
# ============================================================
class DeepSeekProvider(LLMProvider):
    def __init__(self, model: str = "deepseek-chat") -> None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("请设置 DEEPSEEK_API_KEY 环境变量")
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )
        self.model = model

    def generate(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
    ) -> Message:
        # ── 1. 转换内部消息 → OpenAI 格式 ──
        api_messages = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                api_messages.append({"role": "system", "content": msg.content})
            elif msg.role == Role.USER:
                if msg.tool_call_id:
                    api_messages.append({
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    })
                else:
                    api_messages.append({"role": "user", "content": msg.content})
            elif msg.role == Role.ASSISTANT:
                entry: dict = {"role": "assistant", "content": msg.content or ""}
                if msg.tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                api_messages.append(entry)

        # ── 2. 转换工具定义 → OpenAI 格式 ──
        api_tools = None
        if tools:
            api_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]

        # ── 3. 调用 API ──
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
        }
        if api_tools:
            kwargs["tools"] = api_tools

        resp = self.client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message

        # ── 4. 转换 OpenAI 回复 → 内部 Message ──
        tool_calls = []
        if choice.tool_calls:
            for tc in choice.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        usage = None
        if resp.usage:
            usage = Usage(
                prompt_tokens=resp.usage.prompt_tokens,
                completion_tokens=resp.usage.completion_tokens,
            )

        return Message(
            role=Role.ASSISTANT,
            content=choice.content or "",
            tool_calls=tool_calls,
            usage=usage,
        )


# ============================================================
# Mock 大脑：不调 API，轮次驱动返回预设内容
# ============================================================
class MockProvider:
    def __init__(self) -> None:
        self.turn = 0

    def generate(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
    ) -> Message:
        if tools is None:
            return Message(
                role=Role.ASSISTANT,
                content="【推理中】目标是检查文件。我需要先调用 bash 执行 ls 看看目录下有什么，再决定下一步。",
            )

        self.turn += 1

        if self.turn == 1:
            return Message(
                role=Role.ASSISTANT,
                content="让我来看看当前目录下有什么文件。",
                tool_calls=[
                    ToolCall(
                        id="call_123",
                        name="bash",
                        arguments={"command": "ls -la"},
                    )
                ],
            )

        return Message(
            role=Role.ASSISTANT,
            content="我看到了文件列表，里面包含 main.py，任务完成！",
        )
