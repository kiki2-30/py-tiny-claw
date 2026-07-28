"""
benchmarks/diff_benchmark.py —— SimpleDiffEngine vs MyersDiffEngine 量化对比
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tiny_claw.tools import SimpleDiffEngine

# 加载 C++ 模块
accel_build = Path(__file__).resolve().parent.parent / "accel" / "build"
if str(accel_build) not in sys.path:
    sys.path.insert(0, str(accel_build))


class MyersDiffEngine:
    """C++ 加速版 diff"""
    def apply_edit(self, content: str, old_text: str, new_text: str) -> str:
        from _diff import fuzzy_locate
        r = fuzzy_locate(content, old_text)
        return content[:r.start] + new_text + content[r.end:]


def generate_file(lines: int) -> str:
    """生成测试文件"""
    return "\n".join(
        f"def func_{i}():\n    x = {i}\n    return x * 2\n"
        for i in range(lines)
    )


def benchmark(name, engine, content, old_text, new_text, rounds=10):
    times = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        engine.apply_edit(content, old_text, new_text)
        times.append(time.perf_counter() - t0)
    avg = sum(times) / len(times)
    print(f"  {name}: {avg*1000:.1f}ms (avg of {rounds})")
    return avg


print("=" * 55)
print("DiffEngine Benchmark: Python SimpleDiffEngine vs C++ MyersDiffEngine")
print("=" * 55)

for size in [1000, 5000, 10000]:
    print(f"\n--- {size} 行文件 ---")
    content = generate_file(size)
    mid = size // 2
    # 模糊场景：old_text 比原文多一个空格（L1 精确匹配失败，L2 模糊匹配介入）
    original = "\n".join(content.split("\n")[mid:mid + 5])
    old_text = original.replace("def ", " def ")  # 加一个空格，模拟 AI 的细微偏差
    new_text = "REPLACED_CONTENT"

    py_avg = benchmark("SimpleDiffEngine", SimpleDiffEngine(),
                       content, old_text, new_text)
    cpp_avg = benchmark("MyersDiffEngine ", MyersDiffEngine(),
                        content, old_text, new_text)
    if py_avg > 0:
        print(f"  >>> 加速比: {py_avg/cpp_avg:.1f}x")

print(f"\n--- 100 行文件（小文件基准）---")
content = generate_file(100)
original = "\n".join(content.split("\n")[50:55])
old_text = original.replace("def ", " def ")
py_avg = benchmark("SimpleDiffEngine", SimpleDiffEngine(), content, old_text, "X")
cpp_avg = benchmark("MyersDiffEngine ", MyersDiffEngine(), content, old_text, "X")
if py_avg > 0:
    print(f"  >>> 加速比: {py_avg/cpp_avg:.1f}x")
