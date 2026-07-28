"""
mcp_server.py —— 四大工具 → MCP Server（自研，零依赖）
MCP 本质是 JSON-RPC over stdio：tools/list + tools/call

TODO: Transport 层
  - [ ] stdio（当前）
  - [ ] HTTP/SSE（团队共享 + 飞书 webhook + 手机 bot）

TODO: 功能增强
  - [ ] Session 管理 —— 多用户并发隔离
  - [ ] spawn_agent 工具 —— MCP 暴露完整 Agent 能力（多轮推理+多工具协同）
        当前 tools/call 只做单工具执行，引擎未介入。
        加 spawn_agent 后 IDE 可委派复杂任务：prompt → engine.run() → 返回总结
  - [ ] 工具热加载 —— 不重启注册新工具
  - [ ] 认证鉴权 —— API Key / Token
  - [ ] 结构化错误码 —— 区分「工具不存在」vs「执行失败」vs「超时」
  - [ ] 请求日志 —— 审计谁调了什么

TODO: 运维
  - [ ] 优雅关闭
  - [ ] 配置文件 (.claw.yaml)
"""

import asyncio
import json
import logging
import sys
from typing import Optional

from .tools import BashTool, EditFileTool, ReadFileTool, WriteFileTool

logger = logging.getLogger(__name__)


class MCPServer:
    """MCP 协议适配层 —— 把四大工具暴露成 IDE 可调用的协议"""

    def __init__(self, work_dir: str):
        self.work_dir = work_dir
        self.tools = {
            "read_file": ReadFileTool(work_dir),
            "write_file": WriteFileTool(work_dir),
            "bash": BashTool(work_dir),
            "edit_file": EditFileTool(work_dir),
        }

    # ── Transport 层（未来可插拔）──────────────────────────
    # TODO: 抽象 Transport 接口，支持 stdio / HTTP / SSE

    def _send(self, response: dict) -> None:
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

    def handle(self, request: dict) -> Optional[dict]:
        method = request.get("method")
        req_id = request.get("id")

        # TODO: notifications（无 id 的消息）静默处理

        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"protocolVersion": "2024-11-05",
                           "serverInfo": {"name": "tiny-claw", "version": "0.1.0"}},
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"tools": [
                    {"name": t.name, "description": t.definition.description,
                     "inputSchema": t.definition.input_schema}
                    for t in self.tools.values()
                ]},
            }

        if method == "tools/call":
            params = request.get("params", {})
            name = params.get("name", "")
            args = params.get("arguments", {})

            # TODO: 认证检查点
            # TODO: 结构化错误码（区分 -32600/-32601/-32602/-32603）

            tool = self.tools.get(name)
            if not tool:
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32601, "message": f"Tool not found: {name}"}}
            try:
                result = tool.execute(args)
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": result}]}}
            except Exception as e:
                return {"jsonrpc": "2.0", "id": req_id,
                        "result": {"content": [{"type": "text", "text": str(e)}],
                                   "isError": True}}

        return None

    # ── 生命周期 ──────────────────────────────────────────

    async def run_stdio(self) -> None:
        """stdio Transport —— IDE 通过管道通信"""
        loop = asyncio.get_event_loop()
        buf = ""
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break  # EOF → 父进程关闭了管道
            buf += line
            try:
                req = json.loads(buf)
                buf = ""
                resp = self.handle(req)
                if resp:
                    self._send(resp)
            except json.JSONDecodeError:
                continue
        # TODO: shutdown hook —— 清理临时文件、保存 Session

    def run(self) -> None:
        """入口：启动 stdio MCP Server"""
        asyncio.run(self.run_stdio())
