"""
Teste robusto: batch=100, retry ate 5x, sem pausa longa, validar completude.
3 lotes novos de 300.
"""
import csv, os, time, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
BATCH_SIZE = 100  # menor = mais confiavel
SD = os.path.dirname(__file__)

PROMPT = """Nosso banco armazena produtores e vinhos neste formato (exemplos reais):
  produtor: "chateau levangile"     vinho: "blason de levangile pomerol"
  produtor: "chateau lenclos"       vinho: "pomerol"
  produtor: "domaine de la romanee conti"  vinho: "romanee conti grand cru"
  produtor: "bodega catena zapata"  vinho: "catena alta malbec"
  produtor: "tenuta san guido"      vinho: "sassicaia"
  produtor: "penfolds"              vinho: "grange shiraz"
  produtor: "joseph phelps vineyards"  vinho: "insignia"
  produtor: "bodegas muga"          vinho: "prado enea gran reserva rioja"
  produtor: "marchesi antinori"     vinho: "tignanello toscana"
  produtor: "vina errazuriz"        vinho: "max reserva cabernet sauvignon"

TAREFA em 3 passos:

PASSO 1 — CORRIGIR o nome para o nome OFICIAL do vinho. Se o nome comeca com uma regiao (ex: "val de loire", "cotes du rhone"), identifique o produtor real que aparece DEPOIS da regiao.

PASSO 2 — CLASSIFICAR E EXTRAIR:
  - X = nao e vinho | S = destilado/spirit
  - W = vinho: W|NomeCorrigido|ProdBanco|VinhoBanco|Pais|Cor
    - NomeCorrigido = nome oficial (com acentos)
    - ProdBanco = produtor formato banco: minusculo, sem acento, l' junto, saint junto
    - VinhoBanco = vinho formato banco: mesma regra
    - Pais = 2 letras (??) | Cor: r/w/p/s/f/d

PASSO 3 — DUPLICATAS: mesmo vinho com safra/formato diferente = =N

NAO invente. ?? se nao sabe. Se nome nao faz sentido = X.

ITEMS:
"""


def load(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

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
        if not line: continue
        p = line.split(". ", 1)
        if len(p) == 2 and p[0].strip().isdigit():
            m[int(p[0].strip())] = p[1].strip()
    return m

def get_db():
    return psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                            user="postgres", password="postgres123",
                            options="-c client_encoding=UTF8")


def call_batch(model, items, start_num):
    """Chama LLM com retry ate 5x. Retorna dict {num: resposta}."""
    txt = "\n".join(f"{start_num+i}. {it['loja_nome']}" for i, it in enumerate(items))

    for attempt in range(5):
        try:
            r = model.generate_content(PROMPT + txt,
                generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=4096))
            text = r.text.strip()
            lines = parse(text)

            # Checar se respondeu pelo menos 50% dos itens
            responded = len(lines)
            if responded >= len(items) * 0.5:
                return lines, responded, attempt + 1

            # Resposta incompleta, retry
            print(f"(parcial {responded}/{len(items)}, retry {attempt+1})", end=" ", flush=True)

        except Exception as e:
            print(f"(erro: {str(e)[:30]}, retry {attempt+1})", end=" ", flush=True)

        time.sleep(3)

    return {}, 0, 5  # falhou 5x


