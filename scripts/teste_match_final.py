"""
Teste final: LLM classifica + extrai produtor/vinho.
Depois nos buscamos no vivino_match com o produtor limpo e verificamos match.
"""
import csv, os, time, re, sys
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
CSV_PATH = os.path.join(os.path.dirname(__file__), "teste_match_300.csv")
BATCH_SIZE = 150

PROMPT = """TAREFA: Classifique cada item e extraia dados.

REGRAS:
- X = nao e vinho (comida, objeto, cosmetico, cerveja, codigo, texto sem sentido)
- S = destilado/spirit (whisky, gin, rum, vodka, cognac, etc)
- W = vinho. Formato: W|Produtor|Vinho|Pais|Cor
  - Produtor = nome EXATO da vinicola/bodega. Se nao sabe: ??
  - Vinho = nome do vinho SEM produtor. Se nao sabe: ??
  - Pais = codigo 2 letras. Se nao sabe: ??
  - Cor: r=tinto, w=branco, p=rose, s=espumante, f=fortificado, d=sobremesa
- DUPLICATAS: se o item e o mesmo vinho que outro no lote (safra/formato diferente), adicione =N
- Se o nome nao faz sentido como vinho, responda X
- NAO invente dados. Se nao consegue identificar o produtor, use ??

ITEMS:
"""


