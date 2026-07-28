"""
ch06 demo —— 三大工具协同 (ReadFile + WriteFile + Bash)

运行前设置环境变量:
    export DEEPSEEK_API_KEY="你的key"

运行: python3 cmd/demo_ch06.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw import (
    AgentEngine,
    BashTool,
    DeepSeekProvider,
    ReadFileTool,
    ToolRegistry,
    WriteFileTool,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

print("🚀 ch06 —— 三大工具协同\n")

work_dir = str(Path(__file__).resolve().parent.parent)  # py-tiny-claw/

brain = DeepSeekProvider("deepseek-chat")
registry = ToolRegistry()
registry.register(ReadFileTool(work_dir))
registry.register(WriteFileTool(work_dir))
registry.register(BashTool(work_dir))

engine = AgentEngine(brain, registry, work_dir, enable_thinking=True)

engine.run("""
请帮我做三件事：
1. 用 bash 查看当前 Python 版本 (python3 --version)
2. 写一个 hello_claw.py，打印 "Hello from go-tiny-claw!"
3. 用 bash 运行这个文件，确认它能正常输出
""")

print("\n✨ 多工具协同完成！")