def run_lote(name, csv_file, model):
    print(f"\n{'='*60}")
    print(f"LOTE {name}")
    print(f"{'='*60}")

    items = load(os.path.join(SD, csv_file))
    print(f"Itens: {len(items)}")

    all_lines = {}
    sn = 1
    total_retries = 0

    for bs in range(0, len(items), BATCH_SIZE):
        batch = items[bs:bs+BATCH_SIZE]
        print(f"  Batch {bs//BATCH_SIZE+1}/{(len(items)-1)//BATCH_SIZE+1} (itens {sn}-{sn+len(batch)-1})...", end=" ", flush=True)

        lines, responded, attempts = call_batch(model, batch, sn)
        total_retries += attempts - 1

        w = sum(1 for v in lines.values() if v.startswith("W"))
        x = sum(1 for v in lines.values() if v.startswith("X"))
        s = sum(1 for v in lines.values() if v.startswith("S"))
        dup = sum(1 for v in lines.values() if "=" in v)
        missing = len(batch) - responded

        all_lines.update(lines)
        print(f"W={w} X={x} S={s} dup={dup} missing={missing}" + (f" (retries={attempts-1})" if attempts > 1 else ""))
        sn += len(batch)
        time.sleep(2)  # pausa curta

    # Stats
    total = len(items)
    responded = len(all_lines)
    missing = total - responded
    wines = sum(1 for v in all_lines.values() if v.startswith("W"))
    notwine = sum(1 for v in all_lines.values() if v.startswith("X"))
    spirits = sum(1 for v in all_lines.values() if v.startswith("S"))
    dups = sum(1 for v in all_lines.values() if "=" in v)

    print(f"\n  Completude: {responded}/{total} ({responded*100//total}%) | Missing: {missing} | Retries: {total_retries}")
    print(f"  Classificacao: W={wines} X={notwine} S={spirits} | Dup={dups}")

    # Match pg_trgm
    if wines == 0:
        print(f"  Match: 0 (sem vinhos)")
        return 0, 0, 0, responded, total

    conn = get_db(); cur = conn.cursor()
    ok = 0; no_m = 0

    for i in range(total):
        llm = all_lines.get(i+1, "")
        if not llm.startswith("W"): continue
        parts = llm.split("|")
        if len(parts) < 6: no_m += 1; continue

        prod = norm(parts[2].strip().split("=")[0].strip())
        vin = norm(parts[3].strip().split("=")[0].strip())
        if not prod or prod == "??" or len(prod) < 2: no_m += 1; continue

        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(produtor_normalizado, %s) as ps,
                   similarity(nome_normalizado, %s) as ns
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY similarity(produtor_normalizado, %s) DESC LIMIT 15
        """, (prod, vin, prod, prod))
        cands = cur.fetchall()

        if cands:
            best = max(c[3]*0.5 + c[4]*0.3 for c in cands)
            if best >= 0.35: ok += 1
            else: no_m += 1
        else: no_m += 1

    conn.close()
    pct = ok * 100 // wines if wines else 0
    print(f"  Match Vivino: {ok}/{wines} ({pct}%)")
    return pct, wines, dups, responded, total


def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    # 3 lotes NOVOS
    lotes_info = [
        ("mou-mur", "mou", "mur"),
        ("per-pes", "per", "pes"),
        ("sou-spi", "sou", "spi"),
    ]

    results = {}
    for name, start, end in lotes_info:
        csv_f = f"teste_flash_{name.split('-')[0][0:3]}{name.split('-')[1][0] if '-' in name else ''}.csv".replace("teste_flash_", "teste_flash_")
        # Fix: usar os nomes dos arquivos exportados
        csv_map = {"mou-mur": "teste_flash_1.csv", "per-pes": "teste_flash_2.csv", "sou-spi": "teste_flash_3.csv"}
        csv_f = csv_map.get(name, csv_f)
        pct, wines, dups, responded, total = run_lote(name, csv_f, model)
        results[name] = (pct, wines, dups, responded, total)
        time.sleep(5)

    # Resumo
    print(f"\n\n{'='*60}")
    print("RESULTADO FINAL — Teste Robusto (batch=100, retry 5x)")
    print(f"{'='*60}")

    total_w = 0; total_ok = 0; total_dup = 0; total_resp = 0; total_items = 0
    for name, (pct, wines, dups, responded, total) in results.items():
        bar = "#" * (pct // 2)
        print(f"  {name:<15} Match={pct:>3}% W={wines:>3} Dup={dups:>2} Completude={responded}/{total}  {bar}")
        total_w += wines
        total_ok += int(wines * pct / 100)
        total_dup += dups
        total_resp += responded
        total_items += total

    avg = total_ok * 100 // total_w if total_w else 0
    print(f"\n  {'TOTAL':<15} Match={avg:>3}% W={total_w:>3} Dup={total_dup:>2} Completude={total_resp}/{total_items}")


if __name__ == "__main__":
    main()
