"""Inventario real pre-subida 1,4M vinhos local -> Render.

Le READ-ONLY winegod_db + Render e gera inventory.json + shards.csv em
reports/subida_vinhos_20260424/.

Uso:
  python scripts/data_ops_producers/inventario_subida_vinhos.py [--skip-render]

Env obrigatorias:
  WINEGOD_DATABASE_URL (ou alias WINEGOD_CODEX_DATABASE_URL / DATABASE_URL_LOCAL_WINEGOD)
  DATABASE_URL (Render; opcional se --skip-render)

REGRA 5 (Render pouca memoria): todas as leituras sao SET TRANSACTION READ ONLY +
statement_timeout = 60000 ms. Nao escreve em Render. Nao escreve em winegod_db.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import psycopg2

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # pragma: no cover
    _load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "reports" / "subida_vinhos_20260424"

SHARD_SIZE_DEFAULT = 50_000
LOCAL_SCAN_BATCH_SIZE = 1_000
LOCAL_STATEMENT_TIMEOUT_MS = 60_000
RENDER_STATEMENT_TIMEOUT_MS = 180_000

SOURCES = [
    "tier1_global",
    "tier2_global",
    "tier2_br",
    "amazon_local_legacy_backfill",
    "amazon_mirror_primary",
]

TIER1_METHODS = [
    "api_shopify", "api_woocommerce", "api_vtex",
    "sitemap_html", "sitemap_jsonld", "sitemap_woocommerce", "sitemap_vtex",
    "sitemap_nuvemshop", "sitemap_prestashop", "sitemap_parse",
]
TIER2_METHODS = ["playwright_ia", "playwright"]
AMAZON_MIRROR_FONTES = ["amazon_playwright"]
AMAZON_LEGACY_FONTES = ["amazon", "amazon_scraper", "amazon_scrapingdog"]


# ---------- env ----------


def _load_env() -> None:
    if _load_dotenv is None:
        return
    for p in (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"):
        if p.exists():
            _load_dotenv(p, override=False)


def _winegod_dsn() -> str | None:
    _load_env()
    return (
        os.environ.get("WINEGOD_DATABASE_URL")
        or os.environ.get("WINEGOD_CODEX_DATABASE_URL")
        or os.environ.get("DATABASE_URL_LOCAL_WINEGOD")
    )


def _render_dsn() -> str | None:
    _load_env()
    return os.environ.get("DATABASE_URL")


# ---------- shard planner (PURO, sem DB; testavel) ----------


def _plan_shards(
    total_rows: int,
    min_id: int | None,
    max_id: int | None,
    shard_size: int = SHARD_SIZE_DEFAULT,
) -> list[dict]:
    """Particiona faixa [min_id, max_id] em N shards contiguos sem overlap.

    Regras:
    - total_rows < shard_size e total_rows > 0 -> 1 shard com range inteiro.
    - total_rows >= shard_size -> N = ceil(total_rows/shard_size) shards com
      min/max contiguos (exclusive-next: min_{i+1} = max_i + 1).
    - total_rows <= 0 -> lista vazia.
    - min > max -> ValueError.
    - min/max None (mas total_rows > 0) -> 1 shard com min=0 e max=0 placeholder.
    """

    if total_rows <= 0:
        return []
    if min_id is None or max_id is None:
        return [{
            "shard_index": 0,
            "min_fonte_id": 0,
            "max_fonte_id": 0,
            "expected_rows": int(total_rows),
        }]
    if int(min_id) > int(max_id):
        raise ValueError(f"min_id ({min_id}) > max_id ({max_id})")

    min_id = int(min_id)
    max_id = int(max_id)
    shard_size = int(shard_size)
    if shard_size <= 0:
        raise ValueError("shard_size deve ser > 0")

    if total_rows < shard_size:
        return [{
            "shard_index": 0,
            "min_fonte_id": min_id,
            "max_fonte_id": max_id,
            "expected_rows": int(total_rows),
        }]

    n = math.ceil(total_rows / shard_size)
    span = max_id - min_id + 1
    # largura por shard em id-space (aprox uniforme); ultimo fecha no max real
    width = max(1, math.ceil(span / n))
    shards: list[dict] = []
    cur = min_id
    per_shard = math.ceil(total_rows / n)
    for i in range(n):
        lo = cur
        hi = min(max_id, cur + width - 1)
        if i == n - 1:
            hi = max_id
        if lo > max_id:
            break
        shards.append({
            "shard_index": i,
            "min_fonte_id": lo,
            "max_fonte_id": hi,
            "expected_rows": per_shard if i < n - 1 else max(1, total_rows - per_shard * (n - 1)),
        })
        cur = hi + 1
    return shards


# ---------- queries ----------


class _connect_ro:
    """Context manager read-only com statement_timeout configuravel."""

    def __init__(self, dsn: str, statement_timeout_ms: int = LOCAL_STATEMENT_TIMEOUT_MS):
        self.dsn = dsn
        self.statement_timeout_ms = int(statement_timeout_ms)
        self.conn = None

    def __enter__(self):
        self.conn = psycopg2.connect(self.dsn, connect_timeout=15)
        self.conn.set_session(readonly=True, autocommit=True)
        with self.conn.cursor() as cur:
            cur.execute(f"SET statement_timeout TO {self.statement_timeout_ms}")
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass


def _scalar(conn, sql: str, params: tuple = ()) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    if not row or row[0] is None:
        return 0
    return int(row[0])


def _one(conn, sql: str, params: tuple = ()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _rows(conn, sql: str, params: tuple = ()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _list_country_tables(conn) -> list[str]:
    return [
        r[0]
        for r in _rows(
            conn,
            """
            SELECT table_name
              FROM information_schema.tables
             WHERE table_schema='public'
               AND table_name ~ '^vinhos_[a-z]{2}$'
             ORDER BY table_name
            """,
        )
    ]


def _table_exists(conn, name: str) -> bool:
    r = _one(conn, "SELECT to_regclass(%s)", (f"public.{name}",))
    return bool(r and r[0])


def _table_columns(conn, name: str) -> set[str]:
    rows = _rows(
        conn,
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema='public'
           AND table_name=%s
        """,
        (name,),
    )
    return {str(r[0]) for r in rows}


