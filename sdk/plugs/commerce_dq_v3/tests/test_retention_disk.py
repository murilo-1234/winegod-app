"""Testes retencao + rotacao + disk monitor."""

from __future__ import annotations

import gzip
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sdk.plugs.commerce_dq_v3 import disk_monitor
from sdk.plugs.commerce_dq_v3.retention import (
    RetentionPlan,
    RotationAction,
    apply_plan,
    build_plan,
)


def _make_artifact(fam_dir: Path, name: str, age_days: int = 0) -> Path:
    fam_dir.mkdir(parents=True, exist_ok=True)
    path = fam_dir / f"{name}.jsonl"
    path.write_text('{"hello":"world"}\n', encoding="utf-8")
    summary = fam_dir / f"{name}_summary.json"
    summary.write_text("{}", encoding="utf-8")
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
        os.utime(summary, (old, old))
    return path


def test_disk_monitor_classify() -> None:
    assert disk_monitor.classify(100) == "ok"
    assert disk_monitor.classify(3 * 1024 * 1024 * 1024) == "warning"
    assert disk_monitor.classify(6 * 1024 * 1024 * 1024) == "failed"


def test_disk_monitor_dir_size(tmp_path: Path) -> None:
    (tmp_path / "a.jsonl").write_bytes(b"x" * 1000)
    (tmp_path / "b.jsonl").write_bytes(b"y" * 500)
    assert disk_monitor.dir_size(tmp_path) >= 1500


def test_disk_monitor_summary(tmp_path: Path) -> None:
    (tmp_path / "x.jsonl").write_bytes(b"z" * 2048)
    s = disk_monitor.summary(tmp_path)
    assert s["status"] == "ok"
    assert s["bytes"] >= 2048


def test_build_plan_keep_recent(tmp_path: Path) -> None:
    _make_artifact(tmp_path / "amazon_mirror", "20260424_recent")
    plan = build_plan(
        base_dir=tmp_path,
        max_age_days=30,
        max_files=10,
        compress_after_days=7,
    )
    kinds = [a.kind for a in plan.actions]
    assert "keep" in kinds


def test_build_plan_compress_between_7_and_30(tmp_path: Path) -> None:
    _make_artifact(tmp_path / "tier1", "mid", age_days=10)
    plan = build_plan(
        base_dir=tmp_path,
        max_age_days=30,
        max_files=10,
        compress_after_days=7,
    )
    assert any(a.kind == "compress" for a in plan.actions)


def test_build_plan_delete_old(tmp_path: Path) -> None:
    _make_artifact(tmp_path / "tier2_global", "old", age_days=60)
    plan = build_plan(
        base_dir=tmp_path,
        max_age_days=30,
        max_files=10,
        compress_after_days=7,
    )
    assert any(a.kind == "delete" for a in plan.actions)


def test_build_plan_max_files(tmp_path: Path) -> None:
    fam = tmp_path / "tier1"
    for i in range(15):
        _make_artifact(fam, f"run_{i:02d}", age_days=i)
    plan = build_plan(
        base_dir=tmp_path,
        max_age_days=365,
        max_files=5,
        compress_after_days=999,
    )
    deletes = [a for a in plan.actions if a.kind == "delete"]
    assert len(deletes) >= 10  # 15 - 5 = 10 delete


def test_build_plan_preserva_quarantined(tmp_path: Path) -> None:
    fam = tmp_path / "amazon_mirror"
    fam.mkdir(parents=True)
    (fam / "bad.jsonl.quarantined").write_text("x", encoding="utf-8")
    plan = build_plan(base_dir=tmp_path, max_age_days=1, max_files=0, compress_after_days=0)
    actions = [a for a in plan.actions if ".quarantined" in str(a.artifact)]
    assert all(a.kind == "keep" for a in actions)


def test_apply_plan_compress(tmp_path: Path) -> None:
    fam = tmp_path / "tier2_global"
    art = _make_artifact(fam, "compr", age_days=10)
    plan = build_plan(
        base_dir=tmp_path,
        max_age_days=365,
        max_files=50,
        compress_after_days=7,
    )
    counts = apply_plan(plan)
    assert counts["compressed"] >= 1
    assert not art.exists()
    assert (art.with_suffix(".jsonl.gz")).exists()


def test_apply_plan_delete(tmp_path: Path) -> None:
    fam = tmp_path / "tier2/br"
    art = _make_artifact(fam, "del_me", age_days=60)
    plan = build_plan(
        base_dir=tmp_path,
        max_age_days=30,
        max_files=10,
        compress_after_days=7,
    )
    apply_plan(plan)
    assert not art.exists()
    # summary tambem apagado
    assert not fam.joinpath("del_me_summary.json").exists()
