from __future__ import annotations

import inspect

import pytest

from sdk.plugs.enrichment import external_adapter as ea


def test_describe_interface_points_to_existing_system():
    info = ea.describe_interface()
    assert "enrichment_v3.py" in info["path"]
    assert info["public_function"] == "enrich_items_v3"
    assert info["read_only"] is True
    assert info["cap_batch"] == 20_000


def test_enrich_batch_rejects_over_cap():
    with pytest.raises(ValueError, match="cap=20000"):
        ea.enrich_batch([{"ocr": {"name": f"w{i}"}} for i in range(20_001)])


def test_enrich_batch_returns_empty_for_empty_input(monkeypatch):
    calls = {"count": 0}

    def fake_load():
        calls["count"] += 1
        raise AssertionError("enrich nao deveria ser chamado para lista vazia")

    monkeypatch.setattr(ea, "_load_existing_enrich", fake_load)
    result = ea.enrich_batch([])
    assert result == []
    assert calls["count"] == 0


def test_enrich_batch_proxies_to_existing_system(monkeypatch):
    captured: dict[str, object] = {}

    def fake_enrich(items, source_channel=None, trace=None):
        captured["items"] = items
        captured["channel"] = source_channel
        return {
            "items": [{"index": 1, "kind": "wine", "producer": "P", "wine_name": "W"}],
            "raw_primary": "",
            "raw_escalated": "",
            "stats": {},
        }

    monkeypatch.setattr(ea, "_load_existing_enrich", lambda: fake_enrich)
    result = ea.enrich_batch([{"ocr": {"name": "Wine X"}}])
    assert captured["items"][0]["ocr"]["name"] == "Wine X"
    assert captured["channel"] == "enrichment_loop"
    assert result[0]["kind"] == "wine"


def test_adapter_module_never_modifies_existing_system_paths():
    # Garantia textual: adapter nao faz import de nada fora de backend/services
    # ou stdlib, nem escreve nada em arquivos do sistema existente.
    source = inspect.getsource(ea)
    assert "enrichment_v3" in source  # importado de forma explicita
    banned = ("open(", "write_text", "unlink", "rename")
    for token in banned:
        assert token not in source, f"adapter nao pode usar {token}"
