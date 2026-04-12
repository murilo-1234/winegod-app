"""E2E Fase 2: chamada Claude real com contexto de PDF.

Le os contextos salvos pela Fase 1 (e2e_phase1_*.txt) e chama get_baco_response()
pra ver se o Baco obedece as 5 regras criticas no contexto do PDF.

Nao usa HTTP, bypassa require_credits. So exercita Claude + tool use real.

Run:
  cd backend && python -m tests.e2e_pdf_phase2
"""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from services.baco import get_baco_response
from services.tracing import RequestTrace

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports")

CASES = [
    {
        "name": "Firenze Trattoria",
        "context_file": "e2e_phase1_Firenze_Trattoria.txt",
        "note": "71 vinhos, contexto pequeno (7.5k) — teste facil",
    },
    {
        "name": "Cambio de Tercio",
        "context_file": "e2e_phase1_Cambio_de_Tercio.txt",
        "note": "307 vinhos, contexto gigante (28.6k), £ — stress test",
    },
]


def run_case(case):
    name = case["name"]
    path = os.path.join(REPORTS_DIR, case["context_file"])
    print(f"\n{'=' * 80}")
    print(f"=== CASO: {name} ===")
    print(f"    {case['note']}")
    print(f"{'=' * 80}")

    with open(path, "r", encoding="utf-8") as f:
        message = f.read()

    print(f"  contexto: {len(message)} chars")
    print(f"  chamando get_baco_response() ...", flush=True)

    session_id = f"e2e-phase2-{uuid.uuid4().hex[:8]}"
    trace = RequestTrace(request_id=session_id)

    t0 = time.time()
    try:
        response_text, model = get_baco_response(
            message,
            session_id,
            history=[],
            photo_mode=False,
            trace=trace,
        )
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  FAIL em {elapsed:.1f}s: {type(e).__name__}: {e}")
        return {"name": name, "status": "failed", "error": str(e), "latency": elapsed}

    elapsed = time.time() - t0
    print(f"  OK em {elapsed:.1f}s | modelo: {model}")
    print(f"  tamanho resposta: {len(response_text)} chars")

    # Salvar resposta inteira pra revisao
    safe = name.replace(" ", "_").replace("/", "_")
    out_path = os.path.join(REPORTS_DIR, f"e2e_phase2_{safe}_response.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"=== {name} ===\n")
        f.write(f"Model: {model}\n")
        f.write(f"Latency: {elapsed:.1f}s\n")
        f.write(f"Claude rounds: {getattr(trace, 'claude_rounds', '?')}\n")
        f.write(f"\n---- BACO RESPONSE ----\n")
        f.write(response_text)
    print(f"  salvo em: {out_path}")

    return {
        "name": name,
        "status": "success",
        "latency": elapsed,
        "model": model,
        "response_chars": len(response_text),
        "response_file": out_path,
        "response": response_text,
    }


def main():
    print("\nE2E Fase 2 — Claude real com contextos de PDF da Fase 1\n")
    results = []
    grand_t0 = time.time()
    for c in CASES:
        results.append(run_case(c))
    grand_elapsed = time.time() - grand_t0

    print("\n\n" + "=" * 90)
    print("RESUMO FASE 2")
    print("=" * 90)
    for r in results:
        print(f"  {r['name']:<25} {r.get('status','?'):<10} "
              f"{r.get('latency', 0):>6.1f}s  resp={r.get('response_chars', 0)} chars")
    print(f"\nTotal: {grand_elapsed:.1f}s")

    # Imprimir respostas inteiras no stdout pra facilitar leitura humana
    for r in results:
        if r.get("status") != "success":
            continue
        print("\n\n" + "#" * 90)
        print(f"# RESPOSTA DO BACO — {r['name']}")
        print("#" * 90)
        print(r["response"])


if __name__ == "__main__":
    main()
