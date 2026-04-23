"""Testes do pipeline unico de ingestao (services/bulk_ingest.py).

Executa com:
    cd backend && python -m tests.test_bulk_ingest

A camada de validacao/filtro roda totalmente offline (sem DB).
O teste de dry_run/apply real e marcado `_db` e so roda se DATABASE_URL
estiver acessivel — ele cria e remove um vinho fake isolado.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bulk_ingest import (
    _validate,
    _validate_source,
    _generate_hash_dedup,
    _to_bool,
    _strip_safra,
    _levenshtein,
    _producer_prefix_match,
    _classify_match,
    _check_queue_explosion,
    process_bulk,
    process_sources_only,
)
import services.bulk_ingest as _bulk_ingest_module


def test_validate_reject_empty():
    payload, reason = _validate({})
    assert payload is None
    assert reason == "nome_ausente"


def test_validate_reject_short():
    payload, reason = _validate({"nome": "ab"})
    assert payload is None
    assert reason == "nome_curto"


def test_validate_reject_notwine_whisky():
    payload, reason = _validate({"nome": "Johnnie Walker Black Label Whisky 750ml"})
    assert payload is None
    assert reason.startswith("not_wine:")
    assert "whisky" in reason


def test_validate_reject_notwine_cachaca():
    payload, reason = _validate({"nome": "Cachaca Ypioca 51"})
    assert payload is None
    assert reason.startswith("not_wine:")


def test_validate_accepts_valid_wine():
    payload, reason = _validate({
        "nome": "Chateau Margaux Premier Grand Cru",
        "produtor": "Chateau Margaux",
        "safra": "2015",
        "pais": "FR",
        "tipo": "tinto",
        "uvas": "Cabernet Sauvignon, Merlot",
    })
    assert reason is None
    assert payload is not None
    assert payload["pais"] == "fr"
    assert payload["pais_nome"] == "França"
    assert payload["tipo"] == "tinto"
    assert payload["safra"] == "2015"
    assert payload["uvas"] is not None
    assert "Cabernet Sauvignon" in payload["uvas"]


def test_validate_rejects_invalid_pais():
    payload, reason = _validate({
        "nome": "Chateau Fake Grand Cru",
        "produtor": "Chateau Fake",
        "pais": "INVALIDO",
    })
    # Pais invalido nao rejeita o item — so limpa o campo
    assert reason is None, f"unexpected reject: {reason}"
    assert payload["pais"] is None


def test_validate_rejects_invalid_tipo():
    payload, reason = _validate({
        "nome": "Chateau Fake Grand Cru",
        "produtor": "Chateau Fake",
        "tipo": "martini",
    })
    assert reason is None, f"unexpected reject: {reason}"
    assert payload["tipo"] is None


def test_hash_dedup_stable():
    h1 = _generate_hash_dedup("cabernet riserva", "steidler hof", None)
    h2 = _generate_hash_dedup("cabernet riserva", "steidler hof", None)
    assert h1 == h2
    h3 = _generate_hash_dedup("cabernet riserva", "steidler hof", "2020")
    assert h3 != h1


def test_process_bulk_empty():
    r = process_bulk([], dry_run=True)
    assert r["received"] == 0
    assert r["valid"] == 0
    assert r["would_insert"] == 0
    # DQ V3 Escopo 1+2 -- novos contadores presentes mesmo em payload vazio
    assert r["sources_in_input"] == 0
    assert r["would_insert_sources"] == 0
    assert r["sources_inserted"] == 0


def test_process_bulk_all_rejected_notwine():
    items = [
        {"nome": "Johnnie Walker Black Whisky"},
        {"nome": "Cachaca Ypioca"},
        {"nome": "ab"},
    ]
    r = process_bulk(items, dry_run=True)
    assert r["received"] == 3
    assert r["valid"] == 0
    assert len(r["filtered_notwine"]) == 2
    assert len(r["rejected"]) == 1


# ---------------------------------------------------------------------------
# DQ V3 Escopo 1+2: validacao de sources (offline, sem DB)
# ---------------------------------------------------------------------------

def test_validate_source_happy_path():
    payload, reason = _validate_source({
        "store_id": 123,
        "url": "https://amazon.com.br/dp/B0XYZ",
        "preco": 89.90,
        "moeda": "BRL",
        "disponivel": True,
    })
    assert reason is None
    assert payload["store_id"] == 123
    assert payload["url"] == "https://amazon.com.br/dp/B0XYZ"
    assert payload["preco"] == 89.90
    assert payload["moeda"] == "BRL"
    assert payload["disponivel"] is True
    assert payload["em_promocao"] is False  # default


def test_validate_source_rejects_missing_store_id():
    payload, reason = _validate_source({"url": "https://x.com/abc"})
    assert payload is None
    assert reason == "store_id_missing"


def test_validate_source_rejects_missing_url():
    payload, reason = _validate_source({"store_id": 1})
    assert payload is None
    assert reason == "url_missing"


def test_validate_source_rejects_not_a_dict():
    payload, reason = _validate_source("not a dict")
    assert payload is None
    assert reason == "source_not_a_dict"


def test_validate_source_rejects_url_too_long():
    payload, reason = _validate_source({"store_id": 1, "url": "x" * 2001})
    assert payload is None
    assert reason == "url_too_long"


def test_validate_source_accepts_store_id_as_string_digit():
    payload, reason = _validate_source({"store_id": "42", "url": "https://x.com"})
    assert reason is None
    assert payload["store_id"] == 42


def test_validate_source_rejects_store_id_not_int():
    payload, reason = _validate_source({"store_id": "abc", "url": "https://x.com"})
    assert payload is None
    assert reason == "store_id_not_int"


def test_validate_source_default_disponivel_true():
    payload, _ = _validate_source({"store_id": 1, "url": "https://x.com"})
    assert payload["disponivel"] is True


def test_validate_source_keeps_external_id():
    payload, _ = _validate_source({
        "store_id": 1, "url": "https://x.com",
        "external_id": "B0XYZ123",
    })
    assert payload["external_id"] == "B0XYZ123"


def test_validate_item_without_sources_works():
    """Backward compat: item sem sources tem campos vazios mas continua valido."""
    payload, reason = _validate({
        "nome": "Chateau Margaux", "produtor": "Chateau Margaux",
        "safra": "2015", "pais": "FR", "tipo": "tinto",
    })
    assert reason is None
    assert payload["_sources"] == []
    assert payload["_sources_rejected"] == []


def test_validate_item_with_valid_sources():
    payload, reason = _validate({
        "nome": "Chateau Margaux", "produtor": "Chateau Margaux",
        "safra": "2015", "pais": "FR",
        "sources": [
            {"store_id": 10, "url": "https://loja1.com/chateau"},
            {"store_id": 20, "url": "https://loja2.com/chateau", "preco": 200.0},
        ],
    })
    assert reason is None
    assert len(payload["_sources"]) == 2
    assert payload["_sources"][0]["store_id"] == 10
    assert payload["_sources"][1]["preco"] == 200.0
    assert payload["_sources_rejected"] == []


def test_validate_item_with_mixed_sources_some_rejected():
    """Wine valido: sources invalidas nao rejeitam o wine, mas vao em _sources_rejected."""
    payload, reason = _validate({
        "nome": "Chateau Margaux", "produtor": "Chateau Margaux",
        "sources": [
            {"store_id": 1, "url": "https://ok.com/a"},
            {"store_id": 1},  # falta url
            "not a dict",
            {"url": "https://no-store.com"},  # falta store_id
        ],
    })
    assert reason is None
    assert len(payload["_sources"]) == 1
    assert len(payload["_sources_rejected"]) == 3
    reasons = [r["reason"] for r in payload["_sources_rejected"]]
    assert "url_missing" in reasons
    assert "source_not_a_dict" in reasons
    assert "store_id_missing" in reasons


def test_validate_item_sources_not_a_list():
    payload, reason = _validate({
        "nome": "Chateau Margaux",
        "sources": "not a list",
    })
    assert reason is None  # wine ainda e aceito
    assert payload["_sources"] == []
    assert len(payload["_sources_rejected"]) == 1
    assert payload["_sources_rejected"][0]["reason"] == "sources_not_a_list"


def test_validate_item_notwine_with_sources_still_rejected():
    """NOT_WINE continua rejeitando mesmo se vier com sources validas."""
    payload, reason = _validate({
        "nome": "Johnnie Walker Black Label Whisky 750ml",
        "sources": [{"store_id": 1, "url": "https://x.com"}],
    })
    assert payload is None
    assert reason.startswith("not_wine:")


def test_process_bulk_empty_with_run_id_kwargs():
    """run_id e create_sources aceitos mesmo com payload vazio."""
    r = process_bulk([], dry_run=True, run_id="smoke_test_01", create_sources=True)
    assert r["run_id"] == "smoke_test_01"
    assert r["create_sources"] is True
    assert r["sources_in_input"] == 0


def test_process_bulk_truncates_long_run_id():
    r = process_bulk([], dry_run=True, run_id="x" * 500)
    assert r["run_id"] is not None
    assert len(r["run_id"]) <= 128


# ---------------------------------------------------------------------------
# DQ V3 Hardening: _to_bool parser explicito
# ---------------------------------------------------------------------------

def test_to_bool_string_falsy():
    assert _to_bool("false", default=True) is False
    assert _to_bool("FALSE", default=True) is False
    assert _to_bool("0", default=True) is False
    assert _to_bool("no", default=True) is False
    assert _to_bool("nao", default=True) is False
    assert _to_bool("não", default=True) is False
    assert _to_bool("off", default=True) is False


def test_to_bool_string_truthy():
    assert _to_bool("true", default=False) is True
    assert _to_bool("TRUE", default=False) is True
    assert _to_bool("1", default=False) is True
    assert _to_bool("yes", default=False) is True
    assert _to_bool("sim", default=False) is True
    assert _to_bool("on", default=False) is True


def test_to_bool_real_bool():
    assert _to_bool(True, default=False) is True
    assert _to_bool(False, default=True) is False


def test_to_bool_int_and_float():
    assert _to_bool(1, default=False) is True
    assert _to_bool(0, default=True) is False
    assert _to_bool(2, default=False) is True
    assert _to_bool(0.0, default=True) is False
    assert _to_bool(1.5, default=False) is True


def test_to_bool_missing_returns_default():
    assert _to_bool(None, default=True) is True
    assert _to_bool(None, default=False) is False
    assert _to_bool("", default=True) is True


def test_to_bool_unknown_string_returns_default():
    # "maybe" nao e truthy nem falsy conhecido -> cai no default
    assert _to_bool("maybe", default=True) is True
    assert _to_bool("maybe", default=False) is False


def test_validate_source_disponivel_string_false():
    """Bug hardening: antes, 'false' virava True (bool('false') == True em Python)."""
    payload, _ = _validate_source({
        "store_id": 1, "url": "https://x.com",
        "disponivel": "false",
    })
    assert payload["disponivel"] is False


def test_validate_source_disponivel_string_zero():
    payload, _ = _validate_source({
        "store_id": 1, "url": "https://x.com",
        "disponivel": "0",
    })
    assert payload["disponivel"] is False


def test_validate_source_em_promocao_string_true():
    payload, _ = _validate_source({
        "store_id": 1, "url": "https://x.com",
        "em_promocao": "true",
    })
    assert payload["em_promocao"] is True


# ---------------------------------------------------------------------------
# DQ V3 Hardening: dry-run nao escreve logs (sem DB).
#
# Estrategia: monkey-patch `get_connection`/`release_connection` e as funcoes
# de log. Em dry-run com payload de wines validos, `get_connection` e
# necessaria para fazer lookup; o que NAO pode acontecer e `_log_not_wine`
# ou `_log_run` serem chamadas.
# ---------------------------------------------------------------------------

def test_dry_run_with_all_notwine_skips_db_entirely():
    """Payload 100% NOT_WINE em dry-run: nao chama get_connection nem log."""
    calls = {"get_conn": 0, "log_notwine": 0, "log_run": 0}

    def fake_get_conn():
        calls["get_conn"] += 1
        raise RuntimeError("get_connection should not be called in dry-run with all NOT_WINE")

    orig_conn = _bulk_ingest_module.get_connection
    orig_log_notwine = _bulk_ingest_module._log_not_wine
    orig_log_run = _bulk_ingest_module._log_run

    _bulk_ingest_module.get_connection = fake_get_conn
    _bulk_ingest_module._log_not_wine = lambda *a, **kw: calls.__setitem__("log_notwine", calls["log_notwine"] + 1)
    _bulk_ingest_module._log_run = lambda *a, **kw: calls.__setitem__("log_run", calls["log_run"] + 1)

    try:
        r = process_bulk(
            [{"nome": "Johnnie Walker Whisky"}, {"nome": "Cachaca Ypioca"}],
            dry_run=True,
            run_id="should_not_be_logged",
            source="unit_test_log_block",
        )
    finally:
        _bulk_ingest_module.get_connection = orig_conn
        _bulk_ingest_module._log_not_wine = orig_log_notwine
        _bulk_ingest_module._log_run = orig_log_run

    assert r["valid"] == 0
    assert len(r["filtered_notwine"]) == 2
    assert calls["get_conn"] == 0, "dry-run com zero validos nao pode abrir conexao"
    assert calls["log_notwine"] == 0, "dry-run nao pode chamar _log_not_wine"
    assert calls["log_run"] == 0, "dry-run nao pode chamar _log_run"


def test_apply_with_all_notwine_calls_log_notwine_AND_log_run():
    """Apply com payload 100% NOT_WINE:

    - DEVE chamar `_log_not_wine` para persistir rejections.
    - DEVE chamar `_log_run` (auditoria/rollback granular exige que o run
      apareca em `ingestion_run_log` mesmo se nenhum wine valido veio).
    """
    calls = {"get_conn": 0, "log_notwine": 0, "log_run": 0}

    class _FakeConn:
        pass
    fake_conn = _FakeConn()

    def fake_get_conn():
        calls["get_conn"] += 1
        return fake_conn

    def fake_release_conn(c):
        pass

    orig_conn = _bulk_ingest_module.get_connection
    orig_release = _bulk_ingest_module.release_connection
    orig_log_notwine = _bulk_ingest_module._log_not_wine
    orig_log_run = _bulk_ingest_module._log_run

    _bulk_ingest_module.get_connection = fake_get_conn
    _bulk_ingest_module.release_connection = fake_release_conn
    _bulk_ingest_module._log_not_wine = lambda *a, **kw: calls.__setitem__("log_notwine", calls["log_notwine"] + 1)
    _bulk_ingest_module._log_run = lambda *a, **kw: calls.__setitem__("log_run", calls["log_run"] + 1)

    try:
        r = process_bulk(
            [{"nome": "Johnnie Walker Whisky"}],
            dry_run=False,
            run_id="apply_notwine_log_test",
            source="unit_test_apply_notwine",
        )
    finally:
        _bulk_ingest_module.get_connection = orig_conn
        _bulk_ingest_module.release_connection = orig_release
        _bulk_ingest_module._log_not_wine = orig_log_notwine
        _bulk_ingest_module._log_run = orig_log_run

    assert r["valid"] == 0
    assert r["filtered_notwine_count"] == 1
    assert calls["get_conn"] == 1, f"expected 1 get_connection call, got {calls['get_conn']}"
    assert calls["log_notwine"] == 1, "apply com NOT_WINE deve chamar _log_not_wine"
    assert calls["log_run"] == 1, "apply com run_id deve chamar _log_run mesmo sem wines validos"


def test_route_uses_to_bool_for_dry_run_and_create_sources():
    """A rota `backend/routes/ingest.py` importa `_to_bool` e aplica nos flags
    do body. Sem o parser, `"false"` seria tratado como True (bug).

    Este teste valida o contrato do _to_bool no nivel que a rota depende.
    """
    # dry_run
    assert _to_bool("false", default=True) is False
    assert _to_bool("true", default=False) is True
    assert _to_bool(None, default=True) is True  # default preserved
    # create_sources
    assert _to_bool("0", default=True) is False
    assert _to_bool("1", default=False) is True
    assert _to_bool(None, default=True) is True


def test_route_module_imports_to_bool():
    """Garante que `routes.ingest` importa `_to_bool` -- se alguem remover a
    importacao, o parser volta a ter o bug `bool("false") == True`.
    """
    from routes import ingest as ingest_route
    assert hasattr(ingest_route, "_to_bool"), "routes.ingest deve importar _to_bool"


def test_counters_totals_not_capped_by_sample_limit():
    """Mais de 100 NOT_WINE: counter conta tudo, lista amostra capa em 100."""
    # 150 whiskies -> todos NOT_WINE
    items = [{"nome": f"Johnnie Walker Whisky batch {i}"} for i in range(150)]
    r = process_bulk(items, dry_run=True, source="unit_capped_notwine")
    assert r["received"] == 150
    assert r["filtered_notwine_count"] == 150, f"counter deve ser 150, got {r['filtered_notwine_count']}"
    assert len(r["filtered_notwine"]) == 100, f"lista amostra capada em 100, got {len(r['filtered_notwine'])}"
    # legacy count (len(lista)) nao existe mais -- apenas filtered_notwine_count
    assert r["valid"] == 0


def test_counters_rejected_not_capped():
    """Mais de 100 rejeicoes 'nome_curto': counter conta tudo, lista capa em 100."""
    items = [{"nome": "a"} for _ in range(120)]
    r = process_bulk(items, dry_run=True, source="unit_capped_rejected")
    assert r["received"] == 120
    assert r["rejected_count"] == 120
    assert len(r["rejected"]) == 100
    assert r["filtered_notwine_count"] == 0


def test_counters_sources_rejected_not_capped():
    """Mais de 100 sources rejeitadas: counter conta, lista capa em 100."""
    _skip_if_no_db()
    bad_sources = [{"store_id": 1}] * 150  # todas sem url -> url_missing
    items = [{
        "nome": "Chateau Margaux", "produtor": "Chateau Margaux",
        "sources": bad_sources,
    }]
    r = process_bulk(items, dry_run=True, source="unit_capped_sources")
    # 1 wine valido
    assert r["valid"] == 1
    # 150 sources rejeitadas
    assert r["sources_rejected_count"] == 150
    assert len(r["sources_rejected"]) == 100


def test_apply_all_notwine_without_run_id_still_logs_notwine_only():
    """Apply com NOT_WINE mas sem run_id: _log_not_wine sim, _log_run nao."""
    calls = {"get_conn": 0, "log_notwine": 0, "log_run": 0}

    class _FakeConn:
        pass
    fake_conn = _FakeConn()

    orig_conn = _bulk_ingest_module.get_connection
    orig_release = _bulk_ingest_module.release_connection
    orig_log_notwine = _bulk_ingest_module._log_not_wine
    orig_log_run = _bulk_ingest_module._log_run

    _bulk_ingest_module.get_connection = lambda: (calls.__setitem__("get_conn", calls["get_conn"] + 1) or fake_conn)
    _bulk_ingest_module.release_connection = lambda c: None
    _bulk_ingest_module._log_not_wine = lambda *a, **kw: calls.__setitem__("log_notwine", calls["log_notwine"] + 1)
    _bulk_ingest_module._log_run = lambda *a, **kw: calls.__setitem__("log_run", calls["log_run"] + 1)

    try:
        process_bulk(
            [{"nome": "Johnnie Walker Whisky"}],
            dry_run=False,
            source="unit_no_run_id",
        )
    finally:
        _bulk_ingest_module.get_connection = orig_conn
        _bulk_ingest_module.release_connection = orig_release
        _bulk_ingest_module._log_not_wine = orig_log_notwine
        _bulk_ingest_module._log_run = orig_log_run

    assert calls["log_notwine"] == 1
    assert calls["log_run"] == 0, "sem run_id, nao ha auditoria por run para escrever"


# -------- DB integration tests ----------
# Qualquer teste que chama process_bulk() com item valido (dry_run=True
# incluso) depende do banco, porque process_bulk resolve would_insert/
# would_update contra wines. Esses testes comecam com prefixo `test_db_`
# e sao puladas quando nao ha conexao (exceto em modo strict).


class DBUnavailable(Exception):
    """Levantada quando os testes sao rodados em modo strict sem DB."""


_DB_CACHE: dict = {}


def _db_available() -> bool:
    if "ok" in _DB_CACHE:
        return _DB_CACHE["ok"]
    try:
        from db.connection import get_connection, release_connection
        conn = get_connection()
        release_connection(conn)
        _DB_CACHE["ok"] = True
        _DB_CACHE["err"] = None
    except Exception as e:
        _DB_CACHE["ok"] = False
        _DB_CACHE["err"] = f"{type(e).__name__}: {e}"
    return _DB_CACHE["ok"]


def _db_err() -> str:
    return _DB_CACHE.get("err") or "db indisponivel"


def _skip_if_no_db():
    """Pula o teste atual se nao ha DB. Em modo strict, levanta DBUnavailable."""
    if _db_available():
        return
    if os.environ.get("REQUIRE_DB_TESTS") == "1":
        raise DBUnavailable(_db_err())
    raise _Skip(_db_err())


class _Skip(Exception):
    """Sinal interno para o runner marcar como SKIPPED."""


def test_db_process_bulk_dedup_in_input():
    _skip_if_no_db()
    items = [
        {"nome": "Chateau Margaux", "produtor": "Chateau Margaux", "safra": "2015"},
        {"nome": "Chateau Margaux", "produtor": "Chateau Margaux", "safra": "2015"},
    ]
    r = process_bulk(items, dry_run=True)
    assert r["duplicates_in_input"] == 1
    assert r["valid"] == 1


def test_db_dry_run_detects_update():
    _skip_if_no_db()
    if False:  # compat guard para trechos abaixo
        return
    from db.connection import get_connection, release_connection
    from services.bulk_ingest import _validate
    conn = get_connection()
    row = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nome, produtor, safra, pais FROM wines "
                "WHERE produtor IS NOT NULL AND suppressed_at IS NULL "
                "ORDER BY id LIMIT 50"
            )
            candidates = cur.fetchall()
    finally:
        release_connection(conn)
    for candidate in candidates:
        payload, reason = _validate({"nome": candidate[0], "produtor": candidate[1],
                                      "safra": candidate[2], "pais": candidate[3]})
        if payload is not None:
            row = candidate
            break
    assert row, "nenhum wine real passou no filtro — teste nao pode rodar"
    r = process_bulk(
        [{"nome": row[0], "produtor": row[1], "safra": row[2], "pais": row[3]}],
        dry_run=True,
        source="unittest",
    )
    assert r["valid"] == 1, f"expected valid=1 got {r}"
    assert r["would_update"] == 1, f"expected update=1 got {r}"
    assert r["would_insert"] == 0


def test_db_apply_then_cleanup():
    _skip_if_no_db()
    import uuid
    from db.connection import get_connection, release_connection
    unique = uuid.uuid4().hex[:8]
    fake_nome = f"Bulk Ingest UT Fake Wine {unique}"
    fake_prod = f"Pipeline UT Vinicola {unique}"

    r = process_bulk(
        [{"nome": fake_nome, "produtor": fake_prod, "safra": "2024", "pais": "br", "tipo": "tinto"}],
        dry_run=False,
        source="unittest_apply",
    )
    assert r["inserted"] == 1

    # reaplica -> update
    r2 = process_bulk(
        [{"nome": fake_nome, "produtor": fake_prod, "safra": "2024", "pais": "br"}],
        dry_run=False,
        source="unittest_apply",
    )
    assert r2["updated"] == 1
    assert r2["inserted"] == 0

    # cleanup
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM wines WHERE nome = %s", (fake_nome,))
            conn.commit()
    finally:
        release_connection(conn)


def test_db_legacy_hash_does_not_create_duplicate():
    """Regressao do bug critico.

    Simula wine legado com hash_dedup de outra formula (ex: Vivino import).
    Quando o pipeline recebe a mesma tripla (produtor_norm, nome_norm, safra),
    gera outro hash_dedup. Se o apply usasse so ON CONFLICT(hash_dedup), o
    novo INSERT sucederia — duplicata. Esse teste prova que NAO acontece.
    """
    _skip_if_no_db()
    import uuid
    import hashlib
    from db.connection import get_connection, release_connection
    from tools.normalize import normalizar

    unique = uuid.uuid4().hex[:8]
    fake_nome = f"Legacy Dup Guard {unique}"
    fake_prod = f"Legacy Dup Vinicola {unique}"
    safra = "2019"
    nome_norm = normalizar(fake_nome)
    prod_norm = normalizar(fake_prod)
    legacy_hash = "legacy_" + hashlib.sha1(
        f"{prod_norm}::{nome_norm}::{safra}".encode()
    ).hexdigest()[:24]

    # Insere wine legado diretamente com hash diferente do que o pipeline geraria.
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO wines
                   (hash_dedup, nome, nome_normalizado, produtor, produtor_normalizado,
                    safra, tipo, pais, total_fontes, fontes, descoberto_em, atualizado_em)
                   VALUES (%s, %s, %s, %s, %s, %s, 'tinto', 'fr', 5,
                           '[\"legacy_seed\"]'::jsonb, NOW(), NOW())
                   RETURNING id""",
                (legacy_hash, fake_nome, nome_norm, fake_prod, prod_norm, safra),
            )
            legacy_id = cur.fetchone()[0]
            conn.commit()
    finally:
        release_connection(conn)

    try:
        # Dry-run: deve reconhecer como update, nao insert
        r_dry = process_bulk(
            [{"nome": fake_nome, "produtor": fake_prod, "safra": safra, "pais": "fr"}],
            dry_run=True,
            source="unittest_legacy_guard",
        )
        assert r_dry["would_update"] == 1, f"dry-run deveria ver update, got {r_dry}"
        assert r_dry["would_insert"] == 0, f"dry-run nao pode indicar insert, got {r_dry}"

        # Apply: nao pode criar duplicata
        r_apply = process_bulk(
            [{"nome": fake_nome, "produtor": fake_prod, "safra": safra, "pais": "fr",
              "regiao": "Bordeaux"}],  # regiao nova
            dry_run=False,
            source="unittest_legacy_guard",
        )
        assert r_apply["inserted"] == 0, f"nao pode ter inserido duplicata: {r_apply}"
        assert r_apply["updated"] == 1, f"deveria ter updated 1 row: {r_apply}"

        # Verifica banco: so 1 wine com essa tripla, id preservado,
        # hash_dedup original mantido, regiao mergeada, total_fontes NAO inflado.
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(*) FROM wines
                       WHERE produtor_normalizado=%s AND nome_normalizado=%s AND safra=%s""",
                    (prod_norm, nome_norm, safra),
                )
                count = cur.fetchone()[0]
                assert count == 1, f"deveria ter 1 row, tem {count}"

                cur.execute(
                    """SELECT id, hash_dedup, regiao, total_fontes
                       FROM wines WHERE id=%s""",
                    (legacy_id,),
                )
                row = cur.fetchone()
                assert row[0] == legacy_id
                assert row[1] == legacy_hash, f"hash nao pode ter mudado: {row[1]}"
                assert row[2] == "Bordeaux", f"regiao nao foi mergeada: {row[2]}"
                # total_fontes foi seed=5; bulk_ingest nao mexe nele (UPDATE preserva)
                assert row[3] == 5, f"total_fontes nao pode ter mudado: {row[3]}"
        finally:
            release_connection(conn)
    finally:
        # cleanup
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM wines WHERE id=%s", (legacy_id,))
                conn.commit()
        finally:
            release_connection(conn)


def test_db_reapply_does_not_inflate_total_fontes():
    """Reapply do mesmo payload nao pode inflar total_fontes.

    total_fontes semanticamente representa fontes comerciais (wine_sources),
    nao tentativas de ingestao do mesmo wine.
    """
    _skip_if_no_db()
    import uuid
    from db.connection import get_connection, release_connection

    unique = uuid.uuid4().hex[:8]
    fake_nome = f"Total Fontes Guard {unique}"
    fake_prod = f"Total Fontes Vinicola {unique}"

    # Primeira ingestao
    r1 = process_bulk(
        [{"nome": fake_nome, "produtor": fake_prod, "safra": "2020", "pais": "ar"}],
        dry_run=False,
        source="unittest_totalfontes",
    )
    assert r1["inserted"] == 1

    # Reapply 3x com mesmo payload
    for _ in range(3):
        process_bulk(
            [{"nome": fake_nome, "produtor": fake_prod, "safra": "2020", "pais": "ar"}],
            dry_run=False,
            source="unittest_totalfontes",
        )

    # Check: total_fontes = 0 (bulk_ingest nao cria wine_sources)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT total_fontes, fontes FROM wines WHERE nome=%s",
                (fake_nome,),
            )
            row = cur.fetchone()
            assert row is not None
            total_fontes, fontes = row
            assert total_fontes == 0, (
                f"total_fontes deveria ser 0 — bulk_ingest nao cria "
                f"wine_sources (alinhado com new_wines.py e WineCard.tsx): "
                f"got {total_fontes}"
            )
            # fontes deduplicado: so 1 elemento (mesmo source textual)
            assert isinstance(fontes, list)
            assert len(fontes) == 1, f"fontes nao deduplicado: {fontes}"
            cur.execute("DELETE FROM wines WHERE nome=%s", (fake_nome,))
            conn.commit()
    finally:
        release_connection(conn)


def test_db_new_bulk_insert_starts_with_zero_fontes():
    """Contrato: bulk_ingest NAO cria wine_sources; nao pode aparecer como 1 loja.

    Alinha com `backend/services/new_wines.py` (chat auto-create tambem
    usa total_fontes=0) e com o render do frontend em WineCard.tsx
    (que mostra total_fontes como "loja/lojas").
    """
    _skip_if_no_db()
    import uuid
    from db.connection import get_connection, release_connection

    unique = uuid.uuid4().hex[:8]
    fake_nome = f"Zero Fontes Guard {unique}"
    fake_prod = f"Zero Fontes Vinicola {unique}"

    r = process_bulk(
        [{"nome": fake_nome, "produtor": fake_prod, "safra": "2022", "pais": "pt"}],
        dry_run=False,
        source="unittest_zerofontes",
    )
    assert r["inserted"] == 1

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT total_fontes, fontes FROM wines WHERE nome=%s",
                (fake_nome,),
            )
            total_fontes, fontes = cur.fetchone()
            assert total_fontes == 0, (
                f"bulk_ingest nao pode contar como 1 loja: got {total_fontes}"
            )
            assert fontes == ["bulk_ingest:unittest_zerofontes"], (
                f"provenance textual deve estar em `fontes`: {fontes}"
            )
            cur.execute("DELETE FROM wines WHERE nome=%s", (fake_nome,))
            conn.commit()
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# DQ V3 Escopo 1+2: testes DB para sources
#
# Esses testes precisam de:
#  - DATABASE_URL acessivel
#  - uma `store` qualquer existente (pega a primeira via SELECT)
#
# Quando `create_sources=True`, `process_bulk` chama `_apply_sources_batch`.
# Se migration 018 nao estiver aplicada, a coluna `ingestion_run_id` nao existe
# em wine_sources, e o codigo cai no SQL legacy (sem run_id) -- ainda funciona.
# ---------------------------------------------------------------------------

def _pick_real_store_id():
    """Retorna um store_id existente. Levanta _Skip se nao ha store."""
    from db.connection import get_connection, release_connection
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM stores ORDER BY id LIMIT 1")
            row = cur.fetchone()
            if not row:
                raise _Skip("nenhuma store cadastrada no banco")
            return row[0]
    finally:
        release_connection(conn)


def test_db_dry_run_with_sources_does_not_write():
    _skip_if_no_db()
    store_id = _pick_real_store_id()

    import uuid
    from db.connection import get_connection, release_connection

    unique = uuid.uuid4().hex[:8]
    fake_nome = f"Sources Dry Run {unique}"
    fake_prod = f"Sources Dry Vinicola {unique}"
    fake_url = f"https://test-dry.example.com/{unique}"

    r = process_bulk(
        [{
            "nome": fake_nome, "produtor": fake_prod, "safra": "2020", "pais": "ar",
            "sources": [{"store_id": store_id, "url": fake_url, "preco": 100.0, "moeda": "USD"}],
        }],
        dry_run=True,
        source="unittest_sources_dry",
    )

    # Deve ter contado a source sem escrever nada
    assert r["valid"] == 1
    assert r["sources_in_input"] == 1
    assert r["would_insert_sources"] >= 1  # wine e novo -> source seria insert
    assert r["inserted"] == 0  # dry-run nao insere
    assert r["sources_inserted"] == 0

    # Verificar que nada foi escrito
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM wines WHERE nome=%s", (fake_nome,))
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT COUNT(*) FROM wine_sources WHERE url=%s", (fake_url,))
            assert cur.fetchone()[0] == 0
    finally:
        release_connection(conn)


def test_db_apply_with_sources_creates_wine_and_source():
    _skip_if_no_db()
    store_id = _pick_real_store_id()

    import uuid
    from db.connection import get_connection, release_connection

    unique = uuid.uuid4().hex[:8]
    fake_nome = f"Apply Sources Wine {unique}"
    fake_prod = f"Apply Sources Vinicola {unique}"
    fake_url = f"https://test-apply.example.com/{unique}"

    test_run_id = f"unittest_run_{unique}"
    r = process_bulk(
        [{
            "nome": fake_nome, "produtor": fake_prod, "safra": "2021", "pais": "br",
            "tipo": "tinto",
            "sources": [
                {"store_id": store_id, "url": fake_url, "preco": 50.0, "moeda": "BRL"}
            ],
        }],
        dry_run=False,
        source="unittest_sources_apply",
        run_id=test_run_id,
    )

    assert r["inserted"] == 1, f"esperava 1 wine inserido: {r}"
    assert r["sources_inserted"] == 1, f"esperava 1 source inserida: {r}"

    # cleanup -- limpar wine_sources, wines E entradas do run em tabelas de tracking
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM wine_sources WHERE url=%s", (fake_url,))
            cur.execute("DELETE FROM wines WHERE nome=%s", (fake_nome,))
            # Limpar tracking se migration 018 aplicada (no-op se nao)
            try:
                cur.execute("DELETE FROM ingestion_run_log WHERE run_id=%s", (test_run_id,))
                cur.execute("DELETE FROM not_wine_rejections WHERE run_id=%s", (test_run_id,))
            except Exception:
                conn.rollback()
            conn.commit()
    finally:
        release_connection(conn)


def test_db_reapply_same_source_does_not_duplicate():
    _skip_if_no_db()
    store_id = _pick_real_store_id()

    import uuid
    from db.connection import get_connection, release_connection

    unique = uuid.uuid4().hex[:8]
    fake_nome = f"No Dup Source Wine {unique}"
    fake_prod = f"No Dup Source Vinicola {unique}"
    fake_url = f"https://test-nodup.example.com/{unique}"
    payload = {
        "nome": fake_nome, "produtor": fake_prod, "safra": "2022", "pais": "cl",
        "sources": [{"store_id": store_id, "url": fake_url, "preco": 60.0, "moeda": "USD"}],
    }

    r1 = process_bulk([payload], dry_run=False, source="unittest_nodup")
    assert r1["inserted"] == 1
    assert r1["sources_inserted"] == 1

    # Reaplica exatamente o mesmo payload: source nao duplica
    r2 = process_bulk([payload], dry_run=False, source="unittest_nodup")
    assert r2["inserted"] == 0
    assert r2["updated"] == 1
    assert r2["sources_inserted"] == 0, f"source nao deveria duplicar: {r2}"
    assert r2["sources_updated"] == 1, f"source deveria ter sido atualizada: {r2}"

    # Confere que existe apenas 1 row em wine_sources para essa URL
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM wine_sources WHERE url=%s", (fake_url,))
            assert cur.fetchone()[0] == 1
            cur.execute("DELETE FROM wine_sources WHERE url=%s", (fake_url,))
            cur.execute("DELETE FROM wines WHERE nome=%s", (fake_nome,))
            conn.commit()
    finally:
        release_connection(conn)


def test_db_apply_without_sources_still_works():
    """Backward compat: payload sem `sources` continua funcionando."""
    _skip_if_no_db()
    import uuid
    from db.connection import get_connection, release_connection

    unique = uuid.uuid4().hex[:8]
    fake_nome = f"Backward Compat Wine {unique}"
    fake_prod = f"Backward Compat Vinicola {unique}"

    r = process_bulk(
        [{"nome": fake_nome, "produtor": fake_prod, "safra": "2019", "pais": "fr"}],
        dry_run=False,
        source="unittest_backcompat",
    )
    assert r["inserted"] == 1
    assert r["sources_in_input"] == 0
    assert r["sources_inserted"] == 0

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM wines WHERE nome=%s", (fake_nome,))
            conn.commit()
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# DQ V3 Escopo 4: fuzzy tier + review queue -- testes offline
# ---------------------------------------------------------------------------

def test_strip_safra_removes_year_and_nv():
    assert _strip_safra("guado al tasso 2024 il bruciato") == "guado al tasso il bruciato"
    assert _strip_safra("dom perignon 2013") == "dom perignon"
    assert _strip_safra("champagne krug nv") == "champagne krug"
    assert _strip_safra("champagne krug n.v.") == "champagne krug"
    assert _strip_safra("wine without year") == "wine without year"
    assert _strip_safra("") == ""


def test_strip_safra_collapses_whitespace():
    assert _strip_safra("wine   2019   name") == "wine name"


def test_levenshtein_zero_on_equal():
    assert _levenshtein("bodegas", "bodegas") == 0


def test_levenshtein_small_diff():
    assert _levenshtein("bodega", "bodegas") == 1
    assert _levenshtein("bodegas", "bodega") == 1


def test_levenshtein_caps_at_3():
    # Strings muito diferentes -> para em cap.
    d = _levenshtein("alpha", "zebra_stripes_xyz", cap=3)
    assert d == 3


def test_levenshtein_empty_inputs():
    assert _levenshtein("", "", cap=3) == 0
    assert _levenshtein("abc", "", cap=3) == 3
    assert _levenshtein("", "ab", cap=3) == 2


def test_producer_prefix_match_exact():
    assert _producer_prefix_match("bodegas munoz", "bodegas munoz") is True


def test_producer_prefix_match_truncated():
    # Caso "Bodegas Munoz" -> "Bodegas Munoz Artero"
    assert _producer_prefix_match("bodegas munoz", "bodegas munoz artero") is True
    assert _producer_prefix_match("bodegas munoz artero", "bodegas munoz") is True


def test_producer_prefix_match_rejects_too_short():
    # Ambos precisam ter comprimento >= 4
    assert _producer_prefix_match("el", "el mosto") is False
    assert _producer_prefix_match("ab", "abc") is False


def test_producer_prefix_match_rejects_min_diff_too_small():
    # Diferenca minima de 2 chars -- "abcd" vs "abcde" nao conta.
    assert _producer_prefix_match("abcd", "abcde") is False


def test_producer_prefix_match_disjoint():
    assert _producer_prefix_match("bodegas munoz", "chateau margaux") is False


def test_producer_prefix_match_empty():
    assert _producer_prefix_match("", "bodegas") is False
    assert _producer_prefix_match("bodegas", "") is False


def test_classify_none_when_no_candidates():
    row = {"produtor_normalizado": "bodegas munoz", "safra": "2020"}
    decision, tier, wid = _classify_match(row, [])
    assert decision == "none"
    assert tier is None
    assert wid is None


def test_classify_auto_merge_prefix_unique():
    """1 candidato, produtor prefixo claro, sem conflito de safra -> auto_merge."""
    row = {"produtor_normalizado": "bodegas munoz", "safra": "2020"}
    candidates = [
        {"id": 42, "produtor_normalizado": "bodegas munoz artero", "safra": "2020"},
    ]
    decision, tier, wid = _classify_match(row, candidates)
    assert decision == "auto_merge"
    assert tier == "fuzzy_k3_prefix_unique"
    assert wid == 42


def test_classify_enqueue_when_two_candidates():
    """2+ candidatos -> sempre enqueue, nunca auto-merge."""
    row = {"produtor_normalizado": "bodegas munoz", "safra": "2020"}
    candidates = [
        {"id": 1, "produtor_normalizado": "bodegas munoz artero", "safra": "2020"},
        {"id": 2, "produtor_normalizado": "bodegas munoz jr", "safra": "2020"},
    ]
    decision, tier, wid = _classify_match(row, candidates)
    assert decision == "enqueue"
    assert tier == "fuzzy_k3_multi_candidate"
    assert wid is None


def test_classify_enqueue_on_safra_conflict_even_with_prefix():
    """Ambos com safra preenchida e diferentes: NUNCA auto-merge (regra 5)."""
    row = {"produtor_normalizado": "bodegas munoz", "safra": "2020"}
    candidates = [
        {"id": 42, "produtor_normalizado": "bodegas munoz artero", "safra": "2019"},
    ]
    decision, tier, wid = _classify_match(row, candidates)
    assert decision == "enqueue"
    assert tier == "fuzzy_k3_safra_conflict"
    assert wid is None


def test_classify_auto_merge_when_one_side_has_null_safra():
    """Safra NULL em um dos lados nao e conflito -- auto-merge permitido."""
    row = {"produtor_normalizado": "bodegas munoz", "safra": None}
    candidates = [
        {"id": 42, "produtor_normalizado": "bodegas munoz artero", "safra": "2020"},
    ]
    decision, tier, wid = _classify_match(row, candidates)
    assert decision == "auto_merge"
    assert wid == 42


def test_classify_enqueue_levenshtein_close_not_prefix():
    """Levenshtein <= 2 mas nao e prefix -> enqueue (regra 6). NUNCA auto-merge."""
    row = {"produtor_normalizado": "bodegas munoz", "safra": "2020"}
    candidates = [
        # "bodegas minoz" difere de "bodegas munoz" em 1 char
        {"id": 42, "produtor_normalizado": "bodegas minoz", "safra": "2020"},
    ]
    decision, tier, wid = _classify_match(row, candidates)
    assert decision == "enqueue"
    assert tier == "fuzzy_k3_levenshtein_close"
    assert wid is None


def test_classify_enqueue_disjoint_producer():
    """Produtor totalmente diferente (disjoint) -> enqueue padrao."""
    row = {"produtor_normalizado": "bodegas munoz", "safra": "2020"}
    candidates = [
        {"id": 42, "produtor_normalizado": "chateau margaux", "safra": "2020"},
    ]
    decision, tier, wid = _classify_match(row, candidates)
    assert decision == "enqueue"
    assert tier == "fuzzy_k3_disjoint_producer"
    assert wid is None


def test_check_queue_explosion_absolute_cap():
    """Enqueue acima do cap absoluto bloqueia."""
    # usar defaults do Config (20000, 0.05)
    result = {"would_enqueue_review": 20001, "valid": 1_000_000}
    blocked, reason = _check_queue_explosion(result)
    assert blocked == "BLOCKED_QUEUE_EXPLOSION"
    assert "abs_cap" in reason


def test_check_queue_explosion_percentage_cap():
    """Enqueue acima de 5% do valid bloqueia, mesmo em run pequeno."""
    # 6% de 1000 = 60 -- acima do pct_cap
    result = {"would_enqueue_review": 60, "valid": 1000}
    blocked, reason = _check_queue_explosion(result)
    assert blocked == "BLOCKED_QUEUE_EXPLOSION"
    assert "pct_cap" in reason


def test_check_queue_explosion_does_not_block_under_thresholds():
    """4.9% e 19999 absoluto -- nao bloqueia."""
    result = {"would_enqueue_review": 49, "valid": 1000}
    blocked, reason = _check_queue_explosion(result)
    assert blocked is None
    assert reason is None


def test_check_queue_explosion_handles_zero_valid():
    """Se valid=0, nao aplica pct_cap -- so o abs_cap."""
    result = {"would_enqueue_review": 0, "valid": 0}
    blocked, _reason = _check_queue_explosion(result)
    assert blocked is None


def test_process_bulk_has_escopo4_counters():
    """Response sempre expoe os contadores do Escopo 4, mesmo em payload vazio."""
    r = process_bulk([], dry_run=True)
    assert "would_auto_merge_strict" in r
    assert "auto_merge_strict_count" in r
    assert "would_enqueue_review" in r
    assert "enqueue_for_review_count" in r
    assert "enqueue_for_review" in r
    assert "enqueue_by_tier" in r
    assert "blocked" in r
    assert "block_reason" in r
    assert r["would_enqueue_review"] == 0
    assert r["blocked"] is None


def test_dry_run_with_fuzzy_does_not_write_or_enqueue():
    """Dry-run com items que potencialmente iriam pra fuzzy: nao chama enqueue/logs."""
    calls = {"enqueue": 0, "log_run": 0, "log_notwine": 0}

    orig_enqueue = _bulk_ingest_module._enqueue_review_batch
    orig_log_run = _bulk_ingest_module._log_run
    orig_log_notwine = _bulk_ingest_module._log_not_wine

    _bulk_ingest_module._enqueue_review_batch = (
        lambda *a, **kw: calls.__setitem__("enqueue", calls["enqueue"] + 1) or 0
    )
    _bulk_ingest_module._log_run = (
        lambda *a, **kw: calls.__setitem__("log_run", calls["log_run"] + 1)
    )
    _bulk_ingest_module._log_not_wine = (
        lambda *a, **kw: calls.__setitem__("log_notwine", calls["log_notwine"] + 1)
    )

    # Payload 100% NOT_WINE em dry-run: early return, nem toca em get_connection.
    try:
        r = process_bulk(
            [{"nome": "Johnnie Walker Whisky"}],
            dry_run=True,
            run_id="escopo4_dryrun_test",
            source="unit_escopo4_dryrun",
        )
    finally:
        _bulk_ingest_module._enqueue_review_batch = orig_enqueue
        _bulk_ingest_module._log_run = orig_log_run
        _bulk_ingest_module._log_not_wine = orig_log_notwine

    assert r["valid"] == 0
    assert calls["enqueue"] == 0, "dry-run nao pode enfileirar"
    assert calls["log_run"] == 0
    assert calls["log_notwine"] == 0


def test_apply_blocked_queue_explosion_writes_nothing():
    """Cenario forcado: apply com explosao de queue nao deve escrever NADA."""
    # Monkeypatch: _check_queue_explosion sempre bloqueia.
    calls = {"enqueue": 0, "log_run": 0, "log_notwine": 0,
             "apply_batch": 0, "apply_sources": 0,
             "resolve_fuzzy": 0, "get_conn": 0}

    class _FakeConn:
        def cursor(self):
            raise RuntimeError("blocked run should not create a real cursor")

    orig_check = _bulk_ingest_module._check_queue_explosion
    orig_get_conn = _bulk_ingest_module.get_connection
    orig_release = _bulk_ingest_module.release_connection
    orig_apply = _bulk_ingest_module._apply_batch
    orig_apply_src = _bulk_ingest_module._apply_sources_batch
    orig_enqueue = _bulk_ingest_module._enqueue_review_batch
    orig_log_run = _bulk_ingest_module._log_run
    orig_log_notwine = _bulk_ingest_module._log_not_wine
    orig_resolve = _bulk_ingest_module._resolve_existing
    orig_resolve_fuzzy = _bulk_ingest_module._resolve_fuzzy_k3
    orig_prevalidate = _bulk_ingest_module._prevalidate_store_ids

    # Neutralizar lookups read-only pra nao precisar de DB real.
    _bulk_ingest_module.get_connection = (
        lambda: (calls.__setitem__("get_conn", calls["get_conn"] + 1) or _FakeConn())
    )
    _bulk_ingest_module.release_connection = lambda c: None
    _bulk_ingest_module._resolve_existing = lambda c, b: (set(), {})
    _bulk_ingest_module._resolve_fuzzy_k3 = (
        lambda c, r: calls.__setitem__("resolve_fuzzy", calls["resolve_fuzzy"] + 1) or {}
    )
    _bulk_ingest_module._prevalidate_store_ids = lambda c, s: set()
    # For vezes pra garantir: bloqueio ocorre antes de chamar apply.
    _bulk_ingest_module._check_queue_explosion = lambda r: (
        "BLOCKED_QUEUE_EXPLOSION", "forced_for_test"
    )
    _bulk_ingest_module._apply_batch = (
        lambda *a, **kw: (calls.__setitem__("apply_batch", calls["apply_batch"] + 1), 0, 0, {})[1:]
    )
    _bulk_ingest_module._apply_sources_batch = (
        lambda *a, **kw: (calls.__setitem__("apply_sources", calls["apply_sources"] + 1), 0, 0)[1:]
    )
    _bulk_ingest_module._enqueue_review_batch = (
        lambda *a, **kw: calls.__setitem__("enqueue", calls["enqueue"] + 1) or 0
    )
    _bulk_ingest_module._log_run = (
        lambda *a, **kw: calls.__setitem__("log_run", calls["log_run"] + 1)
    )
    _bulk_ingest_module._log_not_wine = (
        lambda *a, **kw: calls.__setitem__("log_notwine", calls["log_notwine"] + 1)
    )

    try:
        r = process_bulk(
            [{"nome": "Chateau Teste Bloqueio", "produtor": "Chateau Teste"}],
            dry_run=False,
            run_id="blocked_run_test",
            source="unit_blocked",
        )
    finally:
        _bulk_ingest_module._check_queue_explosion = orig_check
        _bulk_ingest_module.get_connection = orig_get_conn
        _bulk_ingest_module.release_connection = orig_release
        _bulk_ingest_module._apply_batch = orig_apply
        _bulk_ingest_module._apply_sources_batch = orig_apply_src
        _bulk_ingest_module._enqueue_review_batch = orig_enqueue
        _bulk_ingest_module._log_run = orig_log_run
        _bulk_ingest_module._log_not_wine = orig_log_notwine
        _bulk_ingest_module._resolve_existing = orig_resolve
        _bulk_ingest_module._resolve_fuzzy_k3 = orig_resolve_fuzzy
        _bulk_ingest_module._prevalidate_store_ids = orig_prevalidate

    assert r["blocked"] == "BLOCKED_QUEUE_EXPLOSION"
    assert r["block_reason"] == "forced_for_test"
    assert calls["apply_batch"] == 0, "nao pode chamar _apply_batch em run bloqueado"
    assert calls["apply_sources"] == 0
    assert calls["enqueue"] == 0
    assert calls["log_run"] == 0, "nao pode chamar _log_run em run bloqueado"
    assert calls["log_notwine"] == 0, "nao pode chamar _log_not_wine em run bloqueado"


def test_enqueue_sample_list_capped_at_100():
    """Mais de 100 enqueues -> lista amostra capada em 100, counter livre."""
    # Forca: 150 items que vao pra enqueue via monkeypatch.
    orig_resolve = _bulk_ingest_module._resolve_existing
    orig_resolve_fuzzy = _bulk_ingest_module._resolve_fuzzy_k3
    orig_get_conn = _bulk_ingest_module.get_connection
    orig_release = _bulk_ingest_module.release_connection
    orig_prevalidate = _bulk_ingest_module._prevalidate_store_ids

    class _FakeConn:
        pass
    fake_conn = _FakeConn()

    _bulk_ingest_module.get_connection = lambda: fake_conn
    _bulk_ingest_module.release_connection = lambda c: None
    _bulk_ingest_module._resolve_existing = lambda c, b: (set(), {})
    # Todos com multi_candidate -> enqueue garantido.
    _bulk_ingest_module._resolve_fuzzy_k3 = lambda c, remainder: {
        row["hash_dedup"]: [
            {"id": 1, "produtor_normalizado": "a", "safra": None},
            {"id": 2, "produtor_normalizado": "b", "safra": None},
        ]
        for row in remainder
    }
    _bulk_ingest_module._prevalidate_store_ids = lambda c, s: set()

    items = [
        {
            "nome": f"Wine Fuzzy Cap {i}",
            "produtor": f"Vinicola Cap {i}",
            "pais": "br",
            "tipo": "tinto",
        }
        for i in range(150)
    ]

    try:
        r = process_bulk(items, dry_run=True, source="unit_enqueue_cap")
    finally:
        _bulk_ingest_module._resolve_existing = orig_resolve
        _bulk_ingest_module._resolve_fuzzy_k3 = orig_resolve_fuzzy
        _bulk_ingest_module.get_connection = orig_get_conn
        _bulk_ingest_module.release_connection = orig_release
        _bulk_ingest_module._prevalidate_store_ids = orig_prevalidate

    # Dica: pct_cap default = 5%. 150 enqueues de 150 validos = 100% -> blocked.
    # Nao importa -- o cap de amostra e aplicado durante a fase 1, antes do
    # cut-off. Verificamos independentemente.
    assert r["would_enqueue_review"] == 150
    assert len(r["enqueue_for_review"]) == 100
    assert r["enqueue_by_tier"]["fuzzy_k3_multi_candidate"] == 150


def test_route_ingest_review_module_loads():
    """Garante que routes.ingest_review importa e registra o endpoint."""
    from routes import ingest_review as review_route
    assert hasattr(review_route, "ingest_review_bp")
    # Funcao principal exposta
    assert hasattr(review_route, "_apply_review_decision")


# ---------------------------------------------------------------------------
# DQ V3 Escopo 6: testes offline de process_sources_only
# ---------------------------------------------------------------------------


def test_process_sources_only_empty_returns_zeroed():
    r = process_sources_only([], dry_run=True)
    assert r["received"] == 0
    assert r["valid"] == 0
    assert r["sources_in_input"] == 0
    assert r["sources_inserted"] == 0
    assert r["rejected_count"] == 0


def test_process_sources_only_rejects_invalid_items_offline():
    """Itens invalidos sao rejeitados na fase offline (antes de abrir DB)."""
    # Monkeypatch get_connection para garantir que items invalidos NAO abrem DB.
    calls = {"get_conn": 0}
    orig_get = _bulk_ingest_module.get_connection

    def fake_get():
        calls["get_conn"] += 1
        raise RuntimeError("nao pode abrir DB quando todos os items sao invalidos")

    _bulk_ingest_module.get_connection = fake_get
    try:
        r = process_sources_only([
            "not a dict",
            {"sources": [{"store_id": 1, "url": "https://x/a"}]},  # sem wine_id nem hash
            {"wine_id": "xxx", "sources": [{"store_id": 1, "url": "https://x/b"}]},  # wine_id nao-int
            {"wine_id": 1, "sources": "not a list"},
            {"wine_id": 2, "sources": []},
        ], dry_run=True)
    finally:
        _bulk_ingest_module.get_connection = orig_get

    assert calls["get_conn"] == 0, "nenhum item valido -> nao abrir DB"
    assert r["rejected_count"] == 5
    reasons = {x["reason"] for x in r["rejected"]}
    assert "not_a_dict" in reasons
    assert "missing_wine_id_and_hash_dedup" in reasons
    assert "wine_id_not_int" in reasons
    assert "sources_missing_or_not_a_list" in reasons


def test_process_sources_only_validates_sources_offline():
    """Sources individuais invalidas incrementam sources_rejected_count."""
    calls = {"get_conn": 0}
    orig_get = _bulk_ingest_module.get_connection

    def fake_get():
        calls["get_conn"] += 1
        raise RuntimeError("nao pode abrir DB quando nao ha source valida")

    _bulk_ingest_module.get_connection = fake_get
    try:
        r = process_sources_only([
            {
                "wine_id": 10,
                "sources": [
                    {"store_id": 1},              # falta url
                    "not a dict",
                    {"url": "https://x.com/no"},  # falta store_id
                ],
            },
        ], dry_run=True)
    finally:
        _bulk_ingest_module.get_connection = orig_get

    assert calls["get_conn"] == 0
    assert r["sources_rejected_count"] == 3
    assert r["valid"] == 0  # item sem sources validas nao entra em prepared


# ---------------------------------------------------------------------------
# DQ V3 Escopo 4: testes DB (opt-in via RUN_DB_TESTS=1)
# ---------------------------------------------------------------------------

def _create_canonical_seed_for_fuzzy(conn, unique: str, produtor_norm: str,
                                     nome_sem_safra: str, pais: str, tipo: str,
                                     safra: str | None = None) -> int:
    """Insere um wine canonical (vivino_id NOT NULL) para fuzzy K3 testing.

    Usa vivino_id grande (>= 9 * 10^8) para minimizar colisao com ids reais.
    Retorna o wine_id criado. Chamador e responsavel pelo cleanup.
    """
    import random
    seed_vivino_id = 900_000_000 + random.randint(0, 99_999_999)
    nome_norm = nome_sem_safra if not safra else f"{nome_sem_safra} {safra}"
    nome_original = f"Canonical Seed {nome_sem_safra} {unique}"
    hash_dedup = f"canonical_seed_{unique}"
    produtor_orig = f"Produtor {unique}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO wines (
                hash_dedup, nome, nome_normalizado, nome_normalizado_sem_safra,
                produtor, produtor_normalizado, safra, pais, tipo,
                vivino_id, total_fontes, fontes, descoberto_em, atualizado_em
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, 0, '[]'::jsonb, NOW(), NOW()
            )
            RETURNING id
            """,
            (hash_dedup, nome_original, nome_norm, nome_sem_safra,
             produtor_orig, produtor_norm, safra, pais, tipo,
             seed_vivino_id),
        )
        wid = cur.fetchone()[0]
        conn.commit()
    return wid


