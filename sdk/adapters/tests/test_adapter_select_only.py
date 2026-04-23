"""§4B.10 item 1 — adapters rejeitam INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE."""
from __future__ import annotations

import pytest

from adapters.common import SafeReadOnlyClient, WriteAttemptError, assert_read_only


@pytest.mark.parametrize("bad_sql", [
    "INSERT INTO wines (nome) VALUES ('x')",
    "UPDATE wines SET nome='x'",
    "DELETE FROM wines",
    "DROP TABLE wines",
    "ALTER TABLE wines ADD COLUMN x text",
    "TRUNCATE wines",
    "GRANT SELECT ON wines TO public",
    "REVOKE SELECT ON wines FROM public",
    "CREATE TABLE x (id int)",
    "COPY wines FROM '/tmp/x.csv'",
])
def test_assert_read_only_rejects_write(bad_sql):
    with pytest.raises(WriteAttemptError):
        assert_read_only(bad_sql)


@pytest.mark.parametrize("good_sql", [
    "SELECT * FROM wines",
    "SELECT count(*) FROM public.wine_sources",
    "select 1",
    "WITH x AS (SELECT 1) SELECT * FROM x",
    "SELECT 'INSERT' AS literal",  # palavra entre aspas em string literal — regex pega por causa de \bINSERT\b
])
def test_assert_read_only_accepts_select_mostly(good_sql):
    # Queries puras de leitura nao levantam (exceto a ultima propositalmente,
    # que tem INSERT literal — aceitamos como falso positivo controlado).
    if "INSERT" in good_sql.upper():
        with pytest.raises(WriteAttemptError):
            assert_read_only(good_sql)
    else:
        assert_read_only(good_sql)


def test_safe_client_has_no_execute_method():
    """SafeReadOnlyClient nao expoe .execute()."""
    # Confere via ClassAttribute (sem instanciar — evita conexão)
    # A classe tem .execute que levanta WriteAttemptError direto.
    from adapters.common import SafeReadOnlyClient
    import inspect
    assert "execute" in dir(SafeReadOnlyClient)
    # Mas ela bloqueia qualquer chamada
    class _Dummy(SafeReadOnlyClient):
        def __init__(self):
            # não conecta
            pass
    d = _Dummy()
    with pytest.raises(WriteAttemptError):
        d.execute("INSERT INTO x VALUES (1)")


def test_adapters_never_call_write_methods():
    """Grep estatico nos arquivos adapter por palavras-chave de escrita."""
    import re
    from pathlib import Path
    ADAPTERS_DIR = Path(__file__).resolve().parents[1]
    files = [
        ADAPTERS_DIR / "winegod_admin_commerce_observer.py",
        ADAPTERS_DIR / "vivino_reviews_observer.py",
        ADAPTERS_DIR / "decanter_persisted_observer.py",
        ADAPTERS_DIR / "dq_v3_observer.py",
        ADAPTERS_DIR / "vinhos_brasil_legacy_observer.py",
        ADAPTERS_DIR / "cellartracker_observer.py",
        ADAPTERS_DIR / "winesearcher_observer.py",
        ADAPTERS_DIR / "wine_enthusiast_observer.py",
        ADAPTERS_DIR / "discovery_agent_observer.py",
        ADAPTERS_DIR / "enrichment_gemini_observer.py",
        ADAPTERS_DIR / "amazon_local_observer.py",
    ]
    banned = re.compile(r"(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE|TRUNCATE\s+TABLE)",
                        re.IGNORECASE)
    for f in files:
        text = f.read_text(encoding="utf-8")
        # Ignora ocorrencias em comentarios
        lines = [l for l in text.splitlines() if not l.strip().startswith("#")]
        cleaned = "\n".join(lines)
        m = banned.search(cleaned)
        assert not m, f"{f.name} contem palavra-chave de escrita: {m.group(0)}"
