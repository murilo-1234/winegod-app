"""Helpers de conexao read-only com `winegod_db` local.

Regras (REGRA 4 + REGRA 5 do CLAUDE.md):
- SOMENTE LEITURA. `connect_readonly()` define `SET TRANSACTION READ ONLY` e
  `statement_timeout`.
- `iter_vinhos_por_pais` pagina por pais usando `ORDER BY f.id DESC` +
  `LIMIT` em janelas de 10.000 (respeita REGRA 5).
- Identificacao de tiers via join com `lojas_scraping.metodo_recomendado`
  (mesma regra do `build_commerce_artifact.py`).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg2

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # pragma: no cover
    _load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_env() -> None:
    if _load_dotenv is None:
        return
    for p in (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"):
        if p.exists():
            _load_dotenv(p, override=False)


def winegod_dsn() -> str | None:
    _load_env()
    return (
        os.environ.get("WINEGOD_DATABASE_URL")
        or os.environ.get("WINEGOD_CODEX_DATABASE_URL")
        or os.environ.get("DATABASE_URL_LOCAL_WINEGOD")
    )


@contextmanager
def connect_readonly(dsn: str | None = None, statement_timeout_ms: int = 60000) -> Iterator[psycopg2.extensions.connection]:
    dsn = dsn or winegod_dsn()
    if not dsn:
        raise RuntimeError(
            "WINEGOD_DATABASE_URL ausente. Defina no .env ou aponte para o dump "
            "restaurado (ver docs/RUNBOOK_COMMERCE_OPERACAO_RECORRENTE.md)."
        )
    conn = psycopg2.connect(dsn, connect_timeout=15)
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout TO {int(statement_timeout_ms)}")
        yield conn
    finally:
        conn.close()


def list_country_tables(conn) -> list[str]:
    """Retorna lista de nomes `vinhos_<cc>` com 2-letter ISO (sem `_fontes`)."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
              AND table_name ~ '^vinhos_[a-z]{2}$'
            ORDER BY table_name
            """
        )
        return [r[0] for r in cur.fetchall()]


def list_lojas_by_method(
    conn,
    *,
    methods: list[str],
    pais_codigo: str | None = None,
) -> dict[str, dict]:
    """Mapeia host_normalizado -> loja (nome, url, metodo).

    Usado pelos exporters Tier1/Tier2 para isolar o tier por evidencia
    tecnica (nao chute). Mesma regra do producer legacy.
    """

    from .base import _normalize_host

    placeholders = ",".join(["%s"] * len(methods))
    sql = f"""
        SELECT nome, url, url_normalizada, metodo_recomendado, pais_codigo
        FROM public.lojas_scraping
        WHERE metodo_recomendado IN ({placeholders})
          AND url_normalizada IS NOT NULL
          AND length(url_normalizada) > 3
    """
    params: list = list(methods)
    if pais_codigo:
        sql += " AND pais_codigo = %s"
        params.append(pais_codigo.upper())
    host_to_loja: dict[str, dict] = {}
    with conn.cursor() as cur:
        cur.execute(sql, params)
        for nome, url, url_norm, metodo, pais in cur.fetchall():
            for candidate in (url_norm, url):
                host = _normalize_host(candidate)
                if host and host not in host_to_loja:
                    host_to_loja[host] = {
                        "nome": nome,
                        "url": url,
                        "metodo": metodo,
                        "pais": pais,
                    }
    return host_to_loja


FONTES_BY_FAMILY = {
    # Amazon mirror primario = feed espelho ativo (apenas `amazon_playwright`).
    "amazon_mirror": ["amazon_playwright"],
    # Amazon legacy = demais `amazon%` historicos (sem mirror ativo).
    "amazon_legacy": ["amazon", "amazon_scraper", "amazon_scrapingdog"],
}
