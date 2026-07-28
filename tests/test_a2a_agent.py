"""
test_a2a_agent.py —— A2A Agent 节点集成测试

两种测试模式：
  standalone: 用 MockProvider，只需 Python 标准库，不调真实 LLM
  integration: 启动真实服务，用 curl 发包（需要 DeepSeek API Key）

用法:
  # 独立测试（零依赖）
  python tests/test_a2a_agent.py

  # 集成测试（需要 DEEPSEEK_API_KEY 和网络）
  DEEPSEEK_API_KEY=sk-xxx python tests/test_a2a_agent.py --integration
"""

import json
import logging
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw.engine import AgentEngine
from tiny_claw.provider import MockProvider
from tiny_claw.schema import Message, Role, ToolDefinition
from tiny_claw.tools import ToolRegistry
from tiny_claw.a2a_server import A2AServer

logging.basicConfig(level=logging.WARNING)


# ── Mock Provider（不调 LLM，固定返回）────────────────────

class TestProvider:
    """测试用 Provider，返回预设响应"""

    def generate(self, messages, tools=None):
        # 检查是否要求用工具
        if tools and any("read_file" in str(t.name) for t in tools):
            return Message(role=Role.ASSISTANT, content="",
                          tool_calls=[])
        return Message(role=Role.ASSISTANT,
                       content="Test response: task completed.")


# ── HTTP 工具函数 ─────────────────────────────────────────

def http_post(url: str, data: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(url: str) -> dict:
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── 测试用例 ──────────────────────────────────────────────

class TestA2AAgent:
    """A2A Agent 独立测试（不调外部 API）"""

    @classmethod
    def setup_class(cls):
        """启动一个测试用的 A2A Server"""
        engine = AgentEngine(TestProvider(), ToolRegistry(), work_dir=".")
        cls.server = A2AServer(engine, port=15002, name="test-agent")
        cls.thread = threading.Thread(target=cls.server.start, daemon=True)
        cls.thread.start()
        time.sleep(0.5)  # 等服务器就绪

    def test_agent_card(self):
        """GET /.well-known/agent-card.json 返回正确的 Agent Card"""
        resp = http_get("http://localhost:15002/.well-known/agent-card.json")
        assert resp["name"] == "test-agent"
        print("  ✅ Agent Card 正确:", resp["name"])

    def test_message_send(self):
        """POST message/send 返回正确格式的响应"""
        payload = {
            "jsonrpc": "2.0",
            "id": "test-1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "hello"}],
                },
                "contextId": "test-ctx",
            },
        }
        resp = http_post("http://localhost:15002/", payload)
        assert "result" in resp
        assert resp["result"]["kind"] == "task"
        assert resp["result"]["status"]["state"] == "completed"
        parts = resp["result"]["artifacts"][0]["parts"]
        assert any("test" in p.get("text", "").lower() for p in parts)
        print("  ✅ message/send 正确:", resp["result"]["status"]["state"])

    def test_unknown_method(self):
        """未知 method 返回错误"""
        payload = {
            "jsonrpc": "2.0", "id": "test-2",
            "method": "unknown/method", "params": {},
        }
        resp = http_post("http://localhost:15002/", payload)
        assert "error" in resp
        print("  ✅ 未知 method 返回错误:", resp["error"]["message"])

    def test_empty_message(self):
        """空消息返回错误"""
        payload = {
            "jsonrpc": "2.0", "id": "test-3",
            "method": "message/send",
            "params": {"message": {"role": "user", "parts": []}},
        }
        resp = http_post("http://localhost:15002/", payload)
        assert "error" in resp
        print("  ✅ 空消息返回错误")

    def test_concurrent_requests(self):
        """并发请求各返回独立结果"""
        import concurrent.futures

        def send_one(i):
            payload = {
                "jsonrpc": "2.0", "id": f"concurrent-{i}",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": f"task {i}"}],
                    },
                },
            }
            return http_post("http://localhost:15002/", payload)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            results = list(ex.map(send_one, range(5)))

        for i, r in enumerate(results):
            assert "result" in r, f"请求 {i} 失败: {r}"
        print("  ✅ 5 并发请求全部成功")

    def test_jsonrpc_format(self):
        """响应格式符合 JSON-RPC 2.0 规范"""
        payload = {
            "jsonrpc": "2.0", "id": "rpc-fmt",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "test"}],
                },
            },
        }
        resp = http_post("http://localhost:15002/", payload)
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == "rpc-fmt"
        print("  ✅ JSON-RPC 2.0 格式正确")


# ── Main ──────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--integration", action="store_true",
                        help="运行集成测试（需要 DEEPSEEK_API_KEY）")
    args = parser.parse_args()

    if args.integration:
        print("=== A2A Agent 集成测试（真实 LLM）===")
        import subprocess
        import os
        src_dir = str(Path(__file__).resolve().parent.parent / "src")
        env = {
            **os.environ,
            "PYTHONPATH": src_dir,
            "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", ""),
        }
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "cmd" / "a2a_agent.py"),
             "--port", "15003", "--name", "integration-test"],
            env=env,
        )
        time.sleep(2)
        try:
            resp = http_post("http://localhost:15003/", {
                "jsonrpc": "2.0", "id": "int-1",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text",
                                   "text": "What is 1+1? Reply with just the number."}],
                    },
                },
            })
            print("  结果:", resp)
        finally:
            proc.terminate()
            proc.wait()
    else:
        print("=== A2A Agent 独立测试（Mock LLM）===")
        test = TestA2AAgent()
        TestA2AAgent.setup_class()
        test.test_agent_card()
        test.test_message_send()
        test.test_unknown_method()
        test.test_empty_message()
        test.test_concurrent_requests()
        test.test_jsonrpc_format()
        print("\n🎉 全部 6 项测试通过！")
