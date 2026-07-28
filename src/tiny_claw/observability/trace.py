"""
observability/trace.py —— 链路追踪（Span Tree）

自研轻量方案，替代 OpenTelemetry + Jaeger。
Agent 是单进程，不需要分布式追踪框架。
导出格式：自研 JSON → 可视化 / OTLP JSON → Jaeger（可选）
"""

import json
import time
from pathlib import Path

class Span:
    """一个时间片段"""
    def __init__(self, name: str) -> None:
        self.name = name
        self.start = time.perf_counter()
        self.end: float = 0
        self.children: list[Span] = []

    def stop(self) -> None:
        self.end = time.perf_counter()

    @property
    def duration_ms(self) -> float:
        return (self.end - self.start) * 1000 if self.end else 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms, 2),
            "children": [c.to_dict() for c in self.children],
        }


class Tracer:
    """管理 Span 树"""

    def __init__(self, root_name: str = "Task") -> None:
        self.root = Span(root_name)
        self._stack: list[Span] = [self.root]

    def start(self, name: str) -> Span:
        span = Span(name)
        self._stack[-1].children.append(span)
        self._stack.append(span)
        return span

    def end(self) -> None:
        if len(self._stack) > 1:
            self._stack.pop().stop()

    def finish(self) -> None:
        while len(self._stack) > 1:
            self.end()
        self.root.stop()

    def export(self, path: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(self.root.to_dict(), f, indent=2, ensure_ascii=False)

    def export_otel(self, path: str) -> None:
        """导出 OTLP JSON 格式 → Jaeger 可视化（可选）
        启动 Jaeger: docker run -p 16686:16686 jaegertracing/all-in-one
        导入: http://localhost:16686 上传此文件"""
        spans = []
        self._flatten_otel(self.root, spans)
        otel = {
            "resourceSpans": [{
                "resource": {"attributes": [
                    {"key": "service.name", "value": {"stringValue": "tiny-claw"}}
                ]},
                "scopeSpans": [{"spans": spans}],
            }]
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(otel, f, indent=2)

    def _flatten_otel(self, span: Span, out: list, parent_id: str = "") -> None:
        import secrets
        sid = secrets.token_hex(8)
        nano = int(span.start * 1e9)
        out.append({
            "traceId": secrets.token_hex(16),
            "spanId": sid,
            "parentSpanId": parent_id or "",
            "name": span.name,
            "startTimeUnixNano": str(nano),
            "endTimeUnixNano": str(nano + int(span.duration_ms * 1e6)),
        })
        for child in span.children:
            self._flatten_otel(child, out, sid)
