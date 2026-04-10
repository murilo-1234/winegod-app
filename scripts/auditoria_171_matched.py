"""
Classificar os 171 matched sem source que TEM URL valida em 4 buckets:
  1. URL absoluta + dominio existe em stores
  2. URL absoluta + dominio NAO existe em stores
  3. URL relativa + dominio inferivel por metadados
  4. URL relativa + sem como inferir dominio
"""
import os, sys, re, json
from collections import defaultdict
from urllib.parse import urlparse
import _env

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = os.environ["DATABASE_URL"]

lc = psycopg2.connect(**LOCAL_DB)
rc = psycopg2.connect(RENDER_DB, options="-c statement_timeout=300000", keepalives=1, keepalives_idle=30)
l = lc.cursor()
r = rc.cursor()

# Carregar domain_to_store
r.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
domain_to_store = {row[0]: row[1] for row in r.fetchall()}
print(f"Stores carregadas: {len(domain_to_store):,}")


def get_domain(url):
    if not url:
        return None
    try:
        parsed = urlparse(url)
        if parsed.netloc:
            return parsed.netloc.replace("www.", "")
        return None
    except:
        return None


def is_absolute(url):
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    except:
        return False


def inferir_dominio(pais, id_orig, fontes_row_extras):
    """Tenta inferir dominio de metadados: dados_extras, fonte, mercado."""
    # fontes_row_extras = (url, preco, moeda, fonte, mercado, dados_extras)
    url, preco, moeda, fonte, mercado, dados_extras = fontes_row_extras

    candidatos = []

    # 1. dados_extras pode ter 'loja', 'dominio', 'url_loja', 'store_url'
    if dados_extras:
        extras = dados_extras if isinstance(dados_extras, dict) else {}
        for key in ["loja", "dominio", "url_loja", "store_url", "loja_url", "url_base", "site"]:
            val = extras.get(key)
            if val and isinstance(val, str):
                dom = get_domain(val) if val.startswith("http") else val.replace("www.", "").strip()
                if dom and "." in dom:
                    candidatos.append(("dados_extras." + key, dom))

    # 2. mercado pode conter dominio
    if mercado and isinstance(mercado, str) and "." in mercado:
        dom = mercado.replace("www.", "").strip()
        candidatos.append(("mercado", dom))

    # 3. fonte pode ser um dominio
    if fonte and isinstance(fonte, str) and "." in fonte:
        dom = fonte.replace("www.", "").strip()
        candidatos.append(("fonte", dom))

    # 4. Tentar reconstruir da tabela vinhos_XX
    try:
        l.execute(f"SELECT fontes FROM vinhos_{pais} WHERE id = %s", (id_orig,))
        row = l.fetchone()
        if row and row[0]:
            fontes_json = row[0]
            if isinstance(fontes_json, list):
                for f in fontes_json:
                    if isinstance(f, str) and "." in f:
                        candidatos.append(("vinhos_XX.fontes", f.replace("www.", "")))
            elif isinstance(fontes_json, str) and "." in fontes_json:
                candidatos.append(("vinhos_XX.fontes", fontes_json.replace("www.", "")))
    except:
        lc.rollback()

    # 5. Tentar da lojas_scraping via id_original
    # (improvavel mas vale tentar)

    return candidatos


# ══════════════════════════════════════════════════════════════════════════════
# COLETAR OS 171
# ══════════════════════════════════════════════════════════════════════════════
print("\nColetando os 171 matched sem source com URL valida...")

l.execute("""SELECT DISTINCT vivino_id FROM y2_results WHERE status = 'matched' AND vivino_id IS NOT NULL""")
all_matched_vids = [row[0] for row in l.fetchall()]

# Achar os sem source
sem_source_vids = []
for i in range(0, len(all_matched_vids), 1000):
    chunk = all_matched_vids[i : i + 1000]
    r.execute(
        """SELECT w.id FROM unnest(%s::int[]) AS vid
           JOIN wines w ON w.id = vid
           WHERE NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)""",
        (chunk,),
    )
    sem_source_vids.extend([row[0] for row in r.fetchall()])

print(f"Total matched sem source: {len(sem_source_vids)}")

# Classificar cada um
bucket1 = []  # absoluta + dominio em stores
bucket2 = []  # absoluta + dominio NAO em stores
bucket3 = []  # relativa + dominio inferivel
bucket4 = []  # relativa + sem inferir
skip_sem_url = 0  # fonte sem URL (nao conta nos 171)
skip_sem_registro = 0  # sem registro em fontes

