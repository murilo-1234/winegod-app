"""Testes offline do endpoint /api/ingest/review/<id> (DQ V3 Escopo 4).

Esses testes NAO tocam no banco real. Para os testes que precisam simular
DB, usamos monkey-patch de `get_connection`/`release_connection` e das
funcoes de apply.

Executa com:
    cd backend && python -m tests.test_ingest_review

Convencao de teste:
- `test_*` -- offline
- `test_db_*` -- requer DB (nenhum nesta primeira rodada -- guardar para
  proxima rodada com autorizacao de banco).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import ingest_review as _ingest_review
from routes.ingest_review import (
    _VALID_ACTIONS,
    _V3_COUNTER_COLS,
    _apply_review_decision,
)


class _Skip(Exception):
    """Sinal interno para o runner marcar como SKIPPED."""


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

def test_valid_actions_set():
    assert _VALID_ACTIONS == {"approve_merge", "approve_new", "reject"}


def test_v3_counter_cols_map():
    assert _V3_COUNTER_COLS["approve_merge"] == "approved_merge"
    assert _V3_COUNTER_COLS["approve_new"] == "approved_new"
    assert _V3_COUNTER_COLS["reject"] == "rejected_review"


# ---------------------------------------------------------------------------
# _apply_review_decision com DB mockado (fake cursor / fake connection)
# ---------------------------------------------------------------------------

class _FakeCursor:
    """Fake cursor que responde a queries previamente programadas.

    Uso:
        cur = _FakeCursor(responses=[
            ("SELECT id, run_id, ...", [(1, "run_x", "src", {"nome": "..."}, "tier", [99], "pending")]),
        ])
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self._last_result = None
        self.executed: list[tuple] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        # Pega o proximo resultado pre-programado.
        if self._responses:
            _match, rows = self._responses.pop(0)
            self._last_result = rows

    def fetchone(self):
        if self._last_result:
            return self._last_result[0]
        return None

    def fetchall(self):
        return self._last_result or []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor
        self.committed = 0
        self.rolled_back = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


def _patch_get_conn(fake_conn, calls):
    orig_get = _ingest_review.get_connection
    orig_release = _ingest_review.release_connection

    def fake_get():
        calls["get_conn"] = calls.get("get_conn", 0) + 1
        return fake_conn

    def fake_release(c):
        calls["release"] = calls.get("release", 0) + 1

    _ingest_review.get_connection = fake_get
    _ingest_review.release_connection = fake_release
    return orig_get, orig_release


def _restore_get_conn(orig_get, orig_release):
    _ingest_review.get_connection = orig_get
    _ingest_review.release_connection = orig_release


def test_queue_id_not_found_returns_404():
    calls = {}
    cursor = _FakeCursor(responses=[
        ("SELECT id, run_id", []),  # fetchone devolvera None
    ])
    fake = _FakeConn(cursor)
    orig_get, orig_release = _patch_get_conn(fake, calls)
    try:
        resp, code = _apply_review_decision(
            queue_id=999, action="reject", canonical_wine_id=None,
            reviewed_by=None, dry_run=False,
        )
    finally:
        _restore_get_conn(orig_get, orig_release)

    assert code == 404
    assert resp["error"] == "queue_id_not_found"
    assert calls.get("release", 0) == 1, "deve liberar a conexao"


def test_already_reviewed_returns_409():
    calls = {}
    cursor = _FakeCursor(responses=[
        ("SELECT id, run_id", [
            (42, "run_xyz", "src", {"nome": "x"}, "fuzzy_k3_multi_candidate",
             [101, 102], "merged"),
        ]),
    ])
    fake = _FakeConn(cursor)
    orig_get, orig_release = _patch_get_conn(fake, calls)
    try:
        resp, code = _apply_review_decision(
            queue_id=42, action="reject", canonical_wine_id=None,
            reviewed_by="murilo", dry_run=False,
        )
    finally:
        _restore_get_conn(orig_get, orig_release)

    assert code == 409
    assert resp["error"] == "already_reviewed"
    assert resp["status"] == "merged"


