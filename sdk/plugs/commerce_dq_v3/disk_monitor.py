"""Disk monitor para `reports/data_ops_artifacts/` commerce.

- `dir_size(path)`: soma bytes recursivamente (ignora dir ausente).
- `classify(size)`: devolve `ok / warning / failed` com thresholds do
  `health.py` (2 GB warning, 5 GB failed).

Usado por `health.py` e pelo CLI de rotacao quando disco estoura.
"""

from __future__ import annotations

from pathlib import Path

WARNING_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
FAILED_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def classify(size_bytes: int) -> str:
    if size_bytes >= FAILED_BYTES:
        return "failed"
    if size_bytes >= WARNING_BYTES:
        return "warning"
    return "ok"


def summary(path: Path) -> dict:
    bytes_total = dir_size(path)
    return {
        "path": str(path),
        "bytes": bytes_total,
        "mb": round(bytes_total / (1024 * 1024), 2),
        "status": classify(bytes_total),
        "warning_at_mb": WARNING_BYTES / (1024 * 1024),
        "failed_at_mb": FAILED_BYTES / (1024 * 1024),
    }
