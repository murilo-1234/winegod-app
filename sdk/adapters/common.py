"""Helpers comuns dos adapters Fase 4."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv


# Regex que pega qualquer query de escrita. Usado como defesa em profundidade
# por SafeReadOnlyClient; adapters que precisam fazer SELECT devem passar por
# este filtro antes de enviar ao banco.
_FORBIDDEN_PATTERNS = [
    re.compile(r"\bINSERT\b", re.IGNORECASE),
    re.compile(r"\bUPDATE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\b", re.IGNORECASE),
    re.compile(r"\bDROP\b", re.IGNORECASE),
    re.compile(r"\bALTER\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\bGRANT\b", re.IGNORECASE),
    re.compile(r"\bREVOKE\b", re.IGNORECASE),
    re.compile(r"\bCREATE\b", re.IGNORECASE),
    re.compile(r"\bCOPY\s+.*\s+FROM\b", re.IGNORECASE),
]
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class WriteAttemptError(RuntimeError):
    """Query contém cláusula de escrita — proibido nos adapters."""


def assert_read_only(sql: str) -> None:
    """Levanta WriteAttemptError se sql contém operação de escrita."""
    for pat in _FORBIDDEN_PATTERNS:
        if pat.search(sql or ""):
            raise WriteAttemptError(
                f"Query escrita detectada ({pat.pattern}). Adapters são read-only."
            )


class SafeReadOnlyClient:
    """Wrapper psycopg2 que bloqueia queries de escrita via assert_read_only.

    Uso:
        client = SafeReadOnlyClient(url)
        rows = client.fetchall("SELECT count(*) FROM public.wines")
    """

    def __init__(self, dsn: str, connect_timeout: int = 15):
        import psycopg2  # import tardio para permitir import do módulo sem psycopg2
        self._psycopg2 = psycopg2
        self._conn = psycopg2.connect(dsn, connect_timeout=connect_timeout)
        # readonly session
        self._conn.set_session(readonly=True, autocommit=False)

    def fetchall(self, sql: str, params: Optional[tuple] = None) -> List[tuple]:
        assert_read_only(sql)
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def fetchone(self, sql: str, params: Optional[tuple] = None) -> Optional[tuple]:
        assert_read_only(sql)
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    # Métodos de escrita NÃO implementados propositadamente.
    def execute(self, *a, **kw):
        raise WriteAttemptError("SafeReadOnlyClient.execute indisponível. Use fetchall/fetchone.")

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_envs_from_repo() -> None:
    """Carrega .env e backend/.env do repo root."""
    root = Path(__file__).resolve().parents[2]
    for p in (root / ".env", root / "backend" / ".env"):
        if p.exists():
            load_dotenv(p, override=False)


def _safe_ident(name: str) -> str:
    if not _IDENTIFIER_RE.match(name or ""):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


def _qualified_table(schema: str, table_name: str) -> str:
    return f"{_safe_ident(schema)}.{_safe_ident(table_name)}"


def table_exists(
    client: SafeReadOnlyClient,
    table_name: str,
    schema: str = "public",
) -> bool:
    row = client.fetchone(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table_name),
    )
    return bool(row)


def list_tables(
    client: SafeReadOnlyClient,
    like_pattern: str,
    schema: str = "public",
) -> List[str]:
    rows = client.fetchall(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name LIKE %s
        ORDER BY table_name
        """,
        (schema, like_pattern),
    )
    return [str(row[0]) for row in rows]


def columns_for_table(
    client: SafeReadOnlyClient,
    table_name: str,
    schema: str = "public",
) -> List[str]:
    rows = client.fetchall(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, table_name),
    )
    return [str(row[0]) for row in rows]


def first_existing_column(columns: List[str], candidates: List[str]) -> Optional[str]:
    known = set(columns)
    for candidate in candidates:
        if candidate in known:
            return candidate
    return None


def count_rows(
    client: SafeReadOnlyClient,
    table_name: str,
    schema: str = "public",
) -> int:
    sql = f"SELECT count(*) FROM {_qualified_table(schema, table_name)}"
    row = client.fetchone(sql)
    return int(row[0] or 0) if row else 0


def count_recent_rows(
    client: SafeReadOnlyClient,
    table_name: str,
    timestamp_column: str,
    hours: int,
    schema: str = "public",
) -> int:
    sql = (
        f"SELECT count(*) FROM {_qualified_table(schema, table_name)} "
        f"WHERE {_safe_ident(timestamp_column)} >= now() - interval '{int(hours)} hours'"
    )
    row = client.fetchone(sql)
    return int(row[0] or 0) if row else 0


def count_distinct(
    client: SafeReadOnlyClient,
    table_name: str,
    column_name: str,
    schema: str = "public",
) -> int:
    sql = (
        f"SELECT count(DISTINCT {_safe_ident(column_name)}) "
        f"FROM {_qualified_table(schema, table_name)}"
    )
    row = client.fetchone(sql)
    return int(row[0] or 0) if row else 0


def sum_column(
    client: SafeReadOnlyClient,
    table_name: str,
    column_name: str,
    schema: str = "public",
) -> float:
    sql = (
        f"SELECT coalesce(sum({_safe_ident(column_name)}), 0) "
        f"FROM {_qualified_table(schema, table_name)}"
    )
    row = client.fetchone(sql)
    return float(row[0] or 0) if row else 0.0


def max_column(
    client: SafeReadOnlyClient,
    table_name: str,
    column_name: str,
    schema: str = "public",
):
    sql = (
        f"SELECT max({_safe_ident(column_name)}) "
        f"FROM {_qualified_table(schema, table_name)}"
    )
    row = client.fetchone(sql)
    return row[0] if row else None


def max_column_by_candidates(
    client: SafeReadOnlyClient,
    table_name: str,
    candidates: List[str],
    schema: str = "public",
):
    columns = columns_for_table(client, table_name, schema=schema)
    column_name = first_existing_column(columns, candidates)
    if not column_name:
        return None
    return max_column(client, table_name, column_name, schema=schema)


def count_recent_rows_by_candidates(
    client: SafeReadOnlyClient,
    table_name: str,
    candidates: List[str],
    hours: int,
    schema: str = "public",
) -> int:
    columns = columns_for_table(client, table_name, schema=schema)
    column_name = first_existing_column(columns, candidates)
    if not column_name:
        return 0
    return count_recent_rows(client, table_name, column_name, hours, schema=schema)
