"""
Teste final v2: LLM extrai produtor + vinho + pais + cor + regiao.
Depois busca no vivino_match com produtor INTEIRO e verifica 1 por 1.
"""
import csv, os, time, re
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
CSV_PATH = os.path.join(os.path.dirname(__file__), "teste_final_300.csv")
BATCH_SIZE = 150

PROMPT = """TAREFA: Classifique cada item e extraia dados.

REGRAS:
- X = nao e vinho (comida, objeto, cosmetico, cerveja, codigo, texto sem sentido)
- S = destilado/spirit (whisky, gin, rum, vodka, cognac, etc)
- W = vinho. Formato: W|Produtor|Vinho|Pais|Cor|Regiao
  - Produtor = nome COMPLETO e EXATO da vinicola/bodega/chateau/domaine. Se nao sabe: ??
  - Vinho = nome do vinho SEM o produtor. Se nao sabe: ??
  - Pais = codigo 2 letras. Se nao sabe: ??
  - Cor: r=tinto, w=branco, p=rose, s=espumante, f=fortificado, d=sobremesa
  - Regiao = regiao vinicola (ex: Champagne, Napa Valley, Barossa Valley). Se nao sabe: ??
- DUPLICATAS: se o item e o mesmo vinho que outro no lote (safra/formato diferente), adicione =N
- Se o nome nao faz sentido como vinho, responda X
- NAO invente dados. Se nao consegue identificar, use ??

ITEMS:
"""


def normalize(s):
    """Normaliza string pra comparacao."""
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9 ]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s


