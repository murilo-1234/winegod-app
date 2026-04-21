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
    _generate_hash_dedup,
    process_bulk,
)


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


if __name__ == "__main__":
    strict = os.environ.get("REQUIRE_DB_TESTS") == "1"
    tests = sorted(name for name in globals() if name.startswith("test_"))
    passed = failed = skipped = 0
    aborted = False
    abort_reason = ""

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
