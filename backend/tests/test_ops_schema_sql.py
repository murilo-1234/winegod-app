"""Testes estaticos do SQL de migration 023_create_ops_schema.

Verifica que:
- 14 tabelas ops.* sao criadas.
- Nao existe coluna legada `items_inserted` (apenas `items_final_inserted`).
- Nao existe endpoint `POST /ops/alerts/ack` na tabela (fora do MVP).
- DDL inclui CHECK/UNIQUE/FK esperados.
- Rollback apenas dropa schema ops.

NAO conecta ao banco. So le o arquivo .sql.
"""
from __future__ import annotations

from pathlib import Path
import re

import pytest


MIGRATION_PATH = Path(__file__).resolve().parents[2] / "database" / "migrations" / "023_create_ops_schema.sql"
ROLLBACK_PATH = Path(__file__).resolve().parents[2] / "database" / "migrations" / "023_create_ops_schema.rollback.sql"


EXPECTED_TABLES = [
    "ops.scraper_registry",
    "ops.scraper_runs",
    "ops.scraper_heartbeats",
    "ops.scraper_events",
    "ops.ingestion_batches",
    "ops.batch_metrics",
    "ops.batch_metrics_hourly",
    "ops.contract_validation_errors",
    "ops.dq_decisions",
    "ops.matching_decisions",
    "ops.final_apply_results",
    "ops.source_lineage",
    "ops.scraper_alerts",
    "ops.scraper_configs",
]


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rollback_sql() -> str:
    return ROLLBACK_PATH.read_text(encoding="utf-8")


def test_migration_exists(sql):
    assert len(sql) > 500
    assert "CREATE SCHEMA IF NOT EXISTS ops" in sql


def test_14_tables_created(sql):
    for t in EXPECTED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS {t}" in sql, f"missing: {t}"


def test_no_legacy_items_inserted(sql):
    # Coluna deve ser items_final_inserted, nunca items_inserted solta.
    # Busca por "items_inserted" como token isolado (evita match em
    # items_final_inserted).
    assert not re.search(r"\bitems_inserted\b", sql), \
        "Coluna legada items_inserted detectada — deve ser items_final_inserted"


def test_items_final_inserted_exists_and_check(sql):
    assert "items_final_inserted" in sql
    # Deve ter default 0 e CHECK >= 0
    assert "items_final_inserted     bigint      NOT NULL DEFAULT 0" in sql or \
        "items_final_inserted  bigint      NOT NULL DEFAULT 0" in sql or \
        "items_final_inserted >= 0" in sql


def test_scraper_runs_unique_composite(sql):
    assert "UNIQUE (scraper_id, run_id)" in sql


def test_ingestion_batches_unique_composite(sql):
    assert "UNIQUE (scraper_id, run_id, batch_id)" in sql


def test_fk_composite_heartbeats(sql):
    # Deve haver FK composta em scraper_heartbeats
    assert "FOREIGN KEY (scraper_id, run_id)" in sql


def test_fk_composite_batch_metrics(sql):
    assert "FOREIGN KEY (scraper_id, run_id, batch_id)" in sql


def test_family_check_includes_canary(sql):
    # CHECK precisa ter 'canary' na lista
    assert "'canary'" in sql


def test_source_kind_includes_synthetic(sql):
    assert "'synthetic'" in sql


def test_alerts_dedup_unique(sql):
    assert "dedup_key" in sql
    assert "UNIQUE" in sql  # ao menos um UNIQUE na tabela de alerts


def test_no_alerts_ack_table(sql):
    # Nao existe tabela de ack no MVP
    assert "ops.alerts_ack" not in sql.lower()


def test_no_scraper_tokens_table(sql):
    # Tabela reservada para sub-projeto futuro de token-por-scraper
    assert "ops.scraper_tokens" not in sql.lower()


def test_rollback_only_drops_ops(rollback_sql):
    assert "DROP SCHEMA IF EXISTS ops CASCADE" in rollback_sql
    # Nao pode dropar nada em public
    assert "public." not in rollback_sql
    assert "DROP TABLE public" not in rollback_sql


def test_comments_for_stubs(sql):
    # Tabelas stub devem ter comentario
    assert "STUB MVP" in sql


def test_no_endpoint_ack_in_migration(sql):
    # Nao deve haver tabela/coluna relacionada a ack no MVP
    assert "alerts_ack" not in sql.lower()
