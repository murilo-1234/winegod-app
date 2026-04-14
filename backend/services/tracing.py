"""Request tracing: mede tempos de OCR, resolucao, Claude, tools."""

import contextvars
import logging
import os
import time

try:
    import resource
except ImportError:  # pragma: no cover - resource existe no Linux/Render
    resource = None

logger = logging.getLogger(__name__)
_CURRENT_REQUEST_ID = contextvars.ContextVar("request_id", default=None)


def current_request_id():
    """Retorna request_id atual, se houver."""
    return _CURRENT_REQUEST_ID.get()


def _read_proc_status_kb(field_name):
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            prefix = f"{field_name}:"
            for line in fh:
                if line.startswith(prefix):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        return int(parts[1])
    except Exception:
        return None
    return None


def _read_first_existing(paths):
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                raw = fh.read().strip()
            if not raw or raw == "max":
                return None
            return int(raw)
        except Exception:
            continue
    return None


def _bytes_to_mb(value):
    if value is None:
        return None
    return round(value / (1024 * 1024), 1)


def memory_snapshot():
    """Snapshot leve de memoria do processo atual.

    Campos:
    - rss_mb: memoria residente atual do processo
    - peak_rss_mb: pico do processo ate aqui
    - cgroup_current_mb: memoria atual do cgroup/container
    - cgroup_limit_mb: limite do cgroup/container, quando conhecido
    """
    rss_kb = _read_proc_status_kb("VmRSS")
    hwm_kb = _read_proc_status_kb("VmHWM")

    peak_bytes = hwm_kb * 1024 if hwm_kb is not None else None
    if resource is not None:
        try:
            ru_peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
            if peak_bytes is None or ru_peak > peak_bytes:
                peak_bytes = ru_peak
        except Exception:
            pass

    cgroup_current = _read_first_existing([
        "/sys/fs/cgroup/memory.current",
        "/sys/fs/cgroup/memory/memory.usage_in_bytes",
    ])
    cgroup_limit = _read_first_existing([
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    ])

    return {
        "rss_mb": _bytes_to_mb(rss_kb * 1024 if rss_kb is not None else None),
        "peak_rss_mb": _bytes_to_mb(peak_bytes),
        "cgroup_current_mb": _bytes_to_mb(cgroup_current),
        "cgroup_limit_mb": _bytes_to_mb(cgroup_limit),
    }


def _format_mb(value):
    return "?" if value is None else f"{value}MB"


def format_memory(snapshot=None):
    snap = snapshot or memory_snapshot()
    return (
        f"rss={_format_mb(snap.get('rss_mb'))} "
        f"peak={_format_mb(snap.get('peak_rss_mb'))} "
        f"cg={_format_mb(snap.get('cgroup_current_mb'))} "
        f"limit={_format_mb(snap.get('cgroup_limit_mb'))}"
    )


def log_memory(prefix, **fields):
    """Loga snapshot de memoria com campos opcionais."""
    snap = memory_snapshot()
    req_id = current_request_id()
    parts = [f"[mem] {prefix}"]
    if req_id:
        parts.append(f"id={req_id}")
    parts.append(format_memory(snap))
    for key, value in fields.items():
        parts.append(f"{key}={value}")
    message = " ".join(parts)
    logger.info(message)
    print(message, flush=True)
    return snap


class RequestTrace:
    """Acumula metricas de timing para um request."""

    def __init__(self, request_id=None):
        self.request_id = request_id
        self.start = time.time()
        self.start_memory = memory_snapshot()
        self.steps = []
        self.tools_used = []
        self.claude_rounds = 0
        self._ctx_token = _CURRENT_REQUEST_ID.set(request_id) if request_id else None

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
        end_memory = memory_snapshot()
        return {
            "request_id": self.request_id,
            "total_ms": total_ms,
            "steps": [{"name": s[0], "ms": s[1]} for s in self.steps],
            "tools_used": self.tools_used,
            "claude_rounds": self.claude_rounds,
            "memory": {
                "start": self.start_memory,
                "end": end_memory,
            },
        }

    def log(self):
        """Loga o trace."""
        s = self.summary()
        steps_str = " | ".join(f"{st['name']}={st['ms']}ms" for st in s["steps"])
        mem_start = s["memory"]["start"]
        mem_end = s["memory"]["end"]
        rss_delta = None
        if mem_start.get("rss_mb") is not None and mem_end.get("rss_mb") is not None:
            rss_delta = round(mem_end["rss_mb"] - mem_start["rss_mb"], 1)
        mem_str = (
            f"mem_start=[{format_memory(mem_start)}] "
            f"mem_end=[{format_memory(mem_end)}] "
            f"rss_delta={rss_delta if rss_delta is not None else '?'}MB"
        )
        logger.info(
            f"[trace] id={s['request_id']} total={s['total_ms']}ms "
            f"rounds={s['claude_rounds']} tools={s['tools_used']} "
            f"steps=[{steps_str}] {mem_str}"
        )
        print(
            f"[trace] id={s['request_id']} total={s['total_ms']}ms "
            f"rounds={s['claude_rounds']} tools={','.join(s['tools_used'])} "
            f"steps=[{steps_str}] {mem_str}",
            flush=True,
        )
        if self._ctx_token is not None:
            _CURRENT_REQUEST_ID.reset(self._ctx_token)
            self._ctx_token = None


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
