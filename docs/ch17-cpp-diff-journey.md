# ch17 C++ Diff 优化实录

**日期**：2026-07-02

---

## 目标

用 C++ pybind11 实现 `MyersDiffEngine`，替换 Python `SimpleDiffEngine`，
预期大文件场景下 10-50x 加速。

---

## 第一版：字符级滑动窗口 + 编辑距离

### 算法

```
for 每个字符位置:
    slice = content[i : i + len(old_text)]
    distance = edit_distance(slice, old_text)
返回 distance 最小的位置
```

### Benchmark 结果

| 文件大小 | Python | C++ | 
|---------|--------|-----|
| 1000 行 | 0.5ms | 76ms |
| 5000 行 | 2.2ms | 383ms |
| 10000 行 | 5.1ms | 838ms |

**C++ 反而慢 150-170x！**

### 根因

C++ 对每个字符位置都计算完整的编辑距离，O(n × m²) 复杂度。
10000 行文件 ≈ 50000 个字符位置 × 100² 次字符比较 = 5 亿次操作。

Python `SimpleDiffEngine` 先做 L1 精确匹配（C 实现的 `str.count()`），
只有失败才降级到 L4 逐行匹配——Agent 场景 90% 精确命中。

**教训**：算法选型 > 编程语言。错误算法用 C++ 写也是错的。

---

## 第二版：逐行去缩进匹配（对标 Python 4 层退化）

### 算法

```
L1: content.find(old_text)          // 精确匹配（C++ string::find，极快）
L2: \r\n → \n 归一化后 find
L3: strip 后 find
L4: 逐行 ltrim 比较                 // 对标 Python strip 但零堆分配
```

复用 Python 版的 4 层退化逻辑，C++ 优势在于：`ltrim()` 是原地操作零分配，
Python `strip()` 每次创建新字符串。

### Benchmark 结果（预热 + 100 次取平均）

| 文件大小 | Python | C++ | 加速比 |
|---------|--------|-----|--------|
| 100 行 | 0.09ms | 0.03ms | 3.2x |
| 1000 行 | 0.94ms | 0.97ms | 1.0x |
| 5000 行 | 5.99ms | 1.69ms | **3.6x** |
| 10000 行 | 8.58ms | 2.63ms | **3.3x** |

### 关键发现

**1000 行持平的原因**：不是 diff 慢，是 `content[:start] + new + content[end:]` 
字符串拼接占主导——Python 和 C++ 都要做这一步，耗时相同。

**之前 benchmark 68ms 的真相**：测的是 benchmark 框架的字符串重新生成 + 
每次 import 模块的开销，不是 C++ 函数本身。C++ 函数本身 1000 行只要 0.03ms。

---

## 第三版：混合策略

```python
class MyersDiffEngine:
    HYBRID_THRESHOLD = 5000  # 字节

    def apply_edit(self, content, old_text, new_text):
        if len(content) >= HYBRID_THRESHOLD:
            r = self._cpp(content, old_text)   # C++ 模糊定位
        else:
            return self._py.apply_edit(...)     # Python（免跨语言开销）
        return content[:r.start] + new_text + content[r.end:]
```

### 设计理由

- 文件 < 5000 字节：pybind11 跨语言开销 > C++ 加速收益
- 文件 ≥ 5000 字节：C++ 零分配 ltrim 明显快于 Python strip()
- Agent 场景 90% 是小文件，用 Python 避免不必要的跨语言调用

---

## 最终结论

1. **C++ 对 Agent edit_file 场景有价值，但只在 5000+ 字节文件上明显**
2. **算法选型优先于编程语言**——第一版编辑距离算法用 C++ 写也是慢的
3. **benchmark 要测对东西**——预热 + 只测目标函数，排除框架开销
4. **混合策略是最优解**——利用两种语言各自优势，不盲目选边站
