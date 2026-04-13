"""Canonical display layer: resolve runtime nota + score for any wine dict.

Regras de nota (qualidade):
  1. nota_wcf + sample >= 100 + vivino > 0  -> clamp(wcf, viv +/- 0.30) -> verified/wcf
  2. nota_wcf + sample >= 25  + vivino > 0  -> clamp(wcf, viv +/- 0.30) -> estimated/wcf
  3. vivino > 0                              -> vivino                   -> estimated/vivino
  4. else                                    -> null

Score (custo-beneficio):
  - winegod_score (pre-computed in calc_score.py)
  - NULL quando sem preco

NAO materializar display fields no banco. Resolver aqui em runtime.
"""


def resolve_display(wine):
    """Resolve canonical display fields for a wine dict.

    Input: dict with at least nota_wcf, vivino_rating, nota_wcf_sample_size,
    confianca_nota, winegod_score.
    Returns: dict with display_note, display_note_type, display_note_source,
             display_score, display_score_available.
    """
    nota_wcf = wine.get("nota_wcf")
    vivino_rating = wine.get("vivino_rating")
    sample_size = wine.get("nota_wcf_sample_size")
    confidence = wine.get("confianca_nota")
    winegod_score = wine.get("winegod_score")
    preco_min = wine.get("preco_min")

    display = _resolve_note(nota_wcf, vivino_rating, sample_size, confidence)

    # Score requires BOTH a computed score AND a valid price
    has_price = preco_min is not None and float(preco_min) > 0
    if winegod_score is not None and has_price:
        display["display_score"] = round(float(winegod_score), 2)
        display["display_score_available"] = True
    else:
        display["display_score"] = None
        display["display_score_available"] = False

    return display


def enrich_wine(wine):
    """Add canonical display fields to a wine dict in-place. Returns the same dict."""
    wine.update(resolve_display(wine))
    return wine


def enrich_wines(wines):
    """Add canonical display fields to a list of wine dicts."""
    for w in wines:
        enrich_wine(w)
    return wines


def _resolve_note(nota_wcf, vivino_rating, sample_size, confidence=None):
    """Apply the 4-rule note resolution."""
    nwcf = float(nota_wcf) if nota_wcf is not None else None
    vr = float(vivino_rating) if vivino_rating is not None else None
    ss = int(sample_size) if sample_size is not None else None
    conf = float(confidence) if confidence is not None else None

    # Rule 1: WCF verified (sample >= 100, vivino anchor)
    if nwcf is not None and ss is not None and ss >= 100 and vr is not None and vr > 0:
        return {
            "display_note": round(_clamp(nwcf, vr - 0.30, vr + 0.30), 2),
            "display_note_type": "verified",
            "display_note_source": "wcf",
        }

    # Rule 2: WCF estimated (25 <= sample < 100, vivino anchor)
    if nwcf is not None and ss is not None and ss >= 25 and vr is not None and vr > 0:
        return {
            "display_note": round(_clamp(nwcf, vr - 0.30, vr + 0.30), 2),
            "display_note_type": "estimated",
            "display_note_source": "wcf",
        }

    # Rule 3: Vivino fallback
    if vr is not None and vr > 0:
        return {
            "display_note": round(vr, 2),
            "display_note_type": "estimated",
            "display_note_source": "vivino",
        }

    # Rule 4: AI-estimated note for auto-created wines when no public note exists.
    # This is opt-in via confianca_nota and only applies when the wine has nota_wcf
    # but no vivino anchor / sample-size evidence.
    if nwcf is not None and conf is not None and conf >= 0.75:
        return {
            "display_note": round(nwcf, 2),
            "display_note_type": "estimated",
            "display_note_source": "ai",
        }

    # Rule 5: No note available
    return {
        "display_note": None,
        "display_note_type": None,
        "display_note_source": None,
    }


def _clamp(value, min_val, max_val):
    return max(min_val, min(value, max_val))
