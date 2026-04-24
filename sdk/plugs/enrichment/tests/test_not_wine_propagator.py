from __future__ import annotations

from pathlib import Path

from sdk.plugs.enrichment import not_wine_propagator as p


_WINE_FILTER_STUB = '''"""Stub"""
_NON_WINE_PATTERNS = [
    r"whisky",
    r"vodka",
]
'''


def test_new_pattern_enters_patch(tmp_path, monkeypatch):
    items = [{"full_name": "Absinto Premium 750ml"}]
    result = p.propose_patch(items, wine_filter_text=_WINE_FILTER_STUB)
    assert len(result.new_patterns) == 1
    assert result.new_patterns[0].pattern.startswith("absinto")
    assert result.diff
    assert "absinto" in result.diff


def test_existing_pattern_is_skipped():
    items = [{"full_name": "Whisky 12 anos"}]
    result = p.propose_patch(items, wine_filter_text=_WINE_FILTER_STUB)
    assert result.new_patterns == []
    assert result.skipped
    assert result.skipped[0]["reason"] == "already_covered"


def test_invalid_regex_is_skipped():
    # Caso extremo: nome so com pontuacao nao gera pattern
    items = [{"full_name": "!!! ### ???"}]
    result = p.propose_patch(items, wine_filter_text=_WINE_FILTER_STUB)
    assert result.new_patterns == []
    assert result.skipped
    assert result.skipped[0]["reason"] == "no_pattern_extractable"


def test_patch_applies_with_git_apply_format(tmp_path):
    # O diff deve comecar com os markers padrao unified_diff
    items = [{"full_name": "Tequila Reposado 750ml"}]
    result = p.propose_patch(items, wine_filter_text=_WINE_FILTER_STUB)
    assert result.diff.startswith("--- scripts/wine_filter.py")
    assert "+++ scripts/wine_filter.py" in result.diff
    assert "tequila" in result.diff


def test_patches_dir_is_used_only_under_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "PATCHES_DIR", tmp_path)
    items = [{"full_name": "Licor de Amora"}]
    result = p.propose_patch(items, wine_filter_text=_WINE_FILTER_STUB)
    path = p.persist_patch(result, timestamp="20260424_120000")
    assert path is not None
    assert path.exists()
    assert path.parent == tmp_path


def test_duplicate_in_batch_is_skipped_second_time():
    items = [
        {"full_name": "Licor Artesanal 500ml"},
        {"full_name": "Licor Artesanal 750ml"},
    ]
    result = p.propose_patch(items, wine_filter_text=_WINE_FILTER_STUB)
    # primeiro "licor" entra, segundo e duplicate_in_batch
    assert len(result.new_patterns) == 1
    assert any(s.get("reason") == "duplicate_in_batch" for s in result.skipped)
