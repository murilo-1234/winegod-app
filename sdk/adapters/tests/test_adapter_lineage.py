"""§4B.10 item 3 + 5 — lineage e PII."""
from __future__ import annotations

import re
from pathlib import Path


ADAPTERS_DIR = Path(__file__).resolve().parents[1]


def _adapter_src(name: str) -> str:
    return (ADAPTERS_DIR / name).read_text(encoding="utf-8")


def test_all_adapters_mention_source_lineage():
    for name in (
        "winegod_admin_commerce_observer.py",
        "vivino_reviews_observer.py",
        "reviewers_vivino_observer.py",
        "catalog_vivino_updates_observer.py",
        "decanter_persisted_observer.py",
        "dq_v3_observer.py",
        "vinhos_brasil_legacy_observer.py",
        "cellartracker_observer.py",
        "winesearcher_observer.py",
        "wine_enthusiast_observer.py",
        "discovery_agent_observer.py",
        "enrichment_gemini_observer.py",
        "amazon_local_observer.py",
    ):
        src = _adapter_src(name)
        # Deve conter source_lineage com os 4 campos minimos
        assert "source_lineage" in src
        assert "source_system" in src
        assert "source_kind" in src
        assert "source_pointer" in src
        assert "source_record_count" in src


def test_no_pii_vivino_payload():
    """Vivino observer NÃO pode enviar reviewer_name/avatar/text/email/profile_url."""
    src = _adapter_src("vivino_reviews_observer.py")
    # Variáveis proibidas não podem aparecer em chaves dict do payload.
    # A presença em PII_FORBIDDEN_KEYS é aceitável (é o filtro).
    banned_keys_in_payload = re.findall(
        r"['\"](reviewer_name|reviewer_avatar_url|review_text_full|email|profile_url)['\"]\s*:",
        src,
    )
    # Permitimos a menção como dict value ou filtro — mas não como chave de payload sendo atribuída.
    # Na pratica nenhum ': ' deveria aparecer apos essas chaves no código do adapter.
    assert not banned_keys_in_payload, f"PII key as dict key encontrada: {banned_keys_in_payload}"


def test_no_decanter_api_call():
    """Decanter adapter NÃO faz HTTP externo para Decanter."""
    src = _adapter_src("decanter_persisted_observer.py")
    assert "pinot.decanter.com" not in src
    assert "decanter.com/v" not in src
    # requests é do SDK (TelemetryDelivery) — mas não deve haver chamadas diretas
    # Grep por padrão suspeito
    import re as _re
    m = _re.search(r"requests\.(get|post|put|delete)\s*\(\s*['\"]https?://[^'\"]*decanter", src, _re.IGNORECASE)
    assert not m, f"Chamada HTTP direta a Decanter detectada: {m.group(0) if m else ''}"


def test_dq_v3_observer_never_writes():
    """DQ V3 observer usa apenas SELECT."""
    src = _adapter_src("dq_v3_observer.py")
    # Grep palavras de escrita (fora de comentário)
    lines = [l for l in src.splitlines() if not l.strip().startswith("#")]
    cleaned = "\n".join(lines)
    import re as _re
    banned = _re.compile(r"(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)", _re.IGNORECASE)
    m = banned.search(cleaned)
    assert not m, f"DQ V3 observer contem escrita: {m.group(0) if m else ''}"


def test_enrichment_observer_no_live_gemini_call():
    src = _adapter_src("enrichment_gemini_observer.py")
    assert "google.generativeai" not in src
    assert "generativelanguage.googleapis.com" not in src
    assert "genai.Client" not in src
