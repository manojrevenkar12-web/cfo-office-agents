"""Observability from day one: every agent decision, tool call and model read is an OpenTelemetry span, kept in
memory and written to `ops/traces.jsonl`, with latency, tool-call counts and model tokens per decision."""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

IBAN_KEEP = 4


def mask(value: str) -> str:
    """IBANs and other account numbers are masked in traces: the last four characters stay."""
    s = str(value)
    return s if len(s) <= IBAN_KEEP + 4 else s[:2] + "*" * (len(s) - 2 - IBAN_KEEP) + s[-IBAN_KEEP:]


class Tracer:
    def __init__(self, service: str):
        self.exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer = provider.get_tracer(service)

    @contextmanager
    def span(self, name: str, **attrs):
        with self.tracer.start_as_current_span(name) as s:
            for k, v in attrs.items():
                if v is not None:
                    s.set_attribute(k, v if isinstance(v, (int, float, bool, str)) else json.dumps(v, default=str)[:2000])
            yield s

    def records(self) -> list[dict]:
        out = []
        for s in self.exporter.get_finished_spans():
            out.append({"trace": f"{s.context.trace_id:032x}", "span": f"{s.context.span_id:016x}",
                        "parent": f"{s.parent.span_id:016x}" if s.parent else None, "name": s.name,
                        "ms": round((s.end_time - s.start_time) / 1e6, 3), "attrs": dict(s.attributes or {})})
        return out

    def write(self, path: Path) -> int:
        recs = self.records()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r, default=str) + "\n" for r in recs))
        return len(recs)


def summarise(records: list[dict], root: str) -> dict:
    """Per decision (root span): latency, tool calls and model tokens."""
    by_trace: dict[str, list[dict]] = {}
    for r in records:
        by_trace.setdefault(r["trace"], []).append(r)
    rows = []
    for spans in by_trace.values():
        top = [s for s in spans if s["name"] == root]
        if not top:
            continue
        rows.append({"ms": top[0]["ms"], "tool_calls": sum(s["name"].startswith("mcp.") for s in spans),
                     "tokens": sum(int(s["attrs"].get("tokens", 0)) for s in spans)})
    if not rows:
        return {"decisions": 0}
    ms = sorted(r["ms"] for r in rows)
    return {"decisions": len(rows), "median_ms": ms[len(ms) // 2], "p95_ms": ms[int(len(ms) * 0.95) - 1 if len(ms) > 1 else 0],
            "tool_calls_per_decision": round(sum(r["tool_calls"] for r in rows) / len(rows), 2),
            "tokens_per_decision": round(sum(r["tokens"] for r in rows) / len(rows), 1)}