def _cleanup_db_run(unique: str, run_id: str, extra_wine_names: list[str] | None = None,
                    extra_urls: list[str] | None = None,
                    extra_wine_ids: list[int] | None = None) -> None:
    from db.connection import get_connection, release_connection
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for url in (extra_urls or []):
                cur.execute("DELETE FROM wine_sources WHERE url = %s", (url,))
            # cleanup por url do seed tambem
            cur.execute(
                "DELETE FROM wine_sources WHERE wine_id IN ("
                "SELECT id FROM wines WHERE hash_dedup = %s)",
                (f"canonical_seed_{unique}",),
            )
            cur.execute("DELETE FROM ingestion_review_queue WHERE run_id = %s", (run_id,))
            try:
                cur.execute("DELETE FROM ingestion_run_log WHERE run_id = %s", (run_id,))
                cur.execute("DELETE FROM not_wine_rejections WHERE run_id = %s", (run_id,))
            except Exception:
                conn.rollback()
            for wid in (extra_wine_ids or []):
                cur.execute("DELETE FROM wines WHERE id = %s", (wid,))
            for nome in (extra_wine_names or []):
                cur.execute("DELETE FROM wines WHERE nome = %s", (nome,))
            cur.execute("DELETE FROM wines WHERE hash_dedup = %s", (f"canonical_seed_{unique}",))
            conn.commit()
    finally:
        release_connection(conn)


