"""Testes estaticos do patch de backup logs+checkpoints (Fase M).

Patch NAO e aplicado. Testes confirmam:
- arquivo existe no repositorio;
- inclui os 3 alvos (amazon_logs, ct_checkpoints, ct_progress);
- usa IF EXIST para nao quebrar se padrao ausente;
- tem upload rclone para `gdrive:winegod-backups/`;
- nao altera horario 04:00 do backup existente.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PATCH_PATH = REPO_ROOT / "reports" / "data_ops_backup_patches" / "add_logs_checkpoints_to_backup.patch"


def _patch_text() -> str:
    return PATCH_PATH.read_text(encoding="utf-8")


def test_patch_file_existe() -> None:
    assert PATCH_PATH.exists(), f"patch nao encontrado: {PATCH_PATH}"


def test_patch_inclui_amazon_logs() -> None:
    txt = _patch_text()
    assert "_amazon_*.log" in txt
    assert "backup_natura_amazon_logs" in txt


def test_patch_inclui_ct_checkpoints() -> None:
    txt = _patch_text()
    assert "_ct_scraper_*.json" in txt
    assert "backup_natura_ct_checkpoints" in txt


def test_patch_inclui_ct_progress() -> None:
    txt = _patch_text()
    assert "_ct_*.progress.json" in txt or "ct_progress" in txt


def test_patch_usa_if_exist() -> None:
    txt = _patch_text()
    # Tres blocos IF EXIST (um por padrao)
    assert txt.count("if exist") >= 3 or txt.count("IF EXIST") >= 3 or txt.count("if exist ") >= 3


def test_patch_faz_upload_rclone() -> None:
    txt = _patch_text()
    assert "rclone" in txt
    assert "gdrive:winegod-backups" in txt


def test_patch_nao_altera_horario() -> None:
    """O snippet nao pode adicionar `schtasks` ou mexer em horario."""

    txt = _patch_text().lower()
    assert "schtasks" not in txt
    assert "/delete" not in txt
    assert "04:00" not in txt or "mantem horario 04:00" in txt


def test_patch_trata_erro_rclone() -> None:
    txt = _patch_text()
    assert "_rclone_err.log" in txt
