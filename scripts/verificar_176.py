"""
Verificar TODOS os 176 vinhos unicos do Sol 3 contra vivino_match.
"""
import csv, os, time, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
SD = os.path.dirname(__file__)

PROMPT = """Exemplos do nosso banco:
  produtor: "chateau levangile"  vinho: "pomerol"
  produtor: "campo viejo"  vinho: "reserva rioja"
  produtor: "penfolds"  vinho: "grange shiraz"

TODOS os itens. Uma linha por item. Sem markdown.

Formato:
1. X
2. S
3. W|ProdBanco|VinhoBanco|Pais|Cor
4. W|ProdBanco|VinhoBanco|Pais|Cor|=3

ProdBanco/VinhoBanco = minusculo, sem acento, l' junto, saint junto.
=M=duplicata. X=nao vinho. S=destilado. ??=nao sabe. NAO invente.

"""

def norm(s):
    s = s.lower().strip()
    for o, n in [("\u00e1","a"),("\u00e0","a"),("\u00e2","a"),("\u00e3","a"),("\u00e4","a"),
                 ("\u00e9","e"),("\u00e8","e"),("\u00ea","e"),("\u00eb","e"),
                 ("\u00ed","i"),("\u00ec","i"),("\u00ee","i"),("\u00ef","i"),
                 ("\u00f3","o"),("\u00f2","o"),("\u00f4","o"),("\u00f5","o"),("\u00f6","o"),
                 ("\u00fa","u"),("\u00f9","u"),("\u00fb","u"),("\u00fc","u"),
                 ("\u00f1","n"),("\u00e7","c")]:
        s = s.replace(o, n)
    s = re.sub(r"['\u2019\u2018`]", "", s)
    s = re.sub(r"-", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def parse(text):
    m = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        p = line.split(". ", 1)
        if len(p) == 2 and p[0].strip().isdigit():
            m[int(p[0].strip())] = p[1].strip()
    return m


def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    items = []
    with open(os.path.join(SD, "teste_sol3.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            items.append(r)

    # Passo 1: LLM classifica
    print("Rodando LLM em 15 batches de 20...")
    all_lines = {}
    sn = 1
    for bs in range(0, len(items), 20):
        batch = items[bs:bs + 20]
        txt = "\n".join(f"{sn + i}. {it['loja_nome']}" for i, it in enumerate(batch))
        for att in range(5):
            try:
                r = model.generate_content(PROMPT + txt,
                    generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=4096))
                lines = parse(r.text.strip())
                if len(lines) >= len(batch) * 0.7:
                    break
            except:
                pass
            time.sleep(3)
        all_lines.update(lines)
        sn += len(batch)
        time.sleep(1.5)
        bn = bs // 20 + 1
        if bn % 5 == 0:
            print(f"  batch {bn}/15 done, {len(all_lines)} resp")

    # Separar
    wines = {}
    dups = {}
    for i in range(len(items)):
        llm = all_lines.get(i + 1, "")
        if not llm.startswith("W"):
            continue
        parts = llm.split("|")
        if len(parts) < 5:
            continue
        prod = norm(parts[1].strip().split("=")[0].strip())
        vin = norm(parts[2].strip().split("=")[0].strip())
        is_dup = "=" in llm
        entry = {"prod": prod, "vin": vin, "loja": items[i]["loja_nome"], "llm": llm}
        if is_dup:
            dups[i] = entry
        else:
            wines[i] = entry

    total_w = len(wines) + len(dups)
    total_x = sum(1 for v in all_lines.values() if v.startswith("X"))
    total_s = sum(1 for v in all_lines.values() if v.startswith("S"))
    resp = len(all_lines)

    print(f"\nRespondidos: {resp}/300")
    print(f"W={total_w} (unicos={len(wines)} dup={len(dups)}) X={total_x} S={total_s}")

    # Passo 2: verificar TODOS unicos contra vivino_match
    conn = psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                            user="postgres", password="postgres123",
                            options="-c client_encoding=UTF8")
    cur = conn.cursor()

    match_ok = 0
    match_errado = 0
    sem_match_vinho = 0
    sem_match_naovinho = 0
    det_ok = []
    det_errado = []
    det_novo = []
    det_nv = []

    for idx, w in wines.items():
        nome_norm = norm(w["loja"])
        search = f"{w['prod']} {w['vin']}".strip()

        # Busca 1: texto_busca com produtor+vinho do LLM
        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(texto_busca, %s) as ts
            FROM vivino_match WHERE texto_busca %% %s
            ORDER BY similarity(texto_busca, %s) DESC LIMIT 3
        """, (search, search, search))
        cands = cur.fetchall()

        # Busca 2: fallback com nome original
        if not cands and len(nome_norm) >= 6:
            cur.execute("""
                SELECT id, produtor_normalizado, nome_normalizado,
                       similarity(texto_busca, %s) as ts
                FROM vivino_match WHERE texto_busca %% %s
                ORDER BY similarity(texto_busca, %s) DESC LIMIT 3
            """, (nome_norm, nome_norm, nome_norm))
            cands = cur.fetchall()

        if cands and cands[0][3] >= 0.30:
            best = cands[0]
            # Verificar: palavras em comum entre busca e resultado
            search_words = set(search.split()) - {"de", "du", "la", "le", "les", "des", "del", "di", "the", "??"}
            db_words = set(best[1].split()) | set(best[2].split())
            db_words -= {"de", "du", "la", "le", "les", "des", "del", "di", "the"}

            if search_words:
                overlap = len(search_words & db_words)
                ratio = overlap / len(search_words)
            else:
                ratio = 0

            if ratio >= 0.25 or best[3] >= 0.50:
                match_ok += 1
                det_ok.append((w["loja"][:40], f"{best[1]} - {best[2]}"[:45], f"{best[3]:.2f}"))
            else:
                match_errado += 1
                det_errado.append((w["loja"][:40], f"{best[1]} - {best[2]}"[:45], f"{best[3]:.2f}", f"ov={ratio:.0%}"))
        else:
            # Sem match: vinho real ou nao-vinho?
            nv_words = ["chip", "soap", "candle", "glass", "mug", "tea ", "coffee", "chocolate",
                        "perfume", "cream", "gel", "spray", "pomelo", "banana", "mango", "vanilla",
                        "cookie", "biscuit", "jam", "honey", "sauce", "pasta", "rice", "book",
                        "shirt", "cap ", "hat ", "set of", "gift", "sticker", "poster", "game",
                        "toy", "phone", "cable", "dvd", " cd ", "vinyl", " live", "concert",
                        "mason", "ticket", "cassava", "green bean", "flavour", "gum"]
            loja_low = w["loja"].lower()
            is_nv = any(nv in loja_low for nv in nv_words)

            if is_nv:
                sem_match_naovinho += 1
                det_nv.append(w["loja"][:55])
            else:
                sem_match_vinho += 1
                det_novo.append((w["loja"][:50], f"{w['prod']}|{w['vin']}"[:30]))

    conn.close()

    nu = len(wines)
    print(f"\n{'=' * 70}")
    print(f"VERIFICACAO DOS {nu} VINHOS UNICOS")
    print(f"{'=' * 70}")
    print(f"")
    print(f"MATCH CORRETO (Vivino):    {match_ok:>4} ({match_ok * 100 // nu}%)")
    print(f"MATCH ERRADO:              {match_errado:>4} ({match_errado * 100 // nu}%)")
    print(f"SEM MATCH (vinho novo):    {sem_match_vinho:>4} ({sem_match_vinho * 100 // nu}%) -> sobe sem vivino_id")
    print(f"NAO-VINHO (LLM errou):     {sem_match_naovinho:>4} ({sem_match_naovinho * 100 // nu}%) -> eliminar")
    print(f"")
    print(f"TOTAL PRO RENDER:")
    print(f"  Com vivino_id:   {match_ok}")
    print(f"  Vinhos novos:    {sem_match_vinho}")
    print(f"  Descartados:     {match_errado + sem_match_naovinho}")
    print(f"  Duplicatas:      {len(dups)}")
    print(f"  Nao-vinho (X):   {total_x}")
    print(f"  Destilados (S):  {total_s}")

    print(f"\n--- MATCH CORRETO ({match_ok}, primeiros 25) ---")
    for loja, db, sim in det_ok[:25]:
        print(f"  {loja:40} -> {db} ({sim})")

    print(f"\n--- MATCH ERRADO ({match_errado}) ---")
    for item in det_errado:
        print(f"  {item[0]:40} -> {item[1]} ({item[2]} {item[3]})")

    print(f"\n--- VINHOS NOVOS sem Vivino ({sem_match_vinho}) ---")
    for loja, data in det_novo:
        print(f"  {loja:50} {data}")

    print(f"\n--- NAO-VINHO que LLM classificou como W ({sem_match_naovinho}) ---")
    for loja in det_nv:
        print(f"  {loja}")


if __name__ == "__main__":
    main()
