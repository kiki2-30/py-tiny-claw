# 设计决策记录 (Design Decision Log)

> 每完成一个章节，在这里记录关键的设计决策。
> 这些笔记就是你面试时能展开讲的故事。

## 章节路线图

| ch | 内容 | 状态 |
|----|------|:--:|
| 01-18 | 核心引擎（schema → engine → tools → session → MCP → C++ 加速） | ✅ |
| 19 | 进程沙箱 C++ | ✅ |
| 20 | A2A Agent 节点 — 接入 agent-communication 多 Agent 系统 | ✅ |
| 21 | CLI 产品化 — `pip install` + `tiny-claw serve` | 📋 |
| 22 | 总结 + 面试叙事 | 📋 |
| 23 | SWE-bench 基准测试 | 📋 |

---

## 项目启动：定位与目标

**日期**：2026-06-26

### 三层目标

1. **学习深度**：参照 Go 版逐章构建，理解 Agent 引擎的每一层原理
2. **产品思维**：集百家之所长，形成自己的「观点」，个人和企业都能真实使用
3. **可量化优势**：在特定维度上必须比 Cursor 等现有方案更好，用数据说话

### 核心策略

1. **章节对标 Go 版，但不盲从**：理解 Go 版的设计意图，用 Python 重新表达并升维
2. **每阶段有可验证产出**：不只是「代码跑通了」，而是「这个指标比 Cursor 好」
3. **量化先于实现**：先定义「好」的标准，再动手做
4. **产品思维贯穿始终**：从 ch01 就考虑 `pip install` 体验，从 ch03 就考虑 `.claw.yaml`

### 集百家之所长的取舍

| 来源 | 学什么 | 不学什么 |
|------|--------|---------|
| **Cursor** | 零配置体验 | 闭源黑盒 |
| **Claude Code** | Think→Act 循环 | — |
| **Aider** | 精确代码编辑 | 复杂的参数体系 |
| **LangChain** | 生态思路 | 框架厚度 |
| **Go 原版** | Harness 架构哲学 | Go 特有的实现模式 |
| **MCP** | 工具开放协议 | — |

### 待确定：量化指标体系

> ⚠️ 以下指标方向已定，具体测量方法和 baseline 待后续实验确定。

| 维度 | 指标方向 | 对标对象 | 测量方法方向 |
|------|---------|---------|------------|
| 速度 | 批量文件操作耗时 | Cursor | 构造 N 文件任务，计时 |
| 安全 | 高危操作拦截率 | Cursor（黑盒） | 注入危险命令集，统计 |
| 记忆 | 上下文信息保留率 | Cursor（固定窗口） | 长对话基准，人工评估 |
| 成本 | 透明度 + 优化率 | Cursor（不透明） | 实时计费 vs 事后估算 |
| 学习曲线 | 到首次完成任务的时间 | Cursor | 新人上手计时 |

### Python vs Go：对 Agent 场景的影响

| 维度 | Go | Python | Agent 场景判断 |
|------|-----|--------|---------------|
| 类型系统 | 静态 struct | Pydantic 动态校验 | Schema 定义 Py 更简洁，但 Go 编译期兜底更安全 |
| 并发模型 | goroutine（抢占式） | asyncio（协作式） | Agent 是 IO 密集，两者都合适，asyncio 生态更好 |
| 接口抽象 | 隐式接口 | Protocol / ABC | Python 显式更清晰，Go 隐式更灵活 |
| AI 生态 | 弱 | **原生** | 这是 Python 最大的优势 |
| 部署 | 单二进制 | 需要运行时 | Go 更好，但 Agent 通常是服务 |

---

## 技术储备：C++ 高性能加速策略

**更新（2026-07-02）**：经实测验证（ch08 计时器 + Claude Code 参考），
Agent 场景下 LLM API 占 99% 耗时，Python CPU 开销可忽略。
C++ 优化点从初始的 5 个收窄为 2 个真正有意义的：

### ✅ 值得用 C++ 的

| 优先级 | 模块 | 方案 | 理由 |
|--------|------|------|------|
| ⭐⭐⭐ | **edit_file** | 滑动窗口 + 编辑距离 | 场景独特（文件 vs 小段文本），非标准 diff，Python 纯字符串循环慢 |
| 🔒🔒🔒 | **进程沙箱** | setrlimit + namespace | Python subprocess 无法限制内存/CPU/网络 |

### ❌ 不做了（理由充分）

| 模块 | 取消原因 |
|------|---------|
| Token 估算 | Python `len()` 已是 C 实现，够快 |
| 安全规则匹配 | 当前不需要 50+ 规则，`re.match()` 底层 C 够用 |
| 文件监控 | 接入成本高，Agent 场景非瓶颈 |

### edit_file 算法选型

**场景**：Agent 通过 edit_file 编辑代码时，AI 提供 old_text（一小段代码），
需要在文件内容（可能数千行）中定位并替换。本质是「在海里找珍珠」。

**为什么不用标准 Myers Diff**：标准 Myers 计算两个文件之间的完整编辑脚本（给 git 用）。
我们的场景是单文件 vs 小段文本，只需定位 + 替换。

**算法**：滑动窗口 + 编辑距离 + 早停优化
- 在文件内容上逐行滑动 old_text 窗口
- 每个位置计算编辑距离
- 编辑距离超过当前最佳值时提前跳过
- C++ 编译为机器码，比 Python 字符串循环快 10-50x

### Agent Harness 耗时分布（决定优化方向）

```
LLM API 网络往返  ████████████████████████████  ~2-10s  (95%+)
工具执行 (bash)   ██                            ~0.1-1s
上下文序列化       █                             ~0.01s
diff 计算          █                             ~0.01s
模式匹配/正则      █                             ~0.005s
```

**关键认知**：LLM API 吃掉 95% 的时间，Premature optimization 毫无意义。先纯 Python 跑通，找到真正的瓶颈再动。

---

### 全模块 C++ 可行性排查（21 个模块逐一过）

原则：不是为了用而用。每个模块都要问「Python 生态是不是已经够快了？」

#### ✅ 值得用 C++ 的（性能加速）

| 优先级 | 模块 | C++ 方案 | 预估加速 | 代价 | 量化方式 | 状态 |
|--------|------|---------|---------|------|---------|------|
| ⭐⭐⭐ | edit_file 的 Myers Diff | pybind11 绑定 C++ 算法 | 10-50x（大文件） | ~50 行 C++ | 1000/5000/10000 行 diff 耗时 | 📊 待 benchmark |
| ⭐⭐ | Compactor Token 估算 | SIMD 加速字符串遍历 | 5-20x（百万字符） | 一个 C 函数 | 100K/500K/1M 字符估算耗时 | 📊 待 benchmark |
| ⭐ | 安全规则匹配 | Hyperscan 多模式匹配 | 10-100x（50+ 规则时） | 需编译库 | N 条规则匹配耗时 | 📊 待 benchmark |

#### 🔒 值得用 C++ 的（能力补全，Python 做不到）

这些不是「更快」，而是「Python 根本实现不了」。

| 优先级 | 模块 | C++ 方案 | Python 为什么做不到 | 代价 | 状态 |
|--------|------|---------|-------------------|------|------|
| 🔒🔒🔒 | 进程资源沙箱 | `setrlimit` + Linux namespace | `subprocess` 无法限制内存/CPU/网络 | ~100 行 C++ | 📋 规划中 |
| 🔒🔒 | 文件系统变更监控 | inotify / fsevents 直接调用 | Python `watchdog` 大项目可能丢事件 | ~80 行 C++ | 📋 规划中 |

**进程沙箱详解**：
```python
# Agent 执行的 bash 命令可能是用户写的任意命令
# Python 的 subprocess 无法做到：
sandbox = Sandbox(
    memory_limit_mb=512,      # 防止 OOM
    cpu_timeout_ms=30000,     # 防止死循环
    network="none",           # 防止数据泄露
    writeable_dirs=["/tmp"]   # 限制文件写入范围
)
sandbox.execute("bash", "-c", user_command)
```

**文件监控详解**：
```python
# Agent 执行 bash 后需要知道「哪些文件变了，才能决定下一步」
# Python watchdog 在 10000+ 文件的仓库里可能漏事件
watcher = FileWatcher(work_dir)
changes = watcher.wait_for_changes(timeout_ms=5000)
# → {"src/main.py": "MODIFIED", "tests/test_new.py": "CREATED"}
```

#### ❌ 不值得用 C++ 的（生态已经帮你 C 过了）

| 模块 | Python 方案 | 底层实际 | 为什么不需要 C++ |
|------|-----------|---------|----------------|
| Schema 序列化 | `pydantic` + `orjson` | `orjson` 是 **Rust** | 已经比你手写 C++ 快 |
| HTTP / API 调用 | `openai` / `httpx` | 网络 IO 瓶颈 | 不在 CPU |
| ReadFile | `pathlib.read_text()` | OS 页缓存 | 小文件够快，大文件 mmap 用 C++ 不值得 |
| WriteFile | `pathlib.write_text()` | 磁盘 IO 瓶颈 | 不在 CPU |
| Bash 执行 | `asyncio.create_subprocess_exec` | `fork` + `exec` | 是系统调用，不是 Python 慢 |
| JSON 参数解析 | `orjson.loads()` | **Rust** | 已经极快 |
| Token 计数 (BPE) | `tiktoken` | **Rust** | 已经极快 |
| Session SQLite | `aiosqlite` | **C** (sqlite3) | 已经极快 |
| Skill YAML 解析 | `PyYAML` | **C** (libyaml) | 已经极快 |
| OpenTelemetry 导出 | 写 JSON 到磁盘 | 磁盘 IO | 不在 CPU |
| MD5 指纹 | `hashlib.md5()` | **C** (OpenSSL) | 已经极快 |
| 终端输出 | `rich` | 渲染到终端 | 不在 CPU |
| FastAPI HTTP 服务 | `uvicorn` | **Cython** | 已经极快 |
| Prompt 字符串拼接 | Jinja2 `Template.render()` | **C** 扩展 | 已经极快 |
| Regex 安全匹配（<50 规则） | `re.match()` | **C** (PCRE) | 已经极快 |
| logging | `loguru` | 磁盘 IO | 不在 CPU |

**结论：21 个模块，18 个不需要动，3 个待 benchmark 确认，2 个是能力补全。**

---

### 跨语言调用方案：pybind11

#### 原理：编译期绑定，不是运行时桥接

pybind11 生成的产物是标准 **CPython 扩展**（`.so` / `.pyd`），和 `numpy`、`pydantic-core`、`orjson` 同级别。

```
┌──────────────────────────────────────────────────────┐
│  Python 代码                                          │
│  from tiny_claw_accel import myers_diff              │
│  result = myers_diff(old, new)   ← 和普通函数一样    │
├──────────────────────────────────────────────────────┤
│  CPython 扩展层（编译期绑定，无运行时桥接）              │
│  _diff.cpython-312-darwin.so                         │
│  └─ pybind11 在编译期生成了所有类型转换代码             │
├──────────────────────────────────────────────────────┤
│  C++ 实现层                                           │
│  std::vector<DiffHunk> myers_diff(string, string)    │
│  └─ 纯 C++ 代码，无任何 Python 依赖                    │
└──────────────────────────────────────────────────────┘
```

#### 三种跨语言方案对比

| 方案 | 原理 | 桥接层 | 每次调用开销 | 适用场景 |
|------|------|--------|------------|---------|
| `ctypes` | 运行时查找 .so 符号，手动声明类型 | ✅ 有 | 中等 | 调用已有 C 库，不写 C 代码 |
| `cffi` | 运行时解析 C 声明，JIT 编译转换 | ✅ 有 | 中等 | 兼顾灵活性和性能 |
| **pybind11** | **编译期生成 CPython 扩展** | **❌ 无** | **极小（微秒级）** | **写新的 C++ 加速模块，首选** |

#### 转换开销分析

pybind11 的类型转换发生在编译期确定的代码路径中，只有两处成本：

| 开销类型 | 量级 | 说明 |
|---------|------|------|
| 类型转换器查找 | ~0.05ms | 编译期确定，实际是一次虚函数调用 |
| 数据拷贝（`str` → `std::string`） | O(n) | 本质是一次 memcpy，500KB 约 0.5ms |

**结论：转换开销占总耗时的比例随数据增大而线性降低**，因为算法加速（O(n²)→O(ND)）的收益远超拷贝开销。

```
1000 行文件（~50KB）：
  Python difflib:  ~20ms
  C++ 拷贝+算法:   ~0.5ms
  加速比:          40x
  转换开销占比:    ~10%

10000 行文件（~500KB）：
  Python difflib:  ~200ms
  C++ 拷贝+算法:   ~5.5ms
  加速比:          36x
  转换开销占比:    ~9%   ← 数据越大占比越低

100000 行文件（~5MB）：
  Python difflib:  ~2000ms+
  C++ 拷贝+算法:   ~50ms
  加速比:          40x+
  转换开销占比:    ~5%   ← 几乎忽略
```

