"""
ch14 demo —— Subagent 子智能体探索

运行前: export DEEPSEEK_API_KEY="你的key"
运行: python3 cmd/demo_ch14.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw import AgentEngine, DeepSeekProvider, ToolRegistry
from tiny_claw import ReadFileTool, BashTool
from tiny_claw.tools.subagent import SubagentTool
from tiny_claw.context.session import Session
from tiny_claw.schema import Message, Role

work_dir = str(Path(__file__).resolve().parent.parent)

# 主 Agent：全功能
main_registry = ToolRegistry()
main_registry.register(ReadFileTool(work_dir))
main_registry.register(BashTool(work_dir))

# 子 Agent：只读
read_only = ToolRegistry()
read_only.register(ReadFileTool(work_dir))
read_only.register(BashTool(work_dir))

engine = AgentEngine(DeepSeekProvider("deepseek-chat"), main_registry, work_dir)

# 注册 Subagent 工具（持有只读 registry）
main_registry.register(SubagentTool(engine, read_only, work_dir))

session = Session("subagent_demo", work_dir)
session.history.append(Message(
    role=Role.USER,
    content="派子 Agent 用 bash 查看当前目录下的 .py 文件列表，向我汇报。"
))

engine.run(session)
print("\n✨ Subagent 协同完成！")
