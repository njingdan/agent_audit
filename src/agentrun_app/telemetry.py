from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


_TRACER = trace.get_tracer("agentrun-a2a-demo")


@contextmanager
def agent_span(agent_name: str, operation: str) -> Iterator[None]:
    """Create a content-free business span; never attach prompts or medical text."""
    with _TRACER.start_as_current_span(
        f"a2a.{agent_name}.{operation}",
        attributes={
            "gen_ai.agent.name": agent_name,
            "rpc.system": "a2a",
            "rpc.method": operation,
        },
    ) as span:
        try:
            yield
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise

