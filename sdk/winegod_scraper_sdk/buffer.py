"""Buffer offline — guarda payloads se backend Render nao responder.

Regras (Design Freeze v2 §8.5):
- Limite 100MB por scraper.
- Retry com backoff 1, 2, 4, 8, 16, 32, 60, 60 s.
- Se estourar espaco, descartar HEARTBEATS primeiro (preservar end/fail/events).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional


BUFFER_LIMIT_BYTES = 100 * 1024 * 1024  # 100 MB


@dataclass
class BufferedItem:
    endpoint: str
    payload: Dict
    idempotency_key: str
    kind: str  # "heartbeat" | "start" | "end" | "fail" | "event" | "batch"
    created_at: float
    filepath: Path

    def is_heartbeat(self) -> bool:
        return self.kind == "heartbeat"


class OfflineBuffer:
    def __init__(self, base_dir: str | Path, scraper_id: str):
        self.scraper_id = scraper_id
        self.base = Path(base_dir) / scraper_id
        self.base.mkdir(parents=True, exist_ok=True)

    # ----- API -----

    def enqueue(
        self, endpoint: str, payload: Dict, idempotency_key: str, kind: str
    ) -> Path:
        """Guarda um payload em disco. Retorna caminho do arquivo."""
        self._gc_if_needed(incoming_kind=kind)

        fid = uuid.uuid4().hex
        fname = f"{int(time.time()*1000):013d}_{kind}_{fid}.json"
        path = self.base / fname
        entry = {
            "endpoint": endpoint,
            "payload": payload,
            "idempotency_key": idempotency_key,
            "kind": kind,
            "created_at": time.time(),
        }
        path.write_text(json.dumps(entry, ensure_ascii=False, default=str), encoding="utf-8")
        return path

    def iter_pending(self) -> Iterator[BufferedItem]:
        """Itera arquivos em ordem cronologica."""
        files = sorted(self.base.glob("*.json"))
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                yield BufferedItem(
                    endpoint=data["endpoint"],
                    payload=data["payload"],
                    idempotency_key=data["idempotency_key"],
                    kind=data["kind"],
                    created_at=float(data["created_at"]),
                    filepath=f,
                )
            except Exception:
                # Arquivo corrompido — pula
                continue

    def mark_sent(self, item: BufferedItem) -> None:
        try:
            item.filepath.unlink()
        except FileNotFoundError:
            pass

    def size_bytes(self) -> int:
        total = 0
        for f in self.base.glob("*.json"):
            try:
                total += f.stat().st_size
            except FileNotFoundError:
                continue
        return total

    def pending_count(self) -> int:
        return sum(1 for _ in self.base.glob("*.json"))

    # ----- GC -----

    def _gc_if_needed(self, incoming_kind: str) -> None:
        """Se buffer > 100MB, descarta heartbeats primeiro."""
        size = self.size_bytes()
        if size <= BUFFER_LIMIT_BYTES:
            return

        # Ordena heartbeats mais antigos primeiro
        heartbeats: List[Path] = []
        for f in self.base.glob("*_heartbeat_*.json"):
            heartbeats.append(f)
        heartbeats.sort(key=lambda p: p.stat().st_mtime)

        for f in heartbeats:
            try:
                size -= f.stat().st_size
                f.unlink()
            except FileNotFoundError:
                pass
            if size <= BUFFER_LIMIT_BYTES:
                return

        # Se ainda estourou, descarta events antigos
        events: List[Path] = list(self.base.glob("*_event_*.json"))
        events.sort(key=lambda p: p.stat().st_mtime)
        for f in events:
            try:
                size -= f.stat().st_size
                f.unlink()
            except FileNotFoundError:
                pass
            if size <= BUFFER_LIMIT_BYTES:
                return

    # ----- Retry backoff -----

    @staticmethod
    def backoff_seconds(attempt: int) -> int:
        schedule = [1, 2, 4, 8, 16, 32, 60]
        if attempt < len(schedule):
            return schedule[attempt]
        return 60


KIND_MAP = {
    "/ops/runs/start":        "start",
    "/ops/runs/heartbeat":    "heartbeat",
    "/ops/runs/end":          "end",
    "/ops/runs/fail":         "fail",
    "/ops/events":            "event",
    "/ops/metrics/batch":     "batch",
    "/ops/scrapers/register": "register",
}


def kind_for_endpoint(endpoint: str) -> str:
    for prefix, kind in KIND_MAP.items():
        if endpoint.endswith(prefix):
            return kind
    return "other"