def test_db_enqueue_creates_review_row():
    """Cenario 1: item com produtor disjoint contra canonical K3 -> enqueue."""
    _skip_if_no_db()
    import uuid
    from db.connection import get_connection, release_connection

    unique = uuid.uuid4().hex[:10]
    pais = "pt"
    tipo = "tinto"
    nome_sem_safra = f"fuzzy enqueue wine {unique}"
    canonical_prod_norm = f"canonical base producer {unique}"

    # item_nome tem que normalizar para EXATAMENTE nome_sem_safra,
    # senao o fuzzy K3 nao bate.
    item_nome = nome_sem_safra.title()
    item_produtor = f"Totally Disjoint Xyz {unique}"
    run_id = f"unittest_enqueue_{unique}"

    # Com 1 item valido indo pra enqueue, ratio seria 100% > 5% (pct_cap)
    # e o cut-off BLOCKED_QUEUE_EXPLOSION dispararia. Neste teste queremos
    # observar o enqueue puro, entao relaxamos o pct_cap temporariamente.
    from config import Config
    orig_pct_cap = Config.INGEST_QUEUE_PCT_CAP
    Config.INGEST_QUEUE_PCT_CAP = 1.0

    canonical_id = None
    conn = get_connection()
    try:
        canonical_id = _create_canonical_seed_for_fuzzy(
            conn, unique, canonical_prod_norm, nome_sem_safra, pais, tipo, safra=None,
        )
    finally:
        release_connection(conn)

    try:
        r = process_bulk(
            [{
                "nome": item_nome,
                "produtor": item_produtor,
                "pais": pais,
                "tipo": tipo,
            }],
            dry_run=False,
            run_id=run_id,
            source="unittest_enqueue_db",
        )
        assert r["blocked"] is None, f"nao deveria bloquear: {r}"
        assert r["would_enqueue_review"] == 1, f"esperava 1 enqueue: {r}"
        assert r["enqueue_for_review_count"] == 1, f"esperava 1 row gravada: {r}"
        assert r["inserted"] == 0
        assert r["updated"] == 0
        assert r["auto_merge_strict_count"] == 0

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT run_id, match_tier, candidate_wine_ids, status
                    FROM ingestion_review_queue
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                rows = cur.fetchall()
                assert len(rows) == 1, f"esperava 1 row na queue, got {len(rows)}"
                queue_run_id, match_tier, candidate_ids, status = rows[0]
                assert queue_run_id == run_id
                assert match_tier == "fuzzy_k3_disjoint_producer"
                assert canonical_id in list(candidate_ids)
                assert status == "pending"
                cur.execute("SELECT COUNT(*) FROM wines WHERE nome = %s", (item_nome,))
                assert cur.fetchone()[0] == 0, "enqueue NAO pode criar wine novo"
        finally:
            release_connection(conn)
    finally:
        Config.INGEST_QUEUE_PCT_CAP = orig_pct_cap
        _cleanup_db_run(
            unique, run_id,
            extra_wine_names=[item_nome],
            extra_wine_ids=[canonical_id] if canonical_id else None,
        )


