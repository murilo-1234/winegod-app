"""Winegod Data Ops — service layer (Fase 1).

Lógica de persistência em schema `ops.*` conforme Design Freeze v2.

Regras de ouro:
- Escreve SOMENTE em `ops.*`.
- NUNCA toca `public.wines`, `wine_sources`, `wine_scores`, `stores`, etc.
- Todos os POSTs idempotentes via `idempotency_key` + UNIQUE constraints.
- `items_final_inserted` é sempre 0 (coluna reservada para futuro).
- Heartbeat em run fechado: ignora e retorna `ignored=True`.
- `POST /ops/events` grava apenas `ops.scraper_events` (não cria batch).
- `OPS_DEBUG_KEEP_SAMPLE=false` → descarta `payload_sample`.
"""
from __future__ import annotations

import json
import hashlib
from typing import Any, Dict, List, Optional, Tuple

try:
    from config import Config
except ImportError:  # pragma: no cover
    from backend.config import Config  # type: ignore

try:
    from db.connection import get_connection, release_connection
except ImportError:  # pragma: no cover
    from backend.db.connection import get_connection, release_connection  # type: ignore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_STATUS_OPEN = ("started", "running")
RUN_STATUS_CLOSED = ("success", "failed", "timeout", "aborted")


def _json_dumps(obj: Any) -> str:
    """Serializa para jsonb. Garante strings ASCII-safe."""
    return json.dumps(obj, ensure_ascii=False, default=str)


def _scrub_payload_sample(sample: Optional[str]) -> Optional[str]:
    """Descarta payload_sample se flag de debug estiver desligada."""
    if not Config.OPS_DEBUG_KEEP_SAMPLE:
        return None
    if sample is None:
        return None
    return sample[:1024]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def register_scraper(payload: Dict[str, Any]) -> Dict[str, Any]:
    """UPSERT em ops.scraper_registry.

    Retorna {accepted:true, duplicated:bool, scraper_id:str}.
    """
    sid = payload["scraper_id"]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM ops.scraper_registry WHERE scraper_id = %s",
                (sid,),
            )
            existed = cur.fetchone() is not None

            cur.execute(
                """
                INSERT INTO ops.scraper_registry (
                    scraper_id, display_name, family, source, variant, host,
                    owner, connector_type, contract_name, contract_version,
                    status, can_create_wine_sources, requires_dq_v3,
                    requires_matching, schedule_hint, freshness_sla_hours,
                    declared_fields, pii_policy, retention_policy,
                    manifest_path, manifest_hash, tags, created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s::jsonb, %s, %s,
                    %s, %s, %s::jsonb, now(), now()
                )
                ON CONFLICT (scraper_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    family = EXCLUDED.family,
                    source = EXCLUDED.source,
                    variant = EXCLUDED.variant,
                    host = EXCLUDED.host,
                    owner = EXCLUDED.owner,
                    connector_type = EXCLUDED.connector_type,
                    contract_name = EXCLUDED.contract_name,
                    contract_version = EXCLUDED.contract_version,
                    status = EXCLUDED.status,
                    can_create_wine_sources = EXCLUDED.can_create_wine_sources,
                    requires_dq_v3 = EXCLUDED.requires_dq_v3,
                    requires_matching = EXCLUDED.requires_matching,
                    schedule_hint = EXCLUDED.schedule_hint,
                    freshness_sla_hours = EXCLUDED.freshness_sla_hours,
                    declared_fields = EXCLUDED.declared_fields,
                    pii_policy = EXCLUDED.pii_policy,
                    retention_policy = EXCLUDED.retention_policy,
                    manifest_path = EXCLUDED.manifest_path,
                    manifest_hash = EXCLUDED.manifest_hash,
                    tags = EXCLUDED.tags,
                    updated_at = now()
                """,
                (
                    sid,
                    payload["display_name"],
                    payload["family"],
                    payload["source"],
                    payload.get("variant"),
                    payload["host"],
                    payload.get("owner", "murilo"),
                    payload["connector_type"],
                    payload["contract_name"],
                    payload["contract_version"],
                    payload.get("status", "registered"),
                    bool(payload.get("can_create_wine_sources", False)),
                    bool(payload.get("requires_dq_v3", False)),
                    bool(payload.get("requires_matching", False)),
                    payload.get("schedule_hint"),
                    int(payload.get("freshness_sla_hours", 24)),
                    _json_dumps(payload.get("declared_fields", [])),
                    payload.get("pii_policy", "strict"),
                    payload.get("retention_policy", "default"),
                    payload.get("manifest_path"),
                    payload.get("manifest_hash"),
                    _json_dumps(payload.get("tags", [])),
                ),
            )
        conn.commit()
        return {"accepted": True, "duplicated": existed, "scraper_id": sid}
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


