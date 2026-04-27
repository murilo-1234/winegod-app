"""Normalizadores de campos de vinho usados pelo plug commerce_dq_v3.

Garante consistencia (case + acento) e validacao contra set fechado para
campos categoricos antes de gravar no banco. Aplicado nos pontos de entrada
do plug (exporters.py).
"""

from __future__ import annotations

import unicodedata


# Tipos canonicos aceitos no banco. Tudo lowercase, sem acento.
# "desconhecido" e mantido como passthrough porque o pipeline atual usa essa
# categoria como sinal de "tipo nao identificado" (ver
# scripts/.../r11_aplica_filtros.py). NAO remover sem migrar esse pipeline.
VALID_WINE_TYPES = {
    "tinto",
    "branco",
    "rose",
    "espumante",
    "fortificado",
    "sobremesa",
    "desconhecido",
}

# Aliases comuns vindos de scrapers em outros idiomas/grafias.
WINE_TYPE_ALIASES = {
    "red": "tinto",
    "white": "branco",
    "rosado": "rose",
    "rosato": "rose",
    "sparkling": "espumante",
    "fortified": "fortificado",
    "dessert": "sobremesa",
}


def normalize_wine_type(value: str | None) -> str | None:
    """Normaliza o tipo de vinho para a forma canonica do banco.

    Aplica em ordem:
      1. Strip + lowercase
      2. Remocao de acentos via unicodedata NFD (Rose -> rose)
      3. Mapeamento de aliases multilingua
      4. Validacao contra VALID_WINE_TYPES

    Returns:
        - String canonica (lowercase, sem acento) se valido
        - None se valor vazio ou nao reconhecido (evita lixo no banco)

    Examples:
        normalize_wine_type("Rose") -> "rose"
        normalize_wine_type("ROSE") -> "rose"
        normalize_wine_type("Tinto") -> "tinto"
        normalize_wine_type("Red") -> "tinto"
        normalize_wine_type("Rosato") -> "rose"
        normalize_wine_type("Sparkling Wine") -> None  (nao reconhecido)
        normalize_wine_type(None) -> None
        normalize_wine_type("") -> None
        normalize_wine_type("desconhecido") -> "desconhecido"
    """
    if not value:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    # Remove acentos: "rose" -> "rose"
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Aplica alias antes da validacao
    s = WINE_TYPE_ALIASES.get(s, s)
    return s if s in VALID_WINE_TYPES else None
