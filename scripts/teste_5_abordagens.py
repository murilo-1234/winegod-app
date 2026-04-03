"""
Teste das 5 abordagens mais promissoras, 300 itens cada.
"""
import csv, os, time, re, sys
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
BATCH_SIZE = 150
SCRIPT_DIR = os.path.dirname(__file__)

# ============================================================
# PROMPTS
# ============================================================

# Teste 1+2: pedir uva + denominacao
PROMPT_T1 = """TAREFA: Classifique cada item e extraia dados de vinho.

REGRAS:
- X = nao e vinho | S = destilado/spirit
- W = vinho. Formato: W|Produtor|Vinho|Pais|Cor|Uva|Denominacao
  - Produtor = nome completo da vinicola/bodega/chateau
  - Vinho = nome do vinho SEM o produtor
  - Pais = 2 letras (?? se nao sabe)
  - Cor: r/w/p/s/f/d
  - Uva = uva principal (ex: merlot, cabernet sauvignon, chardonnay). ?? se nao sabe
  - Denominacao = apelacao/DOC/AOC (ex: Pomerol, Barolo DOCG, Napa Valley). ?? se nao sabe
- DUPLICATAS: =N | NAO invente dados.

ITEMS:
"""

# Teste 6: few-shot com exemplos reais do banco
PROMPT_T6 = """TAREFA: Classifique cada item e extraia dados de vinho.

Nosso banco armazena produtores e vinhos neste formato (exemplos reais):
  produtor: "chateau levangile"     vinho: "blason de levangile pomerol"
  produtor: "chateau lenclos"       vinho: "pomerol"
  produtor: "chateau la bastide"    vinho: "corbieres tradition rouge"
  produtor: "domaine de la romanee conti"  vinho: "romanee conti grand cru"
  produtor: "bodega catena zapata"  vinho: "catena alta malbec"
  produtor: "tenuta san guido"      vinho: "sassicaia"
  produtor: "penfolds"              vinho: "grange shiraz"
  produtor: "opus one"              vinho: "opus one"
  produtor: "antinori"              vinho: "tignanello"
  produtor: "joseph phelps vineyards"  vinho: "insignia"

REGRAS:
- X = nao e vinho | S = destilado/spirit
- W = vinho. Formato: W|ProdBanco|VinhoBanco|Pais|Cor
  - ProdBanco = produtor como estaria no nosso banco: minusculo, sem acentos, sem apostrofos, l' junto (levangile nao l evangile), saint junto (saintemilion nao saint emilion)
  - VinhoBanco = vinho como estaria no banco: mesma regra
  - Pais = 2 letras | Cor: r/w/p/s/f/d
- DUPLICATAS: =N | NAO invente dados.

ITEMS:
"""

# Teste 11: prompt simples (LLM so classifica, match reverso depois)
PROMPT_T11_CLASSIFY = """TAREFA: Classifique cada item.
- W|Produtor|Vinho|Pais|Cor = vinho
- X = nao e vinho | S = destilado
- DUPLICATAS: =N | NAO invente. ?? se nao sabe.

ITEMS:
"""

PROMPT_T11_CONFIRM = """Temos uma lista de vinhos de loja e candidatos do nosso banco de dados.
Para cada par, responda: S (sim, mesmo vinho), N (nao, vinhos diferentes), P (provavelmente).
Responda APENAS S, N ou P para cada numero.

PARES:
"""

# ============================================================
# HELPERS
# ============================================================

def load_items(path):
    items = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            items.append(r)
    return items

def call_llm(model, prompt, items_text):
    try:
        resp = model.generate_content(
            prompt + items_text,
            generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=8192),
        )
        return resp.text.strip()
    except Exception as e:
        print(f"  ERRO: {e}")
        return ""

def parse_lines(text):
    line_map = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line: continue
        parts = line.split(". ", 1)
        if len(parts) == 2 and parts[0].strip().isdigit():
            line_map[int(parts[0].strip())] = parts[1].strip()
    return line_map

