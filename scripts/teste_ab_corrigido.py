"""
Teste A+B (few-shot + pg_trgm) com correcao de nome + dedup.
3 lotes diferentes (C, R, T). Pausa longa entre lotes pra evitar rate limit.
"""
import csv, os, time, re, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import google.generativeai as genai
import psycopg2

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash-lite"
BATCH_SIZE = 150
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

PASSO 1 — CORRIGIR: corrija o nome do vinho para o nome OFICIAL.
  Exemplos:
    "chato margaux 2015" → "Chateau Margaux"
    "catena alta cab sauv" → "Catena Alta Cabernet Sauvignon"
    "dom perignon vintge" → "Dom Perignon Vintage"
    "grner veltliner" → "Gruner Veltliner"
    "19 crimes punishmen" → "19 Crimes Punishment"
  Se nao consegue corrigir, mantenha como esta.

PASSO 2 — CLASSIFICAR E EXTRAIR:
  - X = nao e vinho (comida, objeto, cosmetico, cerveja, codigo, texto sem sentido)
  - S = destilado/spirit
  - W = vinho: W|NomeCorrigido|ProdBanco|VinhoBanco|Pais|Cor
    - NomeCorrigido = nome oficial do vinho (com acentos, maiusculas)
    - ProdBanco = produtor formato banco: minusculo, sem acento, l' junto, saint junto
    - VinhoBanco = vinho formato banco: mesma regra
    - Pais = 2 letras (??) | Cor: r/w/p/s/f/d

PASSO 3 — DUPLICATAS: se dois itens sao o MESMO VINHO (safra, formato, ou loja diferente), marque =N no final (N = numero do primeiro do grupo). Use o NomeCorrigido pra decidir — se corrigidos ficam iguais, sao duplicatas.

REGRAS:
- NAO invente dados. Se nao sabe, use ??
- Se o nome nao faz sentido como vinho, responda X

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

def get_db():
    return psycopg2.connect(host="localhost", port=5432, dbname="winegod_db",
                            user="postgres", password="postgres123",
                            options="-c client_encoding=UTF8")


def run_lote(name, csv_file, model):
    print(f"\n{'='*60}")
    print(f"LOTE {name}: {csv_file}")
    print(f"{'='*60}")

    items = load(os.path.join(SD, csv_file))
    print(f"Itens: {len(items)}")

    # LLM com pausa longa entre batches
    all_lines = {}
    sn = 1
    for bs in range(0, len(items), BATCH_SIZE):
        batch = items[bs:bs+BATCH_SIZE]
        txt = "\n".join(f"{sn+i}. {it['loja_nome']}" for i, it in enumerate(batch))

        print(f"  Lote {bs//BATCH_SIZE+1}...", end=" ", flush=True)

        # Retry ate 3x se der W=0
        for attempt in range(3):
            text = ""
            try:
                r = model.generate_content(PROMPT + txt,
                    generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=8192))
                text = r.text.strip()
            except Exception as e:
                print(f"ERRO: {e}", end=" ", flush=True)

            lines = {}
            for line in text.split("\n"):
                line = line.strip()
                if not line: continue
                p = line.split(". ", 1)
                if len(p) == 2 and p[0].strip().isdigit():
                    lines[int(p[0].strip())] = p[1].strip()

            w = sum(1 for v in lines.values() if v.startswith("W"))
            if w > 0:
                break
            print(f"(retry {attempt+1})", end=" ", flush=True)
            time.sleep(10)

        x = sum(1 for v in lines.values() if v.startswith("X"))
        s = sum(1 for v in lines.values() if v.startswith("S"))
        dup = sum(1 for v in lines.values() if "=" in v)
        print(f"W={w} X={x} S={s} dup={dup}")
        all_lines.update(lines)
        sn += len(batch)
        if bs + BATCH_SIZE < len(items):
            time.sleep(30)

    # Match com pg_trgm
    conn = get_db(); cur = conn.cursor()
    ok = 0; no = 0; tw = 0
    total_dup = sum(1 for v in all_lines.values() if "=" in v and v.startswith("W"))

    exemplos_ok = []
    exemplos_no = []

    for i in range(len(items)):
        llm = all_lines.get(i+1, "")
        if not llm.startswith("W"): continue
        tw += 1
        parts = llm.split("|")
        # W|NomeCorrigido|ProdBanco|VinhoBanco|Pais|Cor
        if len(parts) < 6: no += 1; continue

        nome_corrigido = parts[1].strip().split("=")[0].strip()
        prod = norm(parts[2].strip().split("=")[0].strip())
        vin = norm(parts[3].strip().split("=")[0].strip())

        if not prod or prod == "??" or len(prod) < 2:
            no += 1
            exemplos_no.append((items[i]['loja_nome'], nome_corrigido, prod, vin, "sem produtor"))
            continue

        cur.execute("""
            SELECT id, produtor_normalizado, nome_normalizado,
                   similarity(produtor_normalizado, %s) as ps,
                   similarity(nome_normalizado, %s) as ns
            FROM vivino_match WHERE produtor_normalizado %% %s
            ORDER BY similarity(produtor_normalizado, %s) DESC LIMIT 15
        """, (prod, vin, prod, prod))
        cands = cur.fetchall()

        if cands:
            best_sc = 0
            best_info = ""
            for cid, cprod, cnome, ps, ns in cands:
                sc = ps * 0.5 + ns * 0.3
                if sc > best_sc:
                    best_sc = sc
                    best_info = f"{cprod} - {cnome}"
            if best_sc >= 0.35:
                ok += 1
                if len(exemplos_ok) < 15:
                    exemplos_ok.append((items[i]['loja_nome'], nome_corrigido, prod, best_info, f"{best_sc:.2f}"))
            else:
                no += 1
                if len(exemplos_no) < 10:
                    exemplos_no.append((items[i]['loja_nome'], nome_corrigido, prod, vin, f"score={best_sc:.2f}"))
        else:
            no += 1
            if len(exemplos_no) < 10:
                exemplos_no.append((items[i]['loja_nome'], nome_corrigido, prod, vin, "nao encontrado"))

    conn.close()
    pct = ok * 100 // tw if tw else 0

    print(f"\n  RESULTADO: W={tw} | Match={ok} ({pct}%) | Sem={no} | Dup={total_dup}")

    print(f"\n  --- CORRECOES + MATCHES (top 10) ---")
    for orig, corr, prod, db_info, sc in exemplos_ok[:10]:
        print(f"    {orig[:30]:30} -> {corr[:25]:25} -> DB: {db_info[:30]} ({sc})")

    print(f"\n  --- SEM MATCH (top 8) ---")
    for orig, corr, prod, vin, motivo in exemplos_no[:8]:
        print(f"    {orig[:30]:30} -> {corr[:25]:25} prod={prod[:20]} {motivo}")

    return pct, tw, total_dup


def main():
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL)

    lotes = [
        ("C (cru-cub)", "teste_lote2_C.csv"),
        ("R (mal-man)", "teste_lote2_R.csv"),
        ("T (val-van)", "teste_lote2_T.csv"),
    ]

    results = {}
    total_w = 0
    total_ok = 0
    total_dup = 0

    for name, csv_f in lotes:
        pct, tw, dup = run_lote(name, csv_f, model)
        results[name] = (pct, tw, dup)
        total_w += tw
        total_ok += int(tw * pct / 100)
        total_dup += dup
        time.sleep(30)  # pausa longa entre lotes

    print(f"\n\n{'='*60}")
    print("RESULTADO FINAL — A+B com correcao de nome")
    print(f"{'='*60}")
    for name, (pct, tw, dup) in results.items():
        bar = "#" * (pct // 2)
        print(f"  {name:<25} {pct:>3}% (W={tw:>3}, dup={dup:>2})  {bar}")

    total_pct = total_ok * 100 // total_w if total_w else 0
    print(f"\n  {'MEDIA PONDERADA':<25} {total_pct:>3}% (W={total_w:>3}, dup={total_dup:>2})")


if __name__ == "__main__":
    main()
