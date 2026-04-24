"""Smoke test do planner de shards de `inventario_subida_vinhos._plan_shards`.

Testes puros sem DB. Cobre:
  (a) total < shard_size -> 1 shard com range completo.
  (b) total >= shard_size -> N shards contiguos sem overlap, somando ~total.
  (c) min > max -> ValueError.
  (d) total <= 0 -> lista vazia.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = ROOT / "scripts" / "data_ops_producers"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from inventario_subida_vinhos import _plan_shards  # type: ignore  # noqa: E402


def test_plan_shards_menor_que_shard_size():
    shards = _plan_shards(total_rows=10_000, min_id=1, max_id=10_000, shard_size=50_000)
    assert len(shards) == 1
    assert shards[0]["min_fonte_id"] == 1
    assert shards[0]["max_fonte_id"] == 10_000
    assert shards[0]["expected_rows"] == 10_000


def test_plan_shards_igual_ao_shard_size():
    shards = _plan_shards(total_rows=50_000, min_id=1, max_id=50_000, shard_size=50_000)
    assert len(shards) == 1
    assert shards[0]["min_fonte_id"] == 1
    assert shards[0]["max_fonte_id"] == 50_000


def test_plan_shards_multiplos_sem_overlap():
    total = 175_000
    min_id = 100
    max_id = 100 + 400_000  # range mais largo que total para simular gaps
    shards = _plan_shards(total_rows=total, min_id=min_id, max_id=max_id, shard_size=50_000)

    # N esperado = ceil(175000/50000) = 4
    assert len(shards) == math.ceil(total / 50_000) == 4

    # sem overlap e contiguos
    for i in range(1, len(shards)):
        assert shards[i]["min_fonte_id"] == shards[i - 1]["max_fonte_id"] + 1
        assert shards[i]["min_fonte_id"] > shards[i - 1]["max_fonte_id"]

    # primeiro comeca no min_id, ultimo fecha no max_id
    assert shards[0]["min_fonte_id"] == min_id
    assert shards[-1]["max_fonte_id"] == max_id

    # soma das expected_rows bate com total
    assert sum(s["expected_rows"] for s in shards) == total


def test_plan_shards_tight_range():
    """Quando o range eh exatamente contiguo (sem gaps) os shards tambem batem."""
    total = 120_000
    shards = _plan_shards(total_rows=total, min_id=1, max_id=120_000, shard_size=50_000)
    assert len(shards) == 3
    # contiguidade
    for i in range(1, len(shards)):
        assert shards[i]["min_fonte_id"] == shards[i - 1]["max_fonte_id"] + 1
    assert shards[0]["min_fonte_id"] == 1
    assert shards[-1]["max_fonte_id"] == 120_000


def test_plan_shards_min_maior_que_max_levanta():
    with pytest.raises(ValueError):
        _plan_shards(total_rows=1000, min_id=500, max_id=100, shard_size=50_000)


def test_plan_shards_total_zero_ou_negativo_retorna_vazio():
    assert _plan_shards(total_rows=0, min_id=1, max_id=100) == []
    assert _plan_shards(total_rows=-5, min_id=1, max_id=100) == []


def test_plan_shards_ids_ausentes_mas_com_total():
    shards = _plan_shards(total_rows=42, min_id=None, max_id=None)
    assert len(shards) == 1
    assert shards[0]["expected_rows"] == 42
    assert shards[0]["min_fonte_id"] == 0
    assert shards[0]["max_fonte_id"] == 0


def test_plan_shards_shard_size_invalido():
    with pytest.raises(ValueError):
        _plan_shards(total_rows=100_000, min_id=1, max_id=100_000, shard_size=0)
