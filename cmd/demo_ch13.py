"""
ch13 demo —— Plan 模式 + .claw.yaml 配置

运行前: export DEEPSEEK_API_KEY="你的key"
运行: python3 cmd/demo_ch13.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw import AgentEngine, DeepSeekProvider, ToolRegistry
from tiny_claw import ReadFileTool, WriteFileTool, EditFileTool
from tiny_claw.config.loader import load_config
from tiny_claw.context.session import Session
from tiny_claw.schema import Message, Role

work_dir = str(Path(__file__).resolve().parent.parent)
config = load_config(Path(work_dir) / ".claw.yaml")

print(f"配置加载: model={config.model} plan_mode={config.plan_mode}\n")

registry = ToolRegistry()
registry.register(ReadFileTool(work_dir))
registry.register(WriteFileTool(work_dir))
registry.register(EditFileTool(work_dir))

engine = AgentEngine(
    DeepSeekProvider(config.model),
    registry,
    work_dir,
    enable_thinking=config.enable_thinking,
    plan_mode=config.plan_mode,
)

session = Session("plan_demo", work_dir)
session.history.append(Message(
    role=Role.USER,
    content="帮我创建一个简单的 Python 项目：一个 hello.py 打印 Hello World，一个 README.md 说明用法。"
))

engine.run(session)
print("\n✨ Plan 模式 + .claw.yaml 完成！")
