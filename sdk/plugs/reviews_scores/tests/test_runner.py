from __future__ import annotations

from sdk.plugs.reviews_scores.confidence import confidence as shared_confidence
from sdk.plugs.reviews_scores.exporters import (
    EXPORTERS,
    _canonical_match_key,
    _confidence,
    _normalized_100,
)
from sdk.plugs.reviews_scores.schemas import (
    PER_REVIEW_SOURCES,
    SIGNAL_KIND_BY_SOURCE,
    SOURCES_THAT_UPDATE_WINES,
)


def test_reviews_exporters_catalog_has_all_sources():
    expected = {
        "vivino_wines_to_ratings",
        "vivino_reviews_to_scores_reviews",
        "cellartracker_to_scores_reviews",
        "decanter_to_critic_scores",
        "wine_enthusiast_to_critic_scores",
        "winesearcher_to_market_signals",
    }
    assert expected.issubset(set(EXPORTERS))


def test_signal_kind_map_covers_every_source():
    for source in EXPORTERS:
        assert source in SIGNAL_KIND_BY_SOURCE


def test_vivino_wines_is_source_that_updates_wines():
    assert "vivino_wines_to_ratings" in SOURCES_THAT_UPDATE_WINES


def test_per_review_source_marked_correctly():
    assert "vivino_reviews_to_scores_reviews" in PER_REVIEW_SOURCES
    assert "vivino_wines_to_ratings" not in PER_REVIEW_SOURCES


def test_confidence_shared_is_the_canonical_one():
    # exporters._confidence tem que ser a MESMA funcao importada de
    # sdk.plugs.reviews_scores.confidence (que por sua vez e scripts/wcf_confidence.py).
    assert _confidence is shared_confidence


def test_confidence_matches_wcf_canonical_scale():
    from scripts.wcf_confidence import confianca as canonical  # sys.path ja injetado

    for n, expected in [(None, 0.2), (0, 0.2), (9, 0.2), (10, 0.4), (24, 0.4),
                         (25, 0.6), (49, 0.6), (50, 0.8), (99, 0.8),
                         (100, 1.0), (10_000, 1.0)]:
        assert shared_confidence(n) == expected
        assert canonical(n if n is not None else 0) == expected


def test_confidence_not_duplicated_in_exporters_source():
    # Garantia textual: o arquivo de exporters nao implementa a formula,
    # ele so importa o helper.
    import inspect

    import sdk.plugs.reviews_scores.exporters as exp

    source = inspect.getsource(exp)
    assert "if sample_size >= 100:" not in source
    assert "return 0.2" not in source
    assert "from .confidence import confidence" in source


def test_normalized_100_scales_correctly():
    assert _normalized_100(3.8, 5) == 76.0
    assert _normalized_100(5.0, 5) == 100.0
    assert _normalized_100(87.5, 100) == 87.5
    assert _normalized_100(None, 5) is None
    assert _normalized_100(3.5, 7) is None


def test_canonical_match_key_is_deterministic_and_case_insensitive():
    a = _canonical_match_key("Chateau X", "Producer Y", "2019", "FR")
    b = _canonical_match_key("chateau x", "producer y", "2019", "fr")
    assert a == b
    assert len(a) == 64


def test_runner_rejects_backfill_for_unsupported_source():
    from sdk.plugs.reviews_scores import runner

    parser_sources = set(EXPORTERS)
    assert "cellartracker_to_scores_reviews" in parser_sources
    assert "vivino_wines_to_ratings" in runner.BACKFILL_SUPPORTED_SOURCES
    assert "cellartracker_to_scores_reviews" not in runner.BACKFILL_SUPPORTED_SOURCES


def test_checkpoint_roundtrip(tmp_path, monkeypatch):
    from sdk.plugs.reviews_scores import checkpoint as ck

    monkeypatch.setattr(ck, "STATE_ROOT", tmp_path)
    monkeypatch.setattr(ck, "_state_path", lambda src: tmp_path / f"{src}.json")

    state0 = ck.load_state("vivino_wines_to_ratings")
    assert state0["last_id"] == 0
    assert state0["runs"] == 0

    ck.save_state("vivino_wines_to_ratings", last_id=777, mode="backfill_windowed")
    state1 = ck.load_state("vivino_wines_to_ratings")
    assert state1["last_id"] == 777
    assert state1["runs"] == 1
    assert state1["mode"] == "backfill_windowed"
    assert "updated_at" in state1

    ck.save_state("vivino_wines_to_ratings", last_id=1500, mode="backfill_windowed")
    state2 = ck.load_state("vivino_wines_to_ratings")
    assert state2["last_id"] == 1500
    assert state2["runs"] == 2  # contador progride

    ck.reset_state("vivino_wines_to_ratings")
    state3 = ck.load_state("vivino_wines_to_ratings")
    assert state3["last_id"] == 0
    assert state3["runs"] == 0