def test_approve_merge_without_canonical_returns_400():
    calls = {}
    cursor = _FakeCursor(responses=[
        ("SELECT id, run_id", [
            (42, "run_xyz", "src", {"nome": "x"}, "fuzzy_k3_disjoint_producer",
             [101, 102], "pending"),
        ]),
    ])
    fake = _FakeConn(cursor)
    orig_get, orig_release = _patch_get_conn(fake, calls)
    try:
        resp, code = _apply_review_decision(
            queue_id=42, action="approve_merge",
            canonical_wine_id=None, reviewed_by=None, dry_run=False,
        )
    finally:
        _restore_get_conn(orig_get, orig_release)

    assert code == 400
    assert resp["error"] == "canonical_wine_id_required"


def test_approve_merge_with_non_candidate_returns_400():
    calls = {}
    cursor = _FakeCursor(responses=[
        ("SELECT id, run_id", [
            (42, "run_xyz", "src", {"nome": "x"}, "fuzzy_k3_disjoint_producer",
             [101, 102], "pending"),
        ]),
    ])
    fake = _FakeConn(cursor)
    orig_get, orig_release = _patch_get_conn(fake, calls)
    try:
        resp, code = _apply_review_decision(
            queue_id=42, action="approve_merge",
            canonical_wine_id=999,  # nao esta em [101, 102]
            reviewed_by=None, dry_run=False,
        )
    finally:
        _restore_get_conn(orig_get, orig_release)

    assert code == 400
    assert resp["error"] == "canonical_wine_id_not_in_candidates"
    assert resp["candidates"] == [101, 102]


def test_dry_run_reject_simulates_without_writing():
    """Dry-run NUNCA pode chamar _apply_batch, _apply_sources_batch, update de status, etc."""
    apply_calls = {"apply_batch": 0, "apply_sources": 0,
                   "set_status": 0, "increment_log": 0}

    orig_apply = _ingest_review._apply_batch
    orig_apply_src = _ingest_review._apply_sources_batch
    orig_set_status = _ingest_review._set_queue_status
    orig_increment = _ingest_review._increment_run_log

    _ingest_review._apply_batch = lambda *a, **kw: (
        apply_calls.__setitem__("apply_batch", apply_calls["apply_batch"] + 1), 0, 0, {}
    )[1:]
    _ingest_review._apply_sources_batch = lambda *a, **kw: (
        apply_calls.__setitem__("apply_sources", apply_calls["apply_sources"] + 1), 0, 0
    )[1:]
    _ingest_review._set_queue_status = lambda *a, **kw: apply_calls.__setitem__(
        "set_status", apply_calls["set_status"] + 1
    )
    _ingest_review._increment_run_log = lambda *a, **kw: apply_calls.__setitem__(
        "increment_log", apply_calls["increment_log"] + 1
    )

    calls = {}
    cursor = _FakeCursor(responses=[
        ("SELECT id, run_id", [
            (42, "run_xyz", "src", {"nome": "Wine Test",
                                     "produtor": "Vinicola Test"},
             "fuzzy_k3_disjoint_producer", [101], "pending"),
        ]),
    ])
    fake = _FakeConn(cursor)
    orig_get, orig_release = _patch_get_conn(fake, calls)

    try:
        resp, code = _apply_review_decision(
            queue_id=42, action="reject", canonical_wine_id=None,
            reviewed_by="murilo", dry_run=True,
        )
    finally:
        _restore_get_conn(orig_get, orig_release)
        _ingest_review._apply_batch = orig_apply
        _ingest_review._apply_sources_batch = orig_apply_src
        _ingest_review._set_queue_status = orig_set_status
        _ingest_review._increment_run_log = orig_increment

    assert code == 200
    assert resp["dry_run"] is True
    assert resp["would_update_status"] == "rejected"
    # status original nao foi mudado
    assert resp["status"] == "pending"
    # Nada foi chamado
    assert apply_calls["apply_batch"] == 0
    assert apply_calls["apply_sources"] == 0
    assert apply_calls["set_status"] == 0
    assert apply_calls["increment_log"] == 0
    # Fake conn nao commitou
    assert fake.committed == 0