def list_scrapers(
    family: Optional[str] = None,
    host: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """Lista scrapers com resumo de saúde."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            where = []
            params: List[Any] = []
            if family:
                where.append("rg.family = %s")
                params.append(family)
            if host:
                where.append("rg.host = %s")
                params.append(host)
            if status:
                where.append("rg.status = %s")
                params.append(status)
            where_sql = ("WHERE " + " AND ".join(where)) if where else ""

            cur.execute(
                f"""
                SELECT
                    rg.scraper_id, rg.display_name, rg.family, rg.host, rg.status,
                    rg.freshness_sla_hours,
                    (SELECT max(started_at) FROM ops.scraper_runs r
                       WHERE r.scraper_id = rg.scraper_id) AS last_run_started,
                    (SELECT status FROM ops.scraper_runs r
                       WHERE r.scraper_id = rg.scraper_id
                       ORDER BY started_at DESC LIMIT 1) AS last_run_status
                FROM ops.scraper_registry rg
                {where_sql}
                ORDER BY rg.family, rg.scraper_id
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()
            items = [
                {
                    "scraper_id": r[0],
                    "display_name": r[1],
                    "family": r[2],
                    "host": r[3],
                    "status": r[4],
                    "freshness_sla_hours": r[5],
                    "last_run_started": r[6].isoformat() if r[6] else None,
                    "last_run_status": r[7],
                }
                for r in rows
            ]

            cur.execute(
                f"SELECT count(*) FROM ops.scraper_registry rg {where_sql}",
                params,
            )
            total = cur.fetchone()[0]

        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def start_run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """INSERT em ops.scraper_runs com ON CONFLICT DO NOTHING.

    Idempotency key = run_id.
    """
    run_id = payload["run_id"]
    sid = payload["scraper_id"]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM ops.scraper_runs WHERE run_id = %s", (run_id,)
            )
            existed = cur.fetchone() is not None

            cur.execute(
                """
                INSERT INTO ops.scraper_runs (
                    run_id, scraper_id, status, started_at,
                    host, contract_name, contract_version, run_params
                )
                VALUES (%s, %s, 'started', %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (run_id) DO NOTHING
                """,
                (
                    run_id,
                    sid,
                    payload.get("started_at"),
                    payload["host"],
                    payload["contract_name"],
                    payload["contract_version"],
                    _json_dumps(payload.get("run_params", {})),
                ),
            )
        conn.commit()
        return {"accepted": True, "duplicated": existed, "run_id": run_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


def heartbeat(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Heartbeat com regra D-F0-07.

    - Se run_status in open: INSERT + UPDATE last_heartbeat_at.
    - Se run_status in closed: NÃO grava nada, retorna ignored:true.
    """
    run_id = payload["run_id"]
    sid = payload["scraper_id"]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, scraper_id FROM ops.scraper_runs WHERE run_id = %s",
                (run_id,),
            )
            row = cur.fetchone()
            if row is None:
                # run desconhecido — trata como 404 via retorno
                return {
                    "accepted": False,
                    "duplicated": False,
                    "ignored": True,
                    "note": "run_unknown",
                }

            run_status, canonical_sid = row[0], row[1]

            # Se scraper_id divergir, usa o canonical e registra validation error.
            # No MVP simplificamos: aceitamos o canonical sem registrar CVE aqui
            # (CVE é gravado em validação Pydantic anterior).
            if canonical_sid != sid:
                sid = canonical_sid

            if run_status in RUN_STATUS_CLOSED:
                # Regra D-F0-07: run fechado → não grava nada.
                return {
                    "accepted": True,
                    "duplicated": True,
                    "ignored": True,
                    "note": "run_closed",
                }

            # Run aberto — insere heartbeat com idempotência (run_id, ts, agent_id).
            cur.execute(
                """
                INSERT INTO ops.scraper_heartbeats (
                    run_id, scraper_id, ts, agent_id,
                    items_collected_so_far, items_per_minute,
                    mem_mb, cpu_pct, note
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, ts, agent_id) DO NOTHING
                RETURNING id
                """,
                (
                    run_id,
                    sid,
                    payload["ts"],
                    payload.get("agent_id", "default"),
                    int(payload.get("items_collected_so_far", 0)),
                    payload.get("items_per_minute"),
                    payload.get("mem_mb"),
                    payload.get("cpu_pct"),
                    (payload.get("note") or None),
                ),
            )
            inserted_row = cur.fetchone()
            duplicated = inserted_row is None

            # Atualiza last_heartbeat_at do run (sempre, mesmo se duplicate
            # não inseriu — é custo baixo e garante freshness).
            cur.execute(
                """
                UPDATE ops.scraper_runs
                   SET last_heartbeat_at = %s,
                       status = CASE WHEN status = 'started' THEN 'running' ELSE status END
                 WHERE run_id = %s
                """,
                (payload["ts"], run_id),
            )
        conn.commit()
        return {"accepted": True, "duplicated": duplicated, "ignored": False}
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


def end_run(payload: Dict[str, Any], is_fail: bool = False) -> Dict[str, Any]:
    """Fecha run com status final.

    is_fail=True → status ∈ {failed, timeout}.
    is_fail=False → status ∈ {success, aborted}.
    Se run já fechado, retorna duplicated=True sem atualizar.
    """
    run_id = payload["run_id"]
    status = payload["status"]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, started_at FROM ops.scraper_runs WHERE run_id = %s",
                (run_id,),
            )
            row = cur.fetchone()
            if row is None:
                return {"accepted": False, "duplicated": False, "note": "run_unknown"}

            current_status, started_at = row[0], row[1]
            if current_status in RUN_STATUS_CLOSED:
                return {"accepted": True, "duplicated": True, "run_id": run_id}

            if is_fail:
                cur.execute(
                    """
                    UPDATE ops.scraper_runs
                       SET status = %s,
                           ended_at = COALESCE(%s, now()),
                           duration_ms = EXTRACT(EPOCH FROM (COALESCE(%s, now()) - started_at)) * 1000,
                           error_count_fatal = GREATEST(error_count_fatal, %s),
                           error_summary = %s
                     WHERE run_id = %s
                       AND status IN ('started','running')
                    """,
                    (
                        status,
                        payload.get("ended_at"),
                        payload.get("ended_at"),
                        int(payload.get("error_count_fatal", 1)),
                        (payload.get("error_summary") or "")[:2048],
                        run_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE ops.scraper_runs
                       SET status = %s,
                           ended_at = COALESCE(%s, now()),
                           duration_ms = EXTRACT(EPOCH FROM (COALESCE(%s, now()) - started_at)) * 1000,
                           items_extracted = COALESCE(%s, items_extracted),
                           items_valid_local = COALESCE(%s, items_valid_local),
                           items_sent = COALESCE(%s, items_sent),
                           items_rejected_schema = COALESCE(%s, items_rejected_schema),
                           items_final_inserted = 0,
                           batches_total = COALESCE(%s, batches_total),
                           error_count_transient = COALESCE(%s, error_count_transient),
                           retry_count = COALESCE(%s, retry_count),
                           rate_limit_hits = COALESCE(%s, rate_limit_hits)
                     WHERE run_id = %s
                       AND status IN ('started','running')
                    """,
                    (
                        status,
                        payload.get("ended_at"),
                        payload.get("ended_at"),
                        payload.get("items_extracted"),
                        payload.get("items_valid_local"),
                        payload.get("items_sent"),
                        payload.get("items_rejected_schema"),
                        payload.get("batches_total"),
                        payload.get("error_count_transient"),
                        payload.get("retry_count"),
                        payload.get("rate_limit_hits"),
                        run_id,
                    ),
                )

        conn.commit()
        return {"accepted": True, "duplicated": False, "run_id": run_id, "status": status}
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


def list_runs(
    scraper_id: str,
    status: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Lista runs de 1 scraper."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            where = ["scraper_id = %s"]
            params: List[Any] = [scraper_id]
            if status:
                where.append("status = %s")
                params.append(status)
            if since:
                where.append("started_at >= %s")
                params.append(since)
            where_sql = "WHERE " + " AND ".join(where)

            cur.execute(
                f"""
                SELECT run_id, scraper_id, status, started_at, ended_at,
                       duration_ms, items_extracted, items_valid_local,
                       items_sent, items_final_inserted, batches_total
                FROM ops.scraper_runs
                {where_sql}
                ORDER BY started_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = cur.fetchall()
            items = [
                {
                    "run_id": str(r[0]),
                    "scraper_id": r[1],
                    "status": r[2],
                    "started_at": r[3].isoformat() if r[3] else None,
                    "ended_at": r[4].isoformat() if r[4] else None,
                    "duration_ms": r[5],
                    "items_extracted": r[6],
                    "items_valid_local": r[7],
                    "items_sent": r[8],
                    "items_final_inserted": r[9],
                    "batches_total": r[10],
                }
                for r in rows
            ]
            cur.execute(
                f"SELECT count(*) FROM ops.scraper_runs {where_sql}", params
            )
            total = cur.fetchone()[0]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def emit_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """INSERT em ops.scraper_events.

    Regra v2 do Design Freeze: `POST /ops/events` grava APENAS
    ops.scraper_events. Não cria batch.
    """
    event_id = payload["event_id"]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM ops.scraper_events WHERE event_id = %s",
                (event_id,),
            )
            existed = cur.fetchone() is not None

            cur.execute(
                """
                INSERT INTO ops.scraper_events (
                    event_id, run_id, scraper_id, ts, level, code, message,
                    payload_hash, payload_sample, payload_pointer
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    event_id,
                    payload.get("run_id"),
                    payload["scraper_id"],
                    payload["ts"],
                    payload.get("level", "info"),
                    payload["code"],
                    payload["message"],
                    payload.get("payload_hash"),
                    _scrub_payload_sample(payload.get("payload_sample")),
                    payload.get("payload_pointer"),
                ),
            )
        conn.commit()
        return {"accepted": True, "duplicated": existed, "event_id": event_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# Metrics batch
# ---------------------------------------------------------------------------

def emit_batch_metrics(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Grava ops.ingestion_batches + ops.batch_metrics (+ source_lineage se vier).

    Idempotency: batch_id.
    """
    batch_id = payload["batch_id"]
    run_id = payload["run_id"]
    sid = payload["scraper_id"]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM ops.ingestion_batches WHERE batch_id = %s",
                (batch_id,),
            )
            existed = cur.fetchone() is not None

            # ingestion_batches (idempotente)
            cur.execute(
                """
                INSERT INTO ops.ingestion_batches (
                    batch_id, run_id, scraper_id, seq,
                    started_at, items_count, items_final_inserted,
                    items_duplicate_intra, items_duplicate_cross_run,
                    items_duplicate_cross_scraper, items_rejected_schema,
                    delivery_target, delivery_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (batch_id) DO NOTHING
                """,
                (
                    batch_id,
                    run_id,
                    sid,
                    int(payload["seq"]),
                    payload.get("ts"),
                    int(payload.get("items_extracted", 0)),
                    int(payload.get("items_duplicate", 0)),  # intra (simplif.)
                    0,
                    0,
                    int(payload.get("items_rejected_schema", 0)),
                    payload.get("delivery_target", "ops"),
                    payload.get("delivery_status", "ok"),
                ),
            )

            # batch_metrics (idempotente)
            cur.execute(
                """
                INSERT INTO ops.batch_metrics (
                    batch_id, run_id, scraper_id, ts,
                    items_extracted, items_valid_local, items_sent,
                    items_accepted_ready, items_rejected_notwine,
                    items_needs_enrichment, items_uncertain,
                    items_duplicate, items_final_inserted,
                    items_errored_transport, items_per_second,
                    time_to_first_item_ms, field_coverage
                )
                VALUES (%s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, 0,
                        %s, %s,
                        %s, %s::jsonb)
                ON CONFLICT (batch_id) DO NOTHING
                """,
                (
                    batch_id,
                    run_id,
                    sid,
                    payload["ts"],
                    int(payload.get("items_extracted", 0)),
                    int(payload.get("items_valid_local", 0)),
                    int(payload.get("items_sent", 0)),
                    int(payload.get("items_accepted_ready", 0)),
                    int(payload.get("items_rejected_notwine", 0)),
                    int(payload.get("items_needs_enrichment", 0)),
                    int(payload.get("items_uncertain", 0)),
                    int(payload.get("items_duplicate", 0)),
                    int(payload.get("items_errored_transport", 0)),
                    payload.get("items_per_second"),
                    payload.get("time_to_first_item_ms"),
                    _json_dumps(payload.get("field_coverage", {})),
                ),
            )

            # source_lineage (opcional — só se payload trouxe)
            lineage = payload.get("source_lineage")
            if lineage:
                cur.execute(
                    """
                    INSERT INTO ops.source_lineage (
                        batch_id, run_id, scraper_id,
                        source_system, source_kind, source_pointer,
                        source_record_count, source_read_at, notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (batch_id) DO NOTHING
                    """,
                    (
                        batch_id,
                        run_id,
                        sid,
                        lineage["source_system"],
                        lineage["source_kind"],
                        lineage["source_pointer"],
                        lineage.get("source_record_count"),
                        lineage.get("source_read_at") or payload["ts"],
                        lineage.get("notes"),
                    ),
                )

            # Incrementa contador agregado do run
            cur.execute(
                """
                UPDATE ops.scraper_runs
                   SET batches_total = batches_total + 1,
                       items_extracted = items_extracted + %s,
                       items_valid_local = items_valid_local + %s,
                       items_sent = items_sent + %s
                 WHERE run_id = %s
                   AND status IN ('started','running')
                """,
                (
                    int(payload.get("items_extracted", 0)) if not existed else 0,
                    int(payload.get("items_valid_local", 0)) if not existed else 0,
                    int(payload.get("items_sent", 0)) if not existed else 0,
                    run_id,
                ),
            )

        conn.commit()
        return {"accepted": True, "duplicated": existed, "batch_id": batch_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def health_payload() -> Dict[str, Any]:
    """Monta payload de /ops/health."""
    db_ok = False
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM information_schema.schemata WHERE schema_name = 'ops'"
                )
                db_ok = cur.fetchone() is not None
        finally:
            release_connection(conn)
    except Exception:
        db_ok = False

    return {
        "ok": bool(db_ok),
        "db": "ok" if db_ok else "down",
        "schema": "ops",
        "version": "0.1.0",
        "flags": {
            "OPS_API_ENABLED": Config.OPS_API_ENABLED,
            "OPS_WRITE_ENABLED": Config.OPS_WRITE_ENABLED,
            "OPS_DASHBOARD_ENABLED": Config.OPS_DASHBOARD_ENABLED,
            "OPS_ALERTS_ENABLED": Config.OPS_ALERTS_ENABLED,
            "OPS_CANARY_ENABLED": Config.OPS_CANARY_ENABLED,
        },
    }
