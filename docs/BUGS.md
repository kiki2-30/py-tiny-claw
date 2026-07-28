# Bug 记录

## BUG-001: 多 Subagent 并发时 registry 竞态

**发现日期**：2026-06-30  
**发现方式**：ch15 多 Subagent 并发 demo 运行验证  
**严重程度**：中（多 Subagent 场景必现）

### 现象

主 Agent 一轮返回 2 个 `spawn_subagent`，引擎 `ThreadPoolExecutor` 并发执行。
第二个 Subagent 偶尔报「工具不存在」错误。

```
🤖 [回复]: ...子Agent 2 遇到工具不存在的问题...
```

### 根因

两个线程共享同一个 `engine.registry` 引用：

```python
# SubagentTool.execute() 中的旧代码
saved_registry = self._engine.registry     # 线程 A: 保存 main_registry
self._engine.registry = self._read_only    # 线程 A: 设为 read_only
                                           # 线程 B: 保存 main_registry
                                           # 线程 B: 设为 read_only (覆盖，无影响)
try:
    self._engine.run(session)              # 线程 A 先跑完
finally:
    self._engine.registry = saved_registry # 线程 A: 恢复为 main_registry ！
                                           # 线程 B 还在跑，但 registry 已被 A 改回 main
```

**时序图**：

```
时间 →
线程A: [保存main] [设read_only] [======== run ========] [恢复main]
线程B:              [保存main] [设read_only] [======== run ========] ← registry 已被A改成main！
```

### 修复

`engine.clone_with(registry)` —— 每个 Subagent 创建独立引擎副本：

```python
# 新代码
sub = self._engine.clone_with(self._read_only)
sub.run(session, max_turns=10)
```

`clone_with` 创建一个新 `AgentEngine` 实例，共享 `provider`（线程安全）但拥有独立的 `registry`：

```python
def clone_with(self, registry) -> "AgentEngine":
    return AgentEngine(self.provider, registry, self.work_dir)
```

### 验证

修复前：ch15 demo 中第二个 Subagent 报「工具不存在」  
修复后：两个 Subagent 各自正常执行，不再竞态

### 参考

Claude Code 做法更彻底：每个 Agent 独立线程 + JSONL inbox 文件通信，**零共享内存状态**。
当前 `clone_with` 满足需求，未来可升级为持久化 Teammate 模式。
