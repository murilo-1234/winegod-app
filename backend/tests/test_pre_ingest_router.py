"""Testes do pre_ingest_router.

Fase 2 do `WINEGOD_PRE_INGEST_ROUTER`. Offline — nao toca DB, HTTP ou Gemini.
"""

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))

from pre_ingest_router import run_router, RouterError  # noqa: E402


# ---------- Fixtures ----------

SAMPLE_READY = {
    "nome": "Catena Alta Malbec",
    "produtor": "Catena Zapata",
    "safra": "2020",
    "pais": "ar",
}

SAMPLE_NEEDS = {
    "nome": "Grande Reserva Tinto Especial",
    "produtor": "Vinicola Exemplo Forte",
    "safra": "2020",
}

SAMPLE_NOTWINE = {
    "nome": "Johnnie Walker Black Label Whisky 750ml",
}

SAMPLE_UNCERTAIN = {
    "nome": "Red Wine",
}


def _write_jsonl(path: Path, items):
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


# ---------- Core behavior ----------

def test_roteia_para_4_buckets(tmp_path):
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_READY, SAMPLE_NEEDS, SAMPLE_NOTWINE, SAMPLE_UNCERTAIN])

    r = run_router(
        input_path=str(inp),
        source="unittest_roteia",
        out_dir=str(tmp_path / "out"),
        timestamp="20260421_120000",
    )
    c = r["counts"]
    assert c["total"] == 4
    assert c["ready"] == 1
    assert c["needs_enrichment"] == 1
    assert c["rejected_notwine"] == 1
    assert c["uncertain"] == 1


def test_cria_os_5_arquivos_esperados(tmp_path):
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_READY, SAMPLE_NEEDS, SAMPLE_NOTWINE, SAMPLE_UNCERTAIN])

    r = run_router(
        input_path=str(inp),
        source="unittest_arquivos",
        out_dir=str(tmp_path / "out"),
        timestamp="20260421_120000",
    )
    out_dir = r["out_dir"]
    esperados = [
        "ready.jsonl",
        "needs_enrichment.jsonl",
        "rejected_notwine.jsonl",
        "uncertain_review.csv",
        "summary.md",
    ]
    for name in esperados:
        p = Path(out_dir) / name
        assert p.exists(), f"faltando: {name}"


def test_ready_jsonl_contem_metadados_e_preserva_campos(tmp_path):
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_READY])

    r = run_router(
        input_path=str(inp),
        source="unittest_meta",
        out_dir=str(tmp_path / "out"),
        timestamp="20260421_120000",
    )
    ready_file = Path(r["out_dir"]) / "ready.jsonl"
    lines = [l for l in ready_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    # campos originais preservados
    for k in ("nome", "produtor", "safra", "pais"):
        assert obj[k] == SAMPLE_READY[k], f"{k} nao preservado"
    # metadados do router
    assert obj["_router_status"] == "ready"
    assert isinstance(obj["_router_reasons"], list)
    assert obj["_router_source"] == "unittest_meta"
    assert obj["_router_index"] == 0


def test_uncertain_csv_tem_header_correto_e_raw_json(tmp_path):
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_UNCERTAIN])

    r = run_router(
        input_path=str(inp),
        source="unittest_csv",
        out_dir=str(tmp_path / "out"),
        timestamp="20260421_120000",
    )
    csv_path = Path(r["out_dir"]) / "uncertain_review.csv"
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows = list(reader)

    expected_header = [
        "router_index", "source", "nome", "produtor", "safra",
        "pais", "regiao", "sub_regiao", "ean_gtin", "reasons", "raw_json",
    ]
    assert header == expected_header
    assert len(rows) == 1
    row = rows[0]
    assert row["router_index"] == "0"
    assert row["source"] == "unittest_csv"
    assert row["nome"] == "Red Wine"
    assert row["reasons"]  # nao vazio
    raw = json.loads(row["raw_json"])
    assert raw["nome"] == "Red Wine"
    # raw_json nao deve ter os metadados do router
    assert "_router_status" not in raw


