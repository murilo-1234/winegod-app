"""Smoke test para os 4 casos criticos de busca.
Roda contra o banco real. Uso: python -m tests.test_search_cases
"""

import sys
import os

# Adicionar backend ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from tools.search import search_wine
from tools.normalize import normalizar


def test_case(query, expected_family, extra_kwargs=None):
    """Executa busca e mostra resultados."""
    kwargs = extra_kwargs or {}
    print(f"\n{'='*60}")
    print(f"QUERY: '{query}' (normalizado: '{normalizar(query)}')")
    if kwargs:
        print(f"FILTROS: {kwargs}")
    print(f"ESPERADO: resultados da familia '{expected_family}'")
    print(f"{'='*60}")

    result = search_wine(query, limit=5, **kwargs)
    layer = result.get("search_layer", "?")
    wines = result.get("wines", [])
    print(f"  Camada usada: {layer}")
    print(f"  Total encontrado: {len(wines)}")

    hit = False
    for i, w in enumerate(wines, 1):
        name = w.get("nome", "?")
        producer = w.get("produtor", "?")
        rating = w.get("vivino_rating", "?")
        match_marker = ""
        if expected_family.lower() in (name or "").lower() or expected_family.lower() in (producer or "").lower():
            match_marker = " <<<< HIT"
            hit = True
        print(f"  {i}. {name} | {producer} | rating={rating}{match_marker}")

    if hit:
        print(f"  >>> PASS: encontrou '{expected_family}' nos resultados")
    else:
        print(f"  >>> FAIL: '{expected_family}' NAO encontrado nos top 5")

    return hit


def main():
    print("SMOKE TEST — 4 Casos Criticos de Busca")
    print("=" * 60)

    results = []
    results.append(test_case("Alamos", "Alamos"))
    results.append(test_case("Novecento", "Novecento"))
    results.append(test_case("Moet", "Moët"))
    results.append(test_case("Chandon", "Chandon"))

    # Caso 5: busca com safra (testa que VARCHAR(4) nao quebra)
    results.append(test_case("Alamos", "Alamos", extra_kwargs={"safra": 2020}))

    print(f"\n\n{'='*60}")
    print(f"RESULTADO: {sum(results)}/5 casos passaram")
    print(f"{'='*60}")

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
