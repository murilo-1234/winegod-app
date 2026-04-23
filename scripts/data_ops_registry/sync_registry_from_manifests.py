#!/usr/bin/env python3
"""Sincroniza manifests do Data Ops para ops.scraper_registry.

Uso tipico:
    python scripts/data_ops_registry/sync_registry_from_manifests.py --dry-run
    python scripts/data_ops_registry/sync_registry_from_manifests.py --apply-status-migration --apply

Regras:
- Nao toca tabelas de negocio.
- Escreve apenas em ops.scraper_registry.
- Carrega .env sem imprimir segredos.
- Migration 024 e opcional, idempotente e restrita ao CHECK de status do registry.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "sdk"
BACKEND_ROOT = REPO_ROOT / "backend"
MIGRATION_024 = REPO_ROOT / "database" / "migrations" / "024_ops_scraper_registry_extended_statuses.sql"

for entry in (str(SDK_ROOT), str(BACKEND_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from services.ops_service import register_scraper  # noqa: E402
from winegod_scraper_sdk.manifest import load_manifest  # noqa: E402


def load_envs() -> None:
    for path in (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"):
        if path.exists():
            load_dotenv(path, override=False)


def discover_manifest_paths() -> list[Path]:
    paths = sorted((REPO_ROOT / "sdk" / "adapters" / "manifests").glob("*.yaml"))
    for root in (REPO_ROOT / "sdk" / "plugs").glob("*"):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("manifest*.yaml")):
            paths.append(path)
    return paths


def apply_status_migration() -> None:
    import os
    import psycopg2

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL ausente; nao foi possivel aplicar migration 024")

    sql = MIGRATION_024.read_text(encoding="utf-8")
    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync registry Data Ops a partir dos manifests")
    parser.add_argument("--apply", action="store_true", help="grava em ops.scraper_registry")
    parser.add_argument(
        "--apply-status-migration",
        action="store_true",
        help="aplica a migration 024 antes do sync",
    )
    args = parser.parse_args()

    load_envs()
    manifests = discover_manifest_paths()
    if not manifests:
        print("nenhum manifest encontrado")
        return 1

    if args.apply and args.apply_status_migration:
        apply_status_migration()
        print("migration_024=applied")

    synced = 0
    for path in manifests:
        manifest = load_manifest(path)
        payload = manifest.to_register_payload()
        if args.apply:
            result = register_scraper(payload)
            state = "updated" if result.get("duplicated") else "inserted"
        else:
            state = "would_sync"
        synced += 1
        print(
            f"{manifest.scraper_id}|{payload['status']}|{manifest.family}|"
            f"{manifest.host}|{state}|{path.relative_to(REPO_ROOT)}"
        )

    print(f"total_manifests={synced}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