def test_summary_contem_contadores(tmp_path):
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_READY, SAMPLE_NEEDS, SAMPLE_NOTWINE, SAMPLE_UNCERTAIN])

    r = run_router(
        input_path=str(inp),
        source="unittest_summary",
        out_dir=str(tmp_path / "out"),
        timestamp="20260421_120000",
    )
    summary = (Path(r["out_dir"]) / "summary.md").read_text(encoding="utf-8")
    assert "total received | 4" in summary
    assert "ready | 1" in summary
    assert "needs_enrichment | 1" in summary
    assert "rejected_notwine | 1" in summary
    assert "uncertain | 1" in summary
    assert "ingest_via_bulk.py" in summary
    # Comando sugerido e dry-run explicito — nao deve ter --apply na invocacao.
    # Extrai blocos de codigo e verifica que NENHUM contem --apply como flag.
    import re as _re
    code_blocks = _re.findall(r"```.*?\n(.*?)```", summary, flags=_re.DOTALL)
    assert code_blocks, "summary deve ter pelo menos um bloco de codigo"
    for block in code_blocks:
        assert "--apply" not in block, f"comando sugerido NAO pode ter --apply: {block}"


def test_summary_warning_quando_uncertain_maior_que_20pct(tmp_path):
    # 5 uncertain + 1 ready = 83% uncertain
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_UNCERTAIN] * 5 + [SAMPLE_READY])

    r = run_router(
        input_path=str(inp),
        source="unittest_warning",
        out_dir=str(tmp_path / "out"),
        timestamp="20260421_120000",
    )
    summary = (Path(r["out_dir"]) / "summary.md").read_text(encoding="utf-8")
    assert "WARNING" in summary
    assert "20%" in summary
    # exit ainda e 0 — warning nao bloqueia
    assert r["counts"]["uncertain"] == 5


def test_summary_sem_warning_quando_uncertain_baixo(tmp_path):
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_READY] * 10 + [SAMPLE_UNCERTAIN])

    r = run_router(
        input_path=str(inp),
        source="unittest_sem_warning",
        out_dir=str(tmp_path / "out"),
        timestamp="20260421_120000",
    )
    summary = (Path(r["out_dir"]) / "summary.md").read_text(encoding="utf-8")
    assert "WARNING" not in summary


def test_router_nao_bloqueia_quando_ha_uncertain(tmp_path):
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_UNCERTAIN, SAMPLE_UNCERTAIN, SAMPLE_READY])

    r = run_router(
        input_path=str(inp),
        source="unittest_nao_bloqueia",
        out_dir=str(tmp_path / "out"),
        timestamp="20260421_120000",
    )
    assert r["counts"]["uncertain"] == 2
    assert r["counts"]["ready"] == 1
    # todos os arquivos ainda criados
    assert (Path(r["out_dir"]) / "ready.jsonl").exists()
    assert (Path(r["out_dir"]) / "uncertain_review.csv").exists()


# ---------- Erros ----------

def test_erro_input_inexistente(tmp_path):
    with pytest.raises(RouterError, match="input_nao_existe"):
        run_router(
            input_path=str(tmp_path / "nao_existe.jsonl"),
            source="unittest_no_input",
            out_dir=str(tmp_path / "out"),
            timestamp="20260421_120000",
        )


def test_erro_jsonl_invalido(tmp_path):
    inp = tmp_path / "bad.jsonl"
    inp.write_text('{"nome":"ok"}\nnao eh json\n', encoding="utf-8")
    with pytest.raises(RouterError, match="jsonl_invalido"):
        run_router(
            input_path=str(inp),
            source="unittest_bad",
            out_dir=str(tmp_path / "out"),
            timestamp="20260421_120000",
        )


def test_erro_linha_nao_objeto(tmp_path):
    inp = tmp_path / "bad.jsonl"
    inp.write_text('{"nome":"ok"}\n["array","at","top"]\n', encoding="utf-8")
    with pytest.raises(RouterError, match="jsonl_linha_nao_objeto"):
        run_router(
            input_path=str(inp),
            source="unittest_array",
            out_dir=str(tmp_path / "out"),
            timestamp="20260421_120000",
        )


