"""Testes offline de scripts/enrich_needs.py — mock de Gemini.

Nao chama Gemini real. Nao toca DB. Nao faz HTTP.

Roda com:
    python -m pytest backend/tests/test_enrich_needs.py -q
    python backend/tests/test_enrich_needs.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "scripts"))

from enrich_needs import (  # noqa: E402
    classify_post_enrichment,
    item_to_ocr,
    merge_enriched,
    run_enrich,
    _has_minimum_fields,
    _iso2,
    _map_style,
    _vintage_to_str,
    _abv_to_float,
    _extract_country_hint_from_url,
    _extract_country_hint_from_text,
    _collect_source_hints,
    _detect_country_conflict,
)


# ---------- helpers de mock ----------

def _mock_wine_ready(original: dict) -> dict:
    """Gemini retornou wine completo com country+region."""
    return {
        "index": 1,
        "kind": "wine",
        "full_name": original.get("nome") or "Chateau Mocked Wine",
        "producer": original.get("produtor") or "Chateau Mocked",
        "wine_name": None,
        "country_code": "FR",
        "style": "red",
        "grape": "Cabernet Sauvignon",
        "region": "Bordeaux",
        "sub_region": None,
        "vintage": "2020",
        "abv": 13.5,
        "classification": "AOC",
        "body": "medio",
        "pairing": "carne vermelha",
        "sweetness": "seco",
        "estimated_note": None,
        "confidence": 0.9,
        "source_model": "mock",
        "escalated": False,
    }


def _mock_not_wine(_original: dict) -> dict:
    return {"index": 1, "kind": "not_wine", "confidence": 0.95,
            "source_model": "mock", "escalated": False}


def _mock_spirit(_original: dict) -> dict:
    return {"index": 1, "kind": "spirit", "confidence": 0.9,
            "source_model": "mock", "escalated": False}


def _mock_unknown(_original: dict) -> dict:
    return {"index": 1, "kind": "unknown", "confidence": 0.3,
            "source_model": "mock", "escalated": False}


def _mock_wine_but_missing(_original: dict) -> dict:
    """wine mas sem producer/country — deve cair em uncertain pos-merge."""
    return {"index": 1, "kind": "wine",
            "full_name": "Red", "producer": None,
            "country_code": None, "region": None,
            "confidence": 0.4, "source_model": "mock"}


def make_enrich_fn(per_item_fn):
    """Constroi funcao que simula enrich_items_v3."""
    def _fn(ocr_items, source_channel=None):
        parsed = []
        for i, ocr in enumerate(ocr_items):
            # Chama per_item_fn passando o dict ocr (nao o original) —
            # nos testes, cada funcao nao precisa do original pois ja
            # tem conteudo canned.
            r = per_item_fn(ocr.get("ocr", {}))
            r["index"] = i + 1
            parsed.append(r)
        return {"items": parsed, "raw_primary": "mock",
                "raw_escalated": "mock", "stats": {}}
    return _fn


# ---------- helpers puros ----------

def test_iso2():
    assert _iso2("FR") == "fr"
    assert _iso2("br") == "br"
    assert _iso2("Brasil") is None
    assert _iso2(None) is None


def test_map_style():
    assert _map_style("red") == "tinto"
    assert _map_style("Tinto") == "tinto"
    assert _map_style("sparkling") == "espumante"
    assert _map_style("xxx") is None
    assert _map_style(None) is None


def test_vintage_to_str():
    assert _vintage_to_str("2020") == "2020"
    assert _vintage_to_str(2020) == "2020"
    assert _vintage_to_str("xx") is None
    assert _vintage_to_str("1800") is None


def test_abv_to_float():
    assert _abv_to_float("13.5%") == 13.5
    assert _abv_to_float("13,5") == 13.5
    assert _abv_to_float(100) is None  # fora da range < 30
    assert _abv_to_float(None) is None


# ---------- item_to_ocr ----------

def test_item_to_ocr_campos_minimos():
    it = {"nome": "Chateau X", "produtor": "Produtor X"}
    ocr = item_to_ocr(it)
    assert ocr == {"ocr": {
        "name": "Chateau X", "producer": "Produtor X", "vintage": "",
        "region": "", "grape": "", "line": "", "classification": "",
    }}


def test_item_to_ocr_com_uvas_lista():
    it = {"nome": "X", "uvas": ["Malbec", "Merlot"]}
    ocr = item_to_ocr(it)
    assert ocr["ocr"]["grape"] == "Malbec, Merlot"


def test_item_to_ocr_com_uvas_json():
    it = {"nome": "X", "uvas": '["Syrah"]'}
    ocr = item_to_ocr(it)
    assert ocr["ocr"]["grape"] == "Syrah"


# ---------- merge_enriched ----------

def test_merge_nao_sobrescreve_campos_presentes():
    orig = {"nome": "Orig Name", "produtor": "Orig Producer", "pais": "ar"}
    enriched = {"kind": "wine", "full_name": "Gemini Name",
                "producer": "Gemini Producer", "country_code": "FR"}
    m = merge_enriched(orig, enriched)
    assert m["nome"] == "Orig Name"
    assert m["produtor"] == "Orig Producer"
    assert m["pais"] == "ar"


def test_merge_preenche_campos_ausentes():
    orig = {"produtor": "Chateau Real Producer"}
    enriched = _mock_wine_ready(orig)
    m = merge_enriched(orig, enriched)
    assert m["produtor"] == "Chateau Real Producer"  # preservado
    assert m["nome"] == "Chateau Mocked Wine"
    assert m["pais"] == "fr"
    assert m["regiao"] == "Bordeaux"
    assert m["tipo"] == "tinto"
    assert m["uvas"] == '["Cabernet Sauvignon"]'
    assert m["safra"] == "2020"
    assert m["teor_alcoolico"] == 13.5
    assert m["_enriched_kind"] == "wine"
    assert m["_enriched_confidence"] == 0.9


# ---------- classify_post_enrichment ----------

def test_classify_post_not_wine():
    orig = {"nome": "X", "produtor": "Y"}
    bucket, _, reasons = classify_post_enrichment(orig, _mock_not_wine(orig))
    assert bucket == "enriched_not_wine"
    assert "gemini_kind=not_wine" in reasons


def test_classify_post_spirit():
    bucket, _, _ = classify_post_enrichment({"nome": "X"}, _mock_spirit({}))
    assert bucket == "enriched_not_wine"


def test_classify_post_unknown_vai_uncertain():
    bucket, _, _ = classify_post_enrichment({"nome": "X"}, _mock_unknown({}))
    assert bucket == "enriched_uncertain"


def test_classify_post_wine_ready():
    orig = {"nome": "Chateau Real Producer Grande", "produtor": "Chateau Real Producer"}
    bucket, final, _ = classify_post_enrichment(orig, _mock_wine_ready(orig))
    assert bucket == "enriched_ready"
    assert final["pais"] == "fr"
    assert final["_post_enrich_status"] == "ready"


def test_classify_post_wine_mas_sem_campos_minimos():
    bucket, _, reasons = classify_post_enrichment(
        {"nome": None, "produtor": None},
        _mock_wine_but_missing({}),
    )
    assert bucket == "enriched_uncertain"


# ---------- _has_minimum_fields ----------

def test_has_minimum_fields_positivo():
    assert _has_minimum_fields({"nome": "X", "produtor": "Y", "pais": "fr"})


def test_has_minimum_fields_sem_ancora():
    assert not _has_minimum_fields({"nome": "X", "produtor": "Y"})


def test_has_minimum_fields_sem_produtor_com_ean():
    assert _has_minimum_fields({"nome": "X", "ean_gtin": "7891234567890"})


# ---------- run_enrich: plan_only ----------

def _write_needs(tmp_path: Path, items) -> Path:
    p = tmp_path / "needs.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return p


def test_run_enrich_plan_only_nao_chama_gemini(tmp_path):
    inp = _write_needs(tmp_path, [{"nome": "X"}, {"nome": "Y"}])
    r = run_enrich(
        input_path=str(inp),
        source="ut_plan",
        limit=5,
        out_dir=tmp_path / "out",
        confirm_gemini=False,
    )
    assert r["mode"] == "plan_only"
    assert r["confirmed_gemini"] is False
    assert r["input_needs"] == 2
    # plan_only nao cria dir
    assert not (tmp_path / "out").exists()


def test_run_enrich_source_invalido(tmp_path):
    inp = _write_needs(tmp_path, [{"nome": "X"}])
    with pytest.raises(ValueError, match="source_invalido"):
        run_enrich(
            input_path=str(inp),
            source="bad source",
            limit=5,
            out_dir=tmp_path / "out",
            confirm_gemini=True,
            enrich_fn=make_enrich_fn(_mock_wine_ready),
        )


def test_run_enrich_limit_invalido(tmp_path):
    inp = _write_needs(tmp_path, [{"nome": "X"}])
    with pytest.raises(ValueError, match="limit_invalido"):
        run_enrich(
            input_path=str(inp),
            source="ok",
            limit=0,
            out_dir=tmp_path / "out",
            confirm_gemini=True,
            enrich_fn=make_enrich_fn(_mock_wine_ready),
        )


# ---------- run_enrich: modo real com mock ----------

def test_run_enrich_real_cria_4_saidas(tmp_path):
    items = [
        {"nome": "Chateau Real Producer Grande", "produtor": "Chateau Real Producer",
         "_router_index": 0},
        {"nome": "Chateau Real Producer Grande", "produtor": "Chateau Real Producer",
         "_router_index": 1},
    ]
    inp = _write_needs(tmp_path, items)
    r = run_enrich(
        input_path=str(inp),
        source="ut_real",
        limit=5,
        out_dir=tmp_path / "out",
        confirm_gemini=True,
        enrich_fn=make_enrich_fn(_mock_wine_ready),
    )
    out_dir = Path(r["out_dir"])
    assert (out_dir / "enriched_ready.jsonl").exists()
    assert (out_dir / "enriched_not_wine.jsonl").exists()
    assert (out_dir / "enriched_uncertain_review.csv").exists()
    assert (out_dir / "enriched_summary.md").exists()
    assert (out_dir / "raw_gemini_response.jsonl").exists()
    assert r["mode"] == "gemini_real"
    assert r["gemini_wine"] == 2
    assert r["post_ready"] == 2


def test_run_enrich_real_not_wine_bucket(tmp_path):
    items = [{"nome": "X", "produtor": "Y"}]
    inp = _write_needs(tmp_path, items)
    r = run_enrich(
        input_path=str(inp), source="ut_notwine", limit=5,
        out_dir=tmp_path / "out", confirm_gemini=True,
        enrich_fn=make_enrich_fn(_mock_not_wine),
    )
    assert r["gemini_not_wine"] == 1
    assert r["post_ready"] == 0
    nw_file = Path(r["out_dir"]) / "enriched_not_wine.jsonl"
    lines = [l for l in nw_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1


def test_run_enrich_real_unknown_vai_uncertain(tmp_path):
    items = [{"nome": "X", "produtor": "Y"}]
    inp = _write_needs(tmp_path, items)
    r = run_enrich(
        input_path=str(inp), source="ut_unknown", limit=5,
        out_dir=tmp_path / "out", confirm_gemini=True,
        enrich_fn=make_enrich_fn(_mock_unknown),
    )
    assert r["gemini_unknown"] == 1
    csv_file = Path(r["out_dir"]) / "enriched_uncertain_review.csv"
    text = csv_file.read_text(encoding="utf-8")
    assert "kind,confidence" in text.split("\n")[0]
    # Warning no summary quando unknown > 20%
    summary = (Path(r["out_dir"]) / "enriched_summary.md").read_text(encoding="utf-8")
    assert "WARNING" in summary


def test_run_enrich_summary_sem_warning_quando_baixo(tmp_path):
    # 4 wines + 1 unknown = 20% unknown — exatamente no limite (>20 e strict)
    items = [{"nome": "Y Premier Grand Cru", "produtor": "Chateau X"}] * 4 + [
        {"nome": "Z", "produtor": "W"}
    ]
    inp = _write_needs(tmp_path, items)

    def per_item(ocr):
        # 4 ready + 1 unknown
        global _CALL_COUNT  # not truly global here, just a closure trick
        _CALL_COUNT = globals().setdefault("_CALL_COUNT", 0) + 1
        globals()["_CALL_COUNT"] = _CALL_COUNT
        if _CALL_COUNT == 5:
            globals()["_CALL_COUNT"] = 0
            return _mock_unknown(ocr)
        return _mock_wine_ready(ocr)

    r = run_enrich(
        input_path=str(inp), source="ut_warn", limit=10,
        out_dir=tmp_path / "out", confirm_gemini=True,
        enrich_fn=make_enrich_fn(per_item),
    )
    assert r["gemini_unknown"] == 1
    # 1/5 = 20% — nao estritamente > 20, sem warning
    summary = (Path(r["out_dir"]) / "enriched_summary.md").read_text(encoding="utf-8")
    assert "WARNING" not in summary


def test_run_enrich_raw_audit_tem_linha_por_item(tmp_path):
    items = [{"nome": "X"}, {"nome": "Y"}, {"nome": "Z"}]
    inp = _write_needs(tmp_path, items)
    r = run_enrich(
        input_path=str(inp), source="ut_audit", limit=5,
        out_dir=tmp_path / "out", confirm_gemini=True,
        enrich_fn=make_enrich_fn(_mock_unknown),
    )
    audit = Path(r["out_dir"]) / "raw_gemini_response.jsonl"
    lines = [l for l in audit.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 3
    for line in lines:
        obj = json.loads(line)
        assert "parsed" in obj and "enriched" in obj and "bucket" in obj


# ============ Guardrails factuais ============

def test_hint_url_worldwine_fr():
    iso, reason = _extract_country_hint_from_url(
        "https://www.worldwine.com.br/vin-fr-two-birds-one-stone-tt-rouge-750-028963/p"
    )
    assert iso == "fr"
    assert reason == "url_prefix:vin-fr"


def test_hint_url_worldwine_cl():
    iso, reason = _extract_country_hint_from_url(
        "https://www.worldwine.com.br/vin-chl-concha-y-toro-reserva/p"
    )
    assert iso == "cl"
    assert "vin-chl" in reason


def test_hint_url_worldwine_ch_vira_cl():
    # Convencao do brief: 'ch' no scraper WorldWine = Chile, nao Suica
    iso, reason = _extract_country_hint_from_url(
        "https://www.worldwine.com.br/vin-ch-xxxx/p"
    )
    assert iso == "cl"
    assert reason == "url_prefix:vin-ch"


def test_hint_url_outro_dominio_sem_match():
    iso, reason = _extract_country_hint_from_url(
        "https://loja.x.com.br/produto/123"
    )
    assert iso is None and reason is None


def test_hint_url_none():
    iso, reason = _extract_country_hint_from_url(None)
    assert iso is None and reason is None


def test_hint_texto_vin_de_france():
    iso, reason = _extract_country_hint_from_text(
        "Vin de France — Languedoc-Roussillon"
    )
    assert iso == "fr"
    assert reason in ("text:vin_de_france", "text:languedoc", "text:roussillon")


def test_hint_texto_rioja():
    iso, _ = _extract_country_hint_from_text("Rioja Reserva 2018")
    assert iso == "es"


def test_hint_texto_sem_match():
    iso, reason = _extract_country_hint_from_text("Red Wine 750ml")
    assert iso is None and reason is None


def test_hint_texto_acentos():
    iso, _ = _extract_country_hint_from_text("Côtes du Rhône")
    # match: "cotes du rhone" nao esta na lista exata; "rhone" sim
    assert iso == "fr"


def test_collect_source_hints_ordem():
    original = {
        "pais": "fr",
        "url_original": "https://worldwine.com.br/vin-es-xxx/p",
        "descricao": "Vinho da Italia, toscana",
    }
    hints = _collect_source_hints(original)
    assert hints[0] == ("fr", "original_pais")  # pais original vem primeiro


def test_detect_conflict_two_birds_caso_real():
    """Reproduz o caso detectado pelo Codex: Gemini CL vs URL vin-fr-."""
    original = {
        "nome": "Two Birds One Stone Carignan",
        "url_original": "https://www.worldwine.com.br/vin-fr-two-birds-one-stone-tt-rouge-750-028963/p",
        "descricao": "Vin de France — Languedoc-Roussillon",
    }
    enriched = {"kind": "wine", "country_code": "CL",
                "producer": "Domaine Mocked", "region": "Valle del Maule"}
    conflict = _detect_country_conflict(original, enriched)
    assert conflict is not None
    assert conflict["gemini_pais"] == "cl"
    assert conflict["source_hint_pais"] == "fr"
    assert conflict["source_hint_reason"] == "url_prefix:vin-fr"


def test_detect_conflict_sem_conflito_gemini_bate():
    original = {
        "url_original": "https://www.worldwine.com.br/vin-fr-xxxx/p",
    }
    enriched = {"kind": "wine", "country_code": "FR",
                "producer": "Chateau X", "region": "Bordeaux"}
    assert _detect_country_conflict(original, enriched) is None


def test_detect_conflict_gemini_contradiz_pais_original():
    original = {"pais": "ar"}
    enriched = {"kind": "wine", "country_code": "CL",
                "producer": "X", "region": "Maipo"}
    conflict = _detect_country_conflict(original, enriched)
    assert conflict["gemini_pais"] == "cl"
    assert conflict["source_hint_pais"] == "ar"
    assert conflict["source_hint_reason"] == "original_pais"


def test_detect_conflict_sem_hint_retorna_none():
    original = {"nome": "X"}
    enriched = {"kind": "wine", "country_code": "FR", "producer": "Y"}
    assert _detect_country_conflict(original, enriched) is None


def test_classify_post_two_birds_vai_uncertain(tmp_path):
    original = {
        "nome": "Two Birds One Stone Carignan",
        "url_original": "https://www.worldwine.com.br/vin-fr-two-birds-one-stone-tt-rouge-750-028963/p",
        "descricao": "Vin de France — Languedoc-Roussillon",
    }
    enriched = {
        "kind": "wine",
        "full_name": "Two Birds One Stone Carignan",
        "producer": "Domaine Mocked",
        "country_code": "CL",
        "region": "Valle del Maule",
        "confidence": 0.9,
    }
    bucket, final_item, reasons = classify_post_enrichment(original, enriched)
    assert bucket == "enriched_uncertain"
    assert any(r == "qa_conflict:country_hint_mismatch" for r in reasons)
    assert any(r == "gemini_pais=cl" for r in reasons)
    assert any(r == "source_hint_pais=fr" for r in reasons)
    assert any("source_hint_reason=url_prefix:vin-fr" in r for r in reasons)
    # NAO deve ter mergeado pais=cl no item
    assert final_item.get("pais") != "cl"


def test_classify_post_sem_conflito_continua_ready():
    original = {
        "nome": "Two Birds One Stone Carignan",
        "url_original": "https://www.worldwine.com.br/vin-fr-two-birds-one-stone-tt-rouge-750-028963/p",
        "descricao": "Vin de France — Languedoc-Roussillon",
    }
    enriched = {
        "kind": "wine",
        "full_name": "Two Birds One Stone Carignan Rouge",
        "producer": "Domaine Mocked Languedoc",
        "country_code": "FR",
        "region": "Languedoc-Roussillon",
        "confidence": 0.9,
    }
    bucket, _, _ = classify_post_enrichment(original, enriched)
    assert bucket == "enriched_ready"


def test_run_enrich_from_raw_nao_chama_gemini(tmp_path):
    """--from-raw reprocessa sem chamar Gemini."""
    # Input original com o caso Two Birds
    items = [{
        "_router_index": 0,
        "nome": "Two Birds One Stone Carignan",
        "url_original": "https://www.worldwine.com.br/vin-fr-two-birds-one-stone-tt-rouge-750-028963/p",
        "descricao": "Vin de France",
    }]
    inp = _write_needs(tmp_path, items)

    # Raw cache simulado (como o raw_gemini_response.jsonl real)
    raw = [{
        "router_index": 0,
        "nome_original": "Two Birds One Stone Carignan",
        "produtor_original": None,
        "parsed": {"kind": "wine"},
        "enriched": {
            "kind": "wine",
            "full_name": "Two Birds One Stone Carignan",
            "producer": "Domaine Mocked",
            "country_code": "CL",
            "region": "Valle del Maule",
            "confidence": 0.9,
        },
        "bucket": "enriched_ready",
        "reasons": [],
    }]
    raw_path = tmp_path / "raw.jsonl"
    raw_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in raw),
        encoding="utf-8",
    )

    # Se Gemini fosse chamado, falharia — garantimos que nao ha enrich_fn
    # e confirm_gemini=False: precisa funcionar via from-raw.
    r = run_enrich(
        input_path=str(inp),
        source="ut_fromraw",
        limit=5,
        out_dir=tmp_path / "out",
        confirm_gemini=False,
        raw_cache_path=str(raw_path),
    )
    assert r["mode"] == "gemini_cached"
    assert r["from_raw"] is True
    # Guardrail deve ter disparado: 1 qa_conflict, 0 ready
    assert r["qa_conflicts"] == 1
    assert r["post_ready"] == 0
    assert r["post_uncertain"] == 1


def test_run_enrich_respeita_limit(tmp_path):
    items = [{"nome": f"X{i}"} for i in range(20)]
    inp = _write_needs(tmp_path, items)
    r = run_enrich(
        input_path=str(inp), source="ut_limit", limit=5,
        out_dir=tmp_path / "out", confirm_gemini=True,
        enrich_fn=make_enrich_fn(_mock_unknown),
    )
    assert r["input_needs"] == 5  # cortou a 5


if __name__ == "__main__":
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
