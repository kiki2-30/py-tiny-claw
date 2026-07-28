"""
ch02 demo —— Mock 闭环验证（不需要任何 API Key）

运行: python3 cmd/demo_ch02.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw import AgentEngine, MockProvider, MockRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

print("🚀 欢迎来到 go-tiny-claw 引擎启动序列 (Python 版)\n")

brain = MockProvider()          # 模拟大脑
toolbox = MockRegistry()        # 模拟工具
engine = AgentEngine(brain, toolbox, str(Path.cwd()))

engine.run("帮我检查当前目录的文件")

print("\n✨ 演示结束 —— Mock 闭环跑通！")