for vid in sem_source_vids:
    l.execute("SELECT clean_id FROM y2_results WHERE vivino_id = %s AND status = 'matched'", (vid,))
    cids = [row[0] for row in l.fetchall()]

    tem_url_valida = False
    for cid in cids:
        l.execute("SELECT pais_tabela, id_original, nome_original FROM wines_clean WHERE id = %s", (cid,))
        row = l.fetchone()
        if not row or not row[0] or not re.match(r"^[a-z]{2}$", row[0]):
            continue
        pais, id_orig, nome_orig = row

        try:
            l.execute(
                f"""SELECT url_original, preco, moeda, fonte, mercado, dados_extras
                    FROM vinhos_{pais}_fontes WHERE vinho_id = %s""",
                (id_orig,),
            )
            fontes_rows = l.fetchall()
        except:
            lc.rollback()
            continue

        for frow in fontes_rows:
            url = frow[0]

            # Pular se nao tem URL nenhuma
            if not url:
                continue

            tem_url_valida = True
            r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (int(vid),))
            wine = r.fetchone()
            wine_nome = f"{wine[1]} - {(wine[0] or '')[:40]}" if wine else "???"

            entry = {
                "wine_id": vid,
                "wine_nome": wine_nome,
                "clean_id": cid,
                "pais": pais,
                "id_orig": id_orig,
                "nome_orig": (nome_orig or "")[:60],
                "url": url,
                "preco": frow[1],
                "moeda": frow[2],
                "fonte": frow[3],
                "mercado": frow[4],
            }

            if is_absolute(url):
                dom = get_domain(url)
                entry["dominio"] = dom
                if dom and dom in domain_to_store:
                    entry["store_id"] = domain_to_store[dom]
                    bucket1.append(entry)
                else:
                    entry["store_id"] = None
                    bucket2.append(entry)
            else:
                # URL relativa — tentar inferir
                candidatos = inferir_dominio(pais, id_orig, frow)
                if candidatos:
                    entry["dominio_inferido"] = candidatos[0][1]
                    entry["fonte_inferencia"] = candidatos[0][0]
                    entry["store_id"] = domain_to_store.get(candidatos[0][1])
                    bucket3.append(entry)
                else:
                    entry["dominio_inferido"] = None
                    bucket4.append(entry)

            break  # 1 fonte por clean_id basta para classificar
        if tem_url_valida:
            break

    if not tem_url_valida:
        # Checar se tinha fonte sem URL ou sem registro
        pass  # ja contado antes

# ══════════════════════════════════════════════════════════════════════════════
# RESULTADOS
# ══════════════════════════════════════════════════════════════════════════════
total = len(bucket1) + len(bucket2) + len(bucket3) + len(bucket4)
print(f"\n{'=' * 80}")
print(f"CLASSIFICACAO DOS {total} MATCHED SEM SOURCE COM URL")
print(f"{'=' * 80}")


def print_bucket(num, label, items, corrigivel):
    pct = len(items) / max(total, 1) * 100
    print(f"\n--- BUCKET {num}: {label} ---")
    print(f"  Quantidade: {len(items)} ({pct:.1f}%)")
    print(f"  Corrigivel: {corrigivel}")
    print(f"  Exemplos:")
    for e in items[:5]:
        print(f"    wine_id={e['wine_id']} | {e['wine_nome']}")
        print(f"      clean: pais={e['pais']} nome={e['nome_orig']}")
        print(f"      URL: {e['url'][:75]}")
        if "dominio" in e:
            print(f"      dominio={e.get('dominio')} store_id={e.get('store_id')}")
        if "dominio_inferido" in e:
            print(
                f"      dominio_inferido={e.get('dominio_inferido')} via={e.get('fonte_inferencia')} store_id={e.get('store_id')}"
            )
        print(f"      fonte={e.get('fonte')} mercado={e.get('mercado')} preco={e.get('preco')} {e.get('moeda')}")


print_bucket(
    1,
    "URL ABSOLUTA + DOMINIO EM STORES",
    bucket1,
    "SIM — corrigivel agora. Bug de import: o link deveria ter sido inserido.",
)

print_bucket(
    2,
    "URL ABSOLUTA + DOMINIO NAO EM STORES",
    bucket2,
    "SIM — apos importar o dominio em stores. Gap de stores.",
)

print_bucket(
    3,
    "URL RELATIVA + DOMINIO INFERIVEL",
    bucket3,
    "SIM — apos reconstruir a URL absoluta com dominio inferido. Falha upstream de normalizacao.",
)

print_bucket(
    4,
    "URL RELATIVA + SEM COMO INFERIR",
    bucket4,
    "NAO — irrecuperavel com os dados atuais.",
)

# Resumo
print(f"\n{'=' * 80}")
print(f"RESUMO ACIONAVEL")
print(f"{'=' * 80}")
corrigivel_agora = len(bucket1)
corrigivel_apos = len(bucket2) + len(bucket3)
irrecuperavel = len(bucket4)
print(f"  Total classificados:              {total}")
print(f"  Corrigivel AGORA (bug import):    {corrigivel_agora:>5}  ({corrigivel_agora/max(total,1)*100:.1f}%)")
print(f"  Corrigivel APOS (stores/normaliz):{corrigivel_apos:>5}  ({corrigivel_apos/max(total,1)*100:.1f}%)")
print(f"  Irrecuperavel:                    {irrecuperavel:>5}  ({irrecuperavel/max(total,1)*100:.1f}%)")

# Dominios faltantes do bucket 2
if bucket2:
    doms_faltantes = defaultdict(int)
    for e in bucket2:
        if e.get("dominio"):
            doms_faltantes[e["dominio"]] += 1
    print(f"\n  Dominios faltantes em stores (bucket 2):")
    for dom in sorted(doms_faltantes, key=lambda x: -doms_faltantes[x])[:10]:
        print(f"    {dom:<40} {doms_faltantes[dom]} links")

l.close()
lc.close()
r.close()
rc.close()