def test_linhas_em_branco_sao_ignoradas(tmp_path):
    inp = tmp_path / "with_blanks.jsonl"
    inp.write_text(
        json.dumps(SAMPLE_READY, ensure_ascii=False) + "\n"
        "\n"
        "   \n"
        + json.dumps(SAMPLE_UNCERTAIN, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    r = run_router(
        input_path=str(inp),
        source="unittest_blanks",
        out_dir=str(tmp_path / "out"),
        timestamp="20260421_120000",
    )
    assert r["counts"]["total"] == 2


def test_source_vazio_leva_a_erro(tmp_path):
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_READY])
    with pytest.raises(RouterError, match="source_invalido"):
        run_router(
            input_path=str(inp),
            source="",
            out_dir=str(tmp_path / "out"),
            timestamp="20260421_120000",
        )


# ---------- Hardening: sanitizacao de source ----------

def _prep_input(tmp_path):
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_READY])
    return inp


@pytest.mark.parametrize("bad_source,match", [
    ("minha fonte", "contem_espaco"),
    ("foo bar", "contem_espaco"),
    ("../escape", "path_traversal"),
    ("foo/..", "path_traversal"),
    ("foo/bar", "contem_barra"),
    ("foo\\bar", "contem_barra"),
    ("producao", None),  # controle: SEM acento passa
    ("produção", "so_aceita"),
    ("x:y", "so_aceita"),
    ("x@y", "so_aceita"),
    ("x*y", "so_aceita"),
])
def test_source_sanitizacao(tmp_path, bad_source, match):
    inp = _prep_input(tmp_path)
    if match is None:
        # caso de controle — deve passar
        r = run_router(
            input_path=str(inp),
            source=bad_source,
            out_dir=str(tmp_path / "out"),
            timestamp="20260421_120000",
        )
        assert r["counts"]["total"] == 1
    else:
        with pytest.raises(RouterError, match=f"source_invalido.*{match}"):
            run_router(
                input_path=str(inp),
                source=bad_source,
                out_dir=str(tmp_path / "out"),
                timestamp="20260421_120000",
            )


@pytest.mark.parametrize("good_source", [
    "scraping_real_20260421",
    "vivino_batch_001",
    "loja-x",
    "source.v2",
    "ABC_123-def.ghi",
])
def test_source_valido_cria_diretorio_esperado(tmp_path, good_source):
    inp = _prep_input(tmp_path)
    r = run_router(
        input_path=str(inp),
        source=good_source,
        out_dir=str(tmp_path / "out"),
        timestamp="20260421_120000",
    )
    expected = tmp_path / "out" / f"20260421_120000_{good_source}"
    assert Path(r["out_dir"]) == expected
    assert expected.is_dir()
    # _router_source preserva exatamente o valor validado
    ready = Path(r["out_dir"]) / "ready.jsonl"
    obj = json.loads(ready.read_text(encoding="utf-8").splitlines()[0])
    assert obj["_router_source"] == good_source


# ---------- Hardening: default out-dir ancorado em repo root ----------

def test_default_out_dir_aponta_para_repo_root(tmp_path, monkeypatch):
    """Mesmo rodando de outro cwd, out_dir default aponta pra <repo_root>/reports/ingest_pipeline."""
    import pre_ingest_router as mod
    monkeypatch.chdir(tmp_path)  # cwd diferente do repo root
    resolved = mod._resolve_out_dir(None)
    assert resolved.is_absolute()
    assert resolved.parts[-2:] == ("reports", "ingest_pipeline")
    # E anchored em repo root (nao em tmp_path)
    assert Path(tmp_path).resolve() not in resolved.resolve().parents
    # repo root e o pai do diretorio `scripts/`
    assert (mod._REPO_ROOT / "scripts").is_dir()


def test_out_dir_customizado_e_respeitado(tmp_path):
    inp = _prep_input(tmp_path)
    custom = tmp_path / "custom_out"
    r = run_router(
        input_path=str(inp),
        source="custom_src",
        out_dir=str(custom),
        timestamp="20260421_120000",
    )
    assert Path(r["out_dir"]).resolve() == (custom / "20260421_120000_custom_src").resolve()


# ---------- Hardening: nao criar diretorio em erro de input ----------

def test_input_inexistente_nao_cria_diretorio_de_output(tmp_path):
    out_base = tmp_path / "out_should_not_exist"
    assert not out_base.exists()
    with pytest.raises(RouterError, match="input_nao_existe"):
        run_router(
            input_path=str(tmp_path / "nope.jsonl"),
            source="valid_src",
            out_dir=str(out_base),
            timestamp="20260421_120000",
        )
    assert not out_base.exists(), "diretorio nao pode ter sido criado antes de validar input"


def test_jsonl_invalido_nao_cria_diretorio_de_output(tmp_path):
    inp = tmp_path / "bad.jsonl"
    inp.write_text("nao eh json\n", encoding="utf-8")
    out_base = tmp_path / "out_should_not_exist"
    with pytest.raises(RouterError, match="jsonl_invalido"):
        run_router(
            input_path=str(inp),
            source="valid_src",
            out_dir=str(out_base),
            timestamp="20260421_120000",
        )
    assert not out_base.exists()


def test_source_invalido_nao_cria_diretorio(tmp_path):
    inp = _prep_input(tmp_path)
    out_base = tmp_path / "out_should_not_exist"
    with pytest.raises(RouterError, match="source_invalido"):
        run_router(
            input_path=str(inp),
            source="foo bar",
            out_dir=str(out_base),
            timestamp="20260421_120000",
        )
    assert not out_base.exists()


# ---------- CLI integracao ----------

def test_cli_exit_zero_em_sucesso(tmp_path):
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_READY, SAMPLE_UNCERTAIN])
    script = os.path.join(_REPO_ROOT, "scripts", "pre_ingest_router.py")
    r = subprocess.run(
        [sys.executable, script,
         "--input", str(inp),
         "--source", "cli_smoke",
         "--out-dir", str(tmp_path / "out"),
         "--timestamp", "20260421_120000"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["total"] == 2
    assert out["ready"] == 1
    assert out["uncertain"] == 1


def test_cli_exit_um_quando_input_invalido(tmp_path):
    script = os.path.join(_REPO_ROOT, "scripts", "pre_ingest_router.py")
    r = subprocess.run(
        [sys.executable, script,
         "--input", str(tmp_path / "nao_existe.jsonl"),
         "--source", "cli_erro",
         "--out-dir", str(tmp_path / "out"),
         "--timestamp", "20260421_120000"],
        capture_output=True, text=True,
    )
    assert r.returncode == 1
    assert "input_nao_existe" in r.stderr


def test_ready_jsonl_nao_quebra_ingest_via_bulk_shape(tmp_path):
    """ready.jsonl adiciona so campos `_router_*` — shape compativel."""
    inp = tmp_path / "in.jsonl"
    _write_jsonl(inp, [SAMPLE_READY])
    r = run_router(
        input_path=str(inp),
        source="unittest_shape",
        out_dir=str(tmp_path / "out"),
        timestamp="20260421_120000",
    )
    ready_file = Path(r["out_dir"]) / "ready.jsonl"
    obj = json.loads(ready_file.read_text(encoding="utf-8").splitlines()[0])
    # todos os campos originais existem e preservados
    for k, v in SAMPLE_READY.items():
        assert obj[k] == v
    # extras comecam com _router_
    extras = [k for k in obj if k not in SAMPLE_READY]
    assert all(k.startswith("_router_") for k in extras)


if __name__ == "__main__":
    # Compat com runner nativo (sem pytest)
    tests = sorted(name for name in globals() if name.startswith("test_"))
    passed = failed = 0
    for name in tests:
        try:
            fn = globals()[name]
            import inspect
            sig = inspect.signature(fn)
            if "tmp_path" in sig.parameters:
                import tempfile
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            else:
                fn()
            print(f"  PASS {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
