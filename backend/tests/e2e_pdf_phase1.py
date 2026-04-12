"""E2E Fase 1: extracao de PDF + montagem do contexto que iria pro Baco.

Nao chama Claude. So valida:
  1) process_pdf() extrai vinhos
  2) _process_media() monta o contexto com as 5 regras
  3) Imprime o contexto inteiro pra revisao humana

Run:
  cd backend && python -m tests.e2e_pdf_phase1
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

PDF_URL = (
    "https://media-cdn.getbento.com/accounts/63e56281c4fd62c90c1341f0335654d3/media/"
    "ReSG6OErTa9PSuqHxOb7_MYbMqDcERvW430y96Z0a_Elephante%2520Wine%2520List%25208.21.24.pdf"
)
PDF_NAME = "Elephante"
USER_MESSAGE = "Qual o melhor custo-beneficio dessa carta?"


def main():
    print(f"=== E2E Fase 1: {PDF_NAME} ===\n")

    print(f"[1/3] Baixando PDF...", flush=True)
    req = urllib.request.Request(PDF_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        pdf_bytes = resp.read()
    print(f"      OK: {len(pdf_bytes)} bytes\n", flush=True)

    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    data = {"pdf": pdf_b64}

    print(f"[2/3] Chamando _process_media() com mensagem do usuario...\n", flush=True)
    trace = RequestTrace(request_id="e2e-phase1")
    t0 = time.time()
    message_with_ctx, photo_mode = _process_media(data, USER_MESSAGE, trace)
    elapsed = time.time() - t0
    print(f"\n[3/3] OK em {elapsed:.2f}s. photo_mode={photo_mode}\n", flush=True)

    print("=" * 80)
    print("CONTEXTO QUE SERIA ENVIADO AO BACO (incluindo mensagem do usuario):")
    print("=" * 80)
    print(message_with_ctx)
    print("=" * 80)
    print(f"\nTamanho total do contexto: {len(message_with_ctx)} chars")


if __name__ == "__main__":
    main()
