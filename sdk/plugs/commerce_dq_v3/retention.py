"""Politica de retencao + rotacao dos artefatos commerce.

Regras:
- Manter ultimos `max_age_days` ou `max_files` (o que for menor) por
  familia; default `max_age_days=30`, `max_files=10`.
- Arquivos (JSONL + summary) com mais de `compress_after_days` (default
  7) sao comprimidos (gzip) antes de serem considerados descarte.
- Nunca deleta o JSONL sem deletar o summary correspondente.
- Artefatos `.jsonl.quarantined` sao preservados (parte da trilha de
  incidentes).

Modo `plan`: nao mexe em disco. Retorna `RetentionPlan` com acoes.
Modo `apply`: aplica `plan` (gzip + unlink). Este modulo nao chama
apply sozinho; o CLI faz o gate por env var.
"""

from __future__ import annotations

import gzip
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path


FAMILY_DIRS = {
    "amazon_mirror": "amazon_mirror",
    "amazon_local_legacy_backfill": "amazon_local_legacy_backfill",
    "tier1": "tier1",
    "tier2_global": "tier2_global",
    "tier2_br": "tier2/br",
}


@dataclass
class RotationAction:
    family: str
    artifact: Path
    kind: str  # "compress" | "delete" | "keep"
    reason: str


@dataclass
class RetentionPlan:
    base_dir: Path
    max_age_days: int
    max_files: int
    compress_after_days: int
    actions: list[RotationAction] = field(default_factory=list)


def _jsonl_files(fam_dir: Path) -> list[Path]:
    return sorted(
        [p for p in fam_dir.glob("*.jsonl") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def build_plan(
    *,
    base_dir: Path,
    max_age_days: int = 30,
    max_files: int = 10,
    compress_after_days: int = 7,
    now: datetime | None = None,
) -> RetentionPlan:
    plan = RetentionPlan(
        base_dir=base_dir,
        max_age_days=max_age_days,
        max_files=max_files,
        compress_after_days=compress_after_days,
    )
    now = now or datetime.now(timezone.utc)
    for fam, subpath in FAMILY_DIRS.items():
        fam_dir = base_dir / subpath
        if not fam_dir.exists():
            continue
        files = _jsonl_files(fam_dir)
        for idx, p in enumerate(files):
            mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            age = now - mtime
            if p.name.endswith(".jsonl.quarantined"):
                plan.actions.append(
                    RotationAction(fam, p, "keep", "quarentenado")
                )
                continue
            if age > timedelta(days=max_age_days) or idx >= max_files:
                plan.actions.append(
                    RotationAction(
                        fam,
                        p,
                        "delete",
                        f"age={age.days}d idx={idx} max_age={max_age_days}d max_files={max_files}",
                    )
                )
            elif age > timedelta(days=compress_after_days):
                plan.actions.append(
                    RotationAction(
                        fam,
                        p,
                        "compress",
                        f"age={age.days}d compress_after={compress_after_days}d",
                    )
                )
            else:
                plan.actions.append(RotationAction(fam, p, "keep", f"age={age.days}d"))
    return plan


def apply_plan(plan: RetentionPlan) -> dict:
    """Aplica acoes do plano. Retorna contagem por tipo."""

    counts = {"deleted": 0, "compressed": 0, "kept": 0, "errors": 0}
    for action in plan.actions:
        if action.kind == "keep":
            counts["kept"] += 1
            continue
        try:
            summary_path = action.artifact.with_name(
                action.artifact.stem + "_summary.json"
            )
            if action.kind == "compress":
                gz_path = action.artifact.with_suffix(".jsonl.gz")
                with action.artifact.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                action.artifact.unlink()
                if summary_path.exists():
                    gz_summary = summary_path.with_suffix(".json.gz")
                    with summary_path.open("rb") as src, gzip.open(gz_summary, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    summary_path.unlink()
                counts["compressed"] += 1
            elif action.kind == "delete":
                action.artifact.unlink()
                if summary_path.exists():
                    summary_path.unlink()
                # Se existe versao gzipada, apaga tambem.
                gz_art = action.artifact.with_suffix(".jsonl.gz")
                if gz_art.exists():
                    gz_art.unlink()
                gz_sum = summary_path.with_suffix(".json.gz")
                if gz_sum.exists():
                    gz_sum.unlink()
                counts["deleted"] += 1
        except Exception:
            counts["errors"] += 1
    return counts
