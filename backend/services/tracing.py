"""Request tracing: mede tempos de OCR, resolucao, Claude, tools."""

import time
import logging

logger = logging.getLogger(__name__)


class RequestTrace:
    """Acumula metricas de timing para um request."""

    def __init__(self, request_id=None):
        self.request_id = request_id
        self.start = time.time()
        self.steps = []
        self.tools_used = []
        self.claude_rounds = 0

    def step(self, name):
        """Registra inicio de um passo. Retorna context manager."""
        return _StepTimer(self, name)

    def add_tool(self, tool_name):
        self.tools_used.append(tool_name)

    def add_claude_round(self):
        self.claude_rounds += 1

    def summary(self):
        """Retorna dict com o resumo do trace."""
        total_ms = round((time.time() - self.start) * 1000)
        return {
            "request_id": self.request_id,
            "total_ms": total_ms,
            "steps": [{"name": s[0], "ms": s[1]} for s in self.steps],
            "tools_used": self.tools_used,
            "claude_rounds": self.claude_rounds,
        }

    def log(self):
        """Loga o trace."""
        s = self.summary()
        steps_str = " | ".join(f"{st['name']}={st['ms']}ms" for st in s["steps"])
        logger.info(
            f"[trace] id={s['request_id']} total={s['total_ms']}ms "
            f"rounds={s['claude_rounds']} tools={s['tools_used']} "
            f"steps=[{steps_str}]"
        )
        print(
            f"[trace] id={s['request_id']} total={s['total_ms']}ms "
            f"rounds={s['claude_rounds']} tools={','.join(s['tools_used'])} "
            f"steps=[{steps_str}]",
            flush=True,
        )


class _StepTimer:
    def __init__(self, trace, name):
        self.trace = trace
        self.name = name
        self.t0 = None

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *args):
        elapsed_ms = round((time.time() - self.t0) * 1000)
        self.trace.steps.append((self.name, elapsed_ms))
