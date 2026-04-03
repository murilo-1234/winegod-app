"""
Teste: pedir vivino_id para vinhos que o Gemini disse existir no Vivino.
Depois verifica se os IDs existem na nossa base vivino_match.
"""
import csv, os, time, json
import google.generativeai as genai

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
BATCH_SIZE = 100

PROMPT = """Para cada vinho abaixo, informe o ID numerico do Vivino (vivino.com/w/ID).
Se nao sabe o ID exato, responda 0.
Responda APENAS no formato: numero. id_vivino

Exemplo:
1. 12345
2. 0
3. 67890

VINHOS:
"""

def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    # Carregar vinhos V do formato B
    v_wines = []
    with open("scripts/teste_llm_resultados/formato_B_resultados.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if "|V|" in r["llm"]:
                v_wines.append(r)

    # Pegar 300
    v_wines = v_wines[:300]
    print(f"Total vinhos com V: {len(v_wines)}")

    # Enviar em lotes de 100
    all_results = []
    for batch_start in range(0, len(v_wines), BATCH_SIZE):
        batch = v_wines[batch_start:batch_start + BATCH_SIZE]
        items_text = ""
        for i, w in enumerate(batch):
            items_text += f"{i+1}. {w['loja_nome']}\n"

        print(f"\nLote {batch_start//BATCH_SIZE + 1} ({len(batch)} vinhos)...", end=" ", flush=True)

        try:
            resp = model.generate_content(
                PROMPT + items_text,
                generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=4096),
            )
            text = resp.text.strip()
        except Exception as e:
            print(f"ERRO: {e}")
            text = ""

        # Parse resposta
        lines = text.split("\n")
        id_map = {}
        for line in lines:
            line = line.strip().rstrip(".")
            if ". " in line:
                parts = line.split(". ", 1)
                if parts[0].strip().isdigit():
                    num = int(parts[0].strip())
                    vid = parts[1].strip()
                    # Limpar possiveis textos extras
                    vid = vid.split()[0] if vid else "0"
                    try:
                        id_map[num] = int(vid)
                    except ValueError:
                        id_map[num] = 0

        for i, w in enumerate(batch):
            llm_vid = id_map.get(i + 1, -1)  # -1 = nao respondeu
            all_results.append({
                "loja_nome": w["loja_nome"],
                "llm_response": w["llm"],
                "vivino_id_pipeline": int(w["vivino_id_atual"]) if w["vivino_id_atual"] else 0,
                "vivino_id_llm": llm_vid,
            })

        got = sum(1 for i in range(len(batch)) if id_map.get(i+1, 0) > 0)
        print(f"IDs recebidos: {got}/{len(batch)}")

        if batch_start + BATCH_SIZE < len(v_wines):
            time.sleep(5)

    # Verificar IDs contra banco local
    import psycopg2
    conn = psycopg2.connect(
        host="localhost", port=5432, dbname="winegod_db",
        user="postgres", password="postgres123",
        options="-c client_encoding=UTF8"
    )
    cur = conn.cursor()

    # Buscar todos vivino_ids de uma vez
    llm_ids = [r["vivino_id_llm"] for r in all_results if r["vivino_id_llm"] > 0]
    pipeline_ids = [r["vivino_id_pipeline"] for r in all_results if r["vivino_id_pipeline"] > 0]
    all_ids = list(set(llm_ids + pipeline_ids))

    if all_ids:
        cur.execute(f"SELECT id FROM vivino_match WHERE id = ANY(%s)", (all_ids,))
        valid_ids = set(row[0] for row in cur.fetchall())
    else:
        valid_ids = set()

    conn.close()

    # Analise
    print(f"\n{'='*60}")
    print("RESULTADO DO TESTE VIVINO ID")
    print(f"{'='*60}")

    total = len(all_results)
    llm_gave_id = sum(1 for r in all_results if r["vivino_id_llm"] > 0)
    llm_said_zero = sum(1 for r in all_results if r["vivino_id_llm"] == 0)
    llm_no_answer = sum(1 for r in all_results if r["vivino_id_llm"] == -1)

    print(f"\nTotal vinhos testados: {total}")
    print(f"LLM deu ID:          {llm_gave_id}")
    print(f"LLM disse 0 (nao sabe): {llm_said_zero}")
    print(f"LLM nao respondeu:    {llm_no_answer}")

    # Verificar IDs do LLM
    llm_valid = sum(1 for r in all_results if r["vivino_id_llm"] > 0 and r["vivino_id_llm"] in valid_ids)
    llm_invalid = sum(1 for r in all_results if r["vivino_id_llm"] > 0 and r["vivino_id_llm"] not in valid_ids)
    print(f"\nIDs do LLM que EXISTEM no banco: {llm_valid}")
    print(f"IDs do LLM INVENTADOS:           {llm_invalid}")
    if llm_gave_id > 0:
        print(f"Taxa de alucinacao:              {llm_invalid*100//llm_gave_id}%")

    # Comparar com pipeline
    match_both = 0
    match_same = 0
    match_diff = 0
    for r in all_results:
        if r["vivino_id_llm"] > 0 and r["vivino_id_pipeline"] > 0:
            match_both += 1
            if r["vivino_id_llm"] == r["vivino_id_pipeline"]:
                match_same += 1
            else:
                match_diff += 1

    print(f"\nAmbos (LLM e pipeline) deram ID: {match_both}")
    print(f"  Mesmo ID:                       {match_same}")
    print(f"  IDs diferentes:                 {match_diff}")

    # Exemplos
    print(f"\n--- EXEMPLOS ---")
    print(f"\nIDs inventados pelo LLM (nao existem no banco):")
    count = 0
    for r in all_results:
        if r["vivino_id_llm"] > 0 and r["vivino_id_llm"] not in valid_ids:
            print(f"  {r['loja_nome'][:55]:55} LLM={r['vivino_id_llm']}")
            count += 1
            if count >= 10:
                break

    print(f"\nIDs corretos (LLM = pipeline = existe no banco):")
    count = 0
    for r in all_results:
        if r["vivino_id_llm"] > 0 and r["vivino_id_llm"] == r["vivino_id_pipeline"] and r["vivino_id_llm"] in valid_ids:
            print(f"  {r['loja_nome'][:55]:55} ID={r['vivino_id_llm']}")
            count += 1
            if count >= 10:
                break

    print(f"\nIDs diferentes (LLM != pipeline, mas ambos existem):")
    count = 0
    for r in all_results:
        if r["vivino_id_llm"] > 0 and r["vivino_id_pipeline"] > 0 and r["vivino_id_llm"] != r["vivino_id_pipeline"]:
            llm_ok = "EXISTE" if r["vivino_id_llm"] in valid_ids else "INVENTADO"
            pip_ok = "EXISTE" if r["vivino_id_pipeline"] in valid_ids else "INVENTADO"
            print(f"  {r['loja_nome'][:45]:45} LLM={r['vivino_id_llm']}({llm_ok}) PIP={r['vivino_id_pipeline']}({pip_ok})")
            count += 1
            if count >= 10:
                break


if __name__ == "__main__":
    main()
