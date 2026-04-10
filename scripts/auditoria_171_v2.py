"""
Reclassificar os 171 matched sem source com URL valida.
Buckets com controle de ambiguidade:
  1. Loja unica + store existe
  2. Loja unica + store falta
  3. Loja ambigua (>1 candidato)
  4. Loja nao encontrada
  5. Path lixo (javascript:, tel:, etc.)
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

LIXO_PREFIXES = ("javascript:", "tel:", "mailto:", "#", "data:", "blob:")


def normalizar_nome(nome):
    if not nome:
        return ""
    return re.sub(r"[^a-z0-9 ]", "", nome.strip().lower()).strip()


# ── Carregar lojas_scraping indexada por nome normalizado ──────────────────
print("Carregando lojas_scraping...")
l.execute("""
    SELECT id, nome, url_normalizada, pais_codigo, plataforma
    FROM lojas_scraping
    WHERE url_normalizada IS NOT NULL AND nome IS NOT NULL
""")
# Index: nome_normalizado -> lista de (id, url, pais, plataforma)
lojas_por_nome = defaultdict(list)
for lid, nome, url, pais, plataforma in l.fetchall():
    key = normalizar_nome(nome)
    if key:
        lojas_por_nome[key].append({
            "id": lid,
            "url": url,
            "pais": pais,
            "plataforma": plataforma,
            "nome_orig": nome,
        })

print(f"  Nomes unicos normalizados: {len(lojas_por_nome):,}")

# ── Carregar domain_to_store ──────────────────────────────────────────────
r.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
domain_to_store = {row[0]: row[1] for row in r.fetchall()}
print(f"  Stores com dominio: {len(domain_to_store):,}")

# ── Coletar os 513 matched sem source ─────────────────────────────────────
print("\nColetando matched sem source...")
l.execute("""SELECT DISTINCT vivino_id FROM y2_results WHERE status = 'matched' AND vivino_id IS NOT NULL""")
all_vids = [row[0] for row in l.fetchall()]

sem_source_vids = []
for i in range(0, len(all_vids), 1000):
    chunk = all_vids[i : i + 1000]
    r.execute(
        """SELECT w.id FROM unnest(%s::int[]) AS vid
           JOIN wines w ON w.id = vid
           WHERE NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)""",
        (chunk,),
    )
    sem_source_vids.extend([row[0] for row in r.fetchall()])

print(f"  Total matched sem source: {len(sem_source_vids)}")

# ── Classificar os que tem URL ────────────────────────────────────────────
print("Classificando...")

buckets = {1: [], 2: [], 3: [], 4: [], 5: []}
skip_sem_url_ou_registro = 0


def resolver_loja(nome_loja, mercado_pais, fonte_plataforma):
    """
    Resolver nome da loja em lojas_scraping.
    Retorna (candidatos, criterio).
    candidatos = lista de matches.
    criterio = string descrevendo como resolveu.
    """
    key = normalizar_nome(nome_loja)
    if not key:
        return [], "nome vazio"

    candidatos = lojas_por_nome.get(key, [])

    if len(candidatos) == 0:
        return [], "nome nao encontrado"

    if len(candidatos) == 1:
        return candidatos, "match exato unico"

    # >1 candidato — tentar desempatar
    # 1. Filtrar por pais
    if mercado_pais:
        por_pais = [c for c in candidatos if c["pais"] == mercado_pais.upper() or c["pais"] == mercado_pais.lower()]
        if len(por_pais) == 1:
            return por_pais, f"desempate por pais={mercado_pais}"
        if len(por_pais) > 1:
            candidatos = por_pais  # reduzir mas ainda ambiguo

    # 2. Filtrar por plataforma
    if fonte_plataforma and len(candidatos) > 1:
        por_plat = [c for c in candidatos if c["plataforma"] and c["plataforma"].lower() == fonte_plataforma.lower()]
        if len(por_plat) == 1:
            return por_plat, f"desempate por plataforma={fonte_plataforma}"

    # Ainda ambiguo
    return candidatos, f"ambiguo ({len(candidatos)} candidatos)"


for vid in sem_source_vids:
    l.execute("SELECT clean_id FROM y2_results WHERE vivino_id = %s AND status = 'matched'", (vid,))
    cids = [row[0] for row in l.fetchall()]

    processado = False
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

        for url, preco, moeda, fonte, mercado, extras in fontes_rows:
            if not url:
                continue

            # Info do wine no Render
            r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (int(vid),))
            wine = r.fetchone()
            wine_nome = f"{wine[1]} - {(wine[0] or '')[:40]}" if wine else "???"

            entry = {
                "wine_id": vid,
                "wine_nome": wine_nome,
                "clean_id": cid,
                "pais": pais,
                "id_orig": id_orig,
                "nome_orig": (nome_orig or "")[:55],
                "url": url,
                "preco": preco,
                "moeda": moeda,
                "fonte": fonte,
                "mercado": mercado,
            }

            # Bucket 5: lixo
            if any(url.strip().lower().startswith(p) for p in LIXO_PREFIXES):
                entry["motivo"] = "path lixo"
                buckets[5].append(entry)
                processado = True
                break

            # URL absoluta?
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                dom = parsed.netloc.replace("www.", "")
                store_id = domain_to_store.get(dom)
                entry["dominio"] = dom
                entry["store_id"] = store_id
                entry["criterio"] = "URL absoluta"
                if store_id:
                    buckets[1].append(entry)
                else:
                    buckets[2].append(entry)
                processado = True
                break

            # URL relativa — resolver via dados_extras.loja
            loja_nome = None
            if extras and isinstance(extras, dict):
                loja_nome = extras.get("loja", "").strip()

            if not loja_nome:
                entry["motivo"] = "URL relativa sem dados_extras.loja"
                buckets[4].append(entry)
                processado = True
                break

            candidatos, criterio = resolver_loja(loja_nome, mercado, fonte)

            entry["loja_nome"] = loja_nome
            entry["criterio"] = criterio

            if len(candidatos) == 1:
                loja = candidatos[0]
                dom = loja["url"].replace("www.", "")
                # Limpar trailing paths do dominio (ex: idealwine.com/it)
                if "/" in dom:
                    dom = dom.split("/")[0]
                store_id = domain_to_store.get(dom)
                entry["dominio"] = dom
                entry["loja_url"] = loja["url"]
                entry["store_id"] = store_id
                entry["url_reconstruida"] = f"https://{loja['url']}{url}"
                if store_id:
                    buckets[1].append(entry)
                else:
                    buckets[2].append(entry)
            elif len(candidatos) > 1:
                entry["n_candidatos"] = len(candidatos)
                entry["candidatos"] = [(c["url"], c["pais"]) for c in candidatos[:5]]
                buckets[3].append(entry)
            else:
                buckets[4].append(entry)

            processado = True
            break

        if processado:
            break

    if not processado:
        skip_sem_url_ou_registro += 1

# ══════════════════════════════════════════════════════════════════════════════
# RESULTADOS
# ══════════════════════════════════════════════════════════════════════════════
total = sum(len(b) for b in buckets.values())
print(f"\n{'=' * 80}")
print(f"CLASSIFICACAO DOS {total} MATCHED SEM SOURCE COM URL")
print(f"(+ {skip_sem_url_ou_registro} sem URL ou sem registro — excluidos)")
print(f"{'=' * 80}")

labels = {
    1: "LOJA UNICA + STORE EXISTE -> CORRIGIVEL AGORA",
    2: "LOJA UNICA + STORE FALTA -> CORRIGIVEL APOS STORES",
    3: "LOJA AMBIGUA (>1 candidato) -> REQUER DESEMPATE MANUAL",
    4: "LOJA NAO ENCONTRADA -> NAO RECUPERAVEL AUTOMATICAMENTE",
    5: "PATH LIXO (javascript:, tel:) -> IRRECUPERAVEL",
}

for num in range(1, 6):
    items = buckets[num]
    pct = len(items) / max(total, 1) * 100
    print(f"\n--- BUCKET {num}: {labels[num]} ---")
    print(f"  Quantidade: {len(items)} ({pct:.1f}%)")
    print(f"  Exemplos:")

    for e in items[:5]:
        print(f"    wine_id={e['wine_id']} | {e['wine_nome']}")
        print(f"      clean: pais={e['pais']} | {e['nome_orig']}")
        print(f"      URL: {e['url'][:75]}")
        if "dominio" in e:
            print(f"      dominio={e['dominio']} | store_id={e.get('store_id')}")
        if "loja_nome" in e:
            print(f"      loja=\"{e['loja_nome']}\"")
        if "url_reconstruida" in e:
            print(f"      reconstruida: {e['url_reconstruida'][:75]}")
        if "candidatos" in e:
            print(f"      candidatos ({e['n_candidatos']}): {e['candidatos']}")
        print(f"      criterio: {e.get('criterio', e.get('motivo', '?'))}")
        print(f"      fonte={e.get('fonte')} | mercado={e.get('mercado')} | {e.get('preco')} {e.get('moeda')}")

# Resumo
print(f"\n{'=' * 80}")
print(f"RESUMO ACIONAVEL")
print(f"{'=' * 80}")
print(f"  Total com URL:                      {total}")
print(f"  Sem URL/registro (excluidos):       {skip_sem_url_ou_registro}")
print(f"")
print(f"  1. Corrigivel AGORA:                {len(buckets[1]):>5}  ({len(buckets[1])/max(total,1)*100:.1f}%)")
print(f"  2. Corrigivel apos importar stores: {len(buckets[2]):>5}  ({len(buckets[2])/max(total,1)*100:.1f}%)")
print(f"  3. Ambiguo (desempate manual):      {len(buckets[3]):>5}  ({len(buckets[3])/max(total,1)*100:.1f}%)")
print(f"  4. Loja nao encontrada:             {len(buckets[4]):>5}  ({len(buckets[4])/max(total,1)*100:.1f}%)")
print(f"  5. Path lixo:                       {len(buckets[5]):>5}  ({len(buckets[5])/max(total,1)*100:.1f}%)")
print(f"")
recuperavel = len(buckets[1]) + len(buckets[2])
print(f"  Recuperavel (1+2):                  {recuperavel:>5}  ({recuperavel/max(total,1)*100:.1f}%)")
print(f"  Requer trabalho (3+4):              {len(buckets[3])+len(buckets[4]):>5}  ({(len(buckets[3])+len(buckets[4]))/max(total,1)*100:.1f}%)")
print(f"  Lixo (5):                           {len(buckets[5]):>5}  ({len(buckets[5])/max(total,1)*100:.1f}%)")

l.close(); lc.close()
r.close(); rc.close()
