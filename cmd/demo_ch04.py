"""
ch04 demo —— 接入真实 DeepSeek API

运行前先设置环境变量:
    export DEEPSEEK_API_KEY="你的key"

运行: python3 cmd/demo_ch04.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw import AgentEngine, DeepSeekProvider, MockRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

print("🚀 ch04 —— 接入真实 DeepSeek API\n")

brain = DeepSeekProvider("deepseek-chat")
toolbox = MockRegistry()

engine = AgentEngine(brain, toolbox, str(Path.cwd()), enable_thinking=True)

engine.run("用中文回答：Python 和 Go 各适合什么场景？一句话总结。")

print("\n✨ DeepSeek API 调用成功！")
