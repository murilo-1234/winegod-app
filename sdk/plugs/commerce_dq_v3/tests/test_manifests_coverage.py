"""Testes de cobertura dos manifests commerce.

Garantias:
- todos os manifests `commerce_*.yaml` declaram `plug:commerce_dq_v3`;
- apenas `commerce_dq_v3` escreve em `public.wines` / `public.wine_sources`;
- commerce nao declara `public.stores` / `public.wine_scores` como output;
- flags travadas: `can_create_wine_sources=false`, `requires_dq_v3=false`,
  `requires_matching=false` (alinhado com o contrato);
- `plug_commerce_dq_v3` e dono (familia=commerce em todos).
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFESTS_DIR = REPO_ROOT / "sdk" / "adapters" / "manifests"


def _load_commerce_manifests() -> list[dict]:
    if yaml is None:
        pytest.skip("pyyaml nao instalado")
    out: list[dict] = []
    for p in sorted(MANIFESTS_DIR.glob("commerce_*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        data["_path"] = str(p.name)
        out.append(data)
    return out


def test_existem_manifests_commerce() -> None:
    ms = _load_commerce_manifests()
    assert len(ms) >= 8, f"esperado >=8 manifests commerce, achou {len(ms)}: {[m['_path'] for m in ms]}"


def test_todos_sao_family_commerce() -> None:
    ms = _load_commerce_manifests()
    for m in ms:
        assert m.get("family") == "commerce", f"{m['_path']}: family!=commerce"


def test_todos_tem_tag_plug_commerce_dq_v3() -> None:
    ms = _load_commerce_manifests()
    for m in ms:
        tags = m.get("tags") or []
        assert "plug:commerce_dq_v3" in tags, f"{m['_path']}: falta tag plug:commerce_dq_v3"


def test_nenhum_declara_wine_scores() -> None:
    ms = _load_commerce_manifests()
    for m in ms:
        fields = m.get("declared_fields") or []
        if isinstance(fields, list):
            fields_flat = [str(f) for f in fields]
        else:
            fields_flat = [str(fields)]
        for f in fields_flat:
            assert "wine_score" not in f.lower(), f"{m['_path']}: declara wine_score"


def test_flags_travadas() -> None:
    ms = _load_commerce_manifests()
    for m in ms:
        assert m.get("can_create_wine_sources") is False, f"{m['_path']}: can_create_wine_sources!=False"
        assert m.get("requires_dq_v3") is False, f"{m['_path']}: requires_dq_v3!=False"
        assert m.get("requires_matching") is False, f"{m['_path']}: requires_matching!=False"


def test_outputs_sao_ops_only() -> None:
    ms = _load_commerce_manifests()
    for m in ms:
        outputs = m.get("outputs") or []
        assert outputs == ["ops"] or outputs == ("ops",), (
            f"{m['_path']}: outputs={outputs} deveria ser ['ops']"
        )


def test_nenhum_commerce_declara_public_stores_como_output() -> None:
    """Para garantir separacao de dominio. stores e discovery, nao commerce."""

    ms = _load_commerce_manifests()
    for m in ms:
        raw = m.get("notes") or ""
        assert "public.stores" not in raw.lower() or "plug:discovery" in raw.lower(), (
            f"{m['_path']}: menciona public.stores sem tag discovery"
        )


def test_registry_status_canonico() -> None:
    """Cada manifest carrega um `registry_status` explicito."""

    ms = _load_commerce_manifests()
    allowed = {
        "observed",
        "blocked_external_host",
        "blocked_contract_missing",
        "blocked_missing_source",
        "registered_planned",
    }
    for m in ms:
        st = m.get("registry_status")
        assert st in allowed, f"{m['_path']}: registry_status={st} fora de {allowed}"
