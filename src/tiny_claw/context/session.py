"""
session.py —— 会话管理
"""

import json
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

from ..schema import Message


@dataclass
class Session:
    """一个对话会话：标识 + 工作区 + 历史 + 花费"""
    id: str
    work_dir: str
    history: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    total_cost: float = 0.0


# ============================================================
# SessionStore 接口 —— 可插拔存储后端
# ============================================================
class SessionStore(Protocol):
    def save(self, session: Session) -> None: ...
    def load(self, id: str) -> Optional[Session]: ...
    def delete(self, id: str) -> None: ...


# ============================================================
# SQLiteStore —— 默认持久化后端
# ============================================================
class SQLiteStore:
    def __init__(self, path: str = "sessions.db") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "  id TEXT PRIMARY KEY,"
            "  work_dir TEXT,"
            "  history TEXT,"
            "  created_at REAL,"
            "  total_cost REAL DEFAULT 0"
            ")"
        )
        self.conn.commit()

    def save(self, session: Session) -> None:
        history_json = json.dumps(
            [_msg_to_dict(m) for m in session.history],
            ensure_ascii=False,
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?)",
            (session.id, session.work_dir, history_json,
             session.created_at, session.total_cost),
        )
        self.conn.commit()

    def load(self, id: str) -> Optional[Session]:
        row = self.conn.execute(
            "SELECT work_dir, history, created_at, total_cost "
            "FROM sessions WHERE id = ?",
            (id,),
        ).fetchone()
        if not row:
            return None
        history = [_dict_to_msg(m) for m in json.loads(row[1])]
        return Session(id=id, work_dir=str(row[0]), history=history,
                       created_at=float(row[2]),
                       total_cost=float(row[3] or 0))

    def delete(self, id: str) -> None:
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (id,))
        self.conn.commit()


# ============================================================
# MemoryStore —— 测试用内存存储
# ============================================================
class MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, Session] = {}

    def save(self, session: Session) -> None:
        self._data[session.id] = session

    def load(self, id: str) -> Optional[Session]:
        return self._data.get(id)

    def delete(self, id: str) -> None:
        self._data.pop(id, None)


# ============================================================
# Message ↔ dict 序列化
# ============================================================
def _msg_to_dict(msg: Message) -> dict:
    return {
        "role": msg.role.value,
        "content": msg.content,
        "tool_calls": [
            {"id": t.id, "name": t.name, "arguments": t.arguments}
            for t in msg.tool_calls
        ],
        "tool_call_id": msg.tool_call_id,
    }


def _dict_to_msg(d: dict) -> Message:
    from ..schema import Role, ToolCall

    return Message(
        role=Role(d["role"]),
        content=d.get("content", ""),
        tool_calls=[ToolCall(**t) for t in d.get("tool_calls", [])],
        tool_call_id=d.get("tool_call_id", ""),
    )