#### 用户侧完全无感

```python
# 用户不知道也不关心下面是 Python 还是 C++
from tiny_claw_accel import myers_diff
result = myers_diff(old_text, new_text)

# 和我们每天都在用的东西一样
import numpy as np         # 底层 C + Fortran
import orjson              # 底层 Rust
from pydantic import BaseModel  # pydantic-core 底层 Rust
```

#### 常见疑问：Python 不是不需要编译吗？

```
┌─────────────────────────────────────────────────────┐
│  我们的代码                                          │
│  ├── main.py         → 纯 Python，不编译，直接跑     │
│  └── diff.cpp        → C++ 源码，必须编译成机器码    │
│                          ↓                          │
│       _diff.cpython-312-darwin.so  ← 编译产物        │
│       Python 能直接 import 它                        │
├─────────────────────────────────────────────────────┤
│  用户安装时                                          │
│  pip install tiny-claw         → 纯 Python，零编译   │
│  pip install tiny-claw[accel]  → 下载预编译 .so      │
│       ↑                            ↑                │
│      用户不需要编译器        我们在 CI 里编译好了      │
│                              (和 pip install numpy  │
│                               一样，numpy 也是 C 编译)│
└─────────────────────────────────────────────────────┘
```

**关键点**：编译发生在发布阶段（我们做），不是安装阶段（用户做）。和 `pip install numpy` 一模一样——numpy 底层是 C，但你装的时候不需要 C 编译器。

> 面试能讲：「pybind11 生成的是标准 CPython 扩展，不是 ctypes 那种运行时桥接。转换开销只有一次 memcpy，在大文件场景下占比不到 10%。编译在 CI 里完成，用户 `pip install` 就是预编译的 wheel，和装 numpy 体验一样。」

### 关键架构决策：拆成独立可选包

```
py-tiny-claw/
├── tiny-claw/              # 核心包（纯 Python，零编译依赖）
│   └── pip install tiny-claw
│
├── tiny-claw-accel/        # C++ 加速 + 能力补全包（可选）
│   ├── src/
│   │   ├── diff.cpp        # Myers Diff（性能加速）
│   │   ├── sandbox.cpp     # 进程资源沙箱（能力补全）
│   │   └── fswatch.cpp     # 文件系统变更监控（能力补全）
│   ├── CMakeLists.txt
│   └── pyproject.toml
│   └── pip install tiny-claw[accel]
│
└── benchmarks/
    ├── diff_benchmark.py       # Python vs C++ diff 量化对比
    ├── sandbox_test.py         # 沙箱能力验证
    └── fswatch_benchmark.py    # 文件监控 vs Python watchdog
```

### 为什么拆出去？

| 考量 | 拆出去的好处 |
|------|------------|
| **安装体验** | 核心功能 `pip install tiny-claw` 零编译，3 秒装完 |
| **CI/CD** | 核心包的 CI 不需要 C++ 编译器，更快更简单 |
| **平台兼容** | C++ 包可以单独为不同平台预编译 wheel（manylinux/macOS/Windows） |
| **渐进增强** | 用户先用纯 Python，觉得慢再装加速包，不强绑 |
| **独立演进** | diff 引擎可以独立测试、独立发版、独立 benchmark |
| **面试叙事** | 「性能敏感的模块用 C++ 实现，通过 pybind11 无缝集成，作为可选加速包」——一句话展示跨语言工程能力 |

### 落地节奏

```
Phase 1-2 (ch01-ch08)：纯 Python，先把整个 Agent 跑通
    ↓
Phase 3 (ch09-ch12)：构造 benchmark 找到真正的 CPU 热点
    ├── diff_benchmark：1000/5000/10000 行文件，Python vs C++
    ├── context_benchmark：100K/500K/1M 字符上下文估算
    └── 确认：哪些模块「真的需要」C++ 加速
    ↓
Phase 4 (ch13-ch17)：
    ├── 对确认的热点用 C++ 替换，量化对比
    └── 实现进程沙箱 + 文件监控（能力补全）
    ↓
Phase 5 (ch18-ch22)：C++ 加速包独立发布，CI 自动 benchmark 防退化
```

### 面试叙事升级

