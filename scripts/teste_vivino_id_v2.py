"""
Teste com 300 novos registros em ordem alfabetica:
1. Classificacao (W/X/S)
2. Dados estruturados (produtor, vinho, pais, cor)
3. Vivino ID (pra testar alucinacao)
4. Duplicatas (=N)
"""
import csv, os, time
import google.generativeai as genai

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
CSV_PATH = os.path.join(os.path.dirname(__file__), "teste_dedup_300.csv")
BATCH_SIZE = 150

PROMPT = """TAREFA: Classifique cada item e extraia dados.

REGRAS:
- X = nao e vinho (comida, objeto, cosmetico, cerveja, codigo, texto sem sentido)
- S = destilado/spirit (whisky, gin, rum, vodka, cognac, etc)
- W = vinho. Formato: W|Produtor|Vinho|Pais|Cor|VID|Regiao
  - Produtor = nome EXATO da vinicola/bodega. Se nao sabe: ??
  - Vinho = nome do vinho SEM produtor. Se nao sabe: ??
  - Pais = codigo 2 letras. Se nao sabe: ??
  - Cor: r=tinto, w=branco, p=rose, s=espumante, f=fortificado, d=sobremesa
  - VID = ID numerico do Vivino (vivino.com/w/ID). Se nao sabe o ID exato: 0
  - Regiao = regiao do Vivino (ex: Champagne, Napa Valley). Se nao sabe: omitir
- DUPLICATAS: se o item e o mesmo vinho que outro no lote (safra/formato diferente), adicione =N (N = numero do primeiro)
- Se o nome nao faz sentido como vinho (codigos, numeros soltos, lixo), responda X
- NAO invente dados. Na duvida, use 0 para VID e ?? para campos desconhecidos.

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

    all_responses = []
    start_num = 1

    for batch_start in range(0, len(items), BATCH_SIZE):
        batch = items[batch_start:batch_start + BATCH_SIZE]
        items_text = "\n".join(f"{start_num + i}. {item['loja_nome']}" for i, item in enumerate(batch))

        print(f"\nLote {batch_start//BATCH_SIZE + 1} ({len(batch)} itens)...", flush=True)

        try:
            resp = model.generate_content(
                PROMPT + items_text,
                generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=8192),
            )
            text = resp.text.strip()
        except Exception as e:
            print(f"ERRO: {e}")
            text = ""

        # Parse
        line_map = {}
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split(". ", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                line_map[int(parts[0].strip())] = parts[1].strip()

        for i, item in enumerate(batch):
            num = start_num + i
            llm = line_map.get(num, "MISSING")
            all_responses.append({
                "num": num,
                "loja_nome": item["loja_nome"],
                "destino": item["destino"],
                "score": item["score"],
                "wl": item["wine_likeness"],
                "vid_pipeline": int(item["vid"]) if item["vid"] else 0,
                "vnome_pipeline": item["vnome"],
                "llm": llm,
            })

        start_num += len(batch)
        if batch_start + BATCH_SIZE < len(items):
            time.sleep(5)

    # === ANALISE ===
    print(f"\n{'='*60}")
    print("RESULTADOS")
    print(f"{'='*60}")

    wines = [r for r in all_responses if r["llm"].startswith("W")]
    notwine = [r for r in all_responses if r["llm"].startswith("X")]
    spirits = [r for r in all_responses if r["llm"].startswith("S")]
    print(f"\nClassificacao: W={len(wines)} X={len(notwine)} S={len(spirits)}")

    # Extrair VIDs do LLM
    llm_vids = {}
    for r in wines:
        parts = r["llm"].split("|")
        if len(parts) >= 6:
            try:
                vid = int(parts[5])
                if vid > 0:
                    llm_vids[r["num"]] = {"vid": vid, "nome": r["loja_nome"], "llm": r["llm"], "vid_pipeline": r["vid_pipeline"]}
            except ValueError:
                pass

    print(f"\n--- VIVINO IDs ---")
    print(f"Vinhos classificados W: {len(wines)}")
    print(f"LLM deu VID > 0:       {len(llm_vids)}")
    print(f"LLM disse 0 (nao sabe): {len(wines) - len(llm_vids)}")

    # Verificar contra banco
    if llm_vids:
        import psycopg2
        conn = psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                                user="postgres", password="postgres123",
                                options="-c client_encoding=UTF8")
        cur = conn.cursor()

        all_ids = list(set([v["vid"] for v in llm_vids.values()] + [v["vid_pipeline"] for v in llm_vids.values() if v["vid_pipeline"] > 0]))
        cur.execute("SELECT id, produtor_normalizado, nome_normalizado FROM vivino_match WHERE id = ANY(%s)", (all_ids,))
        db_wines = {row[0]: {"produtor": row[1], "nome": row[2]} for row in cur.fetchall()}
        conn.close()

        llm_valid = 0
        llm_invalid = 0
        llm_same_as_pipeline = 0
        llm_diff_from_pipeline = 0

        print(f"\n--- VERIFICACAO ---")

        invalids = []
        valids = []
        same = []
        diff = []

        for num, info in llm_vids.items():
            vid = info["vid"]
            if vid in db_wines:
                llm_valid += 1
                valids.append((info["nome"], vid, db_wines[vid]["produtor"], db_wines[vid]["nome"]))
            else:
                llm_invalid += 1
                invalids.append((info["nome"], vid))

            if info["vid_pipeline"] > 0:
                if vid == info["vid_pipeline"]:
                    llm_same_as_pipeline += 1
                    same.append((info["nome"], vid))
                else:
                    llm_diff_from_pipeline += 1
                    pip_info = db_wines.get(info["vid_pipeline"], {"produtor": "?", "nome": "?"})
                    diff.append((info["nome"], vid, db_wines.get(vid, {"produtor":"?","nome":"?"})["nome"], info["vid_pipeline"], pip_info["nome"]))

        print(f"IDs que EXISTEM no banco:   {llm_valid}")
        print(f"IDs INVENTADOS:             {llm_invalid}")
        if len(llm_vids) > 0:
            print(f"Taxa de alucinacao:         {llm_invalid*100//len(llm_vids)}%")

        print(f"\nIgual ao pipeline:          {llm_same_as_pipeline}")
        print(f"Diferente do pipeline:      {llm_diff_from_pipeline}")

        print(f"\n--- IDs INVENTADOS (top 15) ---")
        for nome, vid in invalids[:15]:
            print(f"  {nome[:55]:55} VID={vid} (NAO EXISTE)")

        print(f"\n--- IDs CORRETOS (top 15) ---")
        for nome, vid, prod, vnome in valids[:15]:
            print(f"  {nome[:45]:45} VID={vid} -> {prod} - {vnome}")

        print(f"\n--- IDs IGUAIS AO PIPELINE (top 10) ---")
        for nome, vid in same[:10]:
            print(f"  {nome[:55]:55} VID={vid}")

        print(f"\n--- IDs DIFERENTES DO PIPELINE (top 10) ---")
        for nome, llm_vid, llm_nome, pip_vid, pip_nome in diff[:10]:
            print(f"  {nome[:40]:40} LLM={llm_vid}({llm_nome[:25]}) PIP={pip_vid}({pip_nome[:25]})")

    # === DUPLICATAS ===
    dupes = [r for r in all_responses if "=" in r["llm"]]
    print(f"\n--- DUPLICATAS ENCONTRADAS ---")
    print(f"Total itens marcados como duplicata: {len(dupes)}")
    for r in dupes:
        print(f"  #{r['num']} {r['loja_nome'][:55]:55} -> {r['llm'][:60]}")


if __name__ == "__main__":
    main()
