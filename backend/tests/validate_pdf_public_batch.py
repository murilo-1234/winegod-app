"""Homologacao real: bateria de 10 PDFs publicos de restaurantes.

Baixa cada PDF, mede, roda process_pdf(), coleta evidencia.
Salva JSON bruto + resumo Markdown em C:\\winegod-app\\reports\\

Uso:
    cd C:\\winegod-app\\backend
    python -m tests.validate_pdf_public_batch
"""

import sys
import os
import io
import json
import time
import base64
import traceback
import multiprocessing

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_path = os.path.join(_backend_dir, ".env")
load_dotenv(_env_path)

import requests
import pdfplumber

from tools.media import process_pdf, _text_looks_wine_related

# --- Lote oficial de 10 PDFs ---

PDF_CASES = [
    {
        "name": "Elephante",
        "url": "https://media-cdn.getbento.com/accounts/63e56281c4fd62c90c1341f0335654d3/media/ReSG6OErTa9PSuqHxOb7_MYbMqDcERvW430y96Z0a_Elephante%2520Wine%2520List%25208.21.24.pdf",
        "expected_pages": 2,
    },
    {
        "name": "ALINA Restaurant",
        "url": "https://img1.wsimg.com/blobby/go/112640f6-60c2-4158-8008-a14c1119401b/alina%20-2.pdf",
        "expected_pages": 1,
    },
    {
        "name": "Posada Restaurant",
        "url": "https://img1.wsimg.com/blobby/go/26c4a5d2-ee07-47ed-96e6-4a367449196b/Posada%20Wine%20List.pdf",
        "expected_pages": 35,
    },
    {
        "name": "Merrick Inn",
        "url": "https://www.themerrickinn.com/_files/ugd/20972a_6a0f825e53eb4f9c98ce15bd5659a94f.pdf",
        "expected_pages": 1,
    },
    {
        "name": "Hendricks Tavern",
        "url": "https://media-cdn.getbento.com/accounts/8a4c9fdcdd2be12a931a79fe942485bd/media/GfPOXJgSLCk0pviYCJaz_WINE%20LIST%20MAY%202025.pdf",
        "expected_pages": 9,
    },
    {
        "name": "URLA Restaurant",
        "url": "https://www.urlarestaurant.com/wp-content/uploads/URLA-Wine-Menu-08-Sep-24.pdf",
        "expected_pages": 16,
    },
    {
        "name": "La Sirena Ristorante",
        "url": "https://lasirenaonline.com/wp-content/uploads/2025/10/WINELIST-2025-USE-THIS-FILE-pdf-10212025.pdf",
        "expected_pages": 94,
    },
    {
        "name": "Anajak Thai",
        "url": "https://www.anajakthai.com/wp-content/uploads/2020/02/2020.02.18_WineList_new-1.pdf",
        "expected_pages": 1,
    },
    {
        "name": "Firenze Trattoria",
        "url": "https://firenzetrattoria.com/italianfood/wp-content/uploads/Firenze-Wine-List.pdf",
        "expected_pages": 4,
    },
    {
        "name": "Cambio de Tercio",
        "url": "https://zangohosting.com/restaurant/wp-content/uploads/2023/02/604792-9190794c4873cda2a4ea7f351e15a225030bb3.pdf",
        "expected_pages": 28,
    },
]

REPORTS_DIR = os.path.join(os.path.dirname(_backend_dir), "reports")
DOWNLOAD_TIMEOUT = 60  # segundos
PDF_PROCESS_TIMEOUT = 300  # 5 minutos max por PDF


