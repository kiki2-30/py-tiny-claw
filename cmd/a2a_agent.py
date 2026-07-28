#!/usr/bin/env python3
"""
A2A Agent 节点 —— 把 py-tiny-claw 暴露为 A2A 协议 Agent

用法:
  python -m tiny_claw.a2a_server --port 5002 --name "py-tiny-claw"
  # 或者直接运行本文件:
  python cmd/a2a_agent.py --port 5002
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tiny_claw.engine import AgentEngine
from tiny_claw.provider import DeepSeekProvider
from tiny_claw.tools import BashTool, EditFileTool, ReadFileTool, ToolRegistry, WriteFileTool
from tiny_claw.a2a_server import A2AServer


def main():
    parser = argparse.ArgumentParser(description="py-tiny-claw A2A Agent 节点")
    parser.add_argument("--port", type=int, default=5002, help="监听端口 (默认 5002)")
    parser.add_argument("--name", default="py-tiny-claw", help="Agent 名称")
    parser.add_argument("--work-dir", default=".", help="工作目录")
    parser.add_argument("--read-only", action="store_true", help="只读模式（只探索不修改）")
    parser.add_argument("--max-turns", type=int, default=20, help="最大推理轮数 (默认 20)")
    parser.add_argument("--thinking", action="store_true", help="启用 Think 阶段")
    parser.add_argument("--debug", action="store_true", help="调试日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # 构建引擎
    provider = DeepSeekProvider()
    registry = ToolRegistry()
    if not args.read_only:
        registry.register(ReadFileTool(args.work_dir))
        registry.register(WriteFileTool(args.work_dir))
        registry.register(EditFileTool(args.work_dir))
        registry.register(BashTool(args.work_dir))
    else:
        registry.register(ReadFileTool(args.work_dir))
        registry.register(BashTool(args.work_dir))

    engine = AgentEngine(
        provider, registry, args.work_dir,
        enable_thinking=args.thinking,
    )

    # 启动 A2A Server
    server = A2AServer(
        engine=engine,
        work_dir=args.work_dir,
        name=args.name,
        port=args.port,
        read_only=args.read_only,
        max_turns=args.max_turns,
    )
    server.start()


if __name__ == "__main__":
    main()