def _normalize_host(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlparse(value if "://" in value else "https://" + value)
    except Exception:
        return None
    host = (parsed.hostname or "").lower().strip()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host


def _host_eligible(source_host: str | None, eligible_hosts: set[str]) -> bool:
    if not source_host or not eligible_hosts:
        return False
    if source_host in eligible_hosts:
        return True
    return any(source_host.endswith("." + host) for host in eligible_hosts)


def _gate(status: str, reason: str | None = None, **extra) -> dict:
    payload = {"status": status}
    if reason:
        payload["reason"] = reason
    payload.update(extra)
    return payload


def _load_loja_hosts_by_country(conn, methods: list[str]) -> dict[str, set[str]]:
    if not methods:
        return {}
    placeholders = ",".join(["%s"] * len(methods))
    rows = _rows(
        conn,
        f"""
        SELECT COALESCE(pais_codigo, '(null)') AS pais, url, url_normalizada
          FROM public.lojas_scraping
         WHERE metodo_recomendado IN ({placeholders})
           AND (url_normalizada IS NOT NULL OR url IS NOT NULL)
        """,
        tuple(methods),
    )
    out: dict[str, set[str]] = {}
    for pais, url, url_norm in rows:
        cc = str(pais or "(null)").lower()
        hosts = out.setdefault(cc, set())
        for candidate in (url_norm, url):
            host = _normalize_host(candidate)
            if host:
                hosts.add(host)
    return out


def _empty_source_scan(fontes_tbl: str) -> dict:
    return {
        "source_table": fontes_tbl,
        "count": 0,
        "min_fonte_id": None,
        "max_fonte_id": None,
    }


def _update_scan_stat(stat: dict, fonte_id: int) -> None:
    stat["count"] += 1
    if stat["min_fonte_id"] is None or int(fonte_id) < int(stat["min_fonte_id"]):
        stat["min_fonte_id"] = int(fonte_id)
    if stat["max_fonte_id"] is None or int(fonte_id) > int(stat["max_fonte_id"]):
        stat["max_fonte_id"] = int(fonte_id)


def _scan_fontes_table(
    conn,
    *,
    country_code: str,
    fontes_tbl: str,
    tier1_hosts: set[str],
    tier2_hosts: set[str],
    batch_size: int = LOCAL_SCAN_BATCH_SIZE,
) -> tuple[dict[str, dict], set[str]]:
    stats = {
        "tier1_global": _empty_source_scan(fontes_tbl),
        "tier2_global": _empty_source_scan(fontes_tbl),
        "tier2_br": _empty_source_scan(fontes_tbl),
        "amazon_local_legacy_backfill": _empty_source_scan(fontes_tbl),
        "amazon_mirror_primary": _empty_source_scan(fontes_tbl),
    }
    distinct_hosts: set[str] = set()
    last_id = 0
    columns = _table_columns(conn, fontes_tbl)
    host_expr = "host_normalizado" if "host_normalizado" in columns else "NULL::text AS host_normalizado"
    url_expr = "url_original" if "url_original" in columns else "NULL::text AS url_original"
    fonte_expr = "fonte" if "fonte" in columns else "NULL::text AS fonte"

    while True:
        rows = _rows(
            conn,
            f"""
            SELECT id, {host_expr}, {url_expr}, {fonte_expr}
              FROM public.{fontes_tbl}
             WHERE id > %s
             ORDER BY id ASC
             LIMIT %s
            """,
            (last_id, batch_size),
        )
        if not rows:
            break
        for fonte_id, host_normalizado, url_original, fonte in rows:
            last_id = int(fonte_id)
            host = _normalize_host(host_normalizado) or _normalize_host(url_original)
            if host:
                distinct_hosts.add(host)
            if _host_eligible(host, tier1_hosts):
                _update_scan_stat(stats["tier1_global"], fonte_id)
            if _host_eligible(host, tier2_hosts):
                _update_scan_stat(stats["tier2_global"], fonte_id)
                if country_code == "br":
                    _update_scan_stat(stats["tier2_br"], fonte_id)
            if fonte in AMAZON_LEGACY_FONTES:
                _update_scan_stat(stats["amazon_local_legacy_backfill"], fonte_id)
            if fonte in AMAZON_MIRROR_FONTES:
                _update_scan_stat(stats["amazon_mirror_primary"], fonte_id)
        if len(rows) < batch_size:
            break

    return stats, distinct_hosts


# ---------- local inventory ----------


def _collect_local(conn) -> dict:
    out: dict = {}

    out["lojas_scraping_total"] = _scalar(conn, "SELECT COUNT(*) FROM public.lojas_scraping")

    by_metodo_rows = _rows(
        conn,
        """
        SELECT COALESCE(metodo_recomendado,'(null)') AS metodo, COUNT(*)
          FROM public.lojas_scraping
         GROUP BY 1
         ORDER BY 2 DESC
        """,
    )
    out["lojas_by_metodo"] = {str(r[0]): int(r[1]) for r in by_metodo_rows}

    by_pais_metodo = _rows(
        conn,
        """
        SELECT COALESCE(pais_codigo,'(null)') AS pais,
               COALESCE(metodo_recomendado,'(null)') AS metodo,
               COUNT(*) AS c
          FROM public.lojas_scraping
         GROUP BY 1,2
         ORDER BY c DESC
         LIMIT 200
        """,
    )
    out["lojas_by_pais_metodo"] = [
        {"pais": str(r[0]).lower(), "metodo": str(r[1]), "count": int(r[2])}
        for r in by_pais_metodo
    ]

    out["wines_clean_total"] = (
        _scalar(conn, "SELECT COUNT(*) FROM public.wines_clean")
        if _table_exists(conn, "wines_clean")
        else 0
    )

    country_tables = _list_country_tables(conn)
    vinhos_tables: list[dict] = []
    for t in country_tables:
        n_vinhos = _scalar(conn, f"SELECT COUNT(*) FROM public.{t}")
        fontes_tbl = f"{t}_fontes"
        n_fontes = (
            _scalar(conn, f"SELECT COUNT(*) FROM public.{fontes_tbl}")
            if _table_exists(conn, fontes_tbl)
            else 0
        )
        vinhos_tables.append({"tabela": t, "count": n_vinhos, "fontes_count": n_fontes})
    out["vinhos_tables"] = vinhos_tables

    # top 5 paises por total de fontes
    top5 = sorted(vinhos_tables, key=lambda d: d["fontes_count"], reverse=True)[:5]
    fontes_by_fonte: dict[str, list] = {}
    for item in top5:
        cc = item["tabela"].replace("vinhos_", "")
        fontes_tbl = f"vinhos_{cc}_fontes"
        if not _table_exists(conn, fontes_tbl):
            fontes_by_fonte[cc] = []
            continue
        rows = _rows(
            conn,
            f"""
            SELECT COALESCE(fonte,'(null)') AS fonte, COUNT(*) AS c
              FROM public.{fontes_tbl}
             GROUP BY 1
             ORDER BY c DESC
             LIMIT 10
            """,
        )
        fontes_by_fonte[cc] = [{"fonte": str(r[0]), "count": int(r[1])} for r in rows]
    out["fontes_by_fonte_top5_paises"] = fontes_by_fonte

    # Abordagem rapida (plano 3 fases): SQL aggregates em vez de row-scan Python.
    # Razao: _scan_fontes_table lia TODOS os registros um-a-um (batch=1000) para
    # fazer host-matching em Python — inviavel em tabelas de milhoes de rows (>5 min).
    # O exporter ja faz o filtro de elegibilidade na hora do apply. Para o inventario,
    # precisamos apenas de COUNT/MIN/MAX por tabela pra planejar shards.
    #
    # Metodo:
    # - Tier1/Tier2: COUNT/MIN/MAX de vinhos_{cc}_fontes com lojas Tier1/2 existentes.
    #   Para tier1_global/tier2_global: usa tabelas onde lojas elegíveis existem
    #   (via rapido check em lojas_scraping por pais_codigo).
    #   tier2_br: apenas vinhos_br_fontes.
    # - Amazon: COUNT/MIN/MAX filtrado por fonte IN (...).
    # - local_hosts_distinct: count distinto de url_normalizada das lojas Tier1+Tier2.
    #
    # NOTA: counts sao UPPER BOUND (inclui linhas nao-elegiveis por host).
    # O exporter filtra eligibilidade ao rodar; shards cobrem o range completo.

    source_scan_stats: dict[str, list[dict]] = {source: [] for source in SOURCES}

    # lojas countries for tier1/tier2 (fast query on lojas_scraping)
    t1_ph = ",".join(["%s"] * len(TIER1_METHODS))
    t2_ph = ",".join(["%s"] * len(TIER2_METHODS))
    t1_countries_rows = _rows(conn,
        f"SELECT DISTINCT LOWER(pais_codigo) FROM public.lojas_scraping "
        f"WHERE metodo_recomendado IN ({t1_ph}) AND pais_codigo IS NOT NULL",
        tuple(TIER1_METHODS))
    t1_countries = {str(r[0]) for r in t1_countries_rows}
    t2_countries_rows = _rows(conn,
        f"SELECT DISTINCT LOWER(pais_codigo) FROM public.lojas_scraping "
        f"WHERE metodo_recomendado IN ({t2_ph}) AND pais_codigo IS NOT NULL",
        tuple(TIER2_METHODS))
    t2_countries = {str(r[0]) for r in t2_countries_rows}

    distinct_urls: set[str] = set()
    url_norm_rows = _rows(conn,
        f"SELECT url_normalizada FROM public.lojas_scraping "
        f"WHERE metodo_recomendado IN ({t1_ph}) AND url_normalizada IS NOT NULL",
        tuple(TIER1_METHODS))
    for (u,) in url_norm_rows:
        if u: distinct_urls.add(str(u))
    url_norm_rows2 = _rows(conn,
        f"SELECT url_normalizada FROM public.lojas_scraping "
        f"WHERE metodo_recomendado IN ({t2_ph}) AND url_normalizada IS NOT NULL",
        tuple(TIER2_METHODS))
    for (u,) in url_norm_rows2:
        if u: distinct_urls.add(str(u))
    out["local_hosts_distinct"] = len(distinct_urls)

    amazon_legacy_ph = ",".join(["%s"] * len(AMAZON_LEGACY_FONTES))
    amazon_mirror_ph = ",".join(["%s"] * len(AMAZON_MIRROR_FONTES))

    for item in vinhos_tables:
        cc = item["tabela"].replace("vinhos_", "")
        fontes_tbl = f"vinhos_{cc}_fontes"
        if not _table_exists(conn, fontes_tbl):
            continue
        cols = _table_columns(conn, fontes_tbl)
        if "url_original" not in cols:
            continue

        # Fast aggregate: COUNT/MIN/MAX for each source category
        base_sql = f"SELECT COUNT(*), MIN(id), MAX(id) FROM public.{fontes_tbl} WHERE url_original IS NOT NULL"

        def _agg(extra_where: str = "", params: tuple = ()) -> tuple[int, int | None, int | None]:
            sql = base_sql + (" AND " + extra_where if extra_where else "")
            row = _one(conn, sql, params)
            if not row or not row[0]:
                return 0, None, None
            return int(row[0] or 0), (int(row[1]) if row[1] is not None else None), (int(row[2]) if row[2] is not None else None)

        # Tier1 global: tables where tier1 lojas exist for this country
        if cc in t1_countries:
            cnt, lo, hi = _agg()
            if cnt > 0:
                source_scan_stats["tier1_global"].append({
                    "country": cc, "source_table": fontes_tbl,
                    "count": cnt, "min_fonte_id": lo, "max_fonte_id": hi,
                })

        # Tier2 global (excl. br)
        if cc != "br" and cc in t2_countries:
            cnt, lo, hi = _agg()
            if cnt > 0:
                source_scan_stats["tier2_global"].append({
                    "country": cc, "source_table": fontes_tbl,
                    "count": cnt, "min_fonte_id": lo, "max_fonte_id": hi,
                })

        # Tier2 br
        if cc == "br" and "br" in t2_countries:
            cnt, lo, hi = _agg()
            if cnt > 0:
                source_scan_stats["tier2_br"].append({
                    "country": cc, "source_table": fontes_tbl,
                    "count": cnt, "min_fonte_id": lo, "max_fonte_id": hi,
                })

        # Amazon legacy
        if "fonte" in cols:
            cnt, lo, hi = _agg(f"fonte IN ({amazon_legacy_ph})", tuple(AMAZON_LEGACY_FONTES))
            if cnt > 0:
                source_scan_stats["amazon_local_legacy_backfill"].append({
                    "country": cc, "source_table": fontes_tbl,
                    "count": cnt, "min_fonte_id": lo, "max_fonte_id": hi,
                })
            cnt, lo, hi = _agg(f"fonte IN ({amazon_mirror_ph})", tuple(AMAZON_MIRROR_FONTES))
            if cnt > 0:
                source_scan_stats["amazon_mirror_primary"].append({
                    "country": cc, "source_table": fontes_tbl,
                    "count": cnt, "min_fonte_id": lo, "max_fonte_id": hi,
                })

    out["tier1_eligible_count_estimate"] = sum(
        int(s["count"]) for s in source_scan_stats["tier1_global"]
    )
    out["tier2_global_eligible_count_estimate"] = sum(
        int(s["count"]) for s in source_scan_stats["tier2_global"]
    )
    out["tier2_br_eligible_count_estimate"] = sum(
        int(s["count"]) for s in source_scan_stats["tier2_br"]
    )
    out["amazon_legacy_count"] = sum(
        int(s["count"]) for s in source_scan_stats["amazon_local_legacy_backfill"]
    )
    out["amazon_mirror_count"] = sum(
        int(s["count"]) for s in source_scan_stats["amazon_mirror_primary"]
    )
    out["source_scan_stats"] = source_scan_stats
    out["nota_eligible_counts"] = (
        "upper_bound: counts incluem todas rows com url_original IS NOT NULL "
        "no range da fonte; o exporter filtra elegibilidade por host-match na hora do apply"
    )

    return out


# ---------- render inventory ----------


def _collect_render(conn) -> dict:
    out: dict = {}

    def _count_or_estimate(table_name: str) -> tuple[int | None, str]:
        if not _table_exists(conn, table_name):
            return 0, "missing_table"
        try:
            return _scalar(conn, f"SELECT COUNT(*) FROM public.{table_name}"), "exact"
        except Exception:
            row = _one(
                conn,
                """
                SELECT GREATEST(0, COALESCE(reltuples, 0))::bigint
                  FROM pg_class
                 WHERE oid = %s::regclass
                """,
                (f"public.{table_name}",),
            )
            if row:
                return int(row[0] or 0), "estimated_pg_class"
            return None, "unavailable"

    out["wines_total"], out["wines_total_mode"] = _count_or_estimate("wines")
    out["wine_sources_total"], out["wine_sources_total_mode"] = _count_or_estimate("wine_sources")
    out["stores_total"] = _scalar(conn, "SELECT COUNT(*) FROM public.stores") if _table_exists(conn, "stores") else 0

    if _table_exists(conn, "ingestion_review_queue"):
        out["ingestion_review_queue_pending"] = _scalar(
            conn,
            "SELECT COUNT(*) FROM public.ingestion_review_queue WHERE status='pending'",
        )
    else:
        out["ingestion_review_queue_pending"] = 0

    if _table_exists(conn, "score_recalc_queue"):
        # schema real: nao tem coluna 'status'; pendente = processed_at IS NULL
        out["score_recalc_queue_pending"] = _scalar(
            conn,
            "SELECT COUNT(*) FROM public.score_recalc_queue WHERE processed_at IS NULL",
        )
    else:
        out["score_recalc_queue_pending"] = 0

    try:
        r = _one(conn, "SELECT pg_size_pretty(pg_database_size(current_database()))")
        out["db_size_pretty"] = str(r[0]) if r else ""
    except Exception:
        out["db_size_pretty"] = ""

    for t in ("wines", "wine_sources", "wine_scores"):
        key = f"{t}_size_pretty"
        if _table_exists(conn, t):
            try:
                r = _one(conn, f"SELECT pg_size_pretty(pg_total_relation_size('public.{t}'))")
                out[key] = str(r[0]) if r else ""
            except Exception:
                out[key] = ""
        else:
            out[key] = ""

    # wcf_pipeline_control snapshot
    if _table_exists(conn, "wcf_pipeline_control"):
        try:
            rows = _rows(conn, "SELECT key, value FROM public.wcf_pipeline_control LIMIT 200")
            out["wcf_pipeline_control"] = {str(k): str(v) for k, v in rows}
        except Exception:
            out["wcf_pipeline_control"] = {}
    else:
        out["wcf_pipeline_control"] = {}

    if _table_exists(conn, "wcf_upload_batches"):
        try:
            out["wcf_upload_batches_pending"] = _scalar(
                conn,
                "SELECT COUNT(*) FROM public.wcf_upload_batches WHERE status='pending'",
            )
        except Exception:
            out["wcf_upload_batches_pending"] = 0
    else:
        out["wcf_upload_batches_pending"] = 0

    return out


# ---------- shards ----------


def _shards_for_source(
    local_inv: dict,
    source: str,
    shard_size: int = SHARD_SIZE_DEFAULT,
) -> list[dict]:
    """Converte stats precomputadas do inventario em linhas de shards.csv."""

    out: list[dict] = []

    def _emit(cc: str, total: int, lo: int | None, hi: int | None, source_table: str):
        shards = _plan_shards(total, lo, hi, shard_size=shard_size)
        for s in shards:
            out.append({
                "campaign": "subida_vinhos_20260424",
                "phase": "phase1_local_to_render",
                "source": source,
                "shard_id": f"{source}__{cc}__{s['shard_index']:04d}",
                "country": cc,
                "source_table": source_table,
                "min_fonte_id": s["min_fonte_id"],
                "max_fonte_id": s["max_fonte_id"],
                "expected_rows": s["expected_rows"],
                "status": "PLANNED",
                "artifact_path": "",
                "artifact_sha256": "",
                "apply_run_id": "",
            })

    for stat in local_inv.get("source_scan_stats", {}).get(source, []):
        total = int(stat["count"] or 0)
        if total <= 0:
            continue
        _emit(
            stat["country"],
            total,
            stat.get("min_fonte_id"),
            stat.get("max_fonte_id"),
            stat["source_table"],
        )

    return out


# ---------- gates ----------


def _compute_gates(local_inv: dict, render_inv: dict) -> dict:
    db_size = render_inv.get("db_size_pretty", "") or ""
    db_below_12gb = None
    try:
        parts = db_size.replace(",", ".").split()
        if len(parts) == 2:
            val = float(parts[0])
            unit = parts[1].upper()
            gb = val
            if unit.startswith("MB"):
                gb = val / 1024
            elif unit.startswith("KB"):
                gb = val / (1024 * 1024)
            elif unit.startswith("TB"):
                gb = val * 1024
            db_below_12gb = gb < 12.0
    except Exception:
        db_below_12gb = None

    queue_pending = render_inv.get("ingestion_review_queue_pending")
    queue_below_100k = None if queue_pending in (None, "") else int(queue_pending) < 100_000

    stores_local = local_inv.get("lojas_scraping_total")
    stores_render = render_inv.get("stores_total")
    if stores_local in (None, "") or stores_render in (None, ""):
        ratio = None
        stores_diff_ok = None
    else:
        stores_local = int(stores_local or 0)
        stores_render = int(stores_render or 0)
        if stores_render > 0:
            ratio = abs(stores_local - stores_render) / stores_render
            stores_diff_ok = ratio < 0.20
        else:
            ratio = None
            stores_diff_ok = None

    return {
        "db_size_below_12gb": (
            _gate("PASS")
            if db_below_12gb is True
            else _gate("FAIL", db_size_pretty=db_size)
            if db_below_12gb is False
            else _gate("NAO_AVALIADO", reason="db_size_pretty_ausente_ou_invalido")
        ),
        "queue_below_100k": (
            _gate("PASS")
            if queue_below_100k is True
            else _gate("FAIL", queue_pending=queue_pending)
            if queue_below_100k is False
            else _gate("NAO_AVALIADO", reason="queue_pending_ausente")
        ),
        "stores_diff_below_20pct": (
            _gate("PASS", ratio=ratio)
            if stores_diff_ok is True
            else _gate("FAIL", ratio=ratio)
            if stores_diff_ok is False
            else _gate("NAO_AVALIADO", reason="stores_total_render_ausente_ou_zero")
        ),
    }


# ---------- IO ----------


def _write_csv(path: Path, rows: list[dict]) -> None:
    header = [
        "campaign",
        "phase",
        "source",
        "shard_id",
        "country",
        "source_table",
        "min_fonte_id",
        "max_fonte_id",
        "expected_rows",
        "status",
        "artifact_path",
        "artifact_sha256",
        "apply_run_id",
    ]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})


