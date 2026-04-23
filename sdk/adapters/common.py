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