def test_dry_run_approve_merge_reports_without_writing():
    apply_calls = {"apply_batch": 0, "set_status": 0, "increment_log": 0}

    orig_apply = _ingest_review._apply_batch
    orig_set_status = _ingest_review._set_queue_status
    orig_increment = _ingest_review._increment_run_log

    _ingest_review._apply_batch = lambda *a, **kw: (
        apply_calls.__setitem__("apply_batch", apply_calls["apply_batch"] + 1), 0, 0, {}
    )[1:]
    _ingest_review._set_queue_status = lambda *a, **kw: apply_calls.__setitem__(
        "set_status", apply_calls["set_status"] + 1
    )
    _ingest_review._increment_run_log = lambda *a, **kw: apply_calls.__setitem__(
        "increment_log", apply_calls["increment_log"] + 1
    )

    calls = {}
    payload = {"nome": "Wine Merge Test",
               "produtor": "Vinicola Merge Test",
               "sources": [{"store_id": 1, "url": "https://x.com/a"}]}
    cursor = _FakeCursor(responses=[
        ("SELECT id, run_id", [
            (42, "run_xyz", "src", payload,
             "fuzzy_k3_disjoint_producer", [101], "pending"),
        ]),
    ])
    fake = _FakeConn(cursor)
    orig_get, orig_release = _patch_get_conn(fake, calls)

    try:
        resp, code = _apply_review_decision(
            queue_id=42, action="approve_merge",
            canonical_wine_id=101, reviewed_by="murilo", dry_run=True,
        )
    finally:
        _restore_get_conn(orig_get, orig_release)
        _ingest_review._apply_batch = orig_apply
        _ingest_review._set_queue_status = orig_set_status
        _ingest_review._increment_run_log = orig_increment

    assert code == 200
    assert resp["dry_run"] is True
    assert resp["would_update_wine_id"] == 101
    assert resp["would_next_status"] == "merged"
    assert resp["would_upsert_sources"] == 1
    assert apply_calls["apply_batch"] == 0
    assert apply_calls["set_status"] == 0
    assert apply_calls["increment_log"] == 0


def test_apply_reject_updates_status_and_counter():
    """Reject real: UPDATE na queue + increment no run_log. Nenhum apply de wine."""
    apply_calls = {"apply_batch": 0}
    orig_apply = _ingest_review._apply_batch
    orig_increment = _ingest_review._increment_run_log

    _ingest_review._apply_batch = lambda *a, **kw: (
        apply_calls.__setitem__("apply_batch", apply_calls["apply_batch"] + 1), 0, 0, {}
    )[1:]
    increment_args = []
    _ingest_review._increment_run_log = lambda conn, run_id, action: increment_args.append(
        (run_id, action)
    )

    calls = {}
    # Precisa 2 responses: 1 do SELECT, 1 do UPDATE queue.
    cursor = _FakeCursor(responses=[
        ("SELECT id, run_id", [
            (42, "run_xyz", "src", {"nome": "x"}, "fuzzy_k3_disjoint_producer",
             [101], "pending"),
        ]),
        ("UPDATE ingestion_review_queue", []),  # sem fetch
    ])
    fake = _FakeConn(cursor)
    orig_get, orig_release = _patch_get_conn(fake, calls)

    try:
        resp, code = _apply_review_decision(
            queue_id=42, action="reject", canonical_wine_id=None,
            reviewed_by="murilo", dry_run=False,
        )
    finally:
        _restore_get_conn(orig_get, orig_release)
        _ingest_review._apply_batch = orig_apply
        _ingest_review._increment_run_log = orig_increment

    assert code == 200
    assert resp["status"] == "rejected"
    assert apply_calls["apply_batch"] == 0, "reject nao pode chamar _apply_batch"
    assert increment_args == [("run_xyz", "reject")]
    # UPDATE foi executado -> commit feito
    assert fake.committed >= 1


