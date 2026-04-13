"""E2E usability homologation: ALINA Restaurant PDF on production chat endpoint.

Roda o caso real do cliente:
1. Baixa o PDF de https://img1.wsimg.com/blobby/go/.../alina%20-2.pdf
2. POST no endpoint real https://winegod-app.onrender.com/api/chat com PDF base64
3. Roda 5 perguntas obrigatorias na mesma session_id
4. Salva evidencia bruta em C:\\winegod-app\\reports\\

Uso: cd C:\\winegod-app\\backend && python -m tests.e2e_alina_usability
"""

import base64
import json
import os
import sys
import time
import uuid

import requests

PDF_URL = (
    "https://img1.wsimg.com/blobby/go/112640f6-60c2-4158-8008-a14c1119401b/alina%20-2.pdf"
)
# Endpoint pode ser sobrescrito via env var WINEGOD_CHAT_ENDPOINT para validar
# patches locais antes de deploy.
CHAT_ENDPOINT = os.environ.get(
    "WINEGOD_CHAT_ENDPOINT",
    "https://winegod-app.onrender.com/api/chat",
)
HEALTHZ = os.environ.get(
    "WINEGOD_HEALTHZ",
    "https://winegod-app.onrender.com/healthz",
)

QUESTIONS = [
    "Do PDF que enviei, quais vinhos voce confirmou na base?",
    "Desses, quais tem nota e quais tem score de custo-beneficio?",
    "Me ranqueie APENAS os vinhos deste PDF que tiverem score confirmado, do melhor custo-beneficio para o pior.",
    "Agora me diga quais vinhos do PDF voce NAO pode ranquear por falta de score.",
    "Se eu quiser pedir o melhor custo-beneficio desta carta hoje, qual voce recomenda e por que?",
]


def main():
    # 1. Health check
    print(f"Health check: {HEALTHZ}")
    r = requests.get(HEALTHZ, timeout=30)
    print(f"  -> {r.status_code} {r.text}")
    if r.status_code != 200:
        print("Backend nao esta saudavel. Abortando.")
        sys.exit(1)

    # 2. Download PDF
    print(f"\nBaixando PDF: {PDF_URL}")
    r = requests.get(
        PDF_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        timeout=60,
    )
    r.raise_for_status()
    pdf_bytes = r.content
    pdf_b64 = base64.b64encode(pdf_bytes).decode()
    print(f"  -> {len(pdf_bytes)} bytes ({len(pdf_b64)} chars base64)")

    # 3. Session id unico
    session_id = f"e2e-alina-{uuid.uuid4()}"
    print(f"\nsession_id: {session_id}")

    # 4. Rodar as 5 perguntas
    transcript = []
    for i, question in enumerate(QUESTIONS, 1):
        print(f"\n{'='*70}")
        print(f"PERGUNTA {i}/5: {question}")
        print(f"{'='*70}")

        payload = {
            "message": question,
            "session_id": session_id,
        }
        # Anexar PDF apenas na primeira pergunta
        if i == 1:
            payload["pdf"] = pdf_b64
            print(f"  (com PDF anexado, {len(pdf_b64)} chars base64)")

        start = time.time()
        try:
            resp = requests.post(
                CHAT_ENDPOINT,
                json=payload,
                timeout=600,  # PDF pode levar minutos
            )
            elapsed = round(time.time() - start, 2)
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            print(f"  ERRO: {type(e).__name__}: {e} (apos {elapsed}s)")
            transcript.append({
                "question": question,
                "error": f"{type(e).__name__}: {e}",
                "elapsed": elapsed,
            })
            continue

        print(f"  HTTP {resp.status_code} | latencia {elapsed}s")

        try:
            data = resp.json()
        except Exception:
            print(f"  Resposta nao-JSON: {resp.text[:500]}")
            transcript.append({
                "question": question,
                "http_status": resp.status_code,
                "raw_text": resp.text,
                "elapsed": elapsed,
            })
            continue

        response_text = data.get("response", "")
        model = data.get("model", "?")
        print(f"  modelo: {model}")
        print(f"  resposta:\n{response_text}\n")

        transcript.append({
            "question": question,
            "http_status": resp.status_code,
            "model": model,
            "response": response_text,
            "elapsed": elapsed,
            "raw_data": data,
        })

    # 5. Salvar evidencia
    reports_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "reports",
    )
    os.makedirs(reports_dir, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d_%H%M")
    out_path = os.path.join(reports_dir, f"e2e_alina_usability_{timestamp}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "pdf_url": PDF_URL,
                "endpoint": CHAT_ENDPOINT,
                "session_id": session_id,
                "transcript": transcript,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\nEvidencia salva: {out_path}")


if __name__ == "__main__":
    main()