def test_db_auto_merge_strict_updates_canonical_with_original_run_id():
    """Cenario 2: produtor e prefixo claro + K3 bate + 1 unico candidato ->
    auto_merge; canonical recebe ingestion_run_id do upload original."""
    _skip_if_no_db()
    import uuid
    from tools.normalize import normalizar
    from db.connection import get_connection, release_connection

    unique = uuid.uuid4().hex[:10]
    pais = "es"
    tipo = "tinto"
    nome_sem_safra = f"auto merge wine {unique}"
    canonical_prod = f"Producer Base {unique}"
    canonical_prod_norm = normalizar(canonical_prod)

    item_nome = nome_sem_safra.title()  # normaliza pra nome_sem_safra
    item_produtor = "Producer Base"   # prefixo claro de canonical
    run_id = f"unittest_automerge_{unique}"

    canonical_id = None
    conn = get_connection()
    try:
        canonical_id = _create_canonical_seed_for_fuzzy(
            conn, unique, canonical_prod_norm, nome_sem_safra, pais, tipo, safra=None,
        )
    finally:
        release_connection(conn)

    try:
        r = process_bulk(
            [{
                "nome": item_nome,
                "produtor": item_produtor,
                "pais": pais,
                "tipo": tipo,
            }],
            dry_run=False,
            run_id=run_id,
            source="unittest_automerge_db",
        )
        assert r["blocked"] is None
        assert r["auto_merge_strict_count"] == 1, f"esperava 1 auto-merge: {r}"
        assert r["would_auto_merge_strict"] == 1
        assert r["would_enqueue_review"] == 0
        assert r["enqueue_for_review_count"] == 0
        assert r["inserted"] == 0, "nao pode criar wine novo em auto-merge"
        assert r["updated"] == 1, "canonical deveria ter sido atualizado"

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, ingestion_run_id FROM wines WHERE id = %s",
                    (canonical_id,),
                )
                row = cur.fetchone()
                assert row[0] == canonical_id
                assert row[1] == run_id, f"ingestion_run_id esperado {run_id}, got {row[1]}"

                cur.execute("SELECT COUNT(*) FROM wines WHERE nome = %s", (item_nome,))
                assert cur.fetchone()[0] == 0

                cur.execute(
                    "SELECT COUNT(*) FROM ingestion_review_queue WHERE run_id = %s",
                    (run_id,),
                )
                assert cur.fetchone()[0] == 0
        finally:
            release_connection(conn)
    finally:
        _cleanup_db_run(
            unique, run_id,
            extra_wine_names=[item_nome],
            extra_wine_ids=[canonical_id] if canonical_id else None,
        )