def test_invalid_payload_in_queue_returns_500():
    """Se o source_payload da queue falhar na revalidacao, retorna 500 sem mutar."""
    apply_calls = {"apply_batch": 0}
    orig_apply = _ingest_review._apply_batch
    _ingest_review._apply_batch = lambda *a, **kw: (
        apply_calls.__setitem__("apply_batch", apply_calls["apply_batch"] + 1), 0, 0, {}
    )[1:]

    calls = {}
    # source_payload com nome vazio -> _validate rejeita.
    cursor = _FakeCursor(responses=[
        ("SELECT id, run_id", [
            (42, "run_xyz", "src", {"nome": ""}, "fuzzy_k3_disjoint_producer",
             [101], "pending"),
        ]),
    ])
    fake = _FakeConn(cursor)
    orig_get, orig_release = _patch_get_conn(fake, calls)

    try:
        resp, code = _apply_review_decision(
            queue_id=42, action="approve_merge", canonical_wine_id=101,
            reviewed_by=None, dry_run=False,
        )
    finally:
        _restore_get_conn(orig_get, orig_release)
        _ingest_review._apply_batch = orig_apply

    assert code == 500
    assert resp["error"] == "payload_revalidation_failed"
    assert apply_calls["apply_batch"] == 0


# ---------------------------------------------------------------------------
# DB infra (opt-in via RUN_DB_TESTS=1)
# ---------------------------------------------------------------------------

class DBUnavailable(Exception):
    """Levantada quando REQUIRE_DB_TESTS=1 mas DB nao e acessivel."""


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
    if _db_available():
        return
    if os.environ.get("REQUIRE_DB_TESTS") == "1":
        raise DBUnavailable(_db_err())
    raise _Skip(_db_err())


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


def _seed_vivino_wine(conn, unique: str, nome_norm: str, produtor_norm: str,
                      pais: str, tipo: str, safra: str | None = None) -> int:
    """Insere wine canonical (vivino_id NOT NULL) para testes do endpoint.

    nome_norm e usado como nome_normalizado_sem_safra (caller pode passar
    uma string sem ano). Retorna wine_id. Cleanup e responsabilidade do caller.
    """
    import random
    seed_vivino_id = 900_000_000 + random.randint(0, 99_999_999)
    nome_original = f"Review Canonical {nome_norm} {unique}"
    hash_dedup = f"canonical_seed_review_{unique}"
    produtor_orig = f"Produtor {unique}"
    nome_normalizado = nome_norm if not safra else f"{nome_norm} {safra}"
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
            (hash_dedup, nome_original, nome_normalizado, nome_norm,
             produtor_orig, produtor_norm, safra, pais, tipo,
             seed_vivino_id),
        )
        wid = cur.fetchone()[0]
        conn.commit()
    return wid


