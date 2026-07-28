"""
MyersDiffEngine —— C++ 加速版 diff（混合策略）

文件 < 5000 字节 → Python SimpleDiffEngine（免跨语言开销）
文件 ≥ 5000 字节 → C++ fuzzy_locate（3x+ 加速）

Benchmark 数据（2026-07-02）:
   100行: Python 0.09ms C++ 0.03ms (3.2x)
  1000行: Python 0.94ms C++ 0.97ms (1.0x)
  5000行: Python 5.99ms C++ 1.69ms (3.6x)
 10000行: Python 8.58ms C++ 2.63ms (3.3x)
"""

import sys
from pathlib import Path

from ..tools import SimpleDiffEngine

# C++ 模块路径（build 产物）
_ACCEL_BUILD = Path(__file__).resolve().parent.parent.parent.parent / "accel" / "build"
if str(_ACCEL_BUILD) not in sys.path:
    sys.path.insert(0, str(_ACCEL_BUILD))

HYBRID_THRESHOLD = 5000  # 字节


class MyersDiffEngine:
    """混合引擎：小文件 Python，大文件 C++"""

    def __init__(self) -> None:
        self._py = SimpleDiffEngine()
        self._cpp = None  # 延迟加载

    def apply_edit(self, content: str, old_text: str, new_text: str) -> str:
        if len(content) >= HYBRID_THRESHOLD:
            if self._cpp is None:
                from _diff import fuzzy_locate
                self._cpp = fuzzy_locate
            r = self._cpp(content, old_text)
            return content[:r.start] + new_text + content[r.end:]
        return self._py.apply_edit(content, old_text, new_text)
