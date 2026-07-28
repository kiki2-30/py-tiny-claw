"""
ch07 demo —— EditFile 精准代码编辑（可插拔 DiffEngine）

运行前设置环境变量:
    export DEEPSEEK_API_KEY="你的key"

运行: python3 cmd/demo_ch07.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw import (
    AgentEngine,
    DeepSeekProvider,
    EditFileTool,
    ToolRegistry,
)
from tiny_claw.context.session import Session
from tiny_claw.schema import Message, Role

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

print("🚀 ch07 —— EditFile 精准代码编辑\n")

work_dir = str(Path(__file__).resolve().parent.parent)  # py-tiny-claw/

brain = DeepSeekProvider("deepseek-chat")
registry = ToolRegistry()
registry.register(EditFileTool(work_dir))

# EditFileTool 默认使用 SimpleDiffEngine（Python 版）
# 未来换上 C++ 版只需: EditFileTool(work_dir, MyersDiffEngine())

engine = AgentEngine(brain, registry, work_dir, enable_thinking=True)

session = Session("ch07_demo", work_dir)
session.history.append(Message(role=Role.USER, content="""
当前目录下有一个 service.py 文件。
请把 "# TODO: 增加鉴权逻辑" 下面的 if 语句替换为：
    if user is None:
        print("Forbidden!")
        return

请直接使用 edit_file 工具，old_text 用：
    if user is None:
        print("Welcome, guest!")
        return
"""))
engine.run(session)

print("\n✨ EditFile + 可插拔 DiffEngine 测试完成！")
