"""Runner controlado da migration 023 no Render.

Modos:
    dry-run : aplica o SQL dentro de transacao e faz ROLLBACK.
    apply   : aplica o SQL definitivamente (usa BEGIN/COMMIT do proprio arquivo).
    count   : conta tabelas em ops.*.

Uso:
    python scripts/fase2_migration_runner.py dry-run
    python scripts/fase2_migration_runner.py apply
    python scripts/fase2_migration_runner.py count

NAO imprime nenhum valor de DATABASE_URL/token. Apenas host com tail mascarado.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
MIG = ROOT / "database" / "migrations" / "023_create_ops_schema.sql"

EXPECTED_TABLES = [
    "batch_metrics",
    "batch_metrics_hourly",
    "contract_validation_errors",
    "dq_decisions",
    "final_apply_results",
    "ingestion_batches",
    "matching_decisions",
    "scraper_alerts",
    "scraper_configs",
    "scraper_events",
    "scraper_heartbeats",
    "scraper_registry",
    "scraper_runs",
    "source_lineage",
]


def load_db_url() -> str:
    for p in [ROOT / ".env", ROOT / "backend" / ".env"]:
        if p.exists():
            load_dotenv(p)
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.stderr.write("DATABASE_URL missing\n")
        sys.exit(2)
    return url


def mask_host(url: str) -> str:
    m = re.search(r"@([^/]+)/", url)
    if not m:
        return "(unparseable)"
    host = m.group(1)
    return host[:22] + "..."


def load_ddl_without_outer_tx() -> str:
    """Le o SQL da migration e remove BEGIN/COMMIT EXTERNOS (dry-run precisa
    rodar dentro de nossa transacao externa)."""
    raw = MIG.read_text(encoding="utf-8")
    # Remove primeiro BEGIN; do inicio
    cleaned = re.sub(r"^\s*BEGIN\s*;\s*", "", raw, count=1, flags=re.IGNORECASE | re.MULTILINE)
    # Remove ultimo COMMIT; do fim
    cleaned = re.sub(r"COMMIT\s*;\s*$", "", cleaned, count=1, flags=re.IGNORECASE | re.MULTILINE)
    return cleaned


def load_ddl_raw() -> str:
    return MIG.read_text(encoding="utf-8")


def count_ops_tables(cur) -> int:
    cur.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'ops'"
    )
    return int(cur.fetchone()[0])


def list_ops_tables(cur) -> list[str]:
    cur.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'ops' ORDER BY 1"
    )
    return [r[0] for r in cur.fetchall()]


def cmd_dry_run(url: str) -> int:
    print(f"[dry-run] connecting to {mask_host(url)}")
    ddl = load_ddl_without_outer_tx()
    try:
        conn = psycopg2.connect(url, connect_timeout=15)
    except Exception as e:
        print(f"[dry-run] CONNECTION_FAILED: {type(e).__name__}: {e}")
        return 3

    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # Verifica se schema ja existe (caso de re-run)
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name='ops'"
            )
            already = cur.fetchone()
            if already:
                print("[dry-run] WARN: ops schema already exists. Aborting dry-run to not touch it.")
                conn.rollback()
                return 4

            # Executa o DDL da migration dentro da nossa tx
            print(f"[dry-run] executing {len(ddl)} chars of DDL...")
            cur.execute(ddl)
            count = count_ops_tables(cur)
            tables = list_ops_tables(cur)
            print(f"[dry-run] tables_in_ops_after_ddl={count}")
            print(f"[dry-run] tables={tables}")
            if count != 14:
                print(f"[dry-run] FAIL: expected 14 tables, got {count}")
                conn.rollback()
                return 5
            # Rollback obrigatorio
            conn.rollback()
            # Verifica pos-rollback que schema nao ficou
            with conn.cursor() as cur2:
                cur2.execute(
                    "SELECT 1 FROM information_schema.schemata WHERE schema_name='ops'"
                )
                still = cur2.fetchone()
            if still:
                print("[dry-run] FAIL: schema 'ops' still exists after rollback")
                return 6
            print("[dry-run] OK: 14 tables created and rolled back cleanly.")
            return 0
    except Exception as e:
        print(f"[dry-run] ERROR: {type(e).__name__}: {str(e)[:500]}")
        try:
            conn.rollback()
        except Exception:
            pass
        return 7
    finally:
        conn.close()


def cmd_apply(url: str) -> int:
    """Aplica migration definitiva (usa BEGIN/COMMIT do proprio arquivo)."""
    print(f"[apply] connecting to {mask_host(url)}")
    # Guard: se schema ja existe, aborta
    try:
        conn = psycopg2.connect(url, connect_timeout=15)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name='ops'"
            )
            if cur.fetchone():
                print("[apply] WARN: ops schema already exists. Aborting to avoid double-apply.")
                conn.close()
                return 4
        conn.close()
    except Exception as e:
        print(f"[apply] CONNECTION_FAILED: {type(e).__name__}: {e}")
        return 3

    ddl = load_ddl_raw()
    try:
        conn = psycopg2.connect(url, connect_timeout=30)
        conn.autocommit = True  # deixa o BEGIN/COMMIT do arquivo controlar
        try:
            with conn.cursor() as cur:
                print(f"[apply] executing migration 023 ({len(ddl)} chars)...")
                cur.execute(ddl)
            # Verifica pos-apply
            with conn.cursor() as cur:
                count = count_ops_tables(cur)
                tables = list_ops_tables(cur)
                print(f"[apply] tables_in_ops={count}")
                for t in tables:
                    print(f"[apply]   - {t}")
                if count != 14:
                    print(f"[apply] FAIL: expected 14 tables, got {count}")
                    return 5
                # Valida que todas as esperadas estao presentes
                missing = [t for t in EXPECTED_TABLES if t not in tables]
                if missing:
                    print(f"[apply] FAIL: missing tables: {missing}")
                    return 6
            print("[apply] OK: migration applied, 14 tables confirmed.")
            return 0
        finally:
            conn.close()
    except Exception as e:
        print(f"[apply] ERROR: {type(e).__name__}: {str(e)[:800]}")
        return 7


def cmd_count(url: str) -> int:
    try:
        conn = psycopg2.connect(url, connect_timeout=15)
        with conn.cursor() as cur:
            count = count_ops_tables(cur)
            tables = list_ops_tables(cur)
        conn.close()
        print(f"count={count}")
        for t in tables:
            print(f"  - {t}")
        return 0
    except Exception as e:
        print(f"CONNECTION_FAILED: {type(e).__name__}: {e}")
        return 3


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("dry-run", "apply", "count"):
        print("usage: fase2_migration_runner.py {dry-run|apply|count}")
        return 1
    cmd = sys.argv[1]
    url = load_db_url()
    if cmd == "dry-run":
        return cmd_dry_run(url)
    if cmd == "apply":
        return cmd_apply(url)
    if cmd == "count":
        return cmd_count(url)
    return 1


if __name__ == "__main__":
    sys.exit(main())
