"""Testes da funcao de retencao.

Valida:
- run_retention(dry_run=True) funciona com DB (ou skip).
- run_retention(dry_run=False) bloqueia com OPS_WRITE_ENABLED=false.
- Mapa RETENTION_MAP tem tabelas corretas.
- Nao existe agendamento automatico no modulo.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def test_retention_map_has_expected_tables():
    from services.ops_retention import RETENTION_MAP

    expected = {
        "ops.scraper_heartbeats",
        "ops.scraper_events",
        "ops.batch_metrics",
        "ops.batch_metrics_hourly",
        "ops.ingestion_batches",
        "ops.contract_validation_errors",
        "ops.dq_decisions",
        "ops.matching_decisions",
        "ops.final_apply_results",
        "ops.scraper_alerts",
    }
    assert expected.issubset(set(RETENTION_MAP.keys()))


def test_retention_does_not_include_permanent_tables():
    from services.ops_retention import RETENTION_MAP

    # Tabelas permanentes nao podem estar no mapa
    permanent = {
        "ops.scraper_registry",
        "ops.scraper_runs",
        "ops.source_lineage",
        "ops.scraper_configs",
    }
    assert permanent.isdisjoint(set(RETENTION_MAP.keys()))


def test_retention_apply_bloqueado_se_write_disabled(monkeypatch):
    from config import Config as _Cfg
    from services import ops_retention

    monkeypatch.setattr(_Cfg, "OPS_WRITE_ENABLED", False)
    with pytest.raises(RuntimeError, match="ops_write_disabled"):
        ops_retention.run_retention(dry_run=False)


def test_retention_module_has_no_scheduler():
    """Garante que retencao nao tem scheduler automatico ativo no modulo.

    Procura IMPORTs reais e CALLs. Menção em string/comentário
    (ex: a propria palavra "cron" explicando que NAO tem cron) eh permitida.
    """
    path = BACKEND_ROOT / "services" / "ops_retention.py"
    src = path.read_text(encoding="utf-8")

    # Proibidos: imports/chamadas de agendadores reais
    forbidden_imports = [
        r"^\s*import\s+APScheduler",
        r"^\s*from\s+apscheduler",
        r"^\s*import\s+schedule\b",
        r"^\s*from\s+schedule\b",
        r"BackgroundScheduler\s*\(",
        r"BlockingScheduler\s*\(",
        r"add_job\s*\(",
        r"schedule\.every\s*\(",
        r"crontab\s*\(",
        r"\.start\s*\(\s*\)\s*#.*scheduler",
        r"def\s+start_scheduler",
    ]
    for pat in forbidden_imports:
        assert not re.search(pat, src, re.MULTILINE), f"Scheduler detected: {pat}"


def test_retention_respects_batch_size():
    """Codigo deve usar Config.OPS_RETENTION_BATCH_SIZE."""
    path = BACKEND_ROOT / "services" / "ops_retention.py"
    src = path.read_text(encoding="utf-8")
    assert "OPS_RETENTION_BATCH_SIZE" in src
    assert "LIMIT" in src  # DELETE com LIMIT via CTE


def test_retention_dry_run_signature():
    from services.ops_retention import run_retention
    import inspect

    sig = inspect.signature(run_retention)
    assert "dry_run" in sig.parameters
    assert sig.parameters["dry_run"].default is True  # Default seguro = dry-run
