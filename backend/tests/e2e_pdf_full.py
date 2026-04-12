"""E2E full: Fase 1 (extracao + contexto) + Fase 2 (Claude real) em uma chamada.

Usado para re-validar a Regra 4 depois do fix no chat.py. Roda 2 PDFs:
  - Firenze Trattoria (teste facil, era contradicao)
  - Cambio de Tercio (stress test, era ranking sem score)

Run:
  cd backend && python -m tests.e2e_pdf_full
"""
import base64
import os
import sys
import time
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from routes.chat import _process_media
from services.baco import get_baco_response
from services.tracing import RequestTrace

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports")

PDFS = [
    {
        "name": "Firenze Trattoria",
        "url": "https://firenzetrattoria.com/italianfood/wp-content/uploads/Firenze-Wine-List.pdf",
    },
    {
        "name": "Cambio de Tercio",
        "url": "https://zangohosting.com/restaurant/wp-content/uploads/2023/02/604792-9190794c4873cda2a4ea7f351e15a225030bb3.pdf",
    },
]

USER_MESSAGE = "Qual o melhor custo-beneficio dessa carta?"


def run_one(pdf_info):
    name = pdf_info["name"]
    print(f"\n{'=' * 80}")
    print(f"=== {name} ===")
    print(f"{'=' * 80}")

    # Fase 1
    print("[FASE 1] baixando e extraindo ...", flush=True)
    req = urllib.request.Request(pdf_info["url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        pdf_bytes = resp.read()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    trace1 = RequestTrace(request_id=f"e2efull-p1-{name}")
    t0 = time.time()
    ctx_message, photo_mode = _process_media({"pdf": pdf_b64}, USER_MESSAGE, trace1)
    fase1_elapsed = time.time() - t0

    wine_lines = [
        ln for ln in ctx_message.split("\n")
        if ln.startswith("  ") and ln.lstrip().split(".", 1)[0].strip().isdigit()
    ]
    print(f"[FASE 1] OK {fase1_elapsed:.1f}s | {len(wine_lines)} vinhos | {len(ctx_message)} chars")

    # Salvar contexto
    safe = name.replace(" ", "_").replace("/", "_")
    ctx_path = os.path.join(REPORTS_DIR, f"e2e_full_{safe}_context.txt")
    with open(ctx_path, "w", encoding="utf-8") as f:
        f.write(ctx_message)

    # Fase 2
    print("[FASE 2] chamando get_baco_response ...", flush=True)
    trace2 = RequestTrace(request_id=f"e2efull-p2-{name}")
    t0 = time.time()
    try:
        response_text, model = get_baco_response(
            ctx_message,
            f"e2e-full-{uuid.uuid4().hex[:8]}",
            history=[],
            photo_mode=photo_mode,
            trace=trace2,
        )
    except Exception as e:
        print(f"[FASE 2] FAIL: {type(e).__name__}: {e}")
        return {"name": name, "fase1_ok": True, "fase2_ok": False, "error": str(e)}

    fase2_elapsed = time.time() - t0
    print(f"[FASE 2] OK {fase2_elapsed:.1f}s | modelo={model} | {len(response_text)} chars")

    # Salvar resposta
    resp_path = os.path.join(REPORTS_DIR, f"e2e_full_{safe}_response.txt")
    with open(resp_path, "w", encoding="utf-8") as f:
        f.write(f"=== {name} ===\n")
        f.write(f"Model: {model}\n")
        f.write(f"Fase1 latency: {fase1_elapsed:.1f}s\n")
        f.write(f"Fase2 latency: {fase2_elapsed:.1f}s\n")
        f.write(f"Claude rounds: {getattr(trace2, 'claude_rounds', '?')}\n")
        f.write(f"\n---- BACO RESPONSE ----\n")
        f.write(response_text)

    return {
        "name": name,
        "fase1_ok": True,
        "fase2_ok": True,
        "fase1_latency": fase1_elapsed,
        "fase2_latency": fase2_elapsed,
        "model": model,
        "wine_count": len(wine_lines),
        "context_chars": len(ctx_message),
        "response_chars": len(response_text),
        "response": response_text,
        "ctx_file": ctx_path,
        "resp_file": resp_path,
    }


def main():
    print("\nE2E FULL — Fase 1 + Fase 2 com Regra 4 reforcada\n")
    results = []
    grand_t0 = time.time()
    for p in PDFS:
        results.append(run_one(p))
    grand_elapsed = time.time() - grand_t0

    print("\n\n" + "=" * 90)
    print("RESUMO")
    print("=" * 90)
    for r in results:
        if r.get("fase2_ok"):
            print(f"  {r['name']:<25} F1={r['fase1_latency']:>5.1f}s  "
                  f"F2={r['fase2_latency']:>6.1f}s  "
                  f"vinhos={r['wine_count']:<5} resp={r['response_chars']} chars")
        else:
            print(f"  {r['name']:<25} FAIL: {r.get('error')}")
    print(f"\nTotal: {grand_elapsed:.1f}s")

    # Respostas completas
    for r in results:
        if not r.get("fase2_ok"):
            continue
        print("\n\n" + "#" * 90)
        print(f"# RESPOSTA DO BACO — {r['name']}")
        print("#" * 90)
        print(r["response"])


if __name__ == "__main__":
    main()
