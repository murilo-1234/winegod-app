"""Regra canonica de confianca baseada em tamanho de amostra (WCF).

Esta e a UNICA fonte de verdade dessa formula. Tanto o CLI `calc_wcf.py`
quanto o `sdk.plugs.reviews_scores` devem importar daqui.

Mudanca de bucket tem que acontecer neste arquivo - em qualquer outro lugar
isso sera considerado divergencia.
"""
from __future__ import annotations


def confianca(total_reviews: int | None) -> float:
    """Retorna o peso de confianca para uma amostra de N reviews.

    Buckets: 100+ -> 1.0, 50+ -> 0.8, 25+ -> 0.6, 10+ -> 0.4, else 0.2.
    None e tratado como 0 (menor bucket).
    """
    if total_reviews is None:
        total_reviews = 0
    if total_reviews >= 100:
        return 1.0
    if total_reviews >= 50:
        return 0.8
    if total_reviews >= 25:
        return 0.6
    if total_reviews >= 10:
        return 0.4
    return 0.2


__all__ = ["confianca"]
