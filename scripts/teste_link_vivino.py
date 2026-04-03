"""
Teste: pedir LINK do Vivino em vez de ID.
Depois verificar se os links sao reais.
"""
import csv, os, time, re
import google.generativeai as genai

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
CSV_PATH = os.path.join(os.path.dirname(__file__), "teste_link_300.csv")
BATCH_SIZE = 150

PROMPT = """TAREFA: Classifique cada item e extraia dados.

REGRAS:
- X = nao e vinho (comida, objeto, cosmetico, cerveja, codigo, texto sem sentido)
- S = destilado/spirit (whisky, gin, rum, vodka, cognac, etc)
- W = vinho. Formato: W|Produtor|Vinho|Pais|Cor|Link Vivino
  - Produtor = nome EXATO da vinicola/bodega. Se nao sabe: ??
  - Vinho = nome do vinho SEM produtor. Se nao sabe: ??
  - Pais = codigo 2 letras. Se nao sabe: ??
  - Cor: r=tinto, w=branco, p=rose, s=espumante, f=fortificado, d=sobremesa
  - Link Vivino = URL completa da pagina deste vinho no vivino.com (ex: https://www.vivino.com/w/12345). Se nao sabe o link exato: 0
- DUPLICATAS: se o item e o mesmo vinho que outro no lote (safra/formato diferente), adicione =N
- Se o nome nao faz sentido como vinho, responda X
- NAO invente links. Se nao tem certeza do link exato do Vivino, use 0.

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

    # Extrair links
    links_given = []
    links_zero = []
    for r in wines:
        # Procurar URL no campo llm
        urls = re.findall(r'https?://[^\s|,=]+', r["llm"])
        if urls:
            links_given.append({"nome": r["loja_nome"], "link": urls[0], "llm": r["llm"], "vid_pipeline": r["vid_pipeline"]})
        else:
            links_zero.append(r)

    print(f"\nVinhos com link Vivino: {len(links_given)}")
    print(f"Vinhos sem link (0):    {len(links_zero)}")

    # Extrair IDs dos links
    link_ids = {}
    for item in links_given:
        match = re.search(r'/w/(\d+)', item["link"])
        if match:
            link_ids[item["nome"]] = {"vid_llm": int(match.group(1)), "link": item["link"], "vid_pipeline": item["vid_pipeline"]}
        else:
            # Talvez formato diferente
            match2 = re.search(r'vivino\.com/[^/]+/[^/]+/w/(\d+)', item["link"])
            if match2:
                link_ids[item["nome"]] = {"vid_llm": int(match2.group(1)), "link": item["link"], "vid_pipeline": item["vid_pipeline"]}

    print(f"Links com ID extraivel: {len(link_ids)}")

    # Verificar contra banco
    if link_ids:
        import psycopg2
        conn = psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                                user="postgres", password="postgres123",
                                options="-c client_encoding=UTF8")
        cur = conn.cursor()

        all_vids = list(set([v["vid_llm"] for v in link_ids.values()] + [v["vid_pipeline"] for v in link_ids.values() if v["vid_pipeline"] > 0]))
        cur.execute("SELECT id, produtor_normalizado, nome_normalizado FROM vivino_match WHERE id = ANY(%s)", (all_vids,))
        db_wines = {row[0]: {"produtor": row[1], "nome": row[2]} for row in cur.fetchall()}
        conn.close()

        valid = 0
        invalid = 0
        same_as_pipeline = 0
        diff_from_pipeline = 0

        print(f"\n--- VERIFICACAO DOS LINKS ---")

        for nome, info in list(link_ids.items())[:50]:
            vid = info["vid_llm"]
            exists = vid in db_wines
            if exists:
                valid += 1
            else:
                invalid += 1

            if info["vid_pipeline"] > 0:
                if vid == info["vid_pipeline"]:
                    same_as_pipeline += 1
                else:
                    diff_from_pipeline += 1

        # Contar o resto
        for nome, info in list(link_ids.items())[50:]:
            vid = info["vid_llm"]
            if vid in db_wines:
                valid += 1
            else:
                invalid += 1
            if info["vid_pipeline"] > 0:
                if vid == info["vid_pipeline"]:
                    same_as_pipeline += 1
                else:
                    diff_from_pipeline += 1

        print(f"Links que EXISTEM no banco:  {valid}")
        print(f"Links INVENTADOS:            {invalid}")
        if len(link_ids) > 0:
            print(f"Taxa de alucinacao:          {invalid*100//len(link_ids)}%")
        print(f"Igual ao pipeline:           {same_as_pipeline}")
        print(f"Diferente do pipeline:       {diff_from_pipeline}")

        print(f"\n--- LINKS INVENTADOS (top 15) ---")
        count = 0
        for nome, info in link_ids.items():
            if info["vid_llm"] not in db_wines:
                print(f"  {nome[:45]:45} {info['link'][:60]}")
                count += 1
                if count >= 15:
                    break

        print(f"\n--- LINKS CORRETOS (existem no banco, top 15) ---")
        count = 0
        for nome, info in link_ids.items():
            vid = info["vid_llm"]
            if vid in db_wines:
                db = db_wines[vid]
                print(f"  {nome[:40]:40} {info['link'][:45]:45} -> {db['produtor']} - {db['nome'][:25]}")
                count += 1
                if count >= 15:
                    break

        print(f"\n--- LINKS IGUAIS AO PIPELINE (top 10) ---")
        count = 0
        for nome, info in link_ids.items():
            if info["vid_pipeline"] > 0 and info["vid_llm"] == info["vid_pipeline"]:
                print(f"  {nome[:55]:55} VID={info['vid_llm']}")
                count += 1
                if count >= 10:
                    break

        print(f"\n--- LINKS DIFERENTES DO PIPELINE (top 10) ---")
        count = 0
        for nome, info in link_ids.items():
            if info["vid_pipeline"] > 0 and info["vid_llm"] != info["vid_pipeline"]:
                llm_ok = "EXISTE" if info["vid_llm"] in db_wines else "FAKE"
                pip_nome = db_wines.get(info["vid_pipeline"], {"nome": "?"})["nome"]
                llm_nome = db_wines.get(info["vid_llm"], {"nome": "?"})["nome"]
                print(f"  {nome[:35]:35} LLM={info['vid_llm']}({llm_ok},{llm_nome[:20]}) PIP={info['vid_pipeline']}({pip_nome[:20]})")
                count += 1
                if count >= 10:
                    break
    else:
        print("\nNenhum link com ID extraivel encontrado.")

    # Mostrar exemplos de respostas brutas
    print(f"\n--- EXEMPLOS DE RESPOSTAS (primeiros 20 W) ---")
    count = 0
    for r in all_responses:
        if r["llm"].startswith("W"):
            print(f"  #{r['num']} {r['loja_nome'][:45]:45} -> {r['llm'][:80]}")
            count += 1
            if count >= 20:
                break

    # Duplicatas
    dupes = [r for r in all_responses if "=" in r["llm"] and r["llm"].startswith("W")]
    print(f"\n--- DUPLICATAS: {len(dupes)} ---")
    for r in dupes[:20]:
        print(f"  #{r['num']} {r['loja_nome'][:55]:55} -> ...{r['llm'][-15:]}")


if __name__ == "__main__":
    main()
