"""Tests for note_v2 canonical engine.

Covers: seal, source, clamp, shrinkage, bucket, data preservation,
consistency, integration, and WCF hygiene.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from services.note_v2 import (
    resolve_note_v2, _shrinkage, _clamp, _compute_ratings_bucket,
    _get_public_ratings_count,
)


# ---------------------------------------------------------------------------
# Helper: mock bucket lookup
# ---------------------------------------------------------------------------

def _make_bucket(nota_base=3.8, stddev=0.3, delta=None, n=15, delta_n=0,
                 level="pais_tipo", key="ar_tinto"):
    return {
        "bucket_level": level,
        "bucket_key": key,
        "bucket_n": n,
        "nota_base": nota_base,
        "bucket_stddev": stddev,
        "delta_contextual": delta,
        "delta_n": delta_n,
    }


def _bucket_fn(bucket):
    """Return a lookup function that always returns the given bucket."""
    def fn(wine):
        return bucket
    return fn


_NO_BUCKET = lambda wine: None


# ===========================================================================
# 10.1 — Seal tests
# ===========================================================================


class TestSeal:
    def test_verified_75_plus_low_sample(self):
        wine = {"vivino_rating": 4.2, "vivino_reviews": 100,
                "nota_wcf": 3.9, "nota_wcf_sample_size": 5}
        assert resolve_note_v2(wine)["display_note_type"] == "verified"

    def test_verified_75_plus_high_sample(self):
        wine = {"vivino_rating": 4.2, "vivino_reviews": 200,
                "nota_wcf": 4.1, "nota_wcf_sample_size": 50}
        assert resolve_note_v2(wine)["display_note_type"] == "verified"

    def test_estimated_25_to_74(self):
        wine = {"vivino_rating": 4.0, "vivino_reviews": 50,
                "nota_wcf": None, "nota_wcf_sample_size": None}
        assert resolve_note_v2(wine)["display_note_type"] == "estimated"

    def test_low_public_not_verified(self):
        wine = {"vivino_rating": 4.0, "vivino_reviews": 10,
                "nota_wcf": 4.0, "nota_wcf_sample_size": 50}
        assert resolve_note_v2(wine)["display_note_type"] != "verified"

    def test_no_vivino_with_wcf(self):
        wine = {"vivino_rating": None, "vivino_reviews": None,
                "nota_wcf": 4.0, "nota_wcf_sample_size": 50}
        assert resolve_note_v2(wine)["display_note_type"] == "estimated"

    def test_contextual(self):
        bucket = _make_bucket(nota_base=3.8, stddev=0.3)
        wine = {"vivino_rating": None, "vivino_reviews": None,
                "nota_wcf": None, "nota_wcf_sample_size": None,
                "tipo": "tinto", "pais": "AR"}
        result = resolve_note_v2(wine, bucket_lookup_fn=_bucket_fn(bucket))
        assert result["display_note_type"] == "contextual"

    def test_none(self):
        wine = {}
        assert resolve_note_v2(wine)["display_note_type"] is None

    def test_sample_size_does_not_override_public_seal(self):
        wine = {"vivino_rating": 4.0, "vivino_reviews": 200,
                "nota_wcf": 3.5, "nota_wcf_sample_size": 3}
        assert resolve_note_v2(wine)["display_note_type"] == "verified"


# ===========================================================================
# 10.2 — Source tests
# ===========================================================================


class TestSource:
    def test_wcf_shrunk_with_vivino(self):
        bucket = _make_bucket(nota_base=3.9)
        wine = {"vivino_rating": 4.2, "vivino_reviews": 200,
                "nota_wcf": 4.3, "nota_wcf_sample_size": 30,
                "tipo": "tinto", "pais": "AR"}
        result = resolve_note_v2(wine, bucket_lookup_fn=_bucket_fn(bucket))
        assert result["display_note_source"] == "wcf_shrunk"

    def test_wcf_direct_no_bucket(self):
        wine = {"vivino_rating": 4.2, "vivino_reviews": 200,
                "nota_wcf": 4.3, "nota_wcf_sample_size": 30}
        result = resolve_note_v2(wine, bucket_lookup_fn=_NO_BUCKET)
        assert result["display_note_source"] == "wcf_direct"

    def test_vivino_contextual_delta(self):
        bucket = _make_bucket(nota_base=3.9, delta=0.05, delta_n=10)
        wine = {"vivino_rating": 4.2, "vivino_reviews": 100,
                "nota_wcf": 3.8, "nota_wcf_sample_size": 5,
                "tipo": "tinto", "pais": "AR"}
        result = resolve_note_v2(wine, bucket_lookup_fn=_bucket_fn(bucket))
        assert result["display_note_source"] == "vivino_contextual_delta"

    def test_vivino_fallback(self):
        wine = {"vivino_rating": 4.2, "vivino_reviews": 100,
                "nota_wcf": 3.8, "nota_wcf_sample_size": 5}
        result = resolve_note_v2(wine, bucket_lookup_fn=_NO_BUCKET)
        assert result["display_note_source"] == "vivino_fallback"
        assert result["display_note"] == 4.20

    def test_contextual_pure(self):
        bucket = _make_bucket(nota_base=3.8, stddev=0.3)
        wine = {"vivino_rating": None, "vivino_reviews": None,
                "nota_wcf": None, "nota_wcf_sample_size": None,
                "tipo": "tinto", "pais": "AR"}
        result = resolve_note_v2(wine, bucket_lookup_fn=_bucket_fn(bucket))
        assert result["display_note_source"] == "contextual"
        # nota = 3.8 - 0.5 * 0.3 = 3.65
        assert result["display_note"] == 3.65

    def test_none(self):
        wine = {"vivino_rating": None, "vivino_reviews": None,
                "nota_wcf": None, "nota_wcf_sample_size": None}
        result = resolve_note_v2(wine)
        assert result["display_note_source"] == "none"
        assert result["display_note"] is None

    def test_ai_fallback(self):
        wine = {"vivino_rating": None, "vivino_reviews": None,
                "nota_wcf": 4.0, "nota_wcf_sample_size": None,
                "confianca_nota": 0.8}
        result = resolve_note_v2(wine, bucket_lookup_fn=_NO_BUCKET)
        assert result["display_note_source"] == "ai"
        assert result["display_note"] == 4.0


# ===========================================================================
# 10.3 — Clamp tests
# ===========================================================================


class TestClamp:
    def test_clamp_upper(self):
        """Note must not exceed vivino + 0.20."""
        wine = {"vivino_rating": 4.0, "vivino_reviews": 200,
                "nota_wcf": 4.8, "nota_wcf_sample_size": 50}
        result = resolve_note_v2(wine, bucket_lookup_fn=_NO_BUCKET)
        assert result["display_note"] <= 4.20

    def test_clamp_lower(self):
        """Note must not go below vivino - 0.30."""
        wine = {"vivino_rating": 4.0, "vivino_reviews": 200,
                "nota_wcf": 3.2, "nota_wcf_sample_size": 50}
        result = resolve_note_v2(wine, bucket_lookup_fn=_NO_BUCKET)
        assert result["display_note"] >= 3.70

    def test_clamp_asymmetric(self):
        """Upper clamp (+0.20) is tighter than lower (-0.30)."""
        assert _clamp(5.0, 4.0 - 0.30, 4.0 + 0.20) == 4.20
        assert _clamp(3.0, 4.0 - 0.30, 4.0 + 0.20) == 3.70


# ===========================================================================
# 10.4 — Shrinkage tests
# ===========================================================================


class TestShrinkage:
    def test_50_50(self):
        """n=20, k=20 -> 50/50 weight."""
        result = _shrinkage(4.0, 3.5, 20)
        assert round(result, 4) == 3.75

    def test_high_sample(self):
        """n=100 -> WCF dominates ~83%."""
        result = _shrinkage(4.5, 3.5, 100)
        expected = (100 / 120) * 4.5 + (20 / 120) * 3.5
        assert round(result, 4) == round(expected, 4)

    def test_low_sample(self):
        """n=1 -> nota_base dominates ~95%."""
        result = _shrinkage(4.5, 3.5, 1)
        expected = (1 / 21) * 4.5 + (20 / 21) * 3.5
        assert round(result, 4) == round(expected, 4)


# ===========================================================================
# 10.5 — Ratings bucket tests
# ===========================================================================


class TestBucket:
    def test_ranges(self):
        assert _compute_ratings_bucket(None) is None
        assert _compute_ratings_bucket(0) is None
        assert _compute_ratings_bucket(10) is None
        assert _compute_ratings_bucket(24) is None
        assert _compute_ratings_bucket(25) == "25+"
        assert _compute_ratings_bucket(49) == "25+"
        assert _compute_ratings_bucket(50) == "50+"
        assert _compute_ratings_bucket(99) == "50+"
        assert _compute_ratings_bucket(100) == "100+"
        assert _compute_ratings_bucket(199) == "100+"
        assert _compute_ratings_bucket(200) == "200+"
        assert _compute_ratings_bucket(299) == "200+"
        assert _compute_ratings_bucket(300) == "300+"
        assert _compute_ratings_bucket(499) == "300+"
        assert _compute_ratings_bucket(500) == "500+"
        assert _compute_ratings_bucket(10000) == "500+"


# ===========================================================================
# 10.6 — Data preservation tests
# ===========================================================================


class TestPreservation:
    def test_no_data_mutation(self):
        wine = {"vivino_rating": 4.2, "vivino_reviews": 10000,
                "nota_wcf": 4.0, "nota_wcf_sample_size": 50}
        resolve_note_v2(wine)
        assert wine["vivino_reviews"] == 10000
        assert wine["vivino_rating"] == 4.2
        assert wine["nota_wcf"] == 4.0


# ===========================================================================
# 10.7 — Consistency tests
# ===========================================================================


class TestConsistency:
    def test_public_ratings_count(self):
        wine = {"vivino_reviews": 500}
        assert _get_public_ratings_count(wine) == 500

    def test_public_ratings_count_none(self):
        wine = {}
        assert _get_public_ratings_count(wine) is None

    def test_vivino_fallback_2_decimals(self):
        """Vivino fallback should show 2 decimal places (4.2 -> 4.20)."""
        wine = {"vivino_rating": 4.2, "vivino_reviews": 100,
                "nota_wcf": None, "nota_wcf_sample_size": None}
        result = resolve_note_v2(wine)
        assert result["display_note"] == 4.20


# ===========================================================================
# 10.8 — Integration tests
# ===========================================================================


class TestIntegration:
    def test_contextual_is_confirmed_with_note(self):
        """Contextual wines have a display_note, so resolver should treat as confirmed_with_note."""
        bucket = _make_bucket(nota_base=3.8, stddev=0.2)
        wine = {"vivino_rating": None, "vivino_reviews": None,
                "nota_wcf": None, "nota_wcf_sample_size": None,
                "tipo": "tinto", "pais": "AR"}
        result = resolve_note_v2(wine, bucket_lookup_fn=_bucket_fn(bucket))
        assert result["display_note"] is not None
        assert result["display_note_type"] == "contextual"

    def test_full_payload_structure(self):
        """Output must contain all expected keys."""
        wine = {"vivino_rating": 4.0, "vivino_reviews": 100,
                "nota_wcf": 4.1, "nota_wcf_sample_size": 30}
        result = resolve_note_v2(wine)
        expected_keys = {
            "display_note", "display_note_type", "display_note_source",
            "public_ratings_count", "public_ratings_bucket", "wcf_sample_size",
            "context_bucket_key", "context_bucket_level",
            "context_bucket_n", "context_bucket_stddev",
        }
        assert set(result.keys()) == expected_keys

    def test_309k_scenario(self):
        """Wine with 200 public ratings but only 5 WCF reviews -> verified seal, vivino-anchored note."""
        wine = {"vivino_rating": 4.2, "vivino_reviews": 200,
                "nota_wcf": 3.8, "nota_wcf_sample_size": 5}
        result = resolve_note_v2(wine)
        assert result["display_note_type"] == "verified"
        assert result["display_note_source"] == "vivino_fallback"
        assert result["display_note"] == 4.20
        assert result["public_ratings_bucket"] == "200+"
