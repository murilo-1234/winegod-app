"""
Teste v3: LLM extrai dados + normaliza produtor e vinho no formato do banco.
"""
import csv, os, time, re
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
CSV_PATH = os.path.join(os.path.dirname(__file__), "teste_final_300.csv")
BATCH_SIZE = 150

PROMPT = """TAREFA: Classifique cada item e extraia dados de vinho.

REGRAS:
- X = nao e vinho
- S = destilado/spirit
- W = vinho. Formato: W|Produtor|Vinho|Pais|Cor|ProdNorm|VinhoNorm
  - Produtor = nome completo da vinicola/bodega/chateau
  - Vinho = nome do vinho SEM o produtor
  - Pais = codigo 2 letras (ou ??)
  - Cor: r=tinto, w=branco, p=rose, s=espumante, f=fortificado, d=sobremesa
  - ProdNorm = produtor NORMALIZADO: tudo minusculo, sem acentos, sem apostrofos, sem hifens. Exemplos:
    Château l'Évangile → chateau levangile
    Château Lafite Rothschild → chateau lafite rothschild
    Domaine de la Romanée-Conti → domaine de la romanee conti
    Bodega Catena Zapata → bodega catena zapata
    Weingut Dr. Loosen → weingut dr loosen
    IMPORTANTE: l' + palavra = JUNTAR. d' + palavra = JUNTAR. Exemplos:
    Château l'Évangile → chateau levangile
    Château l'Enclos → chateau lenclos
    Château l'Arrosée → chateau larrosee
    Château d'Yquem → chateau dyquem
    Château l'Abeille de Fieuzal → chateau labeille de fieuzal
    Château l'Église-Clinet → chateau leglise clinet
    Saint-Émilion → saintemilion (sem hifen, junto)
  - VinhoNorm = vinho NORMALIZADO: mesma regra. Exemplos:
    Cuvée Spéciale Brut → cuvee speciale brut
    Saint-Émilion Grand Cru → saintemilion grand cru
    Côtes du Rhône → cotes du rhone
    Gewürztraminer Réserve → gewurztraminer reserve
    l'Universelle → luniverselle
    Sainte-Cécile → saintececile
- DUPLICATAS: mesmo vinho, safra/formato diferente → adicione =N
- NAO invente dados. Se nao sabe o produtor, use ??

ITEMS:
"""


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

        w_count = sum(1 for v in line_map.values() if v.startswith("W"))
        x_count = sum(1 for v in line_map.values() if v.startswith("X"))
        print(f"W={w_count} X={x_count}")

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

    # === FASE 2: Match contra vivino_match ===
    print(f"\n{'='*60}")
    print("FASE 2: Match com produtor+vinho normalizados")
    print(f"{'='*60}")

    conn = psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                            user="postgres", password="postgres123",
                            options="-c client_encoding=UTF8")
    cur = conn.cursor()

    wines = [r for r in all_responses if r["llm"].startswith("W")]
    total = len(wines) or 1
    print(f"\nTotal vinhos (W): {len(wines)}")

    match_certo = 0
    sem_match = 0
    igual_pipeline = 0
    diff_pipeline = 0
    novo_match = 0

    det_certo = []
    det_sem = []
    det_novo = []

    for w in wines:
        parts = w["llm"].split("|")
        if len(parts) < 7:
            sem_match += 1
            det_sem.append((w["loja_nome"], w["llm"][:40], "campos insuficientes"))
            continue

        produtor = parts[1].strip()
        vinho = parts[2].strip()
        pais = parts[3].strip()
        cor = parts[4].strip()
        prod_norm = parts[5].strip()
        vinho_norm = parts[6].strip().split("=")[0].strip()  # remover =N se tiver

        if prod_norm == "??" or len(prod_norm) < 2:
            sem_match += 1
            det_sem.append((w["loja_nome"], f"{produtor}|{vinho}", "sem produtor"))
            continue

        # Normalizar l' d' s' no script (LLM nem sempre junta)
        prod_norm = re.sub(r"\bl ", "l", prod_norm)
        prod_norm = re.sub(r"\bd ", "d", prod_norm)
        prod_norm = re.sub(r"\bs ", "s", prod_norm)
        vinho_norm = re.sub(r"\bl ", "l", vinho_norm)
        vinho_norm = re.sub(r"\bd ", "d", vinho_norm)
        vinho_norm = re.sub(r"\bsaint ", "saint", vinho_norm)
        vinho_norm = re.sub(r"\bsainte ", "sainte", vinho_norm)

        # BUSCA 1: produtor exato normalizado
        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado, pais, regiao
            FROM vivino_match
            WHERE produtor_normalizado = %s
        """, (prod_norm,))
        candidates = cur.fetchall()

        # BUSCA 2: ILIKE com produtor normalizado inteiro
        if not candidates:
            cur.execute("""
                SELECT id, produtor_normalizado, nome_normalizado, pais, regiao
                FROM vivino_match
                WHERE produtor_normalizado ILIKE %s
                LIMIT 50
            """, (f"%{prod_norm}%",))
            candidates = cur.fetchall()

        if not candidates:
            sem_match += 1
            det_sem.append((w["loja_nome"], f"{prod_norm}|{vinho_norm}", "produtor nao encontrado"))
            continue

        # Encontrar melhor candidato
        best = None
        best_score = 0

        for cand_id, cand_prod, cand_nome, cand_pais, cand_regiao in candidates:
            score = 0

            # Produtor
            if prod_norm == cand_prod:
                score += 3
            elif prod_norm in cand_prod or cand_prod in prod_norm:
                score += 2
            else:
                score += 1

            # Vinho normalizado
            if vinho_norm and vinho_norm != "??":
                vn_words = set(vinho_norm.split()) - {"de", "du", "la", "le", "les", "des", "del", "di"}
                cn_words = set(cand_nome.split()) - {"de", "du", "la", "le", "les", "des", "del", "di"}
                if vn_words and cn_words:
                    overlap = len(vn_words & cn_words)
                    max_w = max(len(vn_words), len(cn_words))
                    ratio = overlap / max_w
                    if ratio >= 0.7:
                        score += 3
                    elif ratio >= 0.4:
                        score += 2
                    elif overlap >= 1:
                        score += 1
                elif vinho_norm in cand_nome or cand_nome in vinho_norm:
                    score += 2

            # Pais
            if pais != "??" and cand_pais and pais.lower() == cand_pais.lower():
                score += 1

            if score > best_score:
                best_score = score
                best = (cand_id, cand_prod, cand_nome, cand_pais, cand_regiao)

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
                det_novo.append((w["loja_nome"], f"{prod_norm}|{vinho_norm}", info, vid))

            det_certo.append((w["loja_nome"], f"{prod_norm}|{vinho_norm}", info, vid, best_score))
        else:
            sem_match += 1
            best_info = f"{best[1]} - {best[2]}" if best else "nenhum"
            det_sem.append((w["loja_nome"], f"{prod_norm}|{vinho_norm}", f"score={best_score} best={best_info[:35]}"))

    conn.close()

    # === RESULTADO ===
    print(f"\n{'='*60}")
    print(f"RESULTADO")
    print(f"{'='*60}")
    print(f"")
    print(f"Vinhos (W):                    {len(wines)}")
    print(f"MATCH CONFIAVEL (score>=5):     {match_certo} ({match_certo*100//total}%)")
    print(f"SEM MATCH / FRACO:              {sem_match} ({sem_match*100//total}%)")
    print(f"")
    print(f"Igual ao pipeline:              {igual_pipeline}")
    print(f"Diferente do pipeline:          {diff_pipeline}")
    print(f"NOVOS (pipeline nao tinha):     {novo_match}")

    print(f"\n--- MATCH CONFIAVEL (top 25) ---")
    for nome, llm, db_info, vid, sc in det_certo[:25]:
        print(f"  {nome[:35]:35} LLM:{llm[:30]:30} DB:{db_info[:35]:35} s={sc}")

    print(f"\n--- NOVOS MATCHES (top 15) ---")
    for nome, llm, db_info, vid in det_novo[:15]:
        print(f"  {nome[:35]:35} LLM:{llm[:30]:30} -> {db_info[:35]} VID={vid}")

    print(f"\n--- SEM MATCH (top 25) ---")
    for item in det_sem[:25]:
        print(f"  {item[0][:35]:35} {item[1][:30]:30} {item[2][:40]}")


if __name__ == "__main__":
    main()