def test_db_blocked_run_writes_nothing_in_db():
    """Cenario 6: threshold forcado a 0; blocked nao pode escrever em
    wines, wine_sources, ingestion_review_queue nem ingestion_run_log."""
    _skip_if_no_db()
    import uuid
    from db.connection import get_connection, release_connection
    from config import Config

    unique = uuid.uuid4().hex[:10]
    pais = "br"
    tipo = "tinto"
    nome_sem_safra = f"blocked wine {unique}"
    canonical_prod_norm = f"canonical producer {unique}"
    run_id = f"unittest_blocked_{unique}"

    item_nome = nome_sem_safra.title()  # normaliza pra nome_sem_safra
    item_produtor = f"Different Producer {unique}"

    canonical_id = None
    orig_abs = Config.INGEST_QUEUE_ABS_CAP
    Config.INGEST_QUEUE_ABS_CAP = 0  # qualquer enqueue > 0 bloqueia

    conn = get_connection()
    try:
        canonical_id = _create_canonical_seed_for_fuzzy(
            conn, unique, canonical_prod_norm, nome_sem_safra, pais, tipo, safra=None,
        )
    finally:
        release_connection(conn)

    try:
        r = process_bulk(
            [{
                "nome": item_nome,
                "produtor": item_produtor,
                "pais": pais,
                "tipo": tipo,
            }],
            dry_run=False,
            run_id=run_id,
            source="unittest_blocked_db",
        )
        assert r["blocked"] == "BLOCKED_QUEUE_EXPLOSION", f"deveria bloquear: {r}"
        assert r["block_reason"] is not None
        assert r["inserted"] == 0
        assert r["updated"] == 0
        assert r["enqueue_for_review_count"] == 0, "blocked -> nao escreve queue"
        assert r["auto_merge_strict_count"] == 0

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM ingestion_review_queue WHERE run_id = %s",
                    (run_id,),
                )
                assert cur.fetchone()[0] == 0, "blocked nao pode criar review rows"
                try:
                    cur.execute(
                        "SELECT COUNT(*) FROM ingestion_run_log WHERE run_id = %s",
                        (run_id,),
                    )
                    assert cur.fetchone()[0] == 0, "blocked nao pode criar run_log"
                except Exception:
                    conn.rollback()
                cur.execute("SELECT COUNT(*) FROM wines WHERE nome = %s", (item_nome,))
                assert cur.fetchone()[0] == 0, "blocked nao pode criar wine novo"
        finally:
            release_connection(conn)
    finally:
        Config.INGEST_QUEUE_ABS_CAP = orig_abs
        _cleanup_db_run(
            unique, run_id,
            extra_wine_names=[item_nome],
            extra_wine_ids=[canonical_id] if canonical_id else None,
        )


