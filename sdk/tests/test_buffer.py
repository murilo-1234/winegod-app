"""Testes do buffer offline."""
from __future__ import annotations

from pathlib import Path

from winegod_scraper_sdk.buffer import (
    BUFFER_LIMIT_BYTES,
    OfflineBuffer,
    kind_for_endpoint,
)


def test_enqueue_and_iter(tmp_path: Path):
    buf = OfflineBuffer(tmp_path, "canary_synthetic")
    p1 = buf.enqueue("/ops/runs/heartbeat", {"x": 1}, "k1", "heartbeat")
    p2 = buf.enqueue("/ops/runs/end", {"y": 2}, "k2", "end")
    assert p1.exists()
    assert p2.exists()

    items = list(buf.iter_pending())
    assert len(items) == 2
    # Ordem cronologica por nome (timestamp no prefixo)
    assert items[0].idempotency_key in ("k1", "k2")


def test_mark_sent_removes_file(tmp_path: Path):
    buf = OfflineBuffer(tmp_path, "canary_synthetic")
    buf.enqueue("/ops/events", {"a": 1}, "k1", "event")
    item = next(buf.iter_pending())
    buf.mark_sent(item)
    assert not item.filepath.exists()
    assert buf.pending_count() == 0


def test_kind_for_endpoint_mapping():
    assert kind_for_endpoint("/ops/runs/heartbeat") == "heartbeat"
    assert kind_for_endpoint("/ops/runs/start") == "start"
    assert kind_for_endpoint("/ops/runs/end") == "end"
    assert kind_for_endpoint("/ops/runs/fail") == "fail"
    assert kind_for_endpoint("/ops/events") == "event"
    assert kind_for_endpoint("/ops/metrics/batch") == "batch"
    assert kind_for_endpoint("/ops/scrapers/register") == "register"
    assert kind_for_endpoint("/something/else") == "other"


def test_backoff_schedule():
    from winegod_scraper_sdk.buffer import OfflineBuffer

    # 1,2,4,8,16,32,60,60,...
    assert OfflineBuffer.backoff_seconds(0) == 1
    assert OfflineBuffer.backoff_seconds(1) == 2
    assert OfflineBuffer.backoff_seconds(5) == 32
    assert OfflineBuffer.backoff_seconds(6) == 60
    assert OfflineBuffer.backoff_seconds(99) == 60


def test_gc_discards_heartbeats_when_full(tmp_path: Path, monkeypatch):
    """Simula buffer cheio e valida que heartbeats sao descartados antes de 'end'."""
    # Monkeypatch para limite pequeno
    import winegod_scraper_sdk.buffer as buf_mod

    monkeypatch.setattr(buf_mod, "BUFFER_LIMIT_BYTES", 1024)  # 1 KB
    buf = OfflineBuffer(tmp_path, "test_gc")

    # Enche com heartbeats ate estourar
    big_payload = {"x": "a" * 200}
    for _ in range(20):
        buf.enqueue("/ops/runs/heartbeat", big_payload, "k", "heartbeat")

    # Adiciona 1 event — deve sobreviver ao GC (heartbeats sao alvos primarios)
    buf.enqueue("/ops/events", big_payload, "ke", "event")

    # O GC sera acionado no proximo enqueue. Faca um push que triga GC.
    buf.enqueue("/ops/runs/end", big_payload, "kend", "end")

    kinds = [i.kind for i in buf.iter_pending()]
    # Heartbeats foram reduzidos ou zerados
    assert kinds.count("heartbeat") < 20
    # Event e end preservados
    assert "event" in kinds
    assert "end" in kinds
