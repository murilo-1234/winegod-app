"""Normalizacao de texto para busca — replica exata do ingest (scripts/clean_wines.py)."""

import re
import unicodedata


def normalizar(texto):
    """Normaliza texto: NFKD ASCII fold, lowercase, sem caracteres especiais.
    Identica a funcao normalizar() de scripts/clean_wines.py."""
    if not texto:
        return ""
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')
    texto = texto.lower().strip()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto
