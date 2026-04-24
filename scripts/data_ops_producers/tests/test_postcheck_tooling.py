"""Testes estaticos/funcionais do tooling de postcheck (Fase 1 da subida 3 fases).

Escopo:
- extract_result_json_from_summary: parsea o bloco ```json``` do summary.md;
- append_run_manifest.py: anexa uma linha JSONL respeitando RUN_MANIFEST_PATH;
- hash_artifact.py: imprime sha256 hex de um arquivo.

Nao executa nenhum acesso ao Render. psycopg2 nao e chamado.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
POSTCHECK_PATH = REPO_ROOT / "scripts" / "data_ops_producers" / "postcheck_run_id.py"
MANIFEST_SCRIPT = REPO_ROOT / "scripts" / "data_ops_producers" / "append_run_manifest.py"
HASH_SCRIPT = REPO_ROOT / "scripts" / "data_ops_producers" / "hash_artifact.py"


def _import_postcheck():
    """Importa postcheck_run_id sem chamar main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("postcheck_run_id", POSTCHECK_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_postcheck_script_existe() -> None:
    assert POSTCHECK_PATH.exists(), f"script nao encontrado: {POSTCHECK_PATH}"
    assert MANIFEST_SCRIPT.exists(), f"script nao encontrado: {MANIFEST_SCRIPT}"
    assert HASH_SCRIPT.exists(), f"script nao encontrado: {HASH_SCRIPT}"


def test_extract_result_json_from_summary(tmp_path: Path) -> None:
    mod = _import_postcheck()
    payload = {
        "inserted": 100,
        "updated": 50,
        "sources_inserted": 80,
        "sources_updated": 20,
        "filtered_notwine_count": 3,
        "would_enqueue_review": 7,
    }
    md_text = (
        "# Commerce DQ V3 Plug\n"
        "\n"
        "- source: `tier1_global`\n"
        "- run_id: `plug_x`\n"
        "\n"
        "## DQ V3 result\n"
        "\n"
        "```json\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + "\n```\n"
    )
    md_path = tmp_path / "summary.md"
    md_path.write_text(md_text, encoding="utf-8")

    got = mod.extract_result_json_from_summary(md_path)
    assert got == payload


def test_extract_result_json_aceita_crlf(tmp_path: Path) -> None:
    mod = _import_postcheck()
    payload = {"inserted": 1}
    md_text = (
        "# header\r\n"
        "\r\n"
        "## DQ V3 result\r\n"
        "\r\n"
        "```json\r\n"
        + json.dumps(payload, indent=2)
        + "\r\n```\r\n"
    )
    md_path = tmp_path / "summary_crlf.md"
    md_path.write_bytes(md_text.encode("utf-8"))
    got = mod.extract_result_json_from_summary(md_path)
    assert got == payload


def test_extract_result_json_falha_sem_bloco(tmp_path: Path) -> None:
    import pytest

    mod = _import_postcheck()
    md_path = tmp_path / "sem_bloco.md"
    md_path.write_text("# so um header\n", encoding="utf-8")
    with pytest.raises(ValueError):
        mod.extract_result_json_from_summary(md_path)


def test_append_run_manifest_via_env(tmp_path: Path) -> None:
    manifest_path = tmp_path / "run_manifest.jsonl"
    env = {
        "RUN_MANIFEST_PATH": str(manifest_path),
        "PATH": __import__("os").environ.get("PATH", ""),
        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
    }
    cmd = [
        sys.executable,
        str(MANIFEST_SCRIPT),
        "--phase",
        "phase_2_execution",
        "--source",
        "tier1_global",
        "--shard-id",
        "tier1_us_001",
        "--country",
        "us",
        "--source-table",
        "vinhos_us_fontes",
        "--min-fonte-id",
        "1",
        "--max-fonte-id",
        "50000",
        "--expected-rows",
        "50000",
        "--artifact-path",
        "reports/data_ops_artifacts/tier1/xyz.jsonl",
        "--artifact-sha256",
        "abc123",
        "--apply-run-id",
        "plug_commerce_dq_v3_tier1_global_20260425_143022",
        "--status",
        "PASS",
        "--started-at",
        "2026-04-25T14:30:22Z",
        "--finished-at",
        "2026-04-25T14:32:45Z",
        "--metrics-json",
        '{"received":50000}',
        "--decision-rationale",
        "shard ok",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    assert manifest_path.exists()
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["shard_id"] == "tier1_us_001"
    assert payload["phase"] == "phase_2_execution"
    assert payload["source"] == "tier1_global"
    assert payload["status"] == "PASS"
    assert payload["metrics"] == {"received": 50000}
    assert payload["decision_rationale"] == "shard ok"
    assert payload["campaign"] == "subida_vinhos_20260424"


def test_append_run_manifest_concatena(tmp_path: Path) -> None:
    manifest_path = tmp_path / "run_manifest.jsonl"
    env = {
        "RUN_MANIFEST_PATH": str(manifest_path),
        "PATH": __import__("os").environ.get("PATH", ""),
        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
    }
    base_cmd = [
        sys.executable,
        str(MANIFEST_SCRIPT),
        "--phase",
        "phase_1",
        "--source",
        "tier1_global",
        "--artifact-path",
        "a.jsonl",
        "--artifact-sha256",
        "deadbeef",
        "--apply-run-id",
        "run_x",
        "--status",
        "PASS",
        "--started-at",
        "2026-04-25T00:00:00Z",
        "--finished-at",
        "2026-04-25T00:01:00Z",
    ]
    for shard in ("shard_a", "shard_b"):
        cmd = list(base_cmd) + ["--shard-id", shard]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        assert proc.returncode == 0, proc.stderr
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    ids = [json.loads(line)["shard_id"] for line in lines]
    assert ids == ["shard_a", "shard_b"]


def test_hash_artifact(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.bin"
    data = b"winegod-postcheck-fixture"
    fixture.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()

    proc = subprocess.run(
        [sys.executable, str(HASH_SCRIPT), str(fixture)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == expected


def test_hash_artifact_arquivo_inexistente(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(HASH_SCRIPT), str(tmp_path / "nope.bin")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "nao existe" in proc.stderr


def test_hash_artifact_uso_incorreto() -> None:
    proc = subprocess.run(
        [sys.executable, str(HASH_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "uso:" in proc.stderr
