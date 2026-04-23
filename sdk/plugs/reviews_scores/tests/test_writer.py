from __future__ import annotations

from typing import Any

import pytest

from sdk.plugs.reviews_scores import writer as writer_mod
from sdk.plugs.reviews_scores.writer import (
    _prepare_wine_scores_rows,
    _prepare_wines_updates,
    apply_bundle,
    WINE_SCORES_SCORE_MAX,
    VIVINO_RATING_MAX,
)
from sdk.plugs.reviews_scores.confidence import confidence as _confidence


def _item(
    vivino_id: int | None,
    score_value: float | None,
    scale: int,
    sample: int | None = None,
    source: str = "vivino_wines_to_ratings",
) -> dict[str, Any]:
    from sdk.plugs.reviews_scores.exporters import _canonical_match_key

    item = {
        "source": source,
        "wine_identity": {
            "vivino_id": vivino_id,
            "nome": "Vinho X",
            "produtor": "Produtor Y",
            "safra": "2020",
            "pais": "fr",
            "regiao": "Bordeaux",
        },
        "score": {"value": score_value, "scale": scale},
        "review": {"sample_size": sample} if sample is not None else {},
        "reviewer_ref": None,
        "source_lineage": {"source_system": "t", "source_pointer": "p", "source_record_count": 1},
        "signal_kind": "vivino",
        "canonical_match_key": _canonical_match_key("Vinho X", "Produtor Y", "2020", "fr"),
        "source_confidence": _confidence(sample),
        "review_text_present": False,
    }
    if score_value is not None and scale == 5:
        item["score_normalized_100"] = round(score_value * 20.0, 2)
    return item


# ---------- prepare helpers ----------


def test_prepare_wine_scores_skips_unmatched_and_no_score():
    items = [
        _item(111, 4.2, 5, sample=100),
        _item(222, None, 5, sample=5),
        _item(None, 4.5, 5, sample=50),
        _item(333, 4.5, 5, sample=5),
    ]
    lookup = {111: 1001, 222: 1002}
    rows, unmatched, skipped_no_score = _prepare_wine_scores_rows(items, lookup)
    assert len(rows) == 1
    assert unmatched == 2
    assert skipped_no_score == 1
    wine_id, fonte, score, score_raw, confianca, dados_extra = rows[0]
    assert wine_id == 1001
    assert fonte == "vivino"
    assert score == 84.0
    assert confianca == 1.0


def test_prepare_wine_scores_clamps_score_to_column_max():
    items = [_item(1, 9999.99, 100, sample=200)]
    lookup = {1: 42}
    rows, _, _ = _prepare_wine_scores_rows(items, lookup)
    assert rows[0][2] == WINE_SCORES_SCORE_MAX


def test_prepare_wines_updates_only_returns_matched_items():
    items = [
        _item(111, 4.2, 5, sample=123),
        _item(222, 4.0, 5, sample=10),
        _item(None, 4.5, 5, sample=50),
    ]
    lookup = {111: 1001}
    rows = _prepare_wines_updates(items, lookup)
    assert len(rows) == 1
    rating, sample, wine_id = rows[0]
    assert rating == 4.2
    assert sample == 123
    assert wine_id == 1001


def test_prepare_wines_updates_clamps_rating_to_column_max():
    items = [_item(1, 5.0, 5, sample=200)]
    lookup = {1: 42}
    rows = _prepare_wines_updates(items, lookup)
    assert rows[0][0] <= VIVINO_RATING_MAX


def test_per_review_source_is_skipped_entirely(monkeypatch):
    called = {"connect": 0}

    def fake_connect(*_args, **_kwargs):
        called["connect"] += 1
        raise AssertionError("psycopg2.connect nao deveria ter sido chamado")

    monkeypatch.setattr(writer_mod.psycopg2, "connect", fake_connect)
    items = [_item(1, 4.5, 5, sample=50, source="vivino_reviews_to_scores_reviews")]
    result = apply_bundle(items, source="vivino_reviews_to_scores_reviews")
    assert result.skipped_per_review == 1
    assert result.wine_scores_upserted == 0
    assert called["connect"] == 0


