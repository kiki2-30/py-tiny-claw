# learn-claude-code 深度分析：对 py-tiny-claw 的工程启示

> 来源：[learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)（已 fork 到本地）
> 分析日期：2026-06-30
> 分析方法：逐章对照 py-tiny-claw 现有实现，提取可借鉴的工程模式和缺失能力

---

## 一、项目概览

learn-claude-code 是一个**教学仓库**，20 章递进式教你构建 Claude Code 同款 Agent Harness。核心哲学：

> **Agency 来自模型训练，Harness 是让模型能在真实环境中工作的"载具"。**
> Harness = Tools + Knowledge + Observation + Action Interfaces + Permissions

| 指标 | learn-claude-code | py-tiny-claw（当前） |
|------|-------------------|---------------------|
| 语言 | Python + Anthropic SDK | Python + OpenAI SDK (DeepSeek) |
| 章节 | 20 章（s01→s20） | 已完成 ch01-ch09，规划至 ch22 |
| 代码量 | s01: 137 行 → s20: 2123 行 | engine.py: ~90 行 |
| 模型 | claude-sonnet-4-6 | deepseek-chat |
| 设计风格 | 教学极简，每章只加一个机制 | 产品化，Protocol 抽象 + 量化计时 |

---

## 二、全局映射：learn-claude-code 20 章 → py-tiny-claw

| learn-claude-code | 主题 | py-tiny-claw 状态 | 差距分析 |
|-------------------|------|-------------------|---------|
| s01 Agent Loop | while True 循环 | ✅ ch01-03 已完成 | py-tiny-claw 的 Think→Act 双阶段优于单循环 |
| s02 Tool Use | 工具分发 map | ✅ ch05-07 已完成 | ToolRegistry + Protocol 优于字典分发 |
| s03 Permission | 三层闸门 | ❌ 缺失 | 仅有简易字符串黑名单，需引入 |
| s04 Hooks | 事件扩展点 | ❌ 缺失 | 循环内逻辑耦合，需引入 |
| s05 TodoWrite | 计划提醒 | ⏳ ch13 规划中 | 可先做轻量版 |
| s06 Subagent | 上下文隔离 | ⏳ ch17 规划中 | s06 提供清晰参考实现 |
| s07 Skill Loading | 按需加载知识 | ❌ 未规划 | 可选，适合项目规范注入 |
| s08 Context Compact | 四层压缩 | ⏳ ch11 规划中 | 核心参考，L1-L4 设计精妙 |
| s09 Memory | 文件记忆系统 | ⏳ ch10 规划中 | py-tiny-claw 选 SQLite，方向正确 |
| s10 System Prompt | 分段组装 | ❌ 缺失 | 改动极小，立即可做 |
| s11 Error Recovery | 分类恢复 | ⏳ ch12 规划中 | 三种恢复路径可对标 |
| s12 Task System | 任务 DAG | ⏳ ch13 规划中 | 文件持久化 + blockedBy 依赖 |
| s13 Background Tasks | 后台慢操作 | ❌ 未规划 | pip install 等慢命令不阻塞 |
| s14 Cron Scheduler | 定时调度 | ❌ 未规划 | CI/CD 场景有价值 |
| s15 Agent Teams | 多 Agent 团队 | ⏳ ch17 规划中 | MessageBus 文件收件箱设计 |
| s16 Team Protocols | 结构化握手 | ⏳ ch17 规划中 | shutdown/plan_approval 协议 |
| s17 Autonomous Agents | 自主认领任务 | ⏳ ch17 规划中 | idle_poll 轮询机制 |
| s18 Worktree Isolation | git worktree | ❌ 明确不引入 | 太重，当前不需要 |
| s19 MCP Plugin | 外部工具接入 | ✅ ch09 MCP Server 已完成 | py-tiny-claw 更早实现 |
| s20 Comprehensive | 全部合体 | — | 参考终点架构 |

---

## 三、核心工程模式详解

### 3.1 Hooks 机制（s04）— 🔥 最高优先级

#### 当前问题

