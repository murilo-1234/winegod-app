from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
STAGING_ROOT = REPO_ROOT / "reports" / "data_ops_plugs_staging"


def ensure_backend_on_path() -> None:
    entry = str(BACKEND_ROOT)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def ensure_sdk_on_path() -> None:
    entry = str(REPO_ROOT / "sdk")
    if entry not in sys.path:
        sys.path.insert(0, entry)


def load_repo_envs() -> None:
    for path in (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"):
        if path.exists():
            load_dotenv(path, override=False)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_compact() -> str:
    return utc_now().strftime("%Y%m%d_%H%M%S")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def report_path(*parts: str) -> Path:
    path = STAGING_ROOT.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def normalize_domain(url_or_domain: str | None) -> str | None:
    if not url_or_domain:
        return None
    value = url_or_domain.strip()
    if not value:
        return None
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host


def candidate_domains(domain: str | None) -> list[str]:
    if not domain:
        return []
    parts = domain.split(".")
    candidates = [domain]
    if len(parts) >= 3:
        if parts[-2:] in (["com", "br"], ["com", "mx"], ["co", "uk"]):
            candidates.append(".".join(parts[-3:]))
        candidates.append(".".join(parts[-2:]))
    return list(dict.fromkeys([d for d in candidates if d]))


def build_store_lookup() -> dict[str, int]:
    import psycopg2

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return {}
    conn = psycopg2.connect(dsn, connect_timeout=10)
    lookup: dict[str, int] = {}
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout TO 15000")
            cur.execute("SELECT id, dominio, url FROM public.stores")
            for store_id, dominio, url in cur.fetchall():
                for value in (
                    normalize_domain(dominio),
                    normalize_domain(url),
                ):
                    for candidate in candidate_domains(value):
                        lookup.setdefault(candidate, int(store_id))
    finally:
        conn.close()
    return lookup


def resolve_store_id(url_or_domain: str | None, lookup: dict[str, int]) -> int | None:
    domain = normalize_domain(url_or_domain)
    if not domain:
        return None
    for candidate in candidate_domains(domain):
        store_id = lookup.get(candidate)
        if store_id:
            return store_id
    return None


def make_reporter(manifest_path: Path):
    ensure_sdk_on_path()
    from winegod_scraper_sdk import Reporter, TelemetryDelivery  # type: ignore

    if not os.environ.get("OPS_BASE_URL") or not os.environ.get("OPS_TOKEN"):
        return None
    return Reporter.from_manifest(manifest_path, delivery=TelemetryDelivery.from_env())


def process_bulk_local(items: list[dict[str, Any]], *, dry_run: bool, source: str, run_id: str, create_sources: bool = True) -> dict[str, Any]:
    ensure_backend_on_path()
    from services.bulk_ingest import process_bulk  # type: ignore

    return process_bulk(
        items,
        dry_run=dry_run,
        source=source,
        run_id=run_id,
        create_sources=create_sources,
    )


def process_bulk_http(items: list[dict[str, Any]], *, dry_run: bool, source: str, run_id: str, create_sources: bool = True) -> dict[str, Any]:
    base_url = (
        os.environ.get("INGEST_BASE_URL")
        or os.environ.get("OPS_BASE_URL")
        or "http://localhost:5000"
    ).rstrip("/")
    token = os.environ.get("BULK_INGEST_TOKEN", "")
    resp = requests.post(
        f"{base_url}/api/ingest/bulk",
        json={
            "items": items,
            "dry_run": dry_run,
            "source": source,
            "run_id": run_id,
            "create_sources": create_sources,
        },
        headers={"Content-Type": "application/json", "X-Ingest-Token": token},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
