"""
ch03 demo —— 双阶段推理（Thinking + Action）

运行: python3 cmd/demo_ch03.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw import AgentEngine, MockProvider, MockRegistry
from tiny_claw.context.session import Session
from tiny_claw.schema import Message, Role

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

print("🚀 ch03 —— 双阶段推理 (Thinking + Action)\n")

brain = MockProvider()
toolbox = MockRegistry()

# enable_thinking=True —— 开启 Thinking Phase
engine = AgentEngine(brain, toolbox, str(Path.cwd()), enable_thinking=True)

session = Session("ch03_demo", str(Path.cwd()))
session.history.append(Message(role=Role.USER, content="帮我检查当前目录的文件"))
engine.run(session)

print("\n✨ 双阶段推理跑通！")