`engine.py` 的 `run()` 方法中，工具执行逻辑直接耦合在循环体内：

```python
# engine.py 当前写法 — 逻辑耦合
for f in as_completed(futures):
    i, call = futures[f]
    r = f.result()
    logger.info("  %s %s", "❌" if r.is_error else "✅", call.name)
    obs[i] = Message(role=Role.USER, content=r.output,
                     tool_call_id=call.id)
```

每加一个新能力（权限检查、日志、审计、自动 git add），就要改这段代码。

#### learn-claude-code 的做法

循环只调用 `trigger_hooks()`，具体逻辑通过 `register_hook()` 注册：

```python
# 四个标准事件点
HOOKS = {
    "UserPromptSubmit": [],   # 用户输入后、进入 LLM 前
    "PreToolUse": [],         # 工具执行前
    "PostToolUse": [],        # 工具执行后
    "Stop": [],               # 循环退出前
}

def register_hook(event: str, callback):
    HOOKS[event].append(callback)

def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:   # 返回值 ≠ None → 拦截
            return result
    return None
```

循环体变成：

```python
# 工具执行前
blocked = trigger_hooks("PreToolUse", block)
if blocked:
    results.append(tool_result(block.id, str(blocked)))
    continue

# 执行工具
output = execute(block)

# 工具执行后
trigger_hooks("PostToolUse", block, output)
```

#### 对 py-tiny-claw 的建议

在 `engine.py` 的 `run()` 中：

1. 工具执行前后插入 hook 调用点
2. 把现有的 logger.info 移到 `PostToolUse` hook
3. 权限检查挂到 `PreToolUse` hook
4. 循环退出前触发 `Stop` hook（用于计时汇总、清理）

**预估改动**：~40 行新增代码，不破坏现有逻辑。

---

### 3.2 Permission 三层闸门（s03）— 🔥 最高优先级

#### 当前问题

`tools.py` 中仅有简易黑名单：

```python
dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
if any(d in command for d in dangerous):
    return "Error: Dangerous command blocked"
```

问题：
- 字符串匹配太脆弱（`rm -rf /tmp/foo` vs `rm -rf /`）
- 只针对 bash，不覆盖 write_file/edit_file 的越界写入
- 无法区分「必须拒绝」和「需要审批」

#### learn-claude-code 的三层闸门

```
闸门 1: DENY_LIST     → 硬拒绝（永远禁止）
闸门 2: RULES         → 规则匹配（需要审批）
闸门 3: USER_APPROVAL  → 暂停等用户确认

三道都没命中 → 直接执行
```

**闸门 1 — DENY_LIST**：一张硬拒绝表，先查。命中直接返回阻止信息。

```python
DENY_LIST = [
    "rm -rf /", "sudo", "shutdown", "reboot",
    "mkfs", "dd if=", "> /dev/sda",
]
```

**闸门 2 — RULES**：描述「什么时候需要问用户」。每条规则指定工具和检查条件。

```python
PERMISSION_RULES = [
    {
        "tools": ["write_file", "edit_file"],
        "check": lambda args: not is_safe_path(args["path"]),
        "message": "Writing outside workspace",
    },
    {
        "tools": ["bash"],
        "check": lambda args: any(
            kw in args.get("command", "")
            for kw in ["rm ", "> /etc/", "chmod 777"]
        ),
        "message": "Potentially destructive command",
    },
]
```

**闸门 3 — USER_APPROVAL**：规则命中后，暂停等用户输入 `y/n`。

#### 对 py-tiny-claw 的建议

作为 `PreToolUse` hook 实现，天然解耦。与 DESIGN.md 中「高危操作拦截率 100%」的量化目标直接对齐。

**预估改动**：~80 行，新建 `src/tiny_claw/permission.py`。

---

### 3.3 Context Compaction 四层压缩（s08）— 🟡 ch11 核心参考

#### 问题

Agent 跑久了，上下文爆满。API 直接拒绝：`prompt_too_long`。

#### learn-claude-code 的四层策略

核心设计：「便宜的检查先跑，贵的后跑」。