if __name__ == "__main__":
    strict = os.environ.get("REQUIRE_DB_TESTS") == "1"
    # DQ V3 Escopo 4 (correcao processo): por default NAO rodar test_db_*.
    # Testes DB so rodam quando RUN_DB_TESTS=1 (ou REQUIRE_DB_TESTS=1 para
    # modo strict que tambem puxa DB). Sem opt-in, testes DB sao pulados
    # explicitamente no runner, nunca abrindo conexao.
    run_db_tests = strict or (os.environ.get("RUN_DB_TESTS") == "1")

    all_names = sorted(name for name in globals() if name.startswith("test_"))
    if run_db_tests:
        tests = all_names
    else:
        tests = [n for n in all_names if not n.startswith("test_db_")]

    passed = failed = skipped = 0
    db_excluded = 0 if run_db_tests else sum(
        1 for n in all_names if n.startswith("test_db_")
    )
    aborted = False
    abort_reason = ""

    if db_excluded:
        print(f"  (offline-only: {db_excluded} test_db_* pulados; "
              f"setar RUN_DB_TESTS=1 para rodar)")

    for name in tests:
        try:
            globals()[name]()
            print(f"  PASS {name}")
            passed += 1
        except _Skip as e:
            print(f"  SKIP {name}: {e}")
            skipped += 1
        except DBUnavailable as e:
            # Modo strict: DB obrigatorio, aborta imediatamente.
            print(f"  ABORT {name}: REQUIRE_DB_TESTS=1 mas DB indisponivel ({e})")
            aborted = True
            abort_reason = str(e)
            break
        except AssertionError as e:
            print(f"  FAIL {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {skipped} skipped, {failed} failed"
          + (f", {db_excluded} db-excluded" if db_excluded else "")
          + (" (strict mode)" if strict else ""))

    if aborted:
        print(f"\nABORTADO: modo strict exige DB ({abort_reason}).")
        sys.exit(1)
    if failed > 0:
        sys.exit(1)
    if strict and skipped > 0:
        # Em strict, nenhum skip deveria ter acontecido — garantia extra.
        print("\nABORTADO: strict nao tolera SKIP.")
        sys.exit(1)
    sys.exit(0)
