"""
a2a_server.py —— A2A Agent 节点（HTTP Server）

实现 Google A2A 协议的 message/send 端点，
将 py-tiny-claw 的 AgentEngine 暴露为可被 agent-communication 调用的 Agent 节点。

协议：JSON-RPC 2.0 over HTTP
端点：
  POST /                          — 处理 message/send
  GET  /.well-known/agent-card.json — 返回 Agent 元数据
"""

import json
import logging
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

from .engine import AgentEngine, DEFAULT_SYSTEM_PROMPT
from .schema import Message, Role
from .context.session import Session
from .tools import BashTool, EditFileTool, ReadFileTool, ToolRegistry, WriteFileTool

logger = logging.getLogger(__name__)


# ── Agent Card ────────────────────────────────────────────

def build_agent_card(name: str, description: str, url: str,
                     skills: Optional[list[str]] = None) -> dict:
    """构造 A2A 标准的 Agent Card"""
    return {
        "name": name,
        "description": description,
        "url": url,
        "version": "1.0.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
        },
        "skills": [
            {"id": s, "name": s, "description": s}
            for s in (skills or [])
        ],
    }


# ── HTTP Handler ──────────────────────────────────────────

class A2AHandler(BaseHTTPRequestHandler):
    """A2A JSON-RPC 请求处理器"""

    engine: AgentEngine          # 由 A2AServer 注入
    work_dir: str = "."
    agent_card: dict = {}
    agent_name: str = "py-tiny-claw"  # Agent 名称，返回结果时会带标识
    read_only: bool = False
    max_turns: int = 0

    def log_message(self, fmt, *args):
        logger.info("[A2A] %s", fmt % args)

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, req_id, code: int, message: str) -> None:
        self._send_json(200, {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        })

    def do_GET(self) -> None:
        if self.path == "/.well-known/agent-card.json":
            self._send_json(200, self.agent_card)
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"

        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self._error("", -32700, "Parse error")
            return

        req_id = request.get("id", "")
        method = request.get("method", "")

        if method == "message/send":
            self._handle_message_send(req_id, request.get("params", {}))
        elif method == "tasks/get":
            self._error(req_id, -32601, "tasks/get not implemented")
        elif method == "tasks/cancel":
            self._error(req_id, -32601, "tasks/cancel not implemented")
        else:
            self._error(req_id, -32601, f"Method not found: {method}")

    def _handle_message_send(self, req_id: str, params: dict) -> None:
        """核心：收到 message/send，跑 AgentEngine"""
        message = params.get("message", {})
        context_id = message.get("contextId", params.get("contextId", "default"))

        # 提取用户文本
        text = ""
        parts = message.get("parts", [])
        for p in parts:
            if p.get("kind") == "text" or "text" in p:
                text = p.get("text", "")
                break

        if not text:
            self._error(req_id, -32602, "No text content in message")
            return

        logger.info("[A2A] 收到任务 (ctx=%s): %s", context_id, text[:100])

        # 构建 Session → 跑引擎
        session_id = str(uuid.uuid4())[:8]
        session = Session(id=session_id, work_dir=self.work_dir)

        system_prompt = (
            DEFAULT_SYSTEM_PROMPT + " "
            "Complete the user's task step by step, using tools when needed. "
            "Return a clear final answer."
        )
        if self.read_only:
            system_prompt += " IMPORTANT: You have READ-ONLY access. Do NOT modify any files."

        session.history = [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=text),
        ]

        try:
            self.engine.run(session, max_turns=self.max_turns)
        except Exception as e:
            logger.error("[A2A] 引擎异常: %s", e)
            self._error(req_id, -32000, f"Engine error: {e}")
            return

        # 提取最终回复
        result_text = ""
        for msg in reversed(session.history):
            if msg.role == Role.ASSISTANT and msg.content:
                result_text = msg.content
                break
        if not result_text:
            result_text = "[Agent 未产生回复]"

        # 添加 Agent 标识，方便区分是哪个 Agent 回复的
        result_text = f"[{self.agent_name}] {result_text}"

        logger.info("[A2A] 完成 (ctx=%s): %s", context_id, result_text[:100])

        # 返回 A2A 格式响应
        self._send_json(200, {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "kind": "task",
                "id": f"task-{session_id}",
                "contextId": context_id,
                "status": {"state": "completed"},
                "artifacts": [{
                    "parts": [{"kind": "text", "text": result_text}],
                }],
            },
        })


# ── Server ────────────────────────────────────────────────

class A2AServer:
    """A2A Agent 节点服务器"""

    def __init__(self, engine: AgentEngine, work_dir: str = ".",
                 name: str = "py-tiny-claw", description: str = "",
                 port: int = 5002, read_only: bool = False,
                 max_turns: int = 0):
        self.engine = engine
        self.work_dir = str(Path(work_dir).resolve())
        self.name = name
        self.port = port
        self.read_only = read_only
        self.max_turns = max_turns

        self.agent_card = build_agent_card(
            name=name,
            description=description or f"{name} — LLM-powered Agent powered by py-tiny-claw",
            url=f"http://localhost:{port}",
            skills=["coding", "file-operations", "bash"] if not read_only else ["code-exploration"],
        )

    def start(self) -> None:
        # 注入到 handler
        A2AHandler.engine = self.engine
        A2AHandler.work_dir = self.work_dir
        A2AHandler.agent_card = self.agent_card
        A2AHandler.agent_name = self.name
        A2AHandler.read_only = self.read_only
        A2AHandler.max_turns = self.max_turns

        server = HTTPServer(("0.0.0.0", self.port), A2AHandler)
        logger.info("[A2A] %s 启动在端口 %d", self.name, self.port)
        logger.info("[A2A] Agent Card: http://localhost:%d/.well-known/agent-card.json", self.port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("[A2A] 收到中断信号，关闭服务器")
            server.shutdown()