def _insert_review_row(conn, run_id: str, source: str, payload: dict,
                        match_tier: str, candidate_wine_ids: list[int]) -> int:
    import json
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingestion_review_queue
                (run_id, source, source_payload, match_tier,
                 candidate_wine_ids, status)
            VALUES (%s, %s, %s::jsonb, %s, %s, 'pending')
            RETURNING id
            """,
            (run_id, source, json.dumps(payload), match_tier,
             candidate_wine_ids or []),
        )
        qid = cur.fetchone()[0]
        conn.commit()
    return qid


def _cleanup_review_run(run_id: str, extra_wine_names=None,
                         extra_urls=None, extra_wine_ids=None,
                         extra_queue_ids=None, seed_hash_dedups=None):
    from db.connection import get_connection, release_connection
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for url in (extra_urls or []):
                cur.execute("DELETE FROM wine_sources WHERE url = %s", (url,))
            for qid in (extra_queue_ids or []):
                cur.execute("DELETE FROM ingestion_review_queue WHERE id = %s", (qid,))
            cur.execute("DELETE FROM ingestion_review_queue WHERE run_id = %s", (run_id,))
            try:
                cur.execute("DELETE FROM ingestion_run_log WHERE run_id = %s", (run_id,))
            except Exception:
                conn.rollback()
            for wid in (extra_wine_ids or []):
                cur.execute("DELETE FROM wines WHERE id = %s", (wid,))
            for nome in (extra_wine_names or []):
                cur.execute("DELETE FROM wines WHERE nome = %s", (nome,))
            for h in (seed_hash_dedups or []):
                cur.execute("DELETE FROM wines WHERE hash_dedup = %s", (h,))
            conn.commit()
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# DQ V3 Escopo 4 -- testes DB do endpoint
# ---------------------------------------------------------------------------

def test_db_approve_merge_endpoint_inserts_source_and_updates_status():
    """Cenario 3: approve_merge chama _apply_batch + _apply_sources_batch;
    queue row vira 'merged'; wine_sources criado apontando ao canonical;
    ingestion_run_id do wine/source = run_id ORIGINAL da queue row."""
    _skip_if_no_db()
    import uuid
    from db.connection import get_connection, release_connection
    from tools.normalize import normalizar

    unique = uuid.uuid4().hex[:10]
    run_id = f"unittest_approve_merge_{unique}"
    store_id = _pick_real_store_id()
    fake_url = f"https://review-merge.test/{unique}"

    canonical_id = None
    queue_id = None
    conn = get_connection()
    try:
        canonical_id = _seed_vivino_wine(
            conn, unique,
            nome_norm=f"review merge wine {unique}",
            produtor_norm=normalizar(f"Produtor Merge {unique}"),
            pais="it", tipo="tinto", safra=None,
        )
        payload = {
            "nome": f"Review Merge {unique}",
            "produtor": f"Produtor Merge {unique}",
            "pais": "it",
            "tipo": "tinto",
            "sources": [
                {"store_id": store_id, "url": fake_url, "preco": 75.0, "moeda": "EUR"}
            ],
        }
        queue_id = _insert_review_row(
            conn, run_id, "unittest_review_merge_db",
            payload, "fuzzy_k3_disjoint_producer", [canonical_id],
        )
    finally:
        release_connection(conn)

    try:
        resp, code = _apply_review_decision(
            queue_id=queue_id, action="approve_merge",
            canonical_wine_id=canonical_id,
            reviewed_by="murilo", dry_run=False,
        )
        assert code == 200, f"esperava 200, got {code}: {resp}"
        assert resp["status"] == "merged"
        assert resp["wine_id"] == canonical_id
        assert resp["wine_updated"] is True
        assert resp["sources_inserted"] == 1
        assert resp["run_id"] == run_id

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, reviewed_by FROM ingestion_review_queue "
                    "WHERE id = %s",
                    (queue_id,),
                )
                row = cur.fetchone()
                assert row[0] == "merged"
                assert row[1] == "murilo"

                cur.execute(
                    "SELECT wine_id, ingestion_run_id FROM wine_sources "
                    "WHERE url = %s",
                    (fake_url,),
                )
                row = cur.fetchone()
                assert row is not None, "wine_sources nao foi criado"
                assert row[0] == canonical_id
                assert row[1] == run_id, (
                    f"ingestion_run_id esperado {run_id}, got {row[1]}"
                )

                cur.execute(
                    "SELECT ingestion_run_id FROM wines WHERE id = %s",
                    (canonical_id,),
                )
                assert cur.fetchone()[0] == run_id
        finally:
            release_connection(conn)
    finally:
        _cleanup_review_run(
            run_id=run_id,
            extra_urls=[fake_url],
            extra_queue_ids=[queue_id] if queue_id else None,
            extra_wine_ids=[canonical_id] if canonical_id else None,
            seed_hash_dedups=[f"canonical_seed_review_{unique}"],
        )


def test_db_approve_new_endpoint_creates_wine():
    """Cenario 4: approve_new cria wine novo com ingestion_run_id do upload
    ORIGINAL da queue row; queue passa a 'created_new'."""
    _skip_if_no_db()
    import uuid
    from db.connection import get_connection, release_connection

    unique = uuid.uuid4().hex[:10]
    run_id = f"unittest_approve_new_{unique}"
    item_nome = f"Approve New Wine {unique}"
    item_produtor = f"Produtor New {unique}"

    queue_id = None
    conn = get_connection()
    try:
        payload = {
            "nome": item_nome,
            "produtor": item_produtor,
            "pais": "fr",
            "tipo": "tinto",
            "safra": "2020",
        }
        queue_id = _insert_review_row(
            conn, run_id, "unittest_approve_new_db",
            payload, "fuzzy_k3_disjoint_producer", [],
        )
    finally:
        release_connection(conn)

    new_wine_id = None
    try:
        resp, code = _apply_review_decision(
            queue_id=queue_id, action="approve_new",
            canonical_wine_id=None, reviewed_by="murilo", dry_run=False,
        )
        assert code == 200, f"{resp}"
        assert resp["status"] == "created_new"
        assert resp["wine_inserted"] is True
        new_wine_id = resp["wine_id"]
        assert new_wine_id is not None
        assert resp["run_id"] == run_id

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM ingestion_review_queue WHERE id = %s",
                    (queue_id,),
                )
                assert cur.fetchone()[0] == "created_new"

                cur.execute(
                    "SELECT id, ingestion_run_id FROM wines WHERE nome = %s",
                    (item_nome,),
                )
                row = cur.fetchone()
                assert row is not None, "wine novo nao foi criado"
                assert row[0] == new_wine_id
                assert row[1] == run_id, (
                    f"ingestion_run_id esperado {run_id}, got {row[1]}"
                )
        finally:
            release_connection(conn)
    finally:
        _cleanup_review_run(
            run_id=run_id,
            extra_wine_names=[item_nome],
            extra_queue_ids=[queue_id] if queue_id else None,
            extra_wine_ids=[new_wine_id] if new_wine_id else None,
        )


def test_db_reject_endpoint_updates_status_only():
    """Cenario 5: reject muda status da queue para 'rejected', sem nenhum
    INSERT/UPDATE em wines ou wine_sources."""
    _skip_if_no_db()
    import uuid
    from db.connection import get_connection, release_connection

    unique = uuid.uuid4().hex[:10]
    run_id = f"unittest_reject_{unique}"
    item_nome = f"Reject Test {unique}"

    queue_id = None
    conn = get_connection()
    try:
        payload = {
            "nome": item_nome,
            "produtor": f"Prod {unique}",
            "pais": "cl",
            "tipo": "tinto",
        }
        queue_id = _insert_review_row(
            conn, run_id, "unittest_reject_db",
            payload, "fuzzy_k3_disjoint_producer", [999_999_999],
        )
    finally:
        release_connection(conn)

    try:
        resp, code = _apply_review_decision(
            queue_id=queue_id, action="reject",
            canonical_wine_id=None, reviewed_by="murilo", dry_run=False,
        )
        assert code == 200, f"{resp}"
        assert resp["status"] == "rejected"
        assert resp["run_id"] == run_id

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, reviewed_by FROM ingestion_review_queue "
                    "WHERE id = %s",
                    (queue_id,),
                )
                row = cur.fetchone()
                assert row[0] == "rejected"
                assert row[1] == "murilo"

                cur.execute("SELECT COUNT(*) FROM wines WHERE nome = %s", (item_nome,))
                assert cur.fetchone()[0] == 0, "reject nao pode criar wine"
        finally:
            release_connection(conn)
    finally:
        _cleanup_review_run(
            run_id=run_id,
            extra_wine_names=[item_nome],
            extra_queue_ids=[queue_id] if queue_id else None,
        )


# ---------------------------------------------------------------------------
# Runner (offline-only por default; RUN_DB_TESTS=1 para incluir test_db_*)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    strict = os.environ.get("REQUIRE_DB_TESTS") == "1"
    run_db_tests = strict or (os.environ.get("RUN_DB_TESTS") == "1")

    all_names = sorted(name for name in globals() if name.startswith("test_"))
    if run_db_tests:
        tests = all_names
    else:
        tests = [n for n in all_names if not n.startswith("test_db_")]

    db_excluded = 0 if run_db_tests else sum(
        1 for n in all_names if n.startswith("test_db_")
    )
    if db_excluded:
        print(f"  (offline-only: {db_excluded} test_db_* pulados; "
              f"setar RUN_DB_TESTS=1 para rodar)")

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
    sys.exit(0 if failed == 0 else 1)
