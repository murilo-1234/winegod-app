from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from scripts.data_ops_producers.dedup_stores import (  # noqa: E402
    AUTH_ENV,
    DEFAULT_BATCH_SIZE,
    DuplicateGroup,
    StoreRow,
    build_report,
    canonicalize_domain,
    detect_similarity_hits,
    group_exact_duplicates,
    persist_report,
)


def test_canonicalize_domain_removes_www_and_port_and_lowercases():
    assert canonicalize_domain("WWW.Example.COM.br") == "example.com.br"
    assert canonicalize_domain("https://Example.com:443/shop") == "example.com"
    assert canonicalize_domain("http://store.example.com:80") == "store.example.com"


def test_canonicalize_domain_returns_none_when_empty():
    assert canonicalize_domain(None) is None
    assert canonicalize_domain("") is None


def test_group_exact_duplicates_picks_oldest_id_canonical():
    rows = [
        StoreRow(id=3, dominio="www.amazon.com", url=None, canonical="amazon.com"),
        StoreRow(id=1, dominio="amazon.com", url=None, canonical="amazon.com"),
        StoreRow(id=2, dominio="AMAZON.COM", url=None, canonical="amazon.com"),
        StoreRow(id=7, dominio="other.com", url=None, canonical="other.com"),
    ]
    groups = group_exact_duplicates(rows)
    assert len(groups) == 1
    g = groups[0]
    assert g.canonical == "amazon.com"
    assert g.canonical_id == 1
    assert g.alias_ids == [2, 3]


def test_detect_similarity_hits_finds_close_matches():
    # Bucket is 2nd-to-last label, so force same label to trigger comparison.
    hits = detect_similarity_hits(
        ["wine-store.com.br", "winee-store.com.br", "completely-different.store"]
    )
    pairs = {(tuple(sorted([h.a, h.b]))) for h in hits}
    assert any(
        pair == tuple(sorted(["wine-store.com.br", "winee-store.com.br"]))
        for pair in pairs
    )


def test_detect_similarity_hits_ignores_dissimilar_domains():
    hits = detect_similarity_hits(["wine.com", "spirits.com"])
    assert hits == []


def test_apply_without_env_raises(monkeypatch, capsys):
    from scripts.data_ops_producers.dedup_stores import main

    monkeypatch.delenv(AUTH_ENV, raising=False)
    monkeypatch.setattr(sys, "argv", ["dedup_stores", "--apply"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code != 0


def test_apply_even_with_env_is_blocked(monkeypatch):
    from scripts.data_ops_producers.dedup_stores import main

    monkeypatch.setenv(AUTH_ENV, "1")
    monkeypatch.setattr(sys, "argv", ["dedup_stores", "--apply"])
    # Even with env set, apply is hard-blocked in this session.
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code != 0


def test_batching_respects_cap(monkeypatch):
    from scripts.data_ops_producers.dedup_stores import main

    monkeypatch.setattr(sys, "argv", ["dedup_stores", "--batch-size", "999999"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code != 0


def test_build_report_counts_rows_and_canonicals():
    rows = [
        StoreRow(id=1, dominio="www.example.com", url=None, canonical="example.com"),
        StoreRow(id=2, dominio="example.com", url=None, canonical="example.com"),
        StoreRow(id=3, dominio=None, url=None, canonical=None),
    ]
    report = build_report(rows)
    assert report.total_rows == 3
    assert report.rows_without_domain == 1
    assert report.unique_canonical == 1
    assert len(report.exact_duplicate_groups) == 1


def test_persist_report_writes_md_and_json(tmp_path, monkeypatch):
    import scripts.data_ops_producers.dedup_stores as mod

    monkeypatch.setattr(mod, "DEDUP_ROOT", tmp_path)
    rows = [
        StoreRow(id=1, dominio="example.com", url=None, canonical="example.com"),
    ]
    report = build_report(rows)
    md, js = persist_report(report, timestamp="20260424_120000")
    assert md.exists() and js.exists()
    assert "Stores Dedup Report" in md.read_text(encoding="utf-8")
