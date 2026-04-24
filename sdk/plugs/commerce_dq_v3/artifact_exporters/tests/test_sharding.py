"""Testes de sharding nos exporters commerce (plano 3 fases).

Cobre:
- MAX_SHARD_ITEMS hard cap em write_artifact;
- summary contem shard_spec quando passado;
- shard range invalido (min>max) retorna shard_range_invalid;
- source_table_filter limita queries (mockavel via fixture);
- Configs aceitam os novos campos.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import json
import pytest

from sdk.plugs.commerce_dq_v3.artifact_exporters import base
from sdk.plugs.commerce_dq_v3.artifact_exporters.base import (
    MAX_SHARD_ITEMS,
    write_artifact,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.tier1_global import (
    Tier1GlobalConfig,
    run_export as run_tier1_export,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.tier2_global import (
    Tier2GlobalConfig,
    run_export as run_tier2_global_export,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.tier2_br import (
    Tier2BrConfig,
    run_export as run_tier2_br_export,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.amazon_legacy import (
    AmazonLegacyConfig,
    run_export as run_amazon_legacy_export,
)
from sdk.plugs.commerce_dq_v3.artifact_exporters.amazon_mirror import (
    AmazonMirrorConfig,
    run_export as run_amazon_mirror_export,
)


def _valid_item(idx: int) -> dict:
    return {
        "pipeline_family": "tier1",
        "run_id": "test_run",
        "country": "us",
        "store_name": "store",
        "store_domain": "loja.com",
        "url_original": f"https://loja.com/p/{idx}",
        "nome": f"wine {idx}",
        "produtor": "produtor",
        "safra": 2020,
        "preco": 10.0,
        "moeda": "USD",
        "captured_at": "2026-04-24T00:00:00+00:00",
        "source_pointer": f"vinhos_us_fontes#{idx}",
    }


def test_max_shard_items_hard_cap_raises(tmp_path: Path):
    items = [_valid_item(i) for i in range(5)]
    with pytest.raises(ValueError, match="MAX_SHARD_ITEMS"):
        write_artifact(
            items=iter(items),
            output_dir=tmp_path,
            source_label="test",
            pipeline_family="tier1",
            run_id="test_run",
            started_at=datetime.now(timezone.utc),
            max_items=MAX_SHARD_ITEMS + 1,
        )


def test_max_shard_items_exactly_50k_ok(tmp_path: Path):
    # 50000 deve passar (eh o limite, nao excede).
    items = [_valid_item(i) for i in range(3)]
    result = write_artifact(
        items=iter(items),
        output_dir=tmp_path,
        source_label="test",
        pipeline_family="tier1",
        run_id="test_run",
        started_at=datetime.now(timezone.utc),
        max_items=50_000,
    )
    assert result.ok
    assert result.items_emitted == 3


def test_shard_spec_included_in_summary(tmp_path: Path):
    items = [_valid_item(i) for i in range(2)]
    result = write_artifact(
        items=iter(items),
        output_dir=tmp_path,
        source_label="test",
        pipeline_family="tier1",
        run_id="test_run",
        started_at=datetime.now(timezone.utc),
        max_items=100,
        shard_spec={
            "shard_id": "tier1_us_001",
            "source_table": "vinhos_us_fontes",
            "min_fonte_id": 1,
            "max_fonte_id": 50000,
        },
    )
    assert result.ok
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert "shard_spec" in summary
    assert summary["shard_spec"]["shard_id"] == "tier1_us_001"
    assert summary["shard_spec"]["source_table"] == "vinhos_us_fontes"
    assert summary["shard_spec"]["min_fonte_id"] == 1
    assert summary["shard_spec"]["max_fonte_id"] == 50000


def test_shard_spec_absent_when_not_sharded(tmp_path: Path):
    items = [_valid_item(i) for i in range(2)]
    result = write_artifact(
        items=iter(items),
        output_dir=tmp_path,
        source_label="test",
        pipeline_family="tier1",
        run_id="test_run",
        started_at=datetime.now(timezone.utc),
        max_items=100,
    )
    assert result.ok
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert "shard_spec" not in summary


def test_tier1_shard_range_invalid_min_gt_max():
    cfg = Tier1GlobalConfig(min_fonte_id=100, max_fonte_id=50, shard_id="bad")
    result = run_tier1_export(cfg)
    assert not result.ok
    assert result.reason == "shard_range_invalid"


def test_tier2_global_shard_range_invalid():
    cfg = Tier2GlobalConfig(min_fonte_id=100, max_fonte_id=50, shard_id="bad")
    result = run_tier2_global_export(cfg)
    assert not result.ok
    assert result.reason == "shard_range_invalid"


def test_tier2_br_shard_range_invalid():
    cfg = Tier2BrConfig(min_fonte_id=100, max_fonte_id=50, shard_id="bad")
    result = run_tier2_br_export(cfg)
    assert not result.ok
    assert result.reason == "shard_range_invalid"


def test_amazon_legacy_shard_range_invalid():
    cfg = AmazonLegacyConfig(min_fonte_id=100, max_fonte_id=50, shard_id="bad")
    result = run_amazon_legacy_export(cfg)
    assert not result.ok
    assert result.reason == "shard_range_invalid"


def test_amazon_mirror_shard_range_invalid():
    cfg = AmazonMirrorConfig(min_fonte_id=100, max_fonte_id=50, shard_id="bad")
    result = run_amazon_mirror_export(cfg)
    assert not result.ok
    assert result.reason == "shard_range_invalid"


def test_tier1_config_accepts_new_fields():
    cfg = Tier1GlobalConfig(
        source_table_filter="vinhos_us_fontes",
        min_fonte_id=1,
        max_fonte_id=50_000,
        shard_id="tier1_us_001",
    )
    assert cfg.source_table_filter == "vinhos_us_fontes"
    assert cfg.min_fonte_id == 1
    assert cfg.max_fonte_id == 50_000
    assert cfg.shard_id == "tier1_us_001"


def test_all_configs_have_sharding_fields():
    configs = [
        Tier1GlobalConfig(),
        Tier2GlobalConfig(),
        Tier2BrConfig(),
        AmazonLegacyConfig(),
        AmazonMirrorConfig(),
    ]
    for cfg in configs:
        assert hasattr(cfg, "source_table_filter"), f"{type(cfg).__name__} missing source_table_filter"
        assert hasattr(cfg, "min_fonte_id"), f"{type(cfg).__name__} missing min_fonte_id"
        assert hasattr(cfg, "max_fonte_id"), f"{type(cfg).__name__} missing max_fonte_id"
        assert hasattr(cfg, "shard_id"), f"{type(cfg).__name__} missing shard_id"


def test_bulk_ingest_does_not_import_new_wines():
    """Regra absoluta plano 3 fases: commerce apply NAO chama Gemini/enrichment_v3.

    Confirma que backend/services/bulk_ingest.py nao importa new_wines nem
    enrichment_v3 — seria porta de entrada do Gemini no caminho commerce.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parents[5] / "backend" / "services" / "bulk_ingest.py").read_text(encoding="utf-8")
    assert "from services.new_wines" not in src
    assert "from backend.services.new_wines" not in src
    assert "enrich_items_v3" not in src
    assert "_classify_candidates_v3" not in src