def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    # Carregar itens
    items = []
    with open(CSV_PATH, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            items.append(r)
    print(f"Carregados {len(items)} itens")

    # === FASE 1: LLM classifica ===
    all_responses = []
    start_num = 1

    for batch_start in range(0, len(items), BATCH_SIZE):
        batch = items[batch_start:batch_start + BATCH_SIZE]
        items_text = "\n".join(f"{start_num + i}. {item['loja_nome']}" for i, item in enumerate(batch))

        print(f"\nLote {batch_start//BATCH_SIZE + 1} ({len(batch)} itens)...", end=" ", flush=True)

        try:
            resp = model.generate_content(
                PROMPT + items_text,
                generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=8192),
            )
            text = resp.text.strip()
        except Exception as e:
            print(f"ERRO: {e}")
            text = ""

        line_map = {}
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split(". ", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                line_map[int(parts[0].strip())] = parts[1].strip()

        wines_batch = 0
        for i, item in enumerate(batch):
            num = start_num + i
            llm = line_map.get(num, "MISSING")
            if llm.startswith("W"):
                wines_batch += 1
            all_responses.append({
                "num": num,
                "loja_nome": item["loja_nome"],
                "destino": item["destino"],
                "score": item["score"],
                "vid_pipeline": int(item["vid"]) if item["vid"] else 0,
                "vnome_pipeline": item["vnome"],
                "llm": llm,
            })

        not_wine = sum(1 for i2 in range(len(batch)) if line_map.get(start_num + i2, "").startswith("X"))
        print(f"W={wines_batch} X={not_wine} S={len(batch)-wines_batch-not_wine}")
        start_num += len(batch)
        if batch_start + BATCH_SIZE < len(items):
            time.sleep(5)

    # === FASE 2: Buscar no vivino_match com produtor limpo ===
    print(f"\n{'='*60}")
    print("FASE 2: Buscar no vivino_match com produtor do LLM")
    print(f"{'='*60}")

    conn = psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                            user="postgres", password="postgres123",
                            options="-c client_encoding=UTF8")
    cur = conn.cursor()

    wines = [r for r in all_responses if r["llm"].startswith("W")]
    print(f"\nTotal vinhos (W): {len(wines)}")

    match_found = 0
    match_not_found = 0
    match_same_as_pipeline = 0
    match_diff_from_pipeline = 0
    results = []

    for w in wines:
        parts = w["llm"].split("|")
        if len(parts) < 5:
            match_not_found += 1
            results.append({**w, "produtor_llm": "?", "vinho_llm": "?", "vid_found": 0, "match_status": "PARSE_ERROR"})
            continue

        produtor = parts[1].strip()
        vinho = parts[2].strip()

        anchor = ""
        if produtor == "??" or len(produtor) < 2:
            # Sem produtor, tentar buscar so por nome
            vinho_words = [p for p in vinho.lower().split() if len(p) >= 4]
            anchor = max(vinho_words, key=len) if vinho_words else vinho.lower()[:10]
            cur.execute("""
                SELECT id, produtor_normalizado, nome_normalizado
                FROM vivino_match
                WHERE nome_normalizado ILIKE %s
                LIMIT 5
            """, (f"%{anchor}%",))
        else:
            # Buscar por produtor
            # Pegar a palavra mais longa do produtor pra busca
            prod_words = [p for p in produtor.lower().split() if len(p) >= 3 and p not in ('the', 'les', 'del', 'des', 'von', 'van', 'dom', 'don')]
            if not prod_words:
                prod_words = [produtor.lower().split()[0]] if produtor.split() else ["???"]

            anchor = max(prod_words, key=len)

            cur.execute("""
                SELECT id, produtor_normalizado, nome_normalizado
                FROM vivino_match
                WHERE produtor_normalizado ILIKE %s
                ORDER BY similarity(nome_normalizado, %s) DESC
                LIMIT 20
            """, (f"%{anchor}%", vinho.lower()))

        candidates = cur.fetchall()

        if not candidates:
            match_not_found += 1
            results.append({**w, "produtor_llm": produtor, "vinho_llm": vinho, "vid_found": 0, "match_status": "NOT_FOUND"})
            continue

        # Scoring simples: quantas palavras do vinho aparecem no candidato
        best_vid = 0
        best_score = 0
        best_info = None
        vinho_tokens = set(vinho.lower().split())

        for cand_id, cand_prod, cand_nome in candidates:
            cand_tokens = set(cand_nome.lower().split()) | set(cand_prod.lower().split())
            overlap = len(vinho_tokens & cand_tokens)
            prod_match = 1 if anchor in cand_prod.lower() else 0
            score = overlap + prod_match * 2
            if score > best_score:
                best_score = score
                best_vid = cand_id
                best_info = f"{cand_prod} - {cand_nome}"

        if best_score >= 2:
            match_found += 1
            status = "MATCH"
            if w["vid_pipeline"] > 0:
                if best_vid == w["vid_pipeline"]:
                    match_same_as_pipeline += 1
                    status = "MATCH_SAME"
                else:
                    match_diff_from_pipeline += 1
                    status = "MATCH_DIFF"
        else:
            match_not_found += 1
            best_vid = 0
            status = "LOW_SCORE"

        results.append({
            **w,
            "produtor_llm": produtor,
            "vinho_llm": vinho,
            "vid_found": best_vid,
            "vivino_found": best_info or "",
            "match_status": status,
            "match_score_new": best_score,
        })

    conn.close()

    # === RESULTADO ===
    print(f"\n{'='*60}")
    print("RESULTADO FINAL")
    print(f"{'='*60}")

    total_w = len(wines)
    print(f"\nVinhos classificados (W):     {total_w}")
    print(f"Match encontrado no Vivino:   {match_found} ({match_found*100//total_w}%)")
    print(f"Nao encontrado:               {match_not_found} ({match_not_found*100//total_w}%)")
    print(f"")
    print(f"Igual ao pipeline:            {match_same_as_pipeline}")
    print(f"Diferente do pipeline:        {match_diff_from_pipeline}")

    # Comparar com pipeline
    pipeline_had_match = sum(1 for r in results if r["vid_pipeline"] > 0)
    pipeline_no_match = sum(1 for r in results if r["vid_pipeline"] == 0)
    new_matches = sum(1 for r in results if r.get("vid_found", 0) > 0 and r["vid_pipeline"] == 0)

    print(f"\nPipeline tinha match:         {pipeline_had_match}")
    print(f"Pipeline sem match:           {pipeline_no_match}")
    print(f"NOVOS matches (LLM achou):    {new_matches}")

    # Exemplos
    print(f"\n--- MATCH IGUAL AO PIPELINE (top 15) ---")
    count = 0
    for r in results:
        if r.get("match_status") == "MATCH_SAME":
            print(f"  {r['loja_nome'][:40]:40} LLM:{r['produtor_llm'][:15]}|{r['vinho_llm'][:20]:20} VID={r['vid_found']}")
            count += 1
            if count >= 15:
                break

    print(f"\n--- MATCH DIFERENTE DO PIPELINE (top 15) ---")
    count = 0
    for r in results:
        if r.get("match_status") == "MATCH_DIFF":
            print(f"  {r['loja_nome'][:35]:35} LLM_VID={r['vid_found']} ({r.get('vivino_found','')[:30]}) | PIP_VID={r['vid_pipeline']} ({r['vnome_pipeline'][:30]})")
            count += 1
            if count >= 15:
                break

    print(f"\n--- NOVOS MATCHES (pipeline nao tinha, LLM achou) (top 15) ---")
    count = 0
    for r in results:
        if r.get("vid_found", 0) > 0 and r["vid_pipeline"] == 0:
            print(f"  {r['loja_nome'][:35]:35} -> {r['produtor_llm'][:15]}|{r['vinho_llm'][:20]:20} VID={r['vid_found']} ({r.get('vivino_found','')[:35]})")
            count += 1
            if count >= 15:
                break

    print(f"\n--- NAO ENCONTRADO (top 15) ---")
    count = 0
    for r in results:
        if r.get("match_status") in ("NOT_FOUND", "LOW_SCORE"):
            print(f"  {r['loja_nome'][:40]:40} LLM:{r['produtor_llm'][:15]}|{r['vinho_llm'][:20]}")
            count += 1
            if count >= 15:
                break

    # Salvar
    out_path = os.path.join(os.path.dirname(__file__), "teste_llm_resultados", "match_validation_300.csv")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        fields = ["num", "loja_nome", "destino", "produtor_llm", "vinho_llm", "vid_pipeline", "vnome_pipeline", "vid_found", "vivino_found", "match_status"]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"\nSalvo em: {out_path}")


if __name__ == "__main__":
    main()