# ---------- fake conn/cursor para testar apply_bundle e atomicidade ----------


class _FakeCursor:
    def __init__(self, store):
        self.store = store
        self._pending_rows: list[tuple] = []
        self._rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql: str, params: tuple | None = None):
        s = sql.strip().lower()
        if s.startswith("set"):
            return
        if "from public.wines where vivino_id = any" in s:
            wanted = params[0]
            self._pending_rows = [
                (vid, self.store["wines"][vid])
                for vid in wanted
                if vid in self.store["wines"]
            ]
            return
        raise AssertionError(f"unexpected SQL: {s}")

    def fetchall(self):
        rows, self._pending_rows = self._pending_rows, []
        return rows

    @property
    def rowcount(self):
        return self._rowcount


class _FakeConn:
    def __init__(self, store):
        self.store = store
        self.autocommit = False
        self.closed = False

    def cursor(self):
        store = self.store
        cur = _FakeCursor(store)

        def _execute_values_hook(rows_for_sql_type):
            # Este cursor ainda e chamado via execute_values patcheado; rowcount
            # e setado pelo patch antes do commit.
            pass

        return cur

    def commit(self):
        self.store["commits"] += 1

    def rollback(self):
        self.store["rollbacks"] += 1

    def close(self):
        self.closed = True


def _make_store(wines_lookup):
    return {
        "wines": dict(wines_lookup),
        "commits": 0,
        "rollbacks": 0,
        "execute_values_calls": [],  # list of (kind, rows)
        # Configuracao por operacao: retorna rowcount.
        "upsert_rowcount_sequence": [],
        "wines_update_rowcount_sequence": [],
        # Configuracao opcional: falhar no n-esimo UPDATE de wines (1-based).
        "fail_wines_update_at": None,
    }


def _install_fakes(monkeypatch, store):
    monkeypatch.setattr(writer_mod.psycopg2, "connect", lambda *a, **kw: _FakeConn(store))

    def fake_execute_values(cur, sql, rows):
        keyword = sql.strip().split()[0].lower()  # INSERT vs UPDATE
        store["execute_values_calls"].append((keyword, list(rows)))
        if keyword == "insert":
            cur._rowcount = store["upsert_rowcount_sequence"].pop(0) if store["upsert_rowcount_sequence"] else len(rows)
        elif keyword == "update":
            # Contador de chamadas de UPDATE por batch.
            update_call_index = sum(1 for k, _ in store["execute_values_calls"] if k == "update")
            if store.get("fail_wines_update_at") == update_call_index:
                raise RuntimeError("simulated_wines_update_failure")
            cur._rowcount = store["wines_update_rowcount_sequence"].pop(0) if store["wines_update_rowcount_sequence"] else len(rows)

    monkeypatch.setattr(writer_mod, "execute_values", fake_execute_values)


# ---------- testes dos 4 gaps auditados pelo Codex ----------


def test_apply_bundle_records_matched_and_unmatched_counts(monkeypatch):
    store = _make_store({1: 101})
    _install_fakes(monkeypatch, store)

    items = [
        _item(1, 4.1, 5, sample=120),
        _item(99, 3.9, 5, sample=30),
    ]
    result = apply_bundle(items, source="vivino_wines_to_ratings", dsn="postgres://fake")
    assert result.processed == 2
    assert result.matched == 1
    assert result.unmatched == 1
    assert result.wine_scores_upserted == 1
    assert result.batches_committed == 1
    kinds = [k for k, _ in store["execute_values_calls"]]
    assert kinds == ["insert", "update"]


