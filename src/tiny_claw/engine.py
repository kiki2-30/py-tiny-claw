"""
engine.py —— ReAct 循环 + 并发工具执行 + 阶段计时
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .provider import LLMProvider
from .schema import Message, Role, ToolResult
from .context.session import Session
from .context.compactor import Compactor
from .context.plan import PlanManager
from .context.recovery import RecoveryManager, ReminderInjector
from .observability.trace import Tracer
from .tools import ToolRegistry

logger = logging.getLogger(__name__)


class AgentEngine:

    def __init__(self, provider: LLMProvider, registry: ToolRegistry,
                 work_dir: str, enable_thinking: bool = False,
                 plan_mode: bool = False) -> None:
        self.provider = provider
        self.registry = registry
        self.work_dir = work_dir
        self.enable_thinking = enable_thinking
        self.plan_mode = plan_mode
        self.plan = PlanManager(work_dir) if plan_mode else None
        self.compactor = Compactor()
        self.recovery = RecoveryManager()
        self.reminder = ReminderInjector()

    def clone_with(self, registry: ToolRegistry) -> "AgentEngine":
        """创建引擎副本（不同 registry），Subagent 并发安全"""
        clone = AgentEngine(self.provider, registry, self.work_dir,
                           enable_thinking=self.enable_thinking,
                           plan_mode=self.plan_mode)
        # 共享 compactor/recovery/reminder 配置（无状态，安全共享）
        clone.compactor = self.compactor
        clone.recovery = self.recovery
        clone.reminder = self.reminder
        clone.plan = self.plan
        return clone

    def run(self, session: Session, max_turns: int = 0) -> None:
        """从 Session 读取历史，跑 ReAct 循环。max_turns=0 表示不限。"""
        t_total = time.perf_counter()
        tracer = Tracer(f"Task-{session.id[:8]}")

        # 确保 System Prompt 在最前面（只插入一次）
        if not session.history or session.history[0].role != Role.SYSTEM:
            session.history.insert(0, Message(
                role=Role.SYSTEM,
                content="You are an expert coding assistant with tool access.",
            ))

        # Plan 模式：替换 System Prompt
        if self.plan_mode and self.plan:
            plan_prompt = self.plan.inject_plan_prompt()
            if session.history and session.history[0].role == Role.SYSTEM:
                session.history[0] = Message(role=Role.SYSTEM, content=plan_prompt)
            else:
                session.history.insert(0, Message(role=Role.SYSTEM, content=plan_prompt))

        history = session.history

        turn = 0
        acc = {"think": 0.0, "act": 0.0, "tool": 0.0}

        while True:
            turn += 1
            # max_turns 限制
            if max_turns and turn > max_turns:
                logger.info("[Engine] 达到最大轮数 %d，退出", max_turns)
                break
            tools = self.registry.get_definitions()

            # 上下文压缩：超阈值则截断（发 LLM 前）
            # 注意：compact 可能返回新 list，需原地替换以保持 session.history 同步
            compacted = self.compactor.compact(history)
            if compacted is not history:
                history[:] = compacted

            # Phase 1: Thinking —— tools=None 剥夺工具，强制纯推理
            if self.enable_thinking:
                tracer.start("Think")
                t0 = time.perf_counter()
                resp = self.provider.generate(history, None)
                acc["think"] += time.perf_counter() - t0
                tracer.end()
                if resp.content:
                    print(f"🧠 [思考]: {resp.content}")
                    history.append(resp)

            # Phase 2: Action
            tracer.start("Act")
            t0 = time.perf_counter()
            resp = self.provider.generate(history, tools)
            acc["act"] += time.perf_counter() - t0
            tracer.end()
            history.append(resp)

            if resp.content:
                print(f"🤖 [回复]: {resp.content}")

            # 无 ToolCall → 任务结束
            if not resp.tool_calls:
                break

            # 工具并发执行
            tracer.start("Tools")
            t0 = time.perf_counter()
            obs: dict[int, Message] = {}
            with ThreadPoolExecutor() as pool:
                futures = {
                    pool.submit(self.registry.execute, c): (i, c)
                    for i, c in enumerate(resp.tool_calls)
                }
                for f in as_completed(futures):
                    i, call = futures[f]
                    r = f.result()
                    # 失败时注入恢复建议
                    if r.is_error:
                        r.output = self.recovery.analyze(call.name, r.output)
                    logger.info("  %s %s", "❌" if r.is_error else "✅", call.name)
                    obs[i] = Message(role=Role.USER, content=r.output,
                                     tool_call_id=call.id)
            acc["tool"] += time.perf_counter() - t0
            tracer.end()  # Tools

            # 按原顺序追加观察结果
            for i in sorted(obs):
                history.append(obs[i])

            # 死循环检测 —— 遍历所有工具调用，任一反复失败即注入提醒
            if resp.tool_calls:
                for i, call in enumerate(resp.tool_calls):
                    msg = obs.get(i)
                    if msg is None:
                        continue
                    is_err = "恢复建议" in msg.content or "异常" in msg.content
                    nudge = self.reminder.check(
                        call,
                        ToolResult(tool_call_id=call.id,
                                   output=msg.content,
                                   is_error=is_err))
                    if nudge:
                        history.append(Message(role=Role.USER, content=nudge))
                        break  # 一轮只注入一条提醒

        # 计时 + Trace 汇总
        tracer.finish()
        t = time.perf_counter() - t_total
        logger.info("⏱️  总计 %.2fs | Think %.2fs | Act %.2fs | Tool %.2fs",
                     t, acc['think'], acc['act'], acc['tool'])
        if session.total_cost:
            logger.info("💰  累计花费: ¥%.6f", session.total_cost)

        # 自动导出 Trace 到工作区
        trace_dir = Path(self.work_dir) / ".tiny_claw" / "traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        tracer.export(str(trace_dir / f"{session.id[:8]}.json"))
