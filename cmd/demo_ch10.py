"""
ch10 demo —— Session 断点续传

运行前设置: export DEEPSEEK_API_KEY="你的key"
运行: python3 cmd/demo_ch10.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw import AgentEngine, DeepSeekProvider, ToolRegistry, BashTool
from tiny_claw.context.session import Session, SQLiteStore
from tiny_claw.schema import Message, Role

work_dir = str(Path(__file__).resolve().parent.parent)
store = SQLiteStore(Path(work_dir) / "demo_ch10_sessions.db")
session_id = "ch10_demo"
engine = AgentEngine(DeepSeekProvider("deepseek-chat"),
                     ToolRegistry(), work_dir)

print("=" * 50)
print("第 1 轮：记住一个数字")
print("=" * 50)

session = store.load(session_id) or Session(session_id, work_dir)
session.history.append(Message(role=Role.USER,
                               content="请记住：我喜欢的数字是 42。只需回复「记住了」。"))
engine.run(session)
store.save(session)

print(f"\n会话已保存到 SQLite，history {len(session.history)} 条消息\n")

print("=" * 50)
print("第 2 轮：从 SQLite 恢复，追问刚才的数字")
print("=" * 50)

session2 = store.load(session_id)
assert session2 is not None
session2.history.append(Message(role=Role.USER,
                                content="我刚才让你记住的数字是多少？不准调用工具。"))
engine.run(session2)
store.save(session2)

print(f"\n✨ 断点续传完成！两轮对话共 {len(session2.history)} 条消息")
print(f"SQLite 文件: {work_dir}/demo_ch10_sessions.db")