def test_strong_idempotency_zero_change_on_rerun(monkeypatch):
    """Re-run identico: ON CONFLICT DO UPDATE com WHERE IS DISTINCT FROM
    mantem rowcount=0 em wine_scores; wines UPDATE ja guardava por IS DISTINCT FROM."""
    store = _make_store({1: 101})
    # Segundo run: Postgres reporta 0 mudancas.
    store["upsert_rowcount_sequence"] = [0]
    store["wines_update_rowcount_sequence"] = [0]
    _install_fakes(monkeypatch, store)

    items = [_item(1, 4.1, 5, sample=120)]
    result = apply_bundle(items, source="vivino_wines_to_ratings", dsn="postgres://fake")
    assert result.wine_scores_upserted == 1  # tentamos upsert 1 linha
    assert result.wine_scores_changed == 0   # mas nenhuma mudou
    assert result.wines_rating_updated == 0


def test_upsert_sql_has_where_is_distinct_from_guard():
    """Garantia textual: o SQL do UPSERT nao toca criado_em e tem guard completo."""
    from sdk.plugs.reviews_scores.writer import _UPSERT_WINE_SCORES_SQL

    assert "criado_em = NOW()" not in _UPSERT_WINE_SCORES_SQL
    assert "criado_em" not in _UPSERT_WINE_SCORES_SQL.split("DO UPDATE", 1)[1]
    tail = _UPSERT_WINE_SCORES_SQL.split("DO UPDATE", 1)[1].lower()
    # Guarda completa cobrindo todos os campos atualizaveis.
    for col in ("score", "score_raw", "confianca", "dados_extra"):
        assert f"wine_scores.{col} is distinct from excluded.{col}" in tail


def test_batch_atomicity_rollback_on_wines_update_failure(monkeypatch):
    """Se o UPDATE em wines falhar, o lote inteiro rola para tras: nenhum
    commit do wine_scores do mesmo lote permanece."""
    store = _make_store({1: 101, 2: 102})
    # 1a chamada UPDATE (wines) falha.
    store["fail_wines_update_at"] = 1
    _install_fakes(monkeypatch, store)

    items = [_item(1, 4.1, 5, sample=120), _item(2, 4.3, 5, sample=200)]
    with pytest.raises(RuntimeError, match="simulated_wines_update_failure"):
        apply_bundle(items, source="vivino_wines_to_ratings", dsn="postgres://fake")

    # Nenhum commit de batch; ao menos um rollback registrado.
    assert store["commits"] <= 1  # so o commit do lookup (readonly) no maximo
    assert store["rollbacks"] >= 1


def test_batch_atomicity_commit_happens_only_after_both_steps(monkeypatch):
    """Em sucesso, o commit vem DEPOIS de ambos execute_values do lote,
    provando que wine_scores e wines sobem no mesmo commit logico."""
    store = _make_store({1: 101})
    events: list[str] = []

    # Intercepta commit do FakeConn para registrar ordem relativa.
    class _TracedConn(_FakeConn):
        def commit(self):
            events.append("commit")
            super().commit()
        def rollback(self):
            events.append("rollback")
            super().rollback()

    monkeypatch.setattr(writer_mod.psycopg2, "connect", lambda *a, **kw: _TracedConn(store))

    def fake_execute_values(cur, sql, rows):
        keyword = sql.strip().split()[0].lower()
        events.append(keyword)
        cur._rowcount = len(rows)

    monkeypatch.setattr(writer_mod, "execute_values", fake_execute_values)

    items = [_item(1, 4.1, 5, sample=120)]
    apply_bundle(items, source="vivino_wines_to_ratings", dsn="postgres://fake")

    # Sequencia esperada por lote:
    #   commit (do lookup readonly)
    #   insert (wine_scores)
    #   update (wines)
    #   commit (fim do lote - atomico)
    assert events == ["commit", "insert", "update", "commit"]


def test_apply_bundle_no_dsn_returns_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    items = [_item(1, 4.1, 5, sample=120)]
    result = apply_bundle(items, source="vivino_wines_to_ratings", dsn=None)
    assert result.wine_scores_upserted == 0
    assert any("DATABASE_URL" in e for e in result.errors)