| 层 | 方法 | API 调用 | 触发条件 | 作用 |
|----|------|---------|---------|------|
| L1 | `snip_compact` | 0 API | 消息数 > 50 | 裁掉中间旧对话，保留头尾 |
| L2 | `micro_compact` | 0 API | 旧工具结果累积 | 旧 tool_result 替换为占位符 |
| L3 | `auto_compact` | 1 API | Token 超阈值 | LLM 生成压缩摘要 |
| L4 | `reactive_compact` | 1 API | API 报错时 | 比 L3 更激进，只保留最后 5 条 |

**L1 的关键细节**：裁剪消息时，不能把 `assistant(tool_use)` 和后面的 `user(tool_result)` 拆开——它们是配对的消息。

```python
# L1 示例：50 条消息 → 保留头部 3 + 尾部 47
if head_end > 0 and _message_has_tool_use(messages[head_end - 1]):
    while head_end < len(messages) and _is_tool_result_message(messages[head_end]):
        head_end += 1  # 保护 tool_use/tool_result 配对
```

**L2 的关键细节**：只保留最近 3 条 `tool_result` 的完整内容，更旧的替换为一行占位符：

```python
KEEP_RECENT_TOOL_RESULTS = 3
# "[Earlier tool result compacted. Re-run if needed.]"
```

#### 对 py-tiny-claw 的建议

ch11 实现时直接对标这四层。L1+L2 是纯字符串操作，零额外 API 成本——这是最值得学的设计。

**预估改动**：~200 行，新建 `src/tiny_claw/context/compactor.py`。

---

### 3.4 Error Recovery 分类恢复（s11）— 🟡 ch12 核心参考

#### 问题

`engine.py` 中 LLM 调用没有任何错误处理。生产环境中 API 错误是常态。

#### learn-claude-code 的三种恢复路径

| 错误类型 | 恢复策略 | 细节 |
|---------|---------|------|
| `max_tokens` 截断 | 升级 8K→64K → 续写提示 | 升级仅一次，续写最多 3 次 |
| `prompt_too_long` | 触发 reactive_compact → 重试 | 压缩过一次还超限就退出 |
| 429/529 临时故障 | 指数退避 + 抖动 | 连续 529 可切换备用模型 |

**截断恢复的关键设计**：

```python
if response.stop_reason == "max_tokens":
    if not state.has_escalated:
        max_tokens = 64000            # 升级到 64K
        state.has_escalated = True
        continue                       # messages 不变，重试同一请求
    # 64K 还是截断 → 保存输出 + 续写提示
    if state.recovery_count < 3:
        messages.append({
            "role": "user",
            "content": "Output token limit hit. Resume directly — "
                       "no apology, no recap. Pick up mid-thought."
        })
        continue
```

注意：第一次升级时不追加截断输出——保持原始请求不变，只增加 token 预算。只有升级后仍截断才用续写提示。

#### 对 py-tiny-claw 的建议

ch12 实现时对标这套分类恢复逻辑。`RecoveryState` 追踪升级次数和重试次数。

**预估改动**：~100 行，在 `engine.py` 的 LLM 调用处包裹 try/except。

---

### 3.5 System Prompt 分段组装（s10）— 🟢 小改动大收益

#### 当前问题

`engine.py` 中 system prompt 硬编码：

```python
Message(role=Role.SYSTEM,
        content="You are an expert coding assistant with tool access.")
```

#### learn-claude-code 的做法

拆成独立 section，运行时按需拼接：

```python
@dataclass
class PromptSection:
    name: str
    content: str
    condition: Callable[[], bool] = lambda: True

def assemble_system_prompt(sections, state):
    return "\n\n".join(
        s.content for s in sections if s.condition(state)
    )
```

四种 section：

| Section | 加载策略 | 内容 |
|---------|---------|------|
| identity | 始终加载 | Agent 身份、工作目录 |
| tools | 始终加载 | 可用工具列表 |
| memory | 条件加载 | 相关记忆（有记忆时才注入） |
| skills | 条件加载 | 技能目录（有技能时才注入） |

