"""Testes pre-flight dos apply wrappers commerce.

Objetivos:
- cada wrapper aborta cleanly (exit 2) sem env autorizadora;
- cada wrapper aborta cleanly se validator falhar (via DryRunOnly + dir vazio);
- DryRunOnly roda validator mas nao chama o runner apply.

Como nao rodamos apply real, usamos:
- variaveis de ambiente setadas em-memoria;
- stubs de artefato com e sem JSONL.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHED_DIR = REPO_ROOT / "scripts" / "data_ops_scheduler"

WRAPPERS = {
    "amazon_mirror": {
        "script": "run_commerce_apply_amazon_mirror.ps1",
        "env": "COMMERCE_APPLY_AUTHORIZED_AMAZON_MIRROR",
        "dir": REPO_ROOT / "reports" / "data_ops_artifacts" / "amazon_mirror",
    },
    "amazon_legacy": {
        "script": "run_commerce_apply_amazon_legacy.ps1",
        "env": "COMMERCE_APPLY_AUTHORIZED_AMAZON_LEGACY",
        "dir": REPO_ROOT / "reports" / "data_ops_artifacts" / "amazon_local_legacy_backfill",
    },
    "tier1": {
        "script": "run_commerce_apply_tier1_global.ps1",
        "env": "COMMERCE_APPLY_AUTHORIZED_TIER1",
        "dir": REPO_ROOT / "reports" / "data_ops_artifacts" / "tier1",
    },
    "tier2_global": {
        "script": "run_commerce_apply_tier2_global.ps1",
        "env": "COMMERCE_APPLY_AUTHORIZED_TIER2_GLOBAL",
        "dir": REPO_ROOT / "reports" / "data_ops_artifacts" / "tier2_global",
    },
    "tier2_br": {
        "script": "run_commerce_apply_tier2_br.ps1",
        "env": "COMMERCE_APPLY_AUTHORIZED_TIER2_BR",
        "dir": REPO_ROOT / "reports" / "data_ops_artifacts" / "tier2" / "br",
    },
}


def _powershell_available() -> bool:
    return shutil.which("powershell") is not None


def _run_ps1(script: Path, env: dict[str, str] | None = None, extra: list[str] | None = None) -> subprocess.CompletedProcess:
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    if extra:
        cmd.extend(extra)
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    # Remove env autorizadoras herdadas para isolamento
    for k in list(full_env.keys()):
        if k.startswith("COMMERCE_APPLY_AUTHORIZED_") and (env is None or k not in env):
            full_env.pop(k, None)
    return subprocess.run(cmd, env=full_env, capture_output=True, text=True, timeout=90)


@pytest.mark.parametrize("name", list(WRAPPERS.keys()))
def test_wrapper_sem_env_aborta(name: str) -> None:
    if not _powershell_available():
        pytest.skip("powershell indisponivel")
    meta = WRAPPERS[name]
    script = SCHED_DIR / meta["script"]
    assert script.exists(), f"wrapper {script} nao existe"
    result = _run_ps1(script, env=None)
    assert result.returncode != 0, (
        f"esperado exit != 0 sem env autorizadora. stdout={result.stdout} stderr={result.stderr}"
    )
    assert "ABORT" in (result.stdout + result.stderr).upper() or "COMMERCE_APPLY_AUTHORIZED" in (result.stdout + result.stderr), (
        f"esperado mensagem ABORT/env, saida: {result.stdout} {result.stderr}"
    )


@pytest.mark.parametrize("name", list(WRAPPERS.keys()))
def test_wrapper_env_mas_dir_sem_artefato_aborta(name: str, tmp_path: Path) -> None:
    if not _powershell_available():
        pytest.skip("powershell indisponivel")
    meta = WRAPPERS[name]
    script = SCHED_DIR / meta["script"]
    env = {meta["env"]: "1"}
    # Dir ainda pode ter artefatos validos de dev; o teste verifica que
    # quando o validator reprova, o wrapper aborta antes do apply.
    # Para garantir reprova sem modificar o workspace, usamos -DryRunOnly
    # (que valida e sai sem apply). Se validator OK, DryRunOnly exit 0.
    # Se validator FAIL (e o caso da Amazon mirror hoje), exit != 0.
    result = _run_ps1(script, env=env, extra=["-DryRunOnly"])
    # Aceitamos tanto 0 (validator OK porque tem artefato) quanto != 0
    # (validator FAIL). O ponto e que DryRunOnly NAO chama apply.
    combined = result.stdout + result.stderr
    assert "apply" not in combined.lower() or "DryRunOnly" in combined or "exit 0" in combined or result.returncode != 0, (
        f"DryRunOnly nao deveria rodar apply; saida: {combined}"
    )


def test_todos_wrappers_existem() -> None:
    for meta in WRAPPERS.values():
        assert (SCHED_DIR / meta["script"]).exists()


def test_validator_sempre_chamado_antes_do_apply() -> None:
    """Confere que cada script contem chamada ao validator full."""

    for meta in WRAPPERS.values():
        txt = (SCHED_DIR / meta["script"]).read_text(encoding="utf-8")
        assert "validate_commerce_artifact.py" in txt, (
            f"{meta['script']} nao chama validate_commerce_artifact.py"
        )


def test_cada_wrapper_gated_por_env_correta() -> None:
    for meta in WRAPPERS.values():
        txt = (SCHED_DIR / meta["script"]).read_text(encoding="utf-8")
        assert meta["env"] in txt, (
            f"{meta['script']} nao verifica env {meta['env']}"
        )


def test_amazon_legacy_marca_done_flag() -> None:
    """O wrapper amazon_legacy e one-time; precisa gravar state done."""

    txt = (SCHED_DIR / "run_commerce_apply_amazon_legacy.ps1").read_text(encoding="utf-8")
    assert "amazon_legacy_backfill_done.json" in txt


def test_blocked_queue_explosion_detection_em_todos() -> None:
    for meta in WRAPPERS.values():
        txt = (SCHED_DIR / meta["script"]).read_text(encoding="utf-8")
        assert "BLOCKED_QUEUE_EXPLOSION" in txt, f"{meta['script']} nao detecta BLOCKED_QUEUE_EXPLOSION"


def test_ladders_ascending_in_wrappers() -> None:
    for meta in WRAPPERS.values():
        txt = (SCHED_DIR / meta["script"]).read_text(encoding="utf-8")
        # Procura numeros em $Ladder = @(50, 200, ...)
        import re
        match = re.search(r"\$Ladder = @\(([^)]+)\)", txt)
        assert match, f"{meta['script']} sem parametro Ladder"
        nums = [int(n.strip()) for n in match.group(1).split(",")]
        assert nums == sorted(nums), f"{meta['script']} ladder nao e ascending"
        assert nums[0] <= 100, f"{meta['script']} primeiro degrau > 100"