def download_pdf(url, name):
    """Baixa PDF por URL. Retorna (bytes, erro_ou_None)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type and not resp.content[:5] == b"%PDF-":
            return None, f"Content-Type inesperado: {content_type} (primeiros bytes: {resp.content[:20]!r})"
        return resp.content, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def analyze_with_pdfplumber(pdf_bytes):
    """Extrai metadados basicos com pdfplumber."""
    info = {"page_count": 0, "total_chars": 0, "wine_related": None, "text_sample": ""}
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            info["page_count"] = len(pdf.pages)
            texts = []
            for page in pdf.pages[:20]:
                texts.append(page.extract_text() or "")
            full_text = "\n\n".join(texts).strip()
            info["total_chars"] = len(full_text)
            if len(full_text) > 100:
                info["wine_related"] = _text_looks_wine_related(full_text)
            else:
                info["wine_related"] = "N/A (texto curto)"
            info["text_sample"] = full_text[:300]
    except Exception as e:
        info["error"] = f"{type(e).__name__}: {e}"
    return info


def _run_process_pdf_worker(pdf_bytes, result_queue):
    """Worker para rodar em processo filho com timeout."""
    try:
        # Import dentro do worker para multiprocessing spawn no Windows
        _wd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _wd not in sys.path:
            sys.path.insert(0, _wd)
        from dotenv import load_dotenv as _ld
        _ld(os.path.join(_wd, ".env"))
        from tools.media import process_pdf as _process_pdf

        b64 = base64.b64encode(pdf_bytes).decode()
        result = _process_pdf(b64)
        result_queue.put(result)
    except Exception as e:
        result_queue.put({"status": "error", "message": str(e)})


def run_process_pdf(pdf_bytes, timeout=PDF_PROCESS_TIMEOUT):
    """Roda process_pdf() em processo filho com timeout real (terminate)."""
    start = time.time()
    result_queue = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=_run_process_pdf_worker,
        args=(pdf_bytes, result_queue),
    )
    proc.start()
    proc.join(timeout=timeout)

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
        result = {
            "status": "timeout",
            "message": f"process_pdf() excedeu {timeout}s de timeout",
            "extraction_method": "timeout",
        }
    else:
        try:
            result = result_queue.get_nowait()
        except Exception:
            result = {"status": "error", "message": "Worker crashed sem resultado"}

    elapsed = round(time.time() - start, 2)
    result["latency_seconds"] = elapsed
    return result


def extract_sample_wines(result, max_items=10):
    """Extrai amostra de vinhos do resultado."""
    wines = result.get("wines", [])
    sample = []
    for w in wines[:max_items]:
        sample.append({
            "name": w.get("name", "?"),
            "producer": w.get("producer"),
            "price": w.get("price"),
            "vintage": w.get("vintage"),
            "region": w.get("region"),
            "grape": w.get("grape"),
        })
    return sample


def generate_markdown_report(all_results):
    """Gera resumo Markdown da bateria."""
    lines = [
        "# Homologacao Real — PDF Batch (10 PDFs publicos)",
        f"Data: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Resumo",
        "",
        "| # | Nome | Paginas | Chars | Metodo | Vinhos | Truncado | Latencia | Status |",
        "|---|------|---------|-------|--------|--------|----------|----------|--------|",
    ]

    approved = 0
    approved_caveats = 0
    failed = 0

    for i, r in enumerate(all_results, 1):
        if r.get("download_error"):
            lines.append(
                f"| {i} | {r['name']} | - | - | - | - | - | - | DOWNLOAD FALHOU |"
            )
            failed += 1
            continue

        plumber = r.get("pdfplumber", {})
        result = r.get("result", {})
        lines.append(
            f"| {i} | {r['name']} | {plumber.get('page_count', '?')} | "
            f"{plumber.get('total_chars', '?')} | {result.get('extraction_method', '?')} | "
            f"{result.get('wine_count', 0)} | {result.get('was_truncated', '-')} | "
            f"{result.get('latency_seconds', '?')}s | {result.get('status', '?')} |"
        )

        verdict = r.get("verdict", "?")
        if verdict == "Aprovado":
            approved += 1
        elif verdict.startswith("Aprovado"):
            approved_caveats += 1
        else:
            failed += 1

    lines.extend([
        "",
        f"**Aprovados:** {approved} | **Com ressalvas:** {approved_caveats} | **Reprovados:** {failed}",
        "",
    ])

    # Detalhes por PDF
    for i, r in enumerate(all_results, 1):
        lines.append(f"---")
        lines.append(f"## {i}. {r['name']}")
        lines.append(f"URL: {r['url']}")
        lines.append("")

        if r.get("download_error"):
            lines.append(f"**ERRO DE DOWNLOAD:** {r['download_error']}")
            lines.append("")
            continue

        plumber = r.get("pdfplumber", {})
        result = r.get("result", {})

        lines.append(f"- Tamanho: {r.get('size_kb', '?')} KB")
        lines.append(f"- Paginas (pdfplumber): {plumber.get('page_count', '?')}")
        lines.append(f"- Chars extraidos: {plumber.get('total_chars', '?')}")
        lines.append(f"- Wine related (heuristica): {plumber.get('wine_related', '?')}")
        lines.append(f"- Status: {result.get('status', '?')}")
        lines.append(f"- Extraction method: {result.get('extraction_method', '?')}")
        lines.append(f"- Wine count: {result.get('wine_count', 0)}")
        lines.append(f"- Was truncated: {result.get('was_truncated', '-')}")
        lines.append(f"- Pages processed: {result.get('pages_processed', '?')}")
        lines.append(f"- Latencia: {result.get('latency_seconds', '?')}s")
        lines.append("")

        sample = r.get("sample_wines", [])
        if sample:
            lines.append("**Amostra de vinhos:**")
            lines.append("")
            for j, w in enumerate(sample, 1):
                parts = [w.get("name", "?")]
                if w.get("producer"):
                    parts.append(f"produtor: {w['producer']}")
                if w.get("price"):
                    parts.append(f"preco: {w['price']}")
                if w.get("vintage"):
                    parts.append(f"safra: {w['vintage']}")
                lines.append(f"  {j}. {' | '.join(parts)}")
            lines.append("")

        if result.get("message"):
            lines.append(f"**Mensagem:** {result['message']}")
            lines.append("")

        lines.append(f"**Veredicto:** {r.get('verdict', '?')}")
        if r.get("verdict_reason"):
            lines.append(f"**Motivo:** {r['verdict_reason']}")
        lines.append("")

    return "\n".join(lines)


def main():
    has_key = bool(os.getenv("GEMINI_API_KEY"))
    print(f"GEMINI_API_KEY: {'disponivel' if has_key else 'NAO disponivel'}")
    if not has_key:
        print("ERRO: GEMINI_API_KEY nao encontrada.")
        sys.exit(1)

    # Filtro opcional via CLI: --only "Posada,Cambio"
    only_filter = None
    for arg in sys.argv[1:]:
        if arg.startswith("--only="):
            only_filter = [s.strip().lower() for s in arg.split("=", 1)[1].split(",")]

    cases = PDF_CASES
    if only_filter:
        cases = [c for c in PDF_CASES if any(f in c["name"].lower() for f in only_filter)]
        print(f"Filtro aplicado: rodando {len(cases)} de {len(PDF_CASES)} casos")

    all_results = []

    for i, case in enumerate(cases, 1):
        name = case["name"]
        url = case["url"]

        print(f"\n{'='*70}")
        print(f"  [{i}/{len(cases)}] {name}")
        print(f"  URL: {url[:80]}...")
        print(f"{'='*70}")

        entry = {"name": name, "url": url, "expected_pages": case["expected_pages"]}

        # 1. Download
        print(f"  Baixando...", end=" ", flush=True)
        pdf_bytes, dl_error = download_pdf(url, name)
        if dl_error:
            print(f"FALHOU: {dl_error}")
            entry["download_error"] = dl_error
            all_results.append(entry)
            continue
        size_kb = round(len(pdf_bytes) / 1024, 1)
        print(f"OK ({size_kb} KB)")
        entry["size_kb"] = size_kb

        # 2. pdfplumber
        print(f"  Analisando com pdfplumber...", end=" ", flush=True)
        plumber_info = analyze_with_pdfplumber(pdf_bytes)
        print(f"OK ({plumber_info.get('page_count', '?')} paginas, {plumber_info.get('total_chars', '?')} chars)")
        entry["pdfplumber"] = plumber_info

        # 3. process_pdf()
        print(f"  Rodando process_pdf()...", flush=True)
        try:
            result = run_process_pdf(pdf_bytes)
        except Exception as e:
            print(f"  EXCECAO: {type(e).__name__}: {e}")
            traceback.print_exc()
            result = {"status": "exception", "error": str(e), "latency_seconds": 0}
        entry["result"] = result

        # Resultado
        status = result.get("status", "?")
        method = result.get("extraction_method", "?")
        wine_count = result.get("wine_count", 0)
        latency = result.get("latency_seconds", "?")
        truncated = result.get("was_truncated", "-")
        pages = result.get("pages_processed", "?")

        print(f"  status={status} | method={method} | wines={wine_count} | "
              f"truncated={truncated} | pages={pages} | latency={latency}s")

        # Amostra
        sample = extract_sample_wines(result, max_items=10)
        entry["sample_wines"] = sample
        if sample:
            print(f"  Amostra ({len(sample)} itens):")
            for j, w in enumerate(sample, 1):
                parts = [w.get("name", "?")]
                if w.get("producer"):
                    parts.append(w["producer"])
                if w.get("price"):
                    parts.append(w["price"])
                print(f"    {j}. {' | '.join(parts)}")

        if result.get("message"):
            print(f"  Msg: {result['message']}")

        # Placeholder para veredicto (sera preenchido manualmente ou por logica simples)
        entry["verdict"] = "Pendente"
        entry["verdict_reason"] = ""

        all_results.append(entry)

    # --- Salvar artefatos ---
    os.makedirs(REPORTS_DIR, exist_ok=True)

    timestamp = time.strftime("%Y-%m-%d_%H%M")

    # JSON bruto
    json_path = os.path.join(REPORTS_DIR, f"pdf_batch_results_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        # Remover campos muito grandes para o JSON
        clean = []
        for entry in all_results:
            e = dict(entry)
            if "pdfplumber" in e:
                plumb = dict(e["pdfplumber"])
                plumb.pop("text_sample", None)  # manter no json na verdade
                e["pdfplumber"] = plumb
            clean.append(e)
        json.dump(clean, f, ensure_ascii=False, indent=2)
    print(f"\nJSON salvo: {json_path}")

    # Markdown
    md_path = os.path.join(REPORTS_DIR, f"pdf_batch_report_{timestamp}.md")
    md_content = generate_markdown_report(all_results)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Markdown salvo: {md_path}")

    # Resumo final
    print(f"\n{'='*70}")
    print(f"  BATERIA COMPLETA: {len(all_results)}/10 PDFs processados")
    for i, r in enumerate(all_results, 1):
        if r.get("download_error"):
            print(f"  {i}. {r['name']}: DOWNLOAD FALHOU")
        else:
            res = r.get("result", {})
            print(f"  {i}. {r['name']}: status={res.get('status','?')} | "
                  f"wines={res.get('wine_count',0)} | method={res.get('extraction_method','?')} | "
                  f"latency={res.get('latency_seconds','?')}s")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
