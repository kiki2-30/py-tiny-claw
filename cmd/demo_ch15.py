"""
ch15 demo —— 多 Subagent 并发验证

运行前: export DEEPSEEK_API_KEY="你的key"
运行: python3 cmd/demo_ch15.py
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

main_registry = ToolRegistry()
main_registry.register(ReadFileTool(work_dir))

read_only = ToolRegistry()
read_only.register(ReadFileTool(work_dir))
read_only.register(BashTool(work_dir))

engine = AgentEngine(DeepSeekProvider("deepseek-chat"), main_registry, work_dir)
main_registry.register(SubagentTool(engine, read_only, work_dir))

session = Session("multi_subagent", work_dir)
session.history.append(Message(
    role=Role.USER,
    content=(
        "请同时派出两个子 Agent 并行处理：\n"
        "子Agent 1：查看 cmd/ 目录下有哪些 .py 文件\n"
        "子Agent 2：查看 src/tiny_claw/context/ 目录下有哪些 .py 文件\n"
        "请在一轮中同时派出，不要逐个派。"
    ),
))

engine.run(session)
print("\n✨ 多 Subagent 并发完成！")