def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    items = []
    with open(CSV_PATH, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            items.append(r)
    print(f"Carregados {len(items)} itens")

    # === FASE 1: LLM ===
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

        w_count = sum(1 for k, v in line_map.items() if v.startswith("W"))
        x_count = sum(1 for k, v in line_map.items() if v.startswith("X"))
        print(f"W={w_count} X={x_count} S={len(batch)-w_count-x_count}")

        for i, item in enumerate(batch):
            num = start_num + i
            all_responses.append({
                "num": num,
                "loja_nome": item["loja_nome"],
                "destino": item["destino"],
                "vid_pipeline": int(item["vid"]) if item["vid"] else 0,
                "vnome_pipeline": item["vnome"],
                "llm": line_map.get(num, "MISSING"),
            })
        start_num += len(batch)
        if batch_start + BATCH_SIZE < len(items):
            time.sleep(5)

    # === FASE 2: Match rigoroso contra vivino_match ===
    print(f"\n{'='*60}")
    print("FASE 2: Match RIGOROSO com produtor inteiro")
    print(f"{'='*60}")

    conn = psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                            user="postgres", password="postgres123",
                            options="-c client_encoding=UTF8")
    cur = conn.cursor()

    wines = [r for r in all_responses if r["llm"].startswith("W")]
    print(f"\nTotal vinhos (W): {len(wines)}")

    match_certo = 0
    match_errado = 0
    sem_match = 0
    igual_pipeline = 0
    diff_pipeline = 0
    novo_match = 0

    det_certo = []
    det_errado = []
    det_sem = []
    det_novo = []

    for w in wines:
        parts = w["llm"].split("|")
        if len(parts) < 5:
            sem_match += 1
            det_sem.append((w["loja_nome"], "PARSE_ERROR", "", ""))
            continue

        produtor = parts[1].strip()
        vinho = parts[2].strip()
        pais = parts[3].strip() if len(parts) > 3 else "??"
        cor = parts[4].strip() if len(parts) > 4 else "??"
        regiao = parts[5].strip() if len(parts) > 5 else "??"

        if produtor == "??" or len(produtor) < 2:
            sem_match += 1
            det_sem.append((w["loja_nome"], f"??|{vinho}", "", "sem produtor"))
            continue

        # BUSCA RIGOROSA: produtor INTEIRO (nao 1 palavra)
        prod_norm = normalize(produtor)

        # Estrategia 1: busca exata do produtor normalizado
        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado, tipo, pais, regiao
            FROM vivino_match
            WHERE produtor_normalizado = %s
        """, (prod_norm,))
        candidates = cur.fetchall()

        # Estrategia 2: se nao achou exato, busca com ILIKE do produtor inteiro
        if not candidates:
            cur.execute("""
                SELECT id, produtor_normalizado, nome_normalizado, tipo, pais, regiao
                FROM vivino_match
                WHERE produtor_normalizado ILIKE %s
                LIMIT 50
            """, (f"%{prod_norm}%",))
            candidates = cur.fetchall()

        # Estrategia 3: sem acentos/caracteres especiais, busca mais aberta
        if not candidates and len(prod_norm.split()) >= 2:
            # Usar as 2 palavras mais longas
            words = sorted(prod_norm.split(), key=len, reverse=True)[:2]
            pattern = f"%{words[0]}%{words[1]}%" if len(words) > 1 else f"%{words[0]}%"
            cur.execute("""
                SELECT id, produtor_normalizado, nome_normalizado, tipo, pais, regiao
                FROM vivino_match
                WHERE produtor_normalizado ILIKE %s
                LIMIT 50
            """, (pattern,))
            candidates = cur.fetchall()

        if not candidates:
            sem_match += 1
            det_sem.append((w["loja_nome"], f"{produtor}|{vinho}", "", "produtor nao encontrado"))
            continue

        # SCORING RIGOROSO
        vinho_norm = normalize(vinho)
        vinho_words = set(vinho_norm.split()) - {'wine', 'vino', 'vinho', 'red', 'white', 'tinto', 'branco', 'rose', 'brut', 'the', 'les', 'des', 'del'}

        best = None
        best_score = 0

        for cand_id, cand_prod, cand_nome, cand_tipo, cand_pais, cand_regiao in candidates:
            score = 0
            cand_prod_norm = normalize(cand_prod)
            cand_nome_norm = normalize(cand_nome)

            # 1. Produtor match (0-3 pontos)
            if prod_norm == cand_prod_norm:
                score += 3  # exato
            elif prod_norm in cand_prod_norm or cand_prod_norm in prod_norm:
                score += 2  # contem
            else:
                # Overlap de palavras
                p1 = set(prod_norm.split())
                p2 = set(cand_prod_norm.split())
                overlap = len(p1 & p2)
                if overlap >= 2:
                    score += 1
                else:
                    continue  # produtor nao bate, pula

            # 2. Vinho match (0-3 pontos)
            cand_nome_words = set(cand_nome_norm.split()) - {'wine', 'vino', 'vinho', 'red', 'white', 'tinto', 'branco', 'rose', 'brut', 'the', 'les', 'des', 'del'}
            if vinho_words and cand_nome_words:
                overlap = len(vinho_words & cand_nome_words)
                total = max(len(vinho_words), len(cand_nome_words))
                ratio = overlap / total if total > 0 else 0
                if ratio >= 0.8:
                    score += 3
                elif ratio >= 0.5:
                    score += 2
                elif overlap >= 1:
                    score += 1
            elif vinho_norm in cand_nome_norm or cand_nome_norm in vinho_norm:
                score += 2

            # 3. Pais match (0-1 ponto)
            if pais != "??" and cand_pais and pais.lower() == cand_pais.lower():
                score += 1

            # 4. Regiao match (0-1 ponto)
            if regiao != "??" and cand_regiao:
                reg_norm = normalize(regiao)
                cand_reg_norm = normalize(cand_regiao or "")
                if reg_norm and cand_reg_norm and (reg_norm in cand_reg_norm or cand_reg_norm in reg_norm):
                    score += 1

            if score > best_score:
                best_score = score
                best = (cand_id, cand_prod, cand_nome, cand_tipo, cand_pais, cand_regiao)

        # Decisao: score >= 5 = match confiavel (produtor 2-3 + vinho 2-3 + extras)
        if best and best_score >= 5:
            match_certo += 1
            vid = best[0]
            info = f"{best[1]} - {best[2]}"

            if w["vid_pipeline"] > 0:
                if vid == w["vid_pipeline"]:
                    igual_pipeline += 1
                else:
                    diff_pipeline += 1
            else:
                novo_match += 1
                det_novo.append((w["loja_nome"], f"{produtor}|{vinho}", info, vid))

            det_certo.append((w["loja_nome"], f"{produtor}|{vinho}", info, vid, best_score))

        elif best and best_score >= 3:
            # Incerto - produtor bate mas vinho duvidoso
            match_errado += 1  # contamos como nao confiavel
            det_errado.append((w["loja_nome"], f"{produtor}|{vinho}", f"{best[1]} - {best[2]}", best_score))

        else:
            sem_match += 1
            det_sem.append((w["loja_nome"], f"{produtor}|{vinho}", "", f"score={best_score}"))

    conn.close()

    # === RESULTADO ===
    total = len(wines) or 1
    print(f"\n{'='*60}")
    print(f"RESULTADO (score >= 5 = match confiavel)")
    print(f"{'='*60}")
    print(f"")
    print(f"Vinhos (W):                    {len(wines)}")
    print(f"MATCH CONFIAVEL (score>=5):     {match_certo} ({match_certo*100//total}%)")
    print(f"MATCH FRACO (score 3-4):        {match_errado} ({match_errado*100//total}%)")
    print(f"SEM MATCH:                      {sem_match} ({sem_match*100//total}%)")
    print(f"")
    print(f"Igual ao pipeline:              {igual_pipeline}")
    print(f"Diferente do pipeline:          {diff_pipeline}")
    print(f"NOVOS (pipeline nao tinha):     {novo_match}")

    print(f"\n--- MATCH CONFIAVEL (score>=5, top 20) ---")
    for nome, llm, db_info, vid, sc in det_certo[:20]:
        print(f"  {nome[:35]:35} LLM:{llm[:25]:25} DB:{db_info[:30]:30} s={sc}")

    print(f"\n--- MATCH FRACO (score 3-4, top 15) ---")
    for nome, llm, db_info, sc in det_errado[:15]:
        print(f"  {nome[:35]:35} LLM:{llm[:25]:25} DB:{db_info[:30]:30} s={sc}")

    print(f"\n--- SEM MATCH (top 15) ---")
    for item in det_sem[:15]:
        print(f"  {item[0][:35]:35} LLM:{item[1][:25]:25} {item[3] if len(item)>3 else ''}")

    print(f"\n--- NOVOS MATCHES (top 15) ---")
    for nome, llm, db_info, vid in det_novo[:15]:
        print(f"  {nome[:35]:35} LLM:{llm[:25]:25} -> {db_info[:35]} VID={vid}")


if __name__ == "__main__":
    main()
