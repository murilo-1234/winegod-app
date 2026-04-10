"""
Auditoria/dry-run dos ~75K new sem source.

Classifica em buckets acionaveis:
  A. URL absoluta + dominio em stores -> corrigivel agora
  B. URL absoluta + dominio NAO em stores -> corrigivel apos stores
  C. URL relativa + loja inferivel com seguranca -> corrigivel com reconstrucao
  D. URL relativa ambigua -> decisao manual
  E. Sem fonte / irrecuperavel

Para cada wine, tenta TODAS fontes de TODOS clean_ids antes de classificar.
Usa hash_dedup para resolver new -> wines_clean -> fontes.

NAO executa inserts. Gera CSV + relatorio.
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from urllib.parse import urlparse
import _env

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = os.environ["DATABASE_URL"]

LIXO_PREFIXES = ("javascript:", "tel:", "mailto:", "#", "data:", "blob:")
CSV_PATH = os.path.join(os.path.dirname(__file__), "auditoria_new_sem_source.csv")


def normalizar_nome(nome):
    if not nome:
        return ""
    return re.sub(r"[^a-z0-9 ]", "", nome.strip().lower()).strip()


def extrair_dominio(url_raw):
    if not url_raw:
        return None
    s = url_raw.strip()
    if not s.startswith("http://") and not s.startswith("https://"):
        s = "https://" + s
    try:
        parsed = urlparse(s)
        netloc = parsed.netloc
        if not netloc:
            return None
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return None


def get_domain(url):
    if not url:
        return None
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc
        if not netloc:
            return None
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return None


def is_url_lixo(url):
    if not url:
        return True
    return any(url.strip().lower().startswith(p) for p in LIXO_PREFIXES)


def is_url_absoluta(url):
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False


def resolver_loja(nome_loja, mercado_pais, fonte_plataforma, lojas_por_nome):
    key = normalizar_nome(nome_loja)
    if not key:
        return None, "nome vazio", 0

    candidatos = lojas_por_nome.get(key, [])
    if len(candidatos) == 0:
        return None, "nome nao encontrado", 0
    if len(candidatos) == 1:
        return candidatos[0], "match exato unico", 1

    # Desempate por pais
    if mercado_pais:
        mp = mercado_pais.strip().lower()
        por_pais = [c for c in candidatos if (c["pais"] or "").lower() == mp]
        if len(por_pais) == 1:
            return por_pais[0], f"desempate por pais={mercado_pais}", 1
        if len(por_pais) > 1:
            candidatos = por_pais

    # Desempate por plataforma
    if fonte_plataforma and len(candidatos) > 1:
        fp = fonte_plataforma.strip().lower()
        por_plat = [c for c in candidatos if (c["plataforma"] or "").lower() == fp]
        if len(por_plat) == 1:
            return por_plat[0], f"desempate por plataforma={fonte_plataforma}", 1

    return None, f"ambiguo ({len(candidatos)} candidatos)", len(candidatos)


def classificar_wine(wine_id, hash_dedup, l, lc, lojas_por_nome, domain_to_store):
    """
    Tenta TODAS fontes de TODOS clean_ids.
    Retorna o MELHOR resultado encontrado (prioridade: A > B > C > D > E).
    """
    # Resolver hash -> clean origens
    l.execute(
        "SELECT id, pais_tabela, id_original FROM wines_clean WHERE hash_dedup = %s AND id_original IS NOT NULL",
        (hash_dedup,),
    )
    origens = l.fetchall()

    if not origens:
        return "E", {"motivo": "hash nao encontrado no wines_clean"}, None

    # Coletar todas as fontes candidatas classificadas
    candidatos_a = []  # absoluta + store
    candidatos_b = []  # absoluta + sem store
    candidatos_c = []  # relativa + loja unica
    candidatos_d = []  # relativa + ambigua
    motivos_e = defaultdict(int)

    for clean_id, pais, id_orig in origens:
        if not pais or not re.match(r"^[a-z]{2}$", pais):
            motivos_e["pais invalido"] += 1
            continue

        try:
            l.execute(
                f"""SELECT url_original, preco, moeda, fonte, mercado, dados_extras
                    FROM vinhos_{pais}_fontes WHERE vinho_id = %s""",
                (id_orig,),
            )
            fontes_rows = l.fetchall()
        except Exception:
            lc.rollback()
            motivos_e["erro ao ler fontes"] += 1
            continue

        if not fontes_rows:
            motivos_e["sem registro em fontes"] += 1
            continue

        for url, preco, moeda, fonte, mercado, extras in fontes_rows:
            if not url:
                motivos_e["url NULL"] += 1
                continue

            if is_url_lixo(url):
                motivos_e["path lixo"] += 1
                continue

            entry = {
                "clean_id": clean_id,
                "pais": pais,
                "id_orig": id_orig,
                "url": url,
                "preco": preco,
                "moeda": moeda,
                "fonte": fonte,
                "mercado": mercado,
            }

            if is_url_absoluta(url):
                dom = get_domain(url)
                entry["dominio"] = dom
                store_id = domain_to_store.get(dom) if dom else None
                entry["store_id"] = store_id
                if store_id:
                    entry["criterio"] = "URL absoluta"
                    candidatos_a.append(entry)
                else:
                    entry["criterio"] = "URL absoluta, dominio nao em stores"
                    candidatos_b.append(entry)
            else:
                # URL relativa
                loja_nome = None
                if extras and isinstance(extras, dict):
                    loja_nome = extras.get("loja", "").strip()

                if not loja_nome:
                    motivos_e["URL relativa sem dados_extras.loja"] += 1
                    continue

                loja_match, criterio, n_cand = resolver_loja(loja_nome, mercado, fonte, lojas_por_nome)

                if loja_match:
                    dom = extrair_dominio(loja_match["url"])
                    if not dom:
                        motivos_e["dominio nao extraivel"] += 1
                        continue
                    store_id = domain_to_store.get(dom)
                    entry["loja_nome"] = loja_nome
                    entry["dominio"] = dom
                    entry["store_id"] = store_id
                    entry["url_absoluta"] = f"https://{dom}{url}"
                    entry["criterio"] = criterio
                    if store_id:
                        candidatos_c.append(entry)
                    else:
                        entry["criterio"] = f"{criterio}, dominio nao em stores"
                        candidatos_b.append(entry)
                else:
                    entry["loja_nome"] = loja_nome
                    entry["criterio"] = criterio
                    entry["n_candidatos"] = n_cand
                    candidatos_d.append(entry)

    # Retornar o melhor bucket encontrado (prioridade A > C > B > D > E)
    if candidatos_a:
        best = candidatos_a[0]
        best["url_absoluta"] = best["url"]
        return "A", best, candidatos_a
    if candidatos_c:
        return "C", candidatos_c[0], candidatos_c
    if candidatos_b:
        best = candidatos_b[0]
        if "url_absoluta" not in best:
            best["url_absoluta"] = best["url"]
        return "B", best, candidatos_b
    if candidatos_d:
        return "D", candidatos_d[0], candidatos_d
    return "E", {"motivo": max(motivos_e, key=motivos_e.get) if motivos_e else "sem fontes"}, None


def main():
    print("=" * 80)
    print("AUDITORIA NEW SEM SOURCE — DRY-RUN")
    print("=" * 80)

    print("\nConectando...")
    lc = psycopg2.connect(**LOCAL_DB)
    rc = psycopg2.connect(
        RENDER_DB,
        options="-c statement_timeout=300000",
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    l = lc.cursor()
    r = rc.cursor()

    # Indices
    print("Carregando indices...")
    l.execute("""
        SELECT id, nome, url_normalizada, pais_codigo, plataforma
        FROM lojas_scraping WHERE url_normalizada IS NOT NULL AND nome IS NOT NULL
    """)
    lojas_por_nome = defaultdict(list)
    for lid, nome, url, pais, plat in l.fetchall():
        key = normalizar_nome(nome)
        if key:
            lojas_por_nome[key].append({"id": lid, "url": url, "pais": pais, "plataforma": plat})
    print(f"  lojas: {len(lojas_por_nome):,} nomes")

    r.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
    domain_to_store = {row[0]: row[1] for row in r.fetchall()}
    print(f"  stores: {len(domain_to_store):,} dominios")

    # Buscar new sem source
    print("\nBuscando new sem source...")
    r.execute("""
        SELECT w.id, w.hash_dedup
        FROM wines w
        LEFT JOIN wine_sources ws ON ws.wine_id = w.id
        WHERE w.vivino_id IS NULL
        AND w.hash_dedup IS NOT NULL
        AND ws.id IS NULL
        ORDER BY w.id
    """)
    wines = r.fetchall()
    total = len(wines)
    print(f"  New sem source: {total:,}")

    # Classificar cada wine
    print(f"Classificando {total:,} wines...")

    buckets = {"A": [], "B": [], "C": [], "D": [], "E": []}
    motivos_e = defaultdict(int)

    for idx, (wine_id, hash_dedup) in enumerate(wines):
        if (idx + 1) % 5000 == 0:
            print(f"  {idx + 1:,}/{total:,} | A={len(buckets['A']):,} B={len(buckets['B']):,} C={len(buckets['C']):,} D={len(buckets['D']):,} E={len(buckets['E']):,}")

        bucket, best, all_cands = classificar_wine(wine_id, hash_dedup, l, lc, lojas_por_nome, domain_to_store)

        entry = {"wine_id": wine_id, "hash": hash_dedup}
        entry.update(best)

        if bucket == "E":
            motivo = best.get("motivo", "desconhecido")
            motivos_e[motivo] += 1

        buckets[bucket].append(entry)

    # ══════════════════════════════════════════════════════════════════════════
    # RELATORIO
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}")
    print(f"RESULTADO — {total:,} NEW SEM SOURCE")
    print(f"{'=' * 80}")

    labels = {
        "A": "URL absoluta + store existe       -> CORRIGIVEL AGORA",
        "B": "URL absoluta/relativa + store falta -> CORRIGIVEL APOS STORES",
        "C": "URL relativa + loja unica + store   -> CORRIGIVEL AGORA",
        "D": "URL relativa ambigua                -> DECISAO MANUAL",
        "E": "Sem fonte / irrecuperavel           -> NAO ACIONAVEL",
    }

    for bk in ["A", "B", "C", "D", "E"]:
        items = buckets[bk]
        pct = len(items) / max(total, 1) * 100
        print(f"\n--- BUCKET {bk}: {labels[bk]} ---")
        print(f"  Quantidade: {len(items):,} ({pct:.1f}%)")

    corrigivel_agora = len(buckets["A"]) + len(buckets["C"])
    corrigivel_apos = len(buckets["B"])
    manual = len(buckets["D"])
    irrecuperavel = len(buckets["E"])

    print(f"\n{'=' * 80}")
    print(f"RESUMO ACIONAVEL")
    print(f"{'=' * 80}")
    print(f"  Total new sem source:             {total:,}")
    print(f"  Corrigivel AGORA (A+C):           {corrigivel_agora:,}  ({corrigivel_agora/max(total,1)*100:.1f}%)")
    print(f"    Bucket A (absoluta+store):       {len(buckets['A']):,}")
    print(f"    Bucket C (relativa+loja+store):  {len(buckets['C']):,}")
    print(f"  Corrigivel APOS stores (B):       {corrigivel_apos:,}  ({corrigivel_apos/max(total,1)*100:.1f}%)")
    print(f"  Decisao manual (D):               {manual:,}  ({manual/max(total,1)*100:.1f}%)")
    print(f"  Irrecuperavel (E):                {irrecuperavel:,}  ({irrecuperavel/max(total,1)*100:.1f}%)")

    if motivos_e:
        print(f"\n  Detalhamento bucket E:")
        for motivo in sorted(motivos_e, key=lambda x: -motivos_e[x]):
            print(f"    {motivos_e[motivo]:>7,}  {motivo}")

    # Dominios faltantes do bucket B (top 20)
    if buckets["B"]:
        doms_b = defaultdict(int)
        for e in buckets["B"]:
            d = e.get("dominio")
            if d:
                doms_b[d] += 1
        print(f"\n  Top 20 dominios faltantes (bucket B):")
        for dom in sorted(doms_b, key=lambda x: -doms_b[x])[:20]:
            print(f"    {dom:<45} {doms_b[dom]:,} wines")

    # 20 exemplos por bucket
    for bk in ["A", "B", "C", "D", "E"]:
        items = buckets[bk]
        if not items:
            continue
        n_show = min(20, len(items))
        print(f"\n{'=' * 80}")
        print(f"EXEMPLOS BUCKET {bk} ({n_show} de {len(items):,})")
        print(f"{'=' * 80}")
        for i, e in enumerate(items[:n_show], 1):
            r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (e["wine_id"],))
            wine = r.fetchone()
            nome = f"{wine[1]} - {(wine[0] or '')[:35]}" if wine else "???"
            print(f"\n  [{i:>2}] wine_id={e['wine_id']} | {nome}")
            if e.get("url"):
                print(f"       URL: {e['url'][:70]}")
            if e.get("url_absoluta") and e["url_absoluta"] != e.get("url"):
                print(f"       abs: {e['url_absoluta'][:70]}")
            if e.get("dominio"):
                print(f"       dom: {e['dominio']} -> store={e.get('store_id')}")
            if e.get("loja_nome"):
                print(f"       loja: {e['loja_nome']}")
            if e.get("criterio"):
                print(f"       criterio: {e['criterio']}")
            elif e.get("motivo"):
                print(f"       motivo: {e['motivo']}")
            print(f"       fonte={e.get('fonte')} | pais={e.get('pais')} | {e.get('preco')} {e.get('moeda')}")

    # CSV completo (apenas A, B, C — acionaveis)
    print(f"\n{'=' * 80}")
    print(f"CSV")
    print(f"{'=' * 80}")
    csv_rows = []
    for bk in ["A", "B", "C", "D"]:
        for e in buckets[bk]:
            csv_rows.append({
                "bucket": bk,
                "render_wine_id": e["wine_id"],
                "hash": e.get("hash", ""),
                "clean_id": e.get("clean_id", ""),
                "pais": e.get("pais", ""),
                "dominio": e.get("dominio", ""),
                "store_id": e.get("store_id", ""),
                "url_original": e.get("url", ""),
                "url_absoluta": e.get("url_absoluta", ""),
                "loja_nome": e.get("loja_nome", ""),
                "criterio": e.get("criterio", ""),
                "preco": e.get("preco", ""),
                "moeda": e.get("moeda", ""),
                "fonte": e.get("fonte", ""),
            })

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "bucket", "render_wine_id", "hash", "clean_id", "pais", "dominio", "store_id",
            "url_original", "url_absoluta", "loja_nome", "criterio", "preco", "moeda", "fonte",
        ])
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"  CSV: {CSV_PATH}")
    print(f"  Linhas: {len(csv_rows):,} (buckets A+B+C+D, sem E)")

    l.close(); lc.close()
    r.close(); rc.close()
    print("\nFim.")


if __name__ == "__main__":
    main()
