"""
ch05 demo —— 第一个真实工具：ReadFile

运行前设置环境变量:
    export DEEPSEEK_API_KEY="你的key"

运行: python3 cmd/demo_ch05.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw import AgentEngine, DeepSeekProvider, ReadFileTool, ToolRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

print("🚀 ch05 —— 第一个真实工具：ReadFile\n")

work_dir = str(Path(__file__).resolve().parent.parent)  # py-tiny-claw/

brain = DeepSeekProvider("deepseek-chat")
registry = ToolRegistry()
registry.register(ReadFileTool(work_dir))

engine = AgentEngine(brain, registry, work_dir)

engine.run("请读取 hello.txt 的内容，并用一句话向我总结。")

print("\n✨ ReadFile 工具测试完成！")