def _write_summary_txt(path: Path, inv: dict) -> None:
    lines: list[str] = []
    lines.append("# Inventario subida 2026-04-24")
    lines.append(f"generated_at: {inv['generated_at']}")
    loc = inv.get("winegod_local", {})
    ren = inv.get("render", {})
    lines.append("")
    lines.append("## Local (winegod_db)")
    lines.append(f"lojas_scraping_total = {loc.get('lojas_scraping_total')}")
    lines.append(f"wines_clean_total    = {loc.get('wines_clean_total')}")
    lines.append(f"tier1_eligible       = {loc.get('tier1_eligible_count_estimate')}")
    lines.append(f"tier2_global_elig    = {loc.get('tier2_global_eligible_count_estimate')}")
    lines.append(f"tier2_br_eligible    = {loc.get('tier2_br_eligible_count_estimate')}")
    lines.append(f"amazon_legacy        = {loc.get('amazon_legacy_count')}")
    lines.append(f"amazon_mirror        = {loc.get('amazon_mirror_count')}")
    lines.append(f"local_hosts_distinct = {loc.get('local_hosts_distinct')}")
    lines.append(f"vinhos_tables        = {len(loc.get('vinhos_tables') or [])}")
    lines.append("")
    lines.append("## Render")
    lines.append(f"wines_total          = {ren.get('wines_total')}")
    lines.append(f"wine_sources_total   = {ren.get('wine_sources_total')}")
    lines.append(f"stores_total         = {ren.get('stores_total')}")
    lines.append(f"db_size_pretty       = {ren.get('db_size_pretty')}")
    lines.append(f"queue_pending        = {ren.get('ingestion_review_queue_pending')}")
    lines.append("")
    lines.append("## Gates")
    for k, v in (inv.get("gates") or {}).items():
        status = v.get("status", "DESCONHECIDO") if isinstance(v, dict) else str(v)
        reason = v.get("reason") if isinstance(v, dict) else None
        suffix = f" ({reason})" if reason else ""
        lines.append(f"- {k}: {status}{suffix}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------- main ----------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventario pre-subida 2026-04-24")
    parser.add_argument("--skip-render", action="store_true", help="Nao conectar no Render")
    parser.add_argument("--shard-size", type=int, default=SHARD_SIZE_DEFAULT)
    args = parser.parse_args(argv)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    local_dsn = _winegod_dsn()
    if not local_dsn:
        print("ERRO: WINEGOD_DATABASE_URL ausente.", file=sys.stderr)
        return 2

    inventory: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "winegod_local": {},
        "render": {},
        "diff": {},
        "gates": {},
    }

    print("[inventario] conectando local (read-only)...")
    with _connect_ro(local_dsn, statement_timeout_ms=LOCAL_STATEMENT_TIMEOUT_MS) as conn_local:
        local_inv = _collect_local(conn_local)
        inventory["winegod_local"] = local_inv

        all_shards: list[dict] = []
        for src in SOURCES:
            print(f"[inventario] calculando shards source={src}...")
            all_shards.extend(_shards_for_source(local_inv, src, shard_size=args.shard_size))

        shards_path = REPORT_DIR / "shards.csv"
        _write_csv(shards_path, all_shards)
        print(f"[inventario] shards.csv -> {shards_path} ({len(all_shards)} linhas)")

    render_inv: dict = {}
    if not args.skip_render:
        r_dsn = _render_dsn()
        if not r_dsn:
            print("AVISO: DATABASE_URL (Render) ausente; pulando parte Render.", file=sys.stderr)
        else:
            print("[inventario] conectando Render (read-only)...")
            with _connect_ro(r_dsn, statement_timeout_ms=RENDER_STATEMENT_TIMEOUT_MS) as conn_render:
                render_inv = _collect_render(conn_render)
    inventory["render"] = render_inv

    # diff
    stores_local = local_inv.get("lojas_scraping_total")
    stores_render = render_inv.get("stores_total")
    inventory["diff"] = {
        "stores_local_vs_render_delta": (
            int(stores_local) - int(stores_render)
            if stores_local not in (None, "") and stores_render not in (None, "")
            else None
        ),
        "stores_local_vs_render_ratio": (
            (int(stores_local) - int(stores_render)) / int(stores_render)
            if stores_local not in (None, "") and stores_render not in (None, "") and int(stores_render) > 0
            else None
        ),
    }
    inventory["gates"] = _compute_gates(local_inv, render_inv)

    inv_path = REPORT_DIR / "inventory.json"
    inv_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[inventario] inventory.json -> {inv_path}")

    summary_path = REPORT_DIR / "inventory_summary.txt"
    _write_summary_txt(summary_path, inventory)
    print(f"[inventario] inventory_summary.txt -> {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
