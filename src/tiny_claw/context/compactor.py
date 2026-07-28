"""
compactor.py —— 上下文压缩（对标 Go 版规则截断）

TODO: 可插拔压缩策略
  - [ ] RuleCompactor   ← 当前（规则截断，零 API 调用）
  - [ ] LLMCompactor    ← 语义摘要（便宜模型浓缩早期消息）
  - [ ] RAGCompactor    ← 向量检索（Claude Code/Letta 做法，选择性加载相关历史）
  - [ ] SIMD Token 估算 ← C++ 加速字符遍历（Phase 4，100K→1M 字符级别）

TODO: 接口抽象
  - [ ] CompactionStrategy Protocol → 跟 DiffEngine/SessionStore 一样可插拔
"""

import logging

from ..schema import Message, Role

logger = logging.getLogger(__name__)


class Compactor:
    """规则截断：按字符数 + 保护最近 N 条消息"""

    def __init__(self, max_chars: int = 20000, retain_last: int = 6) -> None:
        self.max_chars = max_chars
        self.retain_last = retain_last

    def compact(self, messages: list[Message]) -> list[Message]:
        if self._length(messages) < self.max_chars:
            return messages

        logger.info("⚠️ 上下文 %d 字符超过阈值 %d，触发压缩",
                     self._length(messages), self.max_chars)

        result: list[Message] = []
        protect_start = max(0, len(messages) - self.retain_last)

        for i, msg in enumerate(messages):
            # System 消息永久保留
            if msg.role == Role.SYSTEM:
                result.append(msg)
                continue

            new_msg = Message(role=msg.role, content=msg.content,
                              tool_calls=msg.tool_calls.copy(),
                              tool_call_id=msg.tool_call_id)
            in_working = i >= protect_start

            # 工具结果
            if msg.role == Role.USER and msg.tool_call_id:
                if not in_working and len(msg.content) > 200:
                    new_msg.content = (
                        f"...[早期工具输出已清理，原 {len(msg.content)} 字节]..."
                    )
                elif len(msg.content) > 1000:
                    new_msg.content = (
                        msg.content[:500] +
                        f"\n...[截断 {len(msg.content) - 1000} 字节]...\n" +
                        msg.content[-500:]
                    )

            # 助手推理
            elif msg.role == Role.ASSISTANT and msg.content:
                if not in_working and len(msg.content) > 200:
                    new_msg.content = "...[早期推理已折叠]..."

            result.append(new_msg)

        logger.info("✅ 压缩完成: %d → %d 字符",
                     self._length(messages), self._length(result))
        return result

    def _length(self, messages: list[Message]) -> int:
        total = 0
        for m in messages:
            total += len(m.content)
            for tc in m.tool_calls:
                total += len(tc.name) + len(str(tc.arguments))
        return total
