"""Benchmark: trace pre-resolve query path for key cases.

Counts search_wine/search_wine_tokens calls and simulates timeout costs.
Roda offline: python -m tests.bench_preresolve_path
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.resolver import (
    _fast_resolve, _structured_resolve, _token_resolve,
    _build_scoring_name, _collapse_initials,
)
from tools.normalize import normalizar


# Monkey-patch search functions to count calls and log queries
_call_log = []

def _mock_search_wine(query, **kwargs):
    _call_log.append({"fn": "search_wine", "query": query, **kwargs})
    return {"wines": [], "total": 0, "search_layer": "mock"}

def _mock_search_wine_tokens(tokens, **kwargs):
    _call_log.append({"fn": "search_wine_tokens", "tokens": tokens, **kwargs})
    return {"wines": [], "total": 0, "search_layer": "mock"}

# Patch
import tools.resolver as res
import tools.search as srch
_orig_sw = res.search_wine
_orig_swt = res.search_wine_tokens
res.search_wine = _mock_search_wine
res.search_wine_tokens = _mock_search_wine_tokens


def trace_case(name, w_dict):
    """Trace all search calls for a shelf item."""
    global _call_log
    _call_log = []

    producer = (w_dict.get("producer") or "").strip() or None
    scoring_name = _build_scoring_name(w_dict)
    seen_ids = set()

    name_norm = normalizar(name)
    collapsed = _collapse_initials(name_norm)

    print(f"\n{'='*60}")
    print(f"  CASE: {name}")
    print(f"  producer={producer}, scoring_name={scoring_name!r}")
    print(f"  normalizar={name_norm!r}, collapsed={collapsed!r}")
    print(f"  has_initials={collapsed != name_norm}")
    print(f"{'='*60}")

    # Simulate Tier A shelf flow
    _call_log = []
    _fast_resolve(name, producer, seen_ids, scoring_name=scoring_name)
    fast_calls = len(_call_log)
    print(f"\n  _fast_resolve: {fast_calls} search calls")
    for c in _call_log:
        q = c.get('query', c.get('tokens', '?'))
        prod = c.get('produtor', '-')
        skip = c.get('skip_tokens', False)
        print(f"    {c['fn']}({q!r}, prod={prod!r}, skip_tokens={skip})")

    _call_log = []
    _structured_resolve(w_dict, seen_ids, scoring_name=scoring_name)
    struct_calls = len(_call_log)
    print(f"\n  _structured_resolve: {struct_calls} search calls")
    for c in _call_log:
        q = c.get('query', c.get('tokens', '?'))
        prod = c.get('produtor', '-')
        print(f"    {c['fn']}({q!r}, prod={prod!r})")

    _call_log = []
    _token_resolve(name, producer, seen_ids, scoring_name=scoring_name)
    token_calls = len(_call_log)
    print(f"\n  _token_resolve: {token_calls} search calls")
    for c in _call_log:
        tokens = c.get('tokens', '?')
        prod = c.get('produtor', '-')
        print(f"    {c['fn']}(tokens={tokens!r}, prod={prod!r})")

    total = fast_calls + struct_calls + token_calls
    print(f"\n  TOTAL: {total} search calls")
    # Estimate: each call that hits prefix on 'd%' costs ~1.5s
    prefix_kills = sum(1 for c in [] if True)  # placeholder
    return total


def estimate_latency(name, w_dict):
    """Estimate real-world latency based on query characteristics."""
    global _call_log
    _call_log = []
    producer = (w_dict.get("producer") or "").strip() or None
    scoring_name = _build_scoring_name(w_dict)
    seen_ids = set()

    # Run all phases
    _fast_resolve(name, producer, seen_ids, scoring_name=scoring_name)
    _structured_resolve(w_dict, seen_ids, scoring_name=scoring_name)
    _token_resolve(name, producer, seen_ids, scoring_name=scoring_name)

    total_ms = 0
    for c in _call_log:
        q = c.get('query', '')
        q_norm = normalizar(q) if q else ''
        fn = c['fn']

        if fn == 'search_wine':
            # search_wine goes exact(3ms) + prefix(?ms) + producer(?ms)
            total_ms += 3  # exact always fast
            # prefix: if query starts with single letter + space → timeout
            if q_norm and len(q_norm) > 0 and q_norm[1:2] == ' ':
                total_ms += 1500  # prefix 'd%' → timeout
            else:
                total_ms += 200   # prefix with specific start → fast
            total_ms += 200  # producer
        elif fn == 'search_wine_tokens':
            total_ms += 500  # token LIKE is ~500ms on average

    return total_ms, len(_call_log)


def main():
    print("PRE-RESOLVE QUERY PATH BENCHMARK")
    print("=" * 60)

    cases = [
        ("D. Eugenio Crianza 2018 La Mancha", {
            "name": "D. Eugenio Crianza 2018 La Mancha",
            "producer": "D. Eugenio", "line": "Crianza",
        }),
        ("Cuatro Vientos Tinto", {
            "name": "Cuatro Vientos Tinto",
            "producer": "Aromo", "style": "red",
        }),
        ("MontGras Aura Reserva Carmenere", {
            "name": "MontGras Aura Reserva Carmenere",
            "producer": "MontGras", "line": "Aura",
            "variety": "Carmenere", "classification": "Reserva",
        }),
    ]

    for name, w in cases:
        ms, calls = estimate_latency(name, w)
        print(f"  {name:45s} calls={calls}  est_latency={ms}ms")

    print()

    # Also trace D. Eugenio in detail
    trace_case("D. Eugenio Crianza 2018 La Mancha", cases[0][1])

    # Restore
    res.search_wine = _orig_sw
    res.search_wine_tokens = _orig_swt


if __name__ == "__main__":
    main()