> 我把 21 个模块逐一做了 C++ 可行性排查。其中 18 个不需要动——Python 生态底层已经是 C/Rust 实现了，重复造轮子没有意义。最终确认 3 个性能加速点（待 benchmark）、2 个能力补全点（进程沙箱 + 文件监控，Python 根本做不到）。真正的工程师判断力不是「我会什么就全用什么」，而是「我知道什么时候不该用」。

---

## 集百家之所长的取舍（更新：2026-06-29）

| 来源 | 学什么 | 不学什么 |
|------|--------|---------|
| **Cursor** | 零配置体验 | 闭源黑盒 |
| **Claude Code** | Think→Act 循环、Memory 文件索引、TodoWrite 提醒机制、MCP 命名约定 `mcp__{server}__{tool}`、Subagent 探路者模式、Context Compaction 截断策略 | 原生 Anthropic API 绑定（我们用 openai 兼容） |
| **Aider** | 精确代码编辑 | 复杂的参数体系 |
| **LangChain** | 生态思路 | 框架厚度 |
| **Go 原版** | Harness 架构哲学、fuzzyReplace 退化机制 | Go 特有的 goroutine 模式（用 ThreadPoolExecutor 替代） |
| **MCP** | 工具开放协议、stdio transport | — |

---

## 章节决策记录

### ch01-ch03：骨架 + Mock 闭环 + 双阶段推理

**日期**：2026-06-29

**决策**：
- 用 `dataclass` 替代 Go 的 struct，比 Pydantic 更轻量，够用
- 用 `Protocol` 替代 Go 的 `interface`，鸭子类型，不强制显式 implements
- Thinking Phase 用 `tools=None` 剥夺工具，比 Go 版多一层意图表达
- Role 用 `str, Enum` 而非 `StrEnum`，兼容 Python 3.9

### ch04：接入 DeepSeek API

**日期**：2026-06-29

**决策**：
- 只接 DeepSeek，不搞多厂商抽象。需要时加 Provider 就行，Protocol 已就位
- 用 `openai` 官方 SDK，DeepSeek 100% 兼容 OpenAI API
- 不做 HTTP 手写，比 Go 版省 90% 代码

### ch05-ch07：四大工具

**日期**：2026-06-29

**决策**：
- ReadFile / WriteFile / Bash：逻辑直译 Go 版，Python `pathlib` 比 `filepath.Join` 更安全
- **EditFile 最大设计决策**：抽 `DiffEngine` 接口。当前 `SimpleDiffEngine` 对标 Go 的 4 层 fuzzyReplace，未来 `MyersDiffEngine`（C++ pybind11）一行切换。这是整个项目 C++ 加速的入口点
- 工具注册表从 Mock 升级为真实 `ToolRegistry`，保留 `MockRegistry` 供旧 demo 用

### ch08：并发执行 + 阶段计时

**日期**：2026-06-29

**决策**：
- 用 `ThreadPoolExecutor` 而非 `asyncio`。理由是：工具全是 IO（bash/读写文件），线程池够用，改动最小，且 GIL 在 IO 时自动释放。ch17 再引入 asyncio 对比
- 加 `perf_counter` 计时，发现 LLM API 占总耗时 99%，工具执行 <1%。**量化数据首次确立**

**量化数据**：
```
⏱️  总计 5.75s | Think 2.75s | Act 2.97s | Tool 0.03s
→ LLM API 占比 99.5%，工具并发执行几乎免费
```

### ch09：MCP Server（自研）

**日期**：2026-06-29

**核心决策：不做 FastAPI，改做 MCP Server**

理由：
1. MCP 是 stdio 本地通信，零网络延迟，比 HTTP API 更适合 IDE 集成
2. Cursor / Claude Code / Continue.dev 原生支持 MCP
3. 自研 80 行零依赖，Anthropic Python SDK 需要 3.10+
4. 保留 HTTP Transport 扩展点，后续加（团队共享 + 飞书 webhook）

**从 learn-claude-code（s19_mcp_plugin）学到的**：
- MCP 命名约定 `mcp__{server}__{tool}` — Claude Code 用它区分工具来源
- `assemble_tool_pool` 动态组装 — 目前我们是静态注册，后续改动态
- `readOnly` / `destructive` 标注 — 安全审批中间件的好输入

**当前 TODO（代码中已标记）**：
```
Transport:   stdio ✅ | HTTP/SSE [ ]
功能:        认证 [ ] | Session [ ] | spawn_agent [ ] | 热加载 [ ] | 错误码 [ ] | 审计 [ ]
运维:        优雅关闭 [ ] | .claw.yaml [ ]
```

**MCP 两层能力设计（规划中）**：
```
1. 单工具（tools/call）       → 直接执行，IDE AI 主动调用
2. 全 Agent（spawn_agent）    → engine.run()，IDE 委派复杂任务
```
当前只实现了单工具层，引擎未介入。Session 就位后加 spawn_agent。

---

## learn-claude-code 启发清单

> 来源：[learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 仓库（已 fork 到本地）
> 深度分析文档：[docs/learn-claude-code-analysis.md](docs/learn-claude-code-analysis.md)

### 已吸收的设计

| Claude Code 模式 | 我们的映射 |
|-----------------|-----------|
| `TodoWrite` + `rounds_since_todo` 提醒 | 对标 ch13 Plan 模式 |
| Context Compaction（4 级截断） | 对标 ch11 Compactor |
| Subagent 探路者模式 | 对标 ch17 Subagent |
| Agent Teams + Protocols | 对标 ch17 多智能体 |
| MCP 动态工具发现 | 对齐命名约定 |
| Task 状态机 (pending → in_progress → done) | 考虑引入 |

### 新增吸收（2026-06-30 深度分析后）

> 详见 [docs/learn-claude-code-analysis.md](docs/learn-claude-code-analysis.md)

| Claude Code 模式 | 章节 | 我们的映射 | 优先级 |
|-----------------|------|-----------|--------|
| **Hooks 机制**（PreToolUse/PostToolUse/Stop） | s04 | ch10 引入，挂在 engine.run() 上 | 🔥 P0 |
| **Permission 三层闸门**（DENY_LIST→RULES→APPROVAL） | s03 | ch10 引入，作为 PreToolUse hook | 🔥 P0 |
| **System Prompt 分段组装** | s10 | ch10 引入，替换硬编码 prompt | 🔥 P0 |
| **Error Recovery 分类恢复**（截断/超限/故障） | s11 | ch12 引入，LLM 调用包裹 try/except | 🟡 P1 |
| **Background Tasks**（慢操作后台化） | s13 | ch13 后考虑 | 🟢 P2 |
| **Cron Scheduler**（定时调度） | s14 | ch17 后考虑 | 🔵 P3 |
| **Skill Loading**（按需加载知识） | s07 | 待规划 | 🔵 P3 |

### 架构原则

> 来自 learn-claude-code 全书贯穿的设计哲学：

1. **「挂在循环上，不写进循环里」** — Hooks 是扩展点，循环是稳定核心
2. **「便宜的检查先跑，贵的后跑」** — Compaction L1(0 API)→L4(1 API)，Permission DENY_LIST(O(1))→APPROVAL(阻塞)

### 暂不吸收的

| Claude Code 模式 | 原因 |
|-----------------|------|
| Memory 文件索引 (`.memory/MEMORY.md`) | 单用户适用，我们面向多 Session 选 SQLite |
| Worktree 隔离 (git worktree) | 太重，当前不需要 |
| Team Shutdown 握手协议 | ch17 再评估 |

---

## 更新后的章节规划

| 章节 | 实际内容 | 与 Go 版差异 |
|------|---------|------------|
| ch01-04 | ✅ 骨架 → DeepSeek API | DeepSeek 替智谱 |
| ch05-07 | ✅ 四大工具 | EditFile 提前抽 DiffEngine 接口 |
| ch08 | ✅ 并发 + 计时 | ThreadPoolExecutor 替 goroutine |
| ch09 | ✅ MCP Server（自研） | **完全分叉**——Go 版是飞书 Bot |
| ch10 | ✅ Session + SQLite | Go 版纯内存，我们 SQLite 持久化 |
| ch11 | ✅ 上下文压缩 | 对标 Go ch12，预留 LLM/RAG 策略 |
| ch12 | ✅ 错误自愈 + 死循环 | 对标 Go ch14-15 |
| ch13 | ✅ Plan 模式 + .claw.yaml | .claw.yaml 提前 |
| ch14 | ✅ Subagent 子智能体 | 对标 Go ch17 |
| ch15 | ✅ 多 Subagent 并发 + 竞态修复 | clone_with 独立引擎副本 |
| ch16 | ✅ Cost Tracker + Span 链路追踪 | 自研 Tracer + CostTracker |
| ch17 | ✅ C++ diff + 混合策略 | benchmark 3.6x |
| ch18 | ✅ 可观测性决策记录 | 放弃 OTEL/Jaeger，保留 SWE-bench |
| ch19 | ⏳ 进程沙箱 C++ | 唯一 Python 做不到的硬核模块 |
| ch20 | ⏳ SWE-bench 评测 | 标准基准验证 Agent 能力 |
| ch21+ | ⏳ Benchmark + CLI 收尾 | |

### ch18：可观测性方案决策

**放弃**：OpenTelemetry + Jaeger（理由：单进程 Agent 不需要分布式追踪框架）

**保留**：SWE-bench —— 不是性能工具，是 Agent 能力基准，有独立价值

### ch18：可观测性方案决策

**原规划**：OpenTelemetry + Jaeger + SWE-bench（对标 Go ch18-20）

**实际决策**：放弃，理由——

| 工具 | 为什么不适合我们 |
|------|----------------|
| OpenTelemetry | 为分布式微服务设计的追踪框架，需部署 Collector + 后端。单进程 Agent 不需要 |
| Jaeger | Uber 的分布式追踪系统，需 Docker 额外服务。JSON 导出够用 |
| SWE-bench | 普林斯顿论文基准，2294 个项目 + 几百刀 API 费。我们是验证自己的框架 |

**我们的替代方案**（已实现）：
```
Tracer (ch16):  Span 树 → JSON 文件        ← 自研 40 行，零依赖
CostTracker (ch16): Token + 花费实时记录     ← 装饰器模式
计时器 (ch08):    Think/Act/Tool 阶段分布   ← perf_counter

可选扩展：Tracer.export_otel() → OTLP 格式 → Jaeger 可视化
```

### ch15 竞态问题总结

**发现**：多 Subagent 并发时第二个报「工具不存在」

**根因**：线程 A 跑完恢复 `engine.registry = main`，线程 B 还在跑但 registry 被篡改

**解决**：`engine.clone_with(registry)` — 每个 Subagent 独立引擎副本

**参考 Claude Code**：独立线程 + JSONL inbox 文件通信，零共享内存。当前够用，未来可升级为持久化 Teammate 模式。

### ch20：A2A Agent 节点

**日期**：2026-07-07

**决策**：
- 用 `http.server.HTTPServer`（Python 标准库，零依赖）
- 实现 Google A2A 协议 `message/send` + Agent Card 端点
- 直接用 `AgentEngine.run()` 处理每个请求，不做持久化会话（每次请求新 Session）
- 新增 `tests/test_a2a_agent.py`：Mock Provider 独立测试（6 个用例）+ 可选真实 LLM 集成测试

**为什么替代原 CLI 规划提前做**：
1. 跟 agent-communication 系统对接，验证 Harness 在多 Agent 场景的价值
2. 对比 C++ Agent（一次 API 调用）vs Python Agent（完整 ReAct 循环）效果
3. A2A 协议采用 JSON-RPC over HTTP，零额外开销

**实现细节**：
```
src/tiny_claw/a2a_server.py  — A2A HTTP Server (~120 行)
cmd/a2a_agent.py              — 启动入口

端点:
  POST /                          — 处理 message/send → AgentEngine.run()
  GET  /.well-known/agent-card.json — 返回 Agent 元数据
```

**测试策略**：
```
独立测试（无外部依赖）: python tests/test_a2a_agent.py
  1. Agent Card 端点
  2. message/send 响应格式
  3. 未知 method 错误处理
  4. 空消息错误处理
  5. 5 并发请求正确性
  6. JSON-RPC 2.0 格式合规

集成测试（需要 DeepSeek API Key）:
  python tests/test_a2a_agent.py --integration
  启动真实服务 → 发送任务 → 验证 LLM 推理结果
```

**扩展现有系统验证**：
```bash
# 1. 启动 agent-communication
cd agent-communication && ./start.sh

# 2. 启动 py-tiny-claw A2A Agent
cd py-tiny-claw
python cmd/a2a_agent.py --port 5002

# 3. 在 agent-communication 的 Orchestrator 中注册它
#    （未来：自动通过 AGENT_ADDR 环境变量注册到 Registry）
```
