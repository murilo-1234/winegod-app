"""Testes commerce health observacional."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sdk.plugs.commerce_dq_v3 import health as health_mod
from sdk.plugs.commerce_dq_v3.artifact_exporters.amazon_mirror import (
    run_export_from_rows as mirror_export,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.tier1_global import (
    run_export_from_rows as tier1_export,
)
from sdk.plugs.commerce_dq_v3.tests.fixtures.commerce_rows import (
    amazon_mirror_rows,
    tier1_rows,
)


def _install_families(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Aponta health.FAMILIES para tmp_path (sub-dirs por familia)."""

    families = {
        "amazon_mirror_primary": {
            "artifact_dir": tmp_path / "amazon_mirror",
            "state_key": "amazon_mirror",
            "accept_empty": True,
            "empty_severity": "warning",
        },
        "tier1": {
            "artifact_dir": tmp_path / "tier1",
            "state_key": None,
            "accept_empty": True,
            "empty_severity": "warning",
        },
        "tier2_global_artifact": {
            "artifact_dir": tmp_path / "tier2_global",
            "state_key": None,
            "accept_empty": True,
            "empty_severity": "warning",
            "expected_family": "tier2",
        },
    }
    monkeypatch.setattr(health_mod, "FAMILIES", families)
    monkeypatch.setattr(health_mod, "REPO_ROOT", tmp_path)
    return tmp_path


def test_health_ok_com_todos_artefatos(tmp_path: Path, monkeypatch) -> None:
    _install_families(monkeypatch, tmp_path)
    mirror_export(amazon_mirror_rows(3), output_dir=tmp_path / "amazon_mirror", update_state=False)
    tier1_export(tier1_rows(3), output_dir=tmp_path / "tier1")
    # tier2_global vazio, status = warning
    report = health_mod.check()
    # overall >= warning (tier2 sem artefato)
    assert report.overall in ("warning", "ok")
    fams = {f.family: f for f in report.families}
    assert fams["amazon_mirror_primary"].status == "ok"
    assert fams["tier1"].status == "ok"


def test_health_warning_sem_artefato(tmp_path: Path, monkeypatch) -> None:
    _install_families(monkeypatch, tmp_path)
    # nenhum artefato
    report = health_mod.check()
    assert report.overall == "warning"
    for f in report.families:
        assert f.status == "warning"


def test_health_failed_contrato_invalido(tmp_path: Path, monkeypatch) -> None:
    _install_families(monkeypatch, tmp_path)
    # cria JSONL corrompido para mirror
    md = tmp_path / "amazon_mirror"
    md.mkdir(parents=True)
    (md / "broken.jsonl").write_text("{invalido json}\n", encoding="utf-8")
    (md / "broken_summary.json").write_text("{}", encoding="utf-8")
    report = health_mod.check()
    assert report.overall == "failed"
    fams = {f.family: f for f in report.families}
    assert fams["amazon_mirror_primary"].status == "failed"


def test_health_disk_warning(tmp_path: Path, monkeypatch) -> None:
    _install_families(monkeypatch, tmp_path)
    monkeypatch.setattr(health_mod, "_artifacts_dir_size", lambda: 3 * 1024 * 1024 * 1024)  # 3 GB
    report = health_mod.check()
    assert report.disk_status == "warning"
    assert report.overall in ("warning", "failed")


def test_health_disk_failed(tmp_path: Path, monkeypatch) -> None:
    _install_families(monkeypatch, tmp_path)
    monkeypatch.setattr(health_mod, "_artifacts_dir_size", lambda: 6 * 1024 * 1024 * 1024)  # 6 GB
    report = health_mod.check()
    assert report.disk_status == "failed"
    assert report.overall == "failed"


def test_health_classify_merge() -> None:
    assert health_mod._merge_status("ok", "warning") == "warning"
    assert health_mod._merge_status("warning", "ok") == "warning"
    assert health_mod._merge_status("warning", "failed") == "failed"
    assert health_mod._merge_status("ok", "ok") == "ok"


def test_health_md_contem_tabela(tmp_path: Path, monkeypatch) -> None:
    _install_families(monkeypatch, tmp_path)
    mirror_export(amazon_mirror_rows(2), output_dir=tmp_path / "amazon_mirror", update_state=False)
    report = health_mod.check()
    md = health_mod._fmt_md(report)
    assert "# Commerce health" in md
    assert "amazon_mirror_primary" in md
    assert "| familia | status" in md


def test_health_exporter_state_integrado(tmp_path: Path, monkeypatch) -> None:
    _install_families(monkeypatch, tmp_path)
    state_dir = tmp_path / "reports" / "data_ops_export_state"
    state_dir.mkdir(parents=True)
    (state_dir / "amazon_mirror.json").write_text(
        json.dumps({"last_captured_at": "2026-04-20T00:00:00+00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(health_mod, "REPO_ROOT", tmp_path)
    # chamar _load_state_files diretamente, pois os modulos state usam REPO_ROOT
    state = health_mod._load_state_files()
    assert "amazon_mirror" in state
    assert state["amazon_mirror"]["last_captured_at"]
