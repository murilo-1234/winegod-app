"""Health observacional commerce (read-only).

Inspeciona:
- ultimo artefato de cada familia em `reports/data_ops_artifacts/*/` e
  roda validator FULL se artefato existir;
- estado de cada exporter em `reports/data_ops_export_state/`;
- tamanho do diretorio `reports/data_ops_artifacts/` (disk monitor).

Classifica em `ok / warning / failed`. Exit codes:
- 0 = ok
- 2 = warning
- 3 = failed

Nao conecta banco, nao chama API externa, nao escreve em nada.
Opcional: `--write-md <path>` para gerar snapshot markdown.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sdk.plugs.commerce_dq_v3.artifact_contract import validate_artifact_dir_full


FAMILIES: dict[str, dict[str, Any]] = {
    "amazon_mirror_primary": {
        "artifact_dir": REPO_ROOT / "reports" / "data_ops_artifacts" / "amazon_mirror",
        "state_key": "amazon_mirror",
        "accept_empty": True,  # blocked_external_host ate JSONL aparecer
        "empty_severity": "warning",
    },
    "amazon_local_legacy_backfill": {
        "artifact_dir": REPO_ROOT / "reports" / "data_ops_artifacts" / "amazon_local_legacy_backfill",
        "state_key": None,
        "accept_empty": True,
        "empty_severity": "ok",  # one-time, pode nao ter rodado ainda
    },
    "tier1": {
        "artifact_dir": REPO_ROOT / "reports" / "data_ops_artifacts" / "tier1",
        "state_key": None,
        "accept_empty": True,
        "empty_severity": "warning",
    },
    "tier2_global_artifact": {
        "artifact_dir": REPO_ROOT / "reports" / "data_ops_artifacts" / "tier2_global",
        "state_key": None,
        "accept_empty": True,
        "empty_severity": "warning",
        "expected_family": "tier2",
    },
    "tier2_br": {
        "artifact_dir": REPO_ROOT / "reports" / "data_ops_artifacts" / "tier2" / "br",
        "state_key": None,
        "accept_empty": True,
        "empty_severity": "warning",
        "expected_family": "tier2",
    },
}

DISK_WARNING_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
DISK_FAILED_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB


@dataclass
class FamilyStatus:
    family: str
    status: str  # ok | warning | failed
    artifact: str | None = None
    lines_validated: int | None = None
    sha256: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class HealthReport:
    overall: str  # ok | warning | failed
    families: list[FamilyStatus] = field(default_factory=list)
    disk_bytes: int = 0
    disk_status: str = "ok"
    exporter_state: dict[str, dict] = field(default_factory=dict)
    generated_at: str = ""


def _load_state_files() -> dict[str, dict]:
    state_dir = REPO_ROOT / "reports" / "data_ops_export_state"
    if not state_dir.exists():
        return {}
    out: dict[str, dict] = {}
    for p in state_dir.glob("*.json"):
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            out[p.stem] = {"error": "state_parse_fail"}
    return out


def _artifacts_dir_size() -> int:
    base = REPO_ROOT / "reports" / "data_ops_artifacts"
    if not base.exists():
        return 0
    total = 0
    for p in base.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _classify_disk(total_bytes: int) -> str:
    if total_bytes >= DISK_FAILED_BYTES:
        return "failed"
    if total_bytes >= DISK_WARNING_BYTES:
        return "warning"
    return "ok"


def _merge_status(a: str, b: str) -> str:
    order = {"ok": 0, "warning": 1, "failed": 2}
    return a if order[a] >= order[b] else b


def _check_family(name: str, meta: dict[str, Any]) -> FamilyStatus:
    artifact_dir: Path = meta["artifact_dir"]
    expected_family = meta.get("expected_family", name)
    if not artifact_dir.exists():
        empty_severity = meta.get("empty_severity", "warning")
        return FamilyStatus(
            family=name,
            status=empty_severity,
            notes=[f"artifact_dir_ausente={artifact_dir}"],
        )
    result = validate_artifact_dir_full(
        artifact_dir=artifact_dir, expected_family=expected_family
    )
    if result.ok:
        return FamilyStatus(
            family=name,
            status="ok",
            artifact=result.artifact_path.name if result.artifact_path else None,
            lines_validated=len(result.items),
            sha256=(result.artifact_sha256 or "")[:16],
            notes=[f"items={len(result.items)}"],
        )
    # sem artefato
    if result.artifact_path is None:
        empty_severity = meta.get("empty_severity", "warning")
        if meta.get("accept_empty", False):
            return FamilyStatus(
                family=name,
                status=empty_severity,
                notes=[f"sem_artefato={artifact_dir.name}", result.reason or ""],
            )
        return FamilyStatus(
            family=name,
            status="failed",
            notes=[f"sem_artefato={artifact_dir.name}", result.reason or ""],
        )
    # artefato existe mas contrato invalido
    return FamilyStatus(
        family=name,
        status="failed",
        artifact=result.artifact_path.name,
        sha256=(result.artifact_sha256 or "")[:16],
        notes=[result.reason or "contrato_invalido"] + list(result.notes[:8]),
    )


def check() -> HealthReport:
    overall = "ok"
    fams = []
    for name, meta in FAMILIES.items():
        st = _check_family(name, meta)
        fams.append(st)
        overall = _merge_status(overall, st.status)
    disk = _artifacts_dir_size()
    disk_status = _classify_disk(disk)
    overall = _merge_status(overall, disk_status)
    return HealthReport(
        overall=overall,
        families=fams,
        disk_bytes=disk,
        disk_status=disk_status,
        exporter_state=_load_state_files(),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _fmt_md(report: HealthReport) -> str:
    lines = [
        "# Commerce health - snapshot",
        "",
        f"- generated_at: `{report.generated_at}`",
        f"- overall_status: **{report.overall}**",
        f"- disk_bytes: {report.disk_bytes:,} ({report.disk_status})",
        "",
        "## Familias",
        "",
        "| familia | status | artefato | items | sha | notas |",
        "|---|---|---|---:|---|---|",
    ]
    for f in report.families:
        lines.append(
            f"| `{f.family}` | **{f.status}** | `{f.artifact or '-'}` | "
            f"{f.lines_validated or 0} | `{f.sha256 or '-'}` | "
            f"{'; '.join(f.notes[:4])} |"
        )
    lines += ["", "## Exporter state files", ""]
    if report.exporter_state:
        for key, state in report.exporter_state.items():
            lines.append(f"- `{key}.json`: `{json.dumps(state, default=str)[:180]}`")
    else:
        lines.append("- (nenhum state file ainda; exporters nao rodaram)")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Commerce health (read-only).")
    parser.add_argument("--stdout", choices=["md", "json", "summary"], default="summary")
    parser.add_argument("--write-md", type=Path, default=None)
    args = parser.parse_args()
    report = check()

    if args.stdout == "md":
        print(_fmt_md(report))
    elif args.stdout == "json":
        print(
            json.dumps(
                {
                    "overall": report.overall,
                    "disk_bytes": report.disk_bytes,
                    "disk_status": report.disk_status,
                    "generated_at": report.generated_at,
                    "families": [f.__dict__ for f in report.families],
                    "exporter_state": report.exporter_state,
                },
                default=str,
                indent=2,
            )
        )
    else:
        print(f"overall={report.overall} disk={report.disk_status} bytes={report.disk_bytes}")
        for f in report.families:
            print(f"  {f.family}: {f.status} artifact={f.artifact or '-'} items={f.lines_validated or 0}")

    if args.write_md:
        args.write_md.parent.mkdir(parents=True, exist_ok=True)
        args.write_md.write_text(_fmt_md(report), encoding="utf-8")

    return {"ok": 0, "warning": 2, "failed": 3}[report.overall]


if __name__ == "__main__":
    raise SystemExit(main())