#### 对 py-tiny-claw 的建议

随 ch10（Session/Memory）一起做。改动极小（~20 行），但为后续扩展打下基础。

---

### 3.6 TodoWrite 提醒机制（s05）— 🟢 长任务不偏航

#### 核心思路

`todo_write` 工具不做实际工作，只让 Agent 先列计划。如果连续 N 轮没调 `todo_write`，自动注入提醒：

```
"你还有未完成的计划，请检查进度。使用 todo_write 更新状态。"
```

#### 对 py-tiny-claw 的建议

在 ch13 的 Plan 模式之前，可以先做 30 行的轻量版验证效果。核心只是一个计数器 + 条件注入。

---

### 3.7 Background Tasks（s13）— 🔵 慢操作不阻塞

#### 问题

`pip install torch` 要 10 分钟，Agent 在等 bash 返回期间完全空闲。LLM 按 token 计费，空转就是浪费。

#### learn-claude-code 的做法

慢操作扔到后台线程，Agent 继续跑循环，完成后把通知注入对话：

```python
def is_slow_operation(tool_name, tool_input):
    if tool_name != "bash":
        return False
    cmd = tool_input.get("command", "").lower()
    slow_keywords = ["install", "build", "test", "deploy", "compile"]
    return any(kw in cmd for kw in slow_keywords)
```

判断标准：模型显式指定 `run_in_background` 参数优先，启发式兜底。

#### 对 py-tiny-claw 的建议

py-tiny-claw 已有 `ThreadPoolExecutor` 并发执行工具——可以在此基础上加入「慢操作后台化」的判断逻辑。ch13 之后考虑引入。

---

### 3.8 Agent Teams（s15-s17）— 🔵 ch17 参考

learn-claude-code 的团队机制演进：

| 阶段 | 章节 | 能力 |
|------|------|------|
| 子 Agent | s06 | 独立 messages[]，用完销毁，只回传结论 |
| 队友线程 | s15 | MessageBus 文件收件箱，多轮通信 |
| 结构化协议 | s16 | shutdown/plan_approval 请求-响应 |
| 自治认领 | s17 | idle_poll 轮询任务板，自动 claim |

**关键技术点**：

- **MessageBus**：文件收件箱（`.jsonl`），消费式读取（读完删除）
- **idle_poll**：队友空闲时每 5 秒轮询收件箱 + 任务板，60 秒超时
- **ProtocolState**：请求状态追踪（pending → approved/rejected）

#### 对 py-tiny-claw 的建议

ch17 实现时对标这套演进路径。MessageBus 的消费式文件收件箱设计简洁实用。

---

### 3.9 Cron Scheduler（s14）— 🔵 CI/CD 场景有价值

四层调度模型：

1. **Scheduler**：daemon 线程，每秒轮询 cron 表达式
2. **Queue**：`cron_queue`，已触发任务
3. **Queue Processor**：Agent 空闲时自动交付
4. **Consumer**：agent_loop 从队列消费

#### 对 py-tiny-claw 的建议

如果 py-tiny-claw 要支持「每天早上 9 点跑测试」这类 CI/CD 场景，cron scheduler 是必经之路。ch17 之后考虑。

---

## 四、py-tiny-claw 已有的优势（保持）

| 方面 | learn-claude-code | py-tiny-claw | 保持理由 |
|------|-------------------|-------------|---------|
| Think→Act 双阶段 | 混在一次调用 | `tools=None` 剥夺工具 | 意图更清晰，节省 token |
| 并发工具执行 | 顺序执行 | ThreadPoolExecutor | IO 密集工具并发收益大 |
| 类型系统 | dict | dataclass + Protocol | 编译期检查 + IDE 提示 |
| Provider 抽象 | 绑死 Anthropic | Protocol 接口 | 一行换模型 |
| MCP | s19 才引入 | ch09 自研完成 | 生态兼容先行 |
| 量化计时 | 无 | perf_counter 阶段计时 | 数据驱动决策 |

---

## 五、两个核心架构原则