def get_db():
    return psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                            user="postgres", password="postgres123",
                            options="-c client_encoding=UTF8")

def normalize_script(s):
    """Normalizacao no script: acentos, l', d', saint-, hifens."""
    s = s.lower().strip()
    # Acentos comuns
    for old, new in [("á","a"),("à","a"),("â","a"),("ã","a"),("ä","a"),
                     ("é","e"),("è","e"),("ê","e"),("ë","e"),
                     ("í","i"),("ì","i"),("î","i"),("ï","i"),
                     ("ó","o"),("ò","o"),("ô","o"),("õ","o"),("ö","o"),
                     ("ú","u"),("ù","u"),("û","u"),("ü","u"),
                     ("ñ","n"),("ç","c")]:
        s = s.replace(old, new)
    # Apostrofos: l' d' s' → juntar
    s = re.sub(r"[''`]", "", s)
    # Hifens: saint-emilion → saintemilion
    s = re.sub(r"-", "", s)
    # Remover caracteres especiais
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def run_llm_batches(model, prompt, items):
    """Roda LLM em batches e retorna dict {num: resposta}."""
    all_lines = {}
    start_num = 1
    for batch_start in range(0, len(items), BATCH_SIZE):
        batch = items[batch_start:batch_start + BATCH_SIZE]
        items_text = "\n".join(f"{start_num + i}. {item['loja_nome']}" for i, item in enumerate(batch))
        print(f"  Lote {batch_start//BATCH_SIZE + 1}...", end=" ", flush=True)
        text = call_llm(model, prompt, items_text)
        lines = parse_lines(text)
        w = sum(1 for v in lines.values() if v.startswith("W"))
        print(f"W={w}")
        for k, v in lines.items():
            all_lines[k] = v
        start_num += len(batch)
        if batch_start + BATCH_SIZE < len(items):
            time.sleep(5)
    return all_lines


# ============================================================
# TESTE 7+8: pg_trgm no produtor + vinho
# ============================================================
def test_trgm(items, model):
    print(f"\n{'='*60}")
    print("TESTE 7+8: pg_trgm no produtor + vinho")
    print(f"{'='*60}")

    # Usar prompt basico
    prompt = """TAREFA: Classifique e extraia dados.
- X = nao e vinho | S = destilado
- W = vinho: W|Produtor|Vinho|Pais|Cor
- DUPLICATAS: =N | NAO invente. ?? se nao sabe.

ITEMS:
"""
    lines = run_llm_batches(model, prompt, items)
    conn = get_db()
    cur = conn.cursor()

    match_ok = 0
    no_match = 0
    total_w = 0

    for i, item in enumerate(items):
        num = i + 1
        llm = lines.get(num, "MISSING")
        if not llm.startswith("W"): continue
        total_w += 1

        parts = llm.split("|")
        if len(parts) < 5: no_match += 1; continue
        produtor = normalize_script(parts[1])
        vinho = normalize_script(parts[2])
        if not produtor or produtor == "??": no_match += 1; continue

        # pg_trgm: busca fuzzy por produtor + vinho combinado
        search_text = f"{produtor} {vinho}".strip()
        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(produtor_normalizado, %s) as prod_sim,
                   similarity(nome_normalizado, %s) as nome_sim
            FROM vivino_match
            WHERE produtor_normalizado %% %s
            ORDER BY similarity(produtor_normalizado, %s) DESC
            LIMIT 10
        """, (produtor, vinho, produtor, produtor))
        candidates = cur.fetchall()

        if candidates:
            best = max(candidates, key=lambda c: c[3] * 0.6 + c[4] * 0.4)
            combined = best[3] * 0.6 + best[4] * 0.4
            if combined >= 0.35:
                match_ok += 1
            else:
                no_match += 1
        else:
            no_match += 1

    conn.close()
    pct = match_ok * 100 // total_w if total_w else 0
    print(f"\n  Vinhos (W): {total_w} | Match: {match_ok} ({pct}%) | Sem: {no_match}")
    return pct


# ============================================================
# TESTE 1+2: uva + denominacao
# ============================================================
def test_uva_denom(items, model):
    print(f"\n{'='*60}")
    print("TESTE 1+2: Uva + Denominacao")
    print(f"{'='*60}")

    lines = run_llm_batches(model, PROMPT_T1, items)
    conn = get_db()
    cur = conn.cursor()

    match_ok = 0
    no_match = 0
    total_w = 0

    for i, item in enumerate(items):
        num = i + 1
        llm = lines.get(num, "MISSING")
        if not llm.startswith("W"): continue
        total_w += 1

        parts = llm.split("|")
        if len(parts) < 7: no_match += 1; continue
        produtor = normalize_script(parts[1])
        vinho = normalize_script(parts[2])
        uva = normalize_script(parts[5]) if parts[5] != "??" else ""
        denom = normalize_script(parts[6].split("=")[0]) if parts[6].split("=")[0] != "??" else ""

        if not produtor or produtor == "??": no_match += 1; continue

        # Busca por produtor com pg_trgm
        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(produtor_normalizado, %s) as sim
            FROM vivino_match
            WHERE produtor_normalizado %% %s
            ORDER BY sim DESC LIMIT 20
        """, (produtor, produtor))
        candidates = cur.fetchall()

        if not candidates:
            no_match += 1; continue

        # Scoring com uva e denominacao
        best_score = 0
        for cand_id, cand_prod, cand_nome, prod_sim in candidates:
            score = prod_sim * 3  # produtor weight

            # Vinho overlap
            vn_words = set(vinho.split()) - {"de","du","la","le","les","des","del","di","the"}
            cn_words = set(cand_nome.split()) - {"de","du","la","le","les","des","del","di","the"}
            if vn_words and cn_words:
                overlap = len(vn_words & cn_words) / max(len(vn_words), len(cn_words))
                score += overlap * 2

            # Uva bonus
            if uva and uva in cand_nome:
                score += 1.5

            # Denominacao bonus
            if denom and denom in cand_nome:
                score += 1.0

            if score > best_score:
                best_score = score

        if best_score >= 2.5:
            match_ok += 1
        else:
            no_match += 1

    conn.close()
    pct = match_ok * 100 // total_w if total_w else 0
    print(f"\n  Vinhos (W): {total_w} | Match: {match_ok} ({pct}%) | Sem: {no_match}")
    return pct


# ============================================================
# TESTE 6: few-shot com exemplos do banco
# ============================================================
def test_fewshot(items, model):
    print(f"\n{'='*60}")
    print("TESTE 6: Few-shot com exemplos do banco")
    print(f"{'='*60}")

    lines = run_llm_batches(model, PROMPT_T6, items)
    conn = get_db()
    cur = conn.cursor()

    match_ok = 0
    no_match = 0
    total_w = 0

    for i, item in enumerate(items):
        num = i + 1
        llm = lines.get(num, "MISSING")
        if not llm.startswith("W"): continue
        total_w += 1

        parts = llm.split("|")
        if len(parts) < 5: no_match += 1; continue
        prod_banco = parts[1].strip().split("=")[0].strip()
        vinho_banco = parts[2].strip().split("=")[0].strip()

        if not prod_banco or prod_banco == "??": no_match += 1; continue

        # Busca direta (LLM ja deu no formato do banco)
        cur.execute("SELECT id, produtor_normalizado, nome_normalizado FROM vivino_match WHERE produtor_normalizado = %s", (prod_banco,))
        candidates = cur.fetchall()

        if not candidates:
            # Fallback pg_trgm
            cur.execute("""
                SELECT id, produtor_normalizado, nome_normalizado,
                       similarity(produtor_normalizado, %s) as sim
                FROM vivino_match WHERE produtor_normalizado %% %s
                ORDER BY sim DESC LIMIT 10
            """, (prod_banco, prod_banco))
            candidates = [(c[0], c[1], c[2]) for c in cur.fetchall()]

        if not candidates:
            no_match += 1; continue

        # Match por vinho
        best_score = 0
        for cand in candidates:
            cand_nome = cand[2]
            if vinho_banco and vinho_banco != "??":
                vn = set(vinho_banco.split()) - {"de","du","la","le","les","des"}
                cn = set(cand_nome.split()) - {"de","du","la","le","les","des"}
                if vn and cn:
                    overlap = len(vn & cn) / max(len(vn), len(cn))
                    score = overlap
                elif vinho_banco in cand_nome or cand_nome in vinho_banco:
                    score = 0.7
                else:
                    score = 0
            else:
                score = 0.3  # produtor achou mas sem vinho
            if score > best_score:
                best_score = score

        if best_score >= 0.3:
            match_ok += 1
        else:
            no_match += 1

    conn.close()
    pct = match_ok * 100 // total_w if total_w else 0
    print(f"\n  Vinhos (W): {total_w} | Match: {match_ok} ({pct}%) | Sem: {no_match}")
    return pct


# ============================================================
# TESTE 15+16: normalizacao no script
# ============================================================
def test_script_norm(items, model):
    print(f"\n{'='*60}")
    print("TESTE 15+16: Normalizacao no script")
    print(f"{'='*60}")

    prompt = """TAREFA: Classifique e extraia dados.
- X = nao e vinho | S = destilado
- W = vinho: W|Produtor|Vinho|Pais|Cor
  - Produtor = nome COMPLETO e original da vinicola (com acentos, apostrofos — como escrito no rotulo)
  - Vinho = nome do vinho SEM o produtor
- DUPLICATAS: =N | NAO invente. ?? se nao sabe.

ITEMS:
"""
    lines = run_llm_batches(model, prompt, items)
    conn = get_db()
    cur = conn.cursor()

    match_ok = 0
    no_match = 0
    total_w = 0

    for i, item in enumerate(items):
        num = i + 1
        llm = lines.get(num, "MISSING")
        if not llm.startswith("W"): continue
        total_w += 1

        parts = llm.split("|")
        if len(parts) < 5: no_match += 1; continue
        produtor_raw = parts[1].strip()
        vinho_raw = parts[2].strip().split("=")[0].strip()

        # Normalizar NO SCRIPT
        produtor = normalize_script(produtor_raw)
        vinho = normalize_script(vinho_raw)

        if not produtor or produtor == "??": no_match += 1; continue

        # pg_trgm com produtor normalizado no script
        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(produtor_normalizado, %s) as sim
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY sim DESC LIMIT 10
        """, (produtor, produtor))
        candidates = cur.fetchall()

        if not candidates:
            no_match += 1; continue

        best_score = 0
        for cand_id, cand_prod, cand_nome, prod_sim in candidates:
            vn = set(vinho.split()) - {"de","du","la","le","les","des","del","di","the"}
            cn = set(cand_nome.split()) - {"de","du","la","le","les","des","del","di","the"}
            if vn and cn:
                overlap = len(vn & cn) / max(len(vn), len(cn))
            elif vinho in cand_nome or cand_nome in vinho:
                overlap = 0.7
            else:
                overlap = 0
            score = prod_sim * 0.6 + overlap * 0.4
            if score > best_score:
                best_score = score

        if best_score >= 0.35:
            match_ok += 1
        else:
            no_match += 1

    conn.close()
    pct = match_ok * 100 // total_w if total_w else 0
    print(f"\n  Vinhos (W): {total_w} | Match: {match_ok} ({pct}%) | Sem: {no_match}")
    return pct


# ============================================================
# TESTE 11: DB candidatos → LLM confirma
# ============================================================
def test_reverse(items, model):
    print(f"\n{'='*60}")
    print("TESTE 11: DB candidatos, LLM confirma")
    print(f"{'='*60}")

    # Fase 1: LLM classifica
    lines = run_llm_batches(model, PROMPT_T11_CLASSIFY, items)

    # Fase 2: buscar candidatos no DB
    conn = get_db()
    cur = conn.cursor()

    pairs = []  # (num, loja_nome, candidato_id, candidato_nome)
    wines_parsed = []

    for i, item in enumerate(items):
        num = i + 1
        llm = lines.get(num, "MISSING")
        if not llm.startswith("W"): continue

        parts = llm.split("|")
        if len(parts) < 5: continue
        produtor = normalize_script(parts[1])
        vinho = normalize_script(parts[2].split("=")[0])
        if not produtor or produtor == "??": continue

        wines_parsed.append(num)

        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(produtor_normalizado, %s) as sim
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY sim DESC LIMIT 3
        """, (produtor, produtor))
        candidates = cur.fetchall()

        if candidates:
            best = candidates[0]
            pairs.append({
                "num": num,
                "loja": item["loja_nome"],
                "cand_id": best[0],
                "cand_prod": best[1],
                "cand_nome": best[2],
            })

    conn.close()

    total_w = len(wines_parsed)
    print(f"\n  Vinhos (W): {total_w} | Candidatos encontrados: {len(pairs)}")

    if not pairs:
        print("  Sem candidatos, abortando.")
        return 0

    # Fase 3: LLM confirma pares
    print("  Enviando pares pro LLM confirmar...")
    match_ok = 0
    for batch_start in range(0, len(pairs), BATCH_SIZE):
        batch = pairs[batch_start:batch_start + BATCH_SIZE]
        pairs_text = ""
        for j, p in enumerate(batch):
            pairs_text += f"{j+1}. LOJA: \"{p['loja']}\" | VIVINO: \"{p['cand_prod']} - {p['cand_nome']}\"\n"

        print(f"  Confirmacao lote {batch_start//BATCH_SIZE + 1}...", end=" ", flush=True)
        text = call_llm(model, PROMPT_T11_CONFIRM, pairs_text)
        confirm_lines = parse_lines(text)

        sim = sum(1 for v in confirm_lines.values() if v.strip().upper() in ("S", "P"))
        nao = sum(1 for v in confirm_lines.values() if v.strip().upper() == "N")
        match_ok += sim
        print(f"S/P={sim} N={nao}")

        if batch_start + BATCH_SIZE < len(pairs):
            time.sleep(5)

    pct = match_ok * 100 // total_w if total_w else 0
    print(f"\n  Vinhos (W): {total_w} | Match confirmado: {match_ok} ({pct}%)")
    return pct


# ============================================================
# MAIN
# ============================================================
def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    test_files = {
        "7+8 (pg_trgm)": "teste_test1.csv",
        "1+2 (uva+denom)": "teste_test2.csv",
        "6 (few-shot)": "teste_test3.csv",
        "15+16 (script norm)": "teste_test4.csv",
        "11 (DB→LLM confirma)": "teste_test5.csv",
    }

    results = {}

    for name, filename in test_files.items():
        path = os.path.join(SCRIPT_DIR, filename)
        items = load_items(path)
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        print(f"\n\nCarregados {len(items)} itens para {name}")

        if "7+8" in name:
            results[name] = test_trgm(items, model)
        elif "1+2" in name:
            results[name] = test_uva_denom(items, model)
        elif "6" in name:
            results[name] = test_fewshot(items, model)
        elif "15+16" in name:
            results[name] = test_script_norm(items, model)
        elif "11" in name:
            results[name] = test_reverse(items, model)

        time.sleep(5)

    # Resumo final
    print(f"\n\n{'='*60}")
    print("RESUMO FINAL — 5 ABORDAGENS")
    print(f"{'='*60}")
    print(f"{'Abordagem':<30} {'Match %':>10}")
    print(f"{'-'*40}")
    for name, pct in sorted(results.items(), key=lambda x: -x[1]):
        bar = "#" * (pct // 2)
        print(f"{name:<30} {pct:>8}%  {bar}")


if __name__ == "__main__":
    main()
