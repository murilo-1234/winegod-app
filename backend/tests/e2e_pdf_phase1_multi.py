"""E2E Fase 1 multi: extracao + contexto para 5 PDFs variados.

Cobre: 4 linguas (IT, TR, ES/EN, EN/IT), 3 moedas, 5 tamanhos, todos branches:
  - Firenze Trattoria  (IT, 4p, native_text mono)
  - URLA Restaurant    (TR, 16p, native_text)
  - Cambio de Tercio   (ES/EN, 28p, chunked direto, GBP)
  - Posada Restaurant  (EN/IT, 35p, chunked direto)
  - Merrick Inn        (scanned, visual_fallback)

Run:
  cd backend && python -m tests.e2e_pdf_phase1_multi
"""
import base64
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from routes.chat import _process_media
from services.tracing import RequestTrace

PDFS = [
    {
        "name": "Firenze Trattoria",
        "lang": "IT",
        "url": "https://firenzetrattoria.com/italianfood/wp-content/uploads/Firenze-Wine-List.pdf",
    },
    {
        "name": "URLA Restaurant",
        "lang": "TR",
        "url": "https://www.urlarestaurant.com/wp-content/uploads/URLA-Wine-Menu-08-Sep-24.pdf",
    },
    {
        "name": "Cambio de Tercio",
        "lang": "ES/EN",
        "url": "https://zangohosting.com/restaurant/wp-content/uploads/2023/02/604792-9190794c4873cda2a4ea7f351e15a225030bb3.pdf",
    },
    {
        "name": "Posada Restaurant",
        "lang": "EN/IT",
        "url": "https://img1.wsimg.com/blobby/go/26c4a5d2-ee07-47ed-96e6-4a367449196b/Posada%20Wine%20List.pdf",
    },
    {
        "name": "Merrick Inn",
        "lang": "EN (scanned)",
        "url": "https://www.themerrickinn.com/_files/ugd/20972a_6a0f825e53eb4f9c98ce15bd5659a94f.pdf",
    },
]

USER_MESSAGE = "Qual o melhor custo-beneficio dessa carta?"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports")


def download(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def run_one(pdf_info):
    name = pdf_info["name"]
    print(f"\n{'=' * 70}")
    print(f"=== {name} ({pdf_info['lang']}) ===")
    print(f"{'=' * 70}")
    out = {"name": name, "lang": pdf_info["lang"]}

    t0 = time.time()
    try:
        pdf_bytes = download(pdf_info["url"])
    except Exception as e:
        print(f"  DOWNLOAD FAIL: {e}")
        out["status"] = "download_failed"
        out["error"] = str(e)
        return out
    print(f"  baixado: {len(pdf_bytes)} bytes")

    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    data = {"pdf": pdf_b64}

    trace = RequestTrace(request_id=f"e2e-{name}")
    try:
        message_with_ctx, photo_mode = _process_media(data, USER_MESSAGE, trace)
    except Exception as e:
        print(f"  PROCESS FAIL: {type(e).__name__}: {e}")
        out["status"] = "process_failed"
        out["error"] = str(e)
        out["latency"] = time.time() - t0
        return out

    elapsed = time.time() - t0

    # Contar vinhos no contexto (linhas que comecam com "  N. ")
    wine_lines = [
        ln for ln in message_with_ctx.split("\n")
        if ln.strip() and ln.lstrip().split(".", 1)[0].strip().isdigit()
        and ln.startswith("  ")
    ]
    wine_count = len(wine_lines)

    # Identificar branch usado pelo source_note
    if "Texto extraido diretamente" in message_with_ctx:
        branch = "native_text"
    elif "em partes apos falha" in message_with_ctx:
        branch = "native_text_chunked"
    elif "escaneado" in message_with_ctx:
        branch = "visual_fallback"
    else:
        branch = "?"

    out.update({
        "status": "success",
        "latency": elapsed,
        "context_chars": len(message_with_ctx),
        "wine_count": wine_count,
        "branch": branch,
        "photo_mode": photo_mode,
    })

    # Salvar contexto inteiro
    safe_name = name.replace(" ", "_").replace("/", "_")
    out_path = os.path.join(OUTPUT_DIR, f"e2e_phase1_{safe_name}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(message_with_ctx)
    out["context_file"] = out_path

    print(f"  branch: {branch}")
    print(f"  vinhos: {wine_count}")
    print(f"  contexto: {len(message_with_ctx)} chars")
    print(f"  latencia: {elapsed:.1f}s")
    print(f"  salvo em: {out_path}")
    return out


def main():
    print("\nE2E Fase 1 MULTI — 5 PDFs variados")
    print(f"Mensagem do usuario: '{USER_MESSAGE}'\n")

    results = []
    grand_t0 = time.time()
    for pdf in PDFS:
        results.append(run_one(pdf))
    grand_elapsed = time.time() - grand_t0

    # Summary table
    print("\n\n" + "=" * 100)
    print("RESUMO")
    print("=" * 100)
    print(f"{'#':<3}{'Nome':<22}{'Lingua':<14}{'Branch':<22}{'Vinhos':<10}{'Chars':<10}{'Latencia':<10}{'Status'}")
    print("-" * 100)
    for i, r in enumerate(results, 1):
        name = r.get("name", "?")[:21]
        lang = r.get("lang", "?")[:13]
        branch = r.get("branch", "?")[:21]
        wines = r.get("wine_count", "-")
        chars = r.get("context_chars", "-")
        lat = f"{r.get('latency', 0):.0f}s" if r.get("latency") else "-"
        status = r.get("status", "?")
        print(f"{i:<3}{name:<22}{lang:<14}{branch:<22}{str(wines):<10}{str(chars):<10}{lat:<10}{status}")
    print("-" * 100)
    print(f"Total: {grand_elapsed:.0f}s")

    success = sum(1 for r in results if r.get("status") == "success")
    print(f"\nSucesso: {success}/{len(results)}")


if __name__ == "__main__":
    main()