learn-claude-code 最值得学的不是某个具体功能，而是贯穿全书的设计哲学：

### 原则 1：「挂在循环上，不写进循环里」

Hooks 是扩展点，循环是稳定的核心。py-tiny-claw 的 `engine.py` 已经开始臃肿——计时、工具分发、结果收集都耦合在一起。引入 Hooks 后，`run()` 方法可以保持 < 50 行。

```
❌ 每加一个能力就改循环
✅ 每加一个能力就注册一个 hook
```

### 原则 2：「便宜的检查先跑，贵的后跑」

```
Compaction:  L1(0 API) → L2(0 API) → L3(1 API) → L4(1 API)
Permission:  DENY_LIST(O(1)) → RULES(O(n)) → USER_APPROVAL(阻塞)
Error:       escalate(0 API) → retry(0 API) → compact(1 API) → fallback_model
```

每一层都是在上一层失败后才触发，避免不必要的开销。

---

## 六、建议实施路线图

| 优先级 | 内容 | 对应 py-tiny-claw 章节 | 来源 | 预估工作量 | 依赖 |
|--------|------|----------------------|------|-----------|------|
| 🔥 P0 | **Hooks 机制** | ch10 | s04 | ~40 行 | 无 |
| 🔥 P0 | **Permission 三层闸门** | ch10 | s03 | ~80 行 | Hooks |
| 🔥 P0 | **System Prompt 分段组装** | ch10 | s10 | ~20 行 | 无 |
| 🟡 P1 | **Context Compaction 四层** | ch11 | s08 | ~200 行 | Hooks |
| 🟡 P1 | **Error Recovery 分类** | ch12 | s11 | ~100 行 | 无 |
| 🟡 P1 | **TodoWrite 提醒（轻量版）** | ch13 前 | s05 | ~30 行 | 无 |
| 🟢 P2 | **Background Tasks** | ch13 后 | s13 | ~50 行 | Hooks |
| 🟢 P2 | **Subagent + Teams** | ch17 | s06/s15-s17 | ~300 行 | Task System |
| 🔵 P3 | **Cron Scheduler** | ch17 后 | s14 | ~100 行 | Background Tasks |
| 🔵 P3 | **Skill Loading** | 未规划 | s07 | ~80 行 | System Prompt |

---

## 七、明确不引入的

| learn-claude-code 模式 | 原因 | 替代方案 |
|------------------------|------|---------|
| Memory 文件索引 (`.memory/MEMORY.md`) | 单用户适用，py-tiny-claw 面向多 Session | SQLite（ch10 规划） |
| Worktree 隔离 (git worktree) | 太重，当前不需要 | — |
| Anthropic 原生 API 绑定 | py-tiny-claw 用 OpenAI 兼容协议 | DeepSeekProvider |

---

## 八、附录：learn-claude-code 各章节代码量参考

| 章节 | 主题 | code.py 行数 |
|------|------|-------------|
| s01 | Agent Loop | 137 |
| s02 | Tool Use | ~150 |
| s03 | Permission | ~200 |
| s04 | Hooks | ~200 |
| s05 | TodoWrite | ~200 |
| s06 | Subagent | ~250 |
| s07 | Skill Loading | ~250 |
| s08 | Context Compact | 524 |
| s09 | Memory | ~250 |
| s10 | System Prompt | ~200 |
| s11 | Error Recovery | ~250 |
| s12 | Task System | 378 |
| s13 | Background Tasks | ~200 |
| s14 | Cron Scheduler | ~200 |
| s15 | Agent Teams | ~300 |
| s16 | Team Protocols | ~200 |
| s17 | Autonomous Agents | ~250 |
| s18 | Worktree Isolation | ~200 |
| s19 | MCP Plugin | ~200 |
| s20 | Comprehensive（全部合体） | 2123 |

---

> **下一步**：建议从 P0 三项（Hooks + Permission + System Prompt）开始，在 ch10 中一并实现。这三项改动小、收益大、不破坏现有逻辑，可以快速验证 Hook 架构的扩展性。
