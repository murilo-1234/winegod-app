"""Canonical display layer: resolve runtime nota + score for any wine dict.

Delegates note resolution to note_v2 (single source of truth).
Score resolution remains here (formula unchanged).

NAO materializar display fields no banco. Resolver aqui em runtime.
"""

from services.note_v2 import resolve_note_v2, get_bucket_lookup
from utils.country_names import iso_to_name


def resolve_display(wine):
    """Resolve canonical display fields for a wine dict.

    Input: dict with at least nota_wcf, vivino_rating, nota_wcf_sample_size,
    vivino_reviews, confianca_nota, winegod_score, pais, sub_regiao, tipo, produtor.
    Returns: dict with display_note, display_note_type, display_note_source,
             display_score, display_score_available, public_ratings_bucket.
    """
    v2 = resolve_note_v2(wine, bucket_lookup_fn=get_bucket_lookup())

    winegod_score = wine.get("winegod_score")
    preco_min = wine.get("preco_min")

    # Score requires BOTH a computed score AND a valid price
    has_price = preco_min is not None and float(preco_min) > 0
    if winegod_score is not None and has_price:
        score = round(float(winegod_score), 2)
        score_available = True
    else:
        score = None
        score_available = False

    pais_iso = wine.get("pais")
    pais_display = iso_to_name(pais_iso) if pais_iso else None
    if not pais_display:
        pais_display = wine.get("pais_nome") or None

    return {
        "display_note": v2["display_note"],
        "display_note_type": v2["display_note_type"],
        "display_note_source": v2["display_note_source"],
        "display_score": score,
        "display_score_available": score_available,
        "public_ratings_bucket": v2["public_ratings_bucket"],
        "pais_display": pais_display,
    }


def enrich_wine(wine):
    """Add canonical display fields to a wine dict in-place. Returns the same dict."""
    wine.update(resolve_display(wine))
    return wine


def enrich_wines(wines):
    """Add canonical display fields to a list of wine dicts."""
    for w in wines:
        enrich_wine(w)
    return wines


# ---------------------------------------------------------------------------
# Legacy note resolution — kept for rollback safety. Remove after v2 is stable.
# ---------------------------------------------------------------------------


def _resolve_note_legacy(nota_wcf, vivino_rating, sample_size, confidence=None):
    """LEGACY: 4-rule note resolution (pre-v2). For rollback only."""
    nwcf = float(nota_wcf) if nota_wcf is not None else None
    vr = float(vivino_rating) if vivino_rating is not None else None
    ss = int(sample_size) if sample_size is not None else None
    conf = float(confidence) if confidence is not None else None

    if nwcf is not None and ss is not None and ss >= 25 and vr is not None and vr > 0:
        return {
            "display_note": round(_clamp_legacy(nwcf, vr - 0.30, vr + 0.30), 2),
            "display_note_type": "verified",
            "display_note_source": "wcf",
        }
    if nwcf is not None and ss is not None and ss >= 1 and vr is not None and vr > 0:
        return {
            "display_note": round(_clamp_legacy(nwcf, vr - 0.30, vr + 0.30), 2),
            "display_note_type": "estimated",
            "display_note_source": "wcf",
        }
    if vr is not None and vr > 0:
        return {
            "display_note": round(vr, 2),
            "display_note_type": "estimated",
            "display_note_source": "vivino",
        }
    if nwcf is not None and conf is not None and conf >= 0.75:
        return {
            "display_note": round(nwcf, 2),
            "display_note_type": "estimated",
            "display_note_source": "ai",
        }
    return {
        "display_note": None,
        "display_note_type": None,
        "display_note_source": None,
    }


def _clamp_legacy(value, min_val, max_val):
    return max(min_val, min(value, max_val))
