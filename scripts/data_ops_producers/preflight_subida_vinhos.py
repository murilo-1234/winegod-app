"""Preflight pre-campanha subida local -> Render 2026-04-24.

Grava preflight.md em reports/subida_vinhos_20260424/.

Checa:
- branch atual + commit HEAD;
- DSNs mascarados (nao expoe senha);
- migrations 018, 019, 020, 021 presentes via to_regclass;
- tabelas ingestion_run_log, not_wine_rejections, ingestion_review_queue,
  wcf_pipeline_control;
- snapshot audit_wines_pre_subida_20260424 (NAO executa CREATE; apenas
  verifica existencia e reporta se precisa criar);
- tasks schtasks nome contendo "Vivino" e "WCF" (Windows only).

Nao tenta pausar nada. Apenas registra estado inicial.

Uso:
  python scripts/data_ops_producers/preflight_subida_vinhos.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import psycopg2

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # pragma: no cover
    _load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "reports" / "subida_vinhos_20260424"

MIGRATION_SCHEMA_CHECKS = {
    "018": ["ingestion_run_log"],
    "019": ["not_wine_rejections"],
    "020": ["ingestion_review_queue"],
    "021": ["wcf_pipeline_control"],
}

AUDIT_SNAPSHOT = "audit_wines_pre_subida_20260424"
AUDIT_SNAPSHOT_SOURCES = "audit_wine_sources_pre_subida_20260424"


def _load_env() -> None:
    if _load_dotenv is None:
        return
    for p in (REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"):
        if p.exists():
            _load_dotenv(p, override=False)


def _mask_dsn(dsn: str | None) -> str:
    if not dsn:
        return "<ausente>"
    try:
        u = urlparse(dsn)
        host = u.hostname or "?"
        db = (u.path or "/?").lstrip("/") or "?"
        return f"postgres://***:***@{host}/{db}"
    except Exception:
        return "postgres://***"


def _git(cmd: list[str]) -> str:
    try:
        out = subprocess.check_output(
            ["git", *cmd], cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8", errors="replace").strip()
    except Exception as exc:
        return f"<erro: {exc}>"


def _connect_ro(dsn: str):
    conn = psycopg2.connect(dsn, connect_timeout=15)
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout TO 60000")
    return conn


def _regclass(conn, name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"public.{name}",))
        r = cur.fetchone()
    return bool(r and r[0])


def _scalar(conn, sql: str) -> int:
    with conn.cursor() as cur:
        cur.execute(sql)
        r = cur.fetchone()
    if not r or r[0] is None:
        return 0
    return int(r[0])


def _check_schtasks() -> list[str]:
    """Lista nomes de scheduled tasks que contem 'Vivino' ou 'WCF'.

    Windows only. Se schtasks nao disponivel, retorna lista vazia.
    """

    if os.name != "nt" or shutil.which("schtasks") is None:
        return []
    try:
        out = subprocess.check_output(
            ["schtasks", "/Query", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        text = out.decode("utf-8", errors="replace")
    except Exception:
        return []
    found: list[str] = []
    for line in text.splitlines():
        low = line.lower()
        if "vivino" in low or "wcf" in low:
            found.append(line.strip())
    return found


def _render_size(conn) -> str:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
            r = cur.fetchone()
        return str(r[0]) if r else ""
    except Exception:
        return ""


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    _load_env()

    lines: list[str] = []
    lines.append(f"# Preflight subida vinhos 2026-04-24")
    lines.append(f"_gerado_em: {datetime.now(timezone.utc).isoformat()}_")
    lines.append("")

    # Branch / commit
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    head = _git(["rev-parse", "HEAD"])
    head_short = _git(["rev-parse", "--short", "HEAD"])
    head_msg = _git(["log", "-1", "--pretty=%s"])
    lines.append("## Branch / Commit")
    lines.append(f"- branch: `{branch}`")
    lines.append(f"- HEAD: `{head}` ({head_short})")
    lines.append(f"- message: {head_msg}")
    lines.append("")

    # DSNs
    local_dsn = (
        os.environ.get("WINEGOD_DATABASE_URL")
        or os.environ.get("WINEGOD_CODEX_DATABASE_URL")
        or os.environ.get("DATABASE_URL_LOCAL_WINEGOD")
    )
    render_dsn = os.environ.get("DATABASE_URL")
    lines.append("## DSNs")
    lines.append(f"- winegod_local: `{_mask_dsn(local_dsn)}`")
    lines.append(f"- render: `{_mask_dsn(render_dsn)}`")
    lines.append("")

    # Schema Render
    lines.append("## Schema Render")
    schema_gates: dict[str, bool] = {}
    render_size = ""
    render_counts: dict[str, int] = {}
    snapshot_exists = False
    snapshot_sources_exists = False
    if not render_dsn:
        lines.append("- AVISO: DATABASE_URL ausente; pulando checks de schema Render.")
    else:
        try:
            conn = _connect_ro(render_dsn)
        except Exception as exc:
            lines.append(f"- ERRO ao conectar no Render: {exc}")
            conn = None
        if conn is not None:
            try:
                for mig, tables in MIGRATION_SCHEMA_CHECKS.items():
                    all_ok = True
                    for t in tables:
                        ok = _regclass(conn, t)
                        lines.append(f"- migration {mig} :: `{t}` -> {'OK' if ok else 'FALTA'}")
                        all_ok = all_ok and ok
                    schema_gates[mig] = all_ok
                snapshot_exists = _regclass(conn, AUDIT_SNAPSHOT)
                snapshot_sources_exists = _regclass(conn, AUDIT_SNAPSHOT_SOURCES)
                render_size = _render_size(conn)
                for t in ("wines", "wine_sources", "stores"):
                    if _regclass(conn, t):
                        render_counts[t] = _scalar(conn, f"SELECT COUNT(*) FROM public.{t}")
                    else:
                        render_counts[t] = 0
                if _regclass(conn, "ingestion_review_queue"):
                    render_counts["ingestion_review_queue_pending"] = _scalar(
                        conn,
                        "SELECT COUNT(*) FROM public.ingestion_review_queue WHERE status='pending'",
                    )
                else:
                    render_counts["ingestion_review_queue_pending"] = 0
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    lines.append("")

    # Counts baseline
    lines.append("## Counts baseline")
    if render_size:
        lines.append(f"- db_size_pretty: {render_size}")
    for k, v in render_counts.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    # Snapshots audit
    lines.append("## Snapshots audit")
    if snapshot_exists:
        lines.append(f"- `{AUDIT_SNAPSHOT}` -> OK (presente)")
    else:
        lines.append(
            f"- `{AUDIT_SNAPSHOT}` -> FALTA CRIAR: "
            f"`CREATE TABLE {AUDIT_SNAPSHOT} AS SELECT id, ingestion_run_id, descoberto_em AS captured_at FROM wines;`"
        )
    if snapshot_sources_exists:
        lines.append(f"- `{AUDIT_SNAPSHOT_SOURCES}` -> OK (presente)")
    else:
        lines.append(
            f"- `{AUDIT_SNAPSHOT_SOURCES}` -> FALTA CRIAR: "
            f"`CREATE TABLE {AUDIT_SNAPSHOT_SOURCES} AS SELECT id, wine_id, ingestion_run_id FROM wine_sources;`"
        )
    lines.append("")

    # Concorrencia (schtasks)
    lines.append("## Concorrencia")
    tasks = _check_schtasks()
    if not tasks:
        lines.append("- schtasks: nenhuma task com 'Vivino' ou 'WCF' encontrada (ou schtasks indisponivel).")
    else:
        for t in tasks:
            lines.append(f"- schtask detectada: `{t}`")
    lines.append("")

    # Gates preflight
    lines.append("## Gates preflight")
    gates: dict[str, bool] = {}
    gates["dsn_local_presente"] = bool(local_dsn)
    gates["dsn_render_presente"] = bool(render_dsn)
    for mig, ok in schema_gates.items():
        gates[f"migration_{mig}_ok"] = bool(ok)
    gates["snapshot_audit_wines_presente"] = bool(snapshot_exists)
    gates["snapshot_audit_wine_sources_presente"] = bool(snapshot_sources_exists)
    for k, v in gates.items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")

    out_path = REPORT_DIR / "preflight.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[preflight] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
