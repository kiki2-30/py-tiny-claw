"""
ch16 demo —— Cost Tracker + 链路追踪

运行前: export DEEPSEEK_API_KEY="你的key"
运行: python3 cmd/demo_ch16.py
"""

import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw import AgentEngine, DeepSeekProvider, ToolRegistry, BashTool
from tiny_claw.observability.tracker import CostTracker
from tiny_claw.context.session import Session
from tiny_claw.schema import Message, Role

work_dir = str(Path(__file__).resolve().parent.parent)

provider = DeepSeekProvider("deepseek-chat")
session = Session("ch16_demo", work_dir)
tracked = CostTracker(provider, "deepseek-chat", session)

engine = AgentEngine(tracked, ToolRegistry(), work_dir)

session.history.append(Message(role=Role.USER, content="用中文回复：1+1=? 只回答数字。"))

engine.run(session)
print(f"\n💰 Session 累计花费: ¥{getattr(session, 'total_cost', 0):.6f}")
