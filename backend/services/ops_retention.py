"""Winegod Data Ops — retencao manual (Fase 1).

Regras (D-F0-05 aprovada pelo Codex):
- Funcao preparada e testavel.
- Nao ativar cron automatico em producao no MVP.
- Rodar so via management command manual OU Render Cron apos autorizacao.
- Batches de 10k (REGRA 5 do CLAUDE.md).
- OPS_WRITE_ENABLED=false bloqueia retencao.

Uso tipico (futuro):
    from services.ops_retention import run_retention
    result = run_retention(dry_run=True)   # so conta
    result = run_retention(dry_run=False)  # apaga
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from config import Config
except ImportError:  # pragma: no cover
    from backend.config import Config  # type: ignore

try:
    from db.connection import get_connection, release_connection
except ImportError:  # pragma: no cover
    from backend.db.connection import get_connection, release_connection  # type: ignore


# Mapa: tabela -> (coluna de tempo, intervalo de retenção)
# Tabelas permanentes (scraper_runs, source_lineage, scraper_registry,
# scraper_configs) NAO aparecem aqui.
RETENTION_MAP = {
    "ops.scraper_heartbeats":      ("ts", "30 days"),
    "ops.scraper_events":          ("ts", "30 days"),
    "ops.batch_metrics":           ("ts", "30 days"),
    "ops.batch_metrics_hourly":    ("hour_bucket", "180 days"),
    "ops.ingestion_batches":       ("started_at", "365 days"),
    "ops.contract_validation_errors": ("last_seen", "90 days"),
    "ops.dq_decisions":            ("decided_at", "365 days"),
    "ops.matching_decisions":      ("decided_at", "365 days"),
    "ops.final_apply_results":     ("applied_at", "365 days"),
    "ops.scraper_alerts":          ("last_seen", "90 days"),
}


def run_retention(dry_run: bool = True) -> Dict[str, Any]:
    """Roda retencao em batches de 10k por tabela.

    Args:
        dry_run: se True, apenas conta linhas candidatas. Se False, deleta.

    Returns:
        dict com tabela -> {candidates, deleted}.

    Raises:
        RuntimeError se OPS_WRITE_ENABLED=false e dry_run=False.
    """
    if not dry_run and not Config.OPS_WRITE_ENABLED:
        raise RuntimeError(
            "ops_write_disabled: apply bloqueado. Setar OPS_WRITE_ENABLED=true "
            "ou usar dry_run=True."
        )

    batch_size = Config.OPS_RETENTION_BATCH_SIZE
    results: Dict[str, Dict[str, int]] = {}

    conn = get_connection()
    try:
        for table, (col, interval) in RETENTION_MAP.items():
            with conn.cursor() as cur:
                # Conta candidatos
                cur.execute(
                    f"SELECT count(*) FROM {table} "
                    f"WHERE {col} < now() - interval %s",
                    (interval,),
                )
                candidates = cur.fetchone()[0]

                deleted = 0
                if not dry_run and candidates > 0:
                    # DELETE em batches de 10k
                    while True:
                        cur.execute(
                            f"""
                            WITH victims AS (
                                SELECT ctid FROM {table}
                                 WHERE {col} < now() - interval %s
                                 LIMIT %s
                            )
                            DELETE FROM {table}
                             WHERE ctid IN (SELECT ctid FROM victims)
                            """,
                            (interval, batch_size),
                        )
                        n = cur.rowcount or 0
                        deleted += n
                        conn.commit()
                        if n < batch_size:
                            break

                results[table] = {
                    "candidates": int(candidates),
                    "deleted": int(deleted),
                }
        return {
            "dry_run": dry_run,
            "batch_size": batch_size,
            "ops_write_enabled": Config.OPS_WRITE_ENABLED,
            "results": results,
        }
    finally:
        release_connection(conn)
