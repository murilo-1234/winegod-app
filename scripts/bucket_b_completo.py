"""
Bucket B completo: importar 5 stores + corrigir 30 wines.
Auto-abort se qualquer ambiguidade.
"""
import csv
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse
import _env

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2
from psycopg2.extras import execute_values

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = os.environ["DATABASE_URL"]

LIXO_PREFIXES = ("javascript:", "tel:", "mailto:", "#", "data:", "blob:")
LIXO_EXATOS = {"false", "true", "null", "undefined", "none", "nan", ""}

CSV_STORES = os.path.join(os.path.dirname(__file__), "stores_bucket_b_dryrun.csv")
CSV_WS = os.path.join(os.path.dirname(__file__), "wine_sources_bucket_b_dryrun.csv")


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


def is_url_lixo(url):
    if not url:
        return True
    s = url.strip().lower()
    if s in LIXO_EXATOS:
        return True
    return any(s.startswith(p) for p in LIXO_PREFIXES)


def is_url_absoluta(url):
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False


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


def resolver_loja(nome_loja, mercado_pais, fonte_plataforma, lojas_por_nome):
    key = normalizar_nome(nome_loja)
    if not key:
        return None, "nome vazio", 0
    candidatos = lojas_por_nome.get(key, [])
    if len(candidatos) == 0:
        return None, "nome nao encontrado", 0
    if len(candidatos) == 1:
        return candidatos[0], "match exato unico", 1
    if mercado_pais:
        mp = mercado_pais.strip().lower()
        por_pais = [c for c in candidatos if (c["pais"] or "").lower() == mp]
        if len(por_pais) == 1:
            return por_pais[0], f"desempate por pais={mercado_pais}", 1
        if len(por_pais) > 1:
            candidatos = por_pais
    if fonte_plataforma and len(candidatos) > 1:
        fp = fonte_plataforma.strip().lower()
        por_plat = [c for c in candidatos if (c["plataforma"] or "").lower() == fp]
        if len(por_plat) == 1:
            return por_plat[0], f"desempate por plataforma={fonte_plataforma}", 1
    return None, f"ambiguo ({len(candidatos)} candidatos)", len(candidatos)


def main():
    print("=" * 80)
    print("BUCKET B COMPLETO: 5 stores + 30 wines")
    print("=" * 80)

    lc = psycopg2.connect(**LOCAL_DB)
    rc = psycopg2.connect(
        RENDER_DB, options="-c statement_timeout=300000",
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )
    l = lc.cursor()
    r = rc.cursor()

    # ══════════════════════════════════════════════════════════════════════════
    # SNAPSHOT ATUAL
    # ══════════════════════════════════════════════════════════════════════════
    print("\n--- SNAPSHOT ATUAL ---")

    r.execute("""
        SELECT COUNT(*) FROM wines w
        LEFT JOIN wine_sources ws ON ws.wine_id = w.id
        WHERE w.vivino_id IS NULL AND ws.id IS NULL
    """)
    new_sem_antes = r.fetchone()[0]

    # Matched sem source
    l.execute("""SELECT DISTINCT vivino_id FROM y2_results WHERE status = 'matched' AND vivino_id IS NOT NULL""")
    all_matched_vids = [row[0] for row in l.fetchall()]
    matched_sem_antes = 0
    for i in range(0, len(all_matched_vids), 1000):
        chunk = all_matched_vids[i:i+1000]
        r.execute("""SELECT COUNT(*) FROM unnest(%s::int[]) AS vid
                     JOIN wines w ON w.id = vid
                     WHERE NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)""", (chunk,))
        matched_sem_antes += r.fetchone()[0]

    r.execute("SELECT COUNT(*) FROM stores")
    total_stores = r.fetchone()[0]
    r.execute("SELECT COUNT(*) FROM wine_sources")
    total_ws = r.fetchone()[0]

    print(f"  New sem source:     {new_sem_antes:,}")
    print(f"  Matched sem source: {matched_sem_antes:,}")
    print(f"  Total stores:       {total_stores:,}")
    print(f"  Total wine_sources: {total_ws:,}")

    # ══════════════════════════════════════════════════════════════════════════
    # CARREGAR INDICES
    # ══════════════════════════════════════════════════════════════════════════
    l.execute("""
        SELECT id, nome, url_normalizada, pais_codigo, plataforma
        FROM lojas_scraping WHERE url_normalizada IS NOT NULL AND nome IS NOT NULL
    """)
    lojas_por_nome = defaultdict(list)
    for lid, nome, url, pais, plat in l.fetchall():
        key = normalizar_nome(nome)
        if key:
            lojas_por_nome[key].append({"id": lid, "url": url, "pais": pais, "plataforma": plat, "nome_orig": nome})

    r.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
    domain_to_store = {row[0]: row[1] for row in r.fetchall()}

    # ══════════════════════════════════════════════════════════════════════════
    # IDENTIFICAR OS 5 DOMINIOS FALTANTES
    # ══════════════════════════════════════════════════════════════════════════
    print("\n--- IDENTIFICAR DOMINIOS FALTANTES ---")

    # Buscar TODOS new+matched sem source e achar os que falham por dominio nao em stores
    # New sem source
    r.execute("""
        SELECT w.id, w.hash_dedup FROM wines w
        LEFT JOIN wine_sources ws ON ws.wine_id = w.id
        WHERE w.vivino_id IS NULL AND w.hash_dedup IS NOT NULL AND ws.id IS NULL
        ORDER BY w.id
    """)
    new_wines = r.fetchall()

    # Matched sem source
    matched_sem_vids = []
    for i in range(0, len(all_matched_vids), 1000):
        chunk = all_matched_vids[i:i+1000]
        r.execute("""SELECT w.id FROM unnest(%s::int[]) AS vid
                     JOIN wines w ON w.id = vid
                     WHERE NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)""", (chunk,))
        matched_sem_vids.extend([row[0] for row in r.fetchall()])

    # Coletar dominios faltantes e seus wines
    dominios_faltantes = defaultdict(list)  # dominio -> [(wine_id, tipo, url, preco, moeda, clean_id, pais, loja)]

    def processar_fontes_para_dominio(wine_id, tipo, origens):
        for clean_id, pais, id_orig in origens:
            if not pais or not re.match(r"^[a-z]{2}$", pais):
                continue
            try:
                l.execute(
                    f"""SELECT url_original, preco, moeda, fonte, mercado, dados_extras
                        FROM vinhos_{pais}_fontes WHERE vinho_id = %s""",
                    (id_orig,),
                )
                for url, preco, moeda, fonte, mercado, extras in l.fetchall():
                    if not url or is_url_lixo(url):
                        continue

                    dom = None
                    loja_nome = None
                    url_final = url

                    if is_url_absoluta(url):
                        dom = get_domain(url)
                    else:
                        if extras and isinstance(extras, dict):
                            loja_nome = extras.get("loja", "").strip()
                        if loja_nome:
                            loja_match, criterio, n = resolver_loja(loja_nome, mercado, fonte, lojas_por_nome)
                            if loja_match:
                                dom = extrair_dominio(loja_match["url"])
                                if dom:
                                    if url.startswith("/"):
                                        url_final = f"https://{dom}{url}"
                                    else:
                                        url_final = f"https://{dom}/{url}"

                    if dom and dom not in domain_to_store:
                        dominios_faltantes[dom].append({
                            "wine_id": wine_id,
                            "tipo": tipo,
                            "url": url_final,
                            "preco": preco,
                            "moeda": moeda,
                            "clean_id": clean_id,
                            "pais": pais,
                            "loja_nome": loja_nome,
                        })
            except Exception:
                lc.rollback()

    # Processar new
    for wine_id, hash_dedup in new_wines:
        l.execute(
            "SELECT id, pais_tabela, id_original FROM wines_clean WHERE hash_dedup = %s AND id_original IS NOT NULL",
            (hash_dedup,),
        )
        origens = l.fetchall()
        processar_fontes_para_dominio(wine_id, "new", origens)

    # Processar matched
    for vid in matched_sem_vids:
        l.execute("SELECT clean_id FROM y2_results WHERE vivino_id = %s AND status = 'matched'", (vid,))
        cids = [row[0] for row in l.fetchall()]
        origens = []
        for cid in cids:
            l.execute("SELECT id, pais_tabela, id_original FROM wines_clean WHERE id = %s AND id_original IS NOT NULL", (cid,))
            row = l.fetchone()
            if row:
                origens.append(row)
        processar_fontes_para_dominio(vid, "matched", origens)

    print(f"  Dominios faltantes encontrados: {len(dominios_faltantes)}")
    for dom in sorted(dominios_faltantes, key=lambda x: -len(dominios_faltantes[x])):
        wines = dominios_faltantes[dom]
        n_new = sum(1 for w in wines if w["tipo"] == "new")
        n_matched = sum(1 for w in wines if w["tipo"] == "matched")
        print(f"    {dom:<45} {len(wines)} wines (new={n_new}, matched={n_matched})")

    # Confirmar que REALMENTE nao existem em stores
    ambiguidades = []
    stores_a_criar = []

    for dom in sorted(dominios_faltantes.keys()):
        r.execute("SELECT id FROM stores WHERE dominio = %s", (dom,))
        existing = r.fetchone()
        if existing:
            print(f"  *** {dom} JA EXISTE em stores (id={existing[0]}) — SKIP ***")
            continue

        # Buscar info da loja no local
        wines = dominios_faltantes[dom]
        # Tentar resolver pais a partir dos wines
        paises = set(w["pais"] for w in wines if w["pais"])
        loja_nomes = set(w["loja_nome"] for w in wines if w["loja_nome"])

        # Buscar na lojas_scraping pelo dominio
        l.execute("SELECT id, nome, url_normalizada, pais_codigo, plataforma FROM lojas_scraping WHERE url_normalizada ILIKE %s", (f"%{dom}%",))
        loja_matches = l.fetchall()

        if len(loja_matches) == 1:
            lid, lnome, lurl, lpais, lplat = loja_matches[0]
            stores_a_criar.append({
                "dominio": dom,
                "nome": lnome,
                "pais": (lpais or "").upper(),
                "plataforma": lplat,
                "loja_id_local": lid,
                "criterio": "match unico por dominio",
                "n_wines": len(wines),
            })
        elif len(loja_matches) == 0:
            # Tentar pelo nome
            if len(loja_nomes) == 1:
                nome = list(loja_nomes)[0]
                loja_match, criterio, n = resolver_loja(nome, list(paises)[0] if len(paises) == 1 else None, None, lojas_por_nome)
                if loja_match:
                    stores_a_criar.append({
                        "dominio": dom,
                        "nome": loja_match.get("nome_orig", nome),
                        "pais": (loja_match.get("pais") or "").upper(),
                        "plataforma": loja_match.get("plataforma"),
                        "loja_id_local": loja_match["id"],
                        "criterio": f"via nome loja: {criterio}",
                        "n_wines": len(wines),
                    })
                else:
                    stores_a_criar.append({
                        "dominio": dom,
                        "nome": nome,
                        "pais": list(paises)[0].upper() if len(paises) == 1 else "XX",
                        "plataforma": None,
                        "loja_id_local": None,
                        "criterio": "sem match local, dados dos wines",
                        "n_wines": len(wines),
                    })
            else:
                stores_a_criar.append({
                    "dominio": dom,
                    "nome": dom,
                    "pais": list(paises)[0].upper() if len(paises) == 1 else "XX",
                    "plataforma": None,
                    "loja_id_local": None,
                    "criterio": "sem match local, usando dominio como nome",
                    "n_wines": len(wines),
                })
        else:
            # Multiplos matches — ambiguo
            ambiguidades.append({
                "dominio": dom,
                "n_candidatos": len(loja_matches),
                "candidatos": [(m[1], m[3]) for m in loja_matches[:5]],
            })

    # Resolver ambiguidades conhecidas por whitelist de dominio->loja
    WHITELIST_DOMINIO = {
        "wolfberger.com": 713973,  # Wolfberger (FR), nao boutique.wolfberger.com
    }
    resolved_ambiguities = []
    remaining_ambiguities = []
    for a in ambiguidades:
        if a["dominio"] in WHITELIST_DOMINIO:
            lid = WHITELIST_DOMINIO[a["dominio"]]
            l.execute("SELECT id, nome, url_normalizada, pais_codigo, plataforma FROM lojas_scraping WHERE id = %s", (lid,))
            row = l.fetchone()
            if row:
                stores_a_criar.append({
                    "dominio": a["dominio"],
                    "nome": row[1],
                    "pais": (row[3] or "").upper(),
                    "plataforma": row[4],
                    "loja_id_local": row[0],
                    "criterio": f"whitelist explicita (loja_id={lid})",
                    "n_wines": len(dominios_faltantes.get(a["dominio"], [])),
                })
                resolved_ambiguities.append(a["dominio"])
            else:
                remaining_ambiguities.append(a)
        else:
            remaining_ambiguities.append(a)

    if resolved_ambiguities:
        print(f"\n  Ambiguidades resolvidas por whitelist: {resolved_ambiguities}")

    if remaining_ambiguities:
        print(f"\n  *** AMBIGUIDADE NAO RESOLVIDA — AUTO-ABORT ***")
        for a in remaining_ambiguities:
            print(f"    {a['dominio']}: {a['n_candidatos']} candidatos: {a['candidatos']}")
        print(f"\n  Abortando. Resolva manualmente os dominios ambiguos.")
        l.close(); lc.close(); r.close(); rc.close()
        return

    # ══════════════════════════════════════════════════════════════════════════
    # DRY-RUN: STORES
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n--- DRY-RUN: {len(stores_a_criar)} STORES A CRIAR ---")
    for s in stores_a_criar:
        print(f"  {s['dominio']:<45} pais={s['pais']} nome={s['nome'][:40]}")
        print(f"    criterio: {s['criterio']} | {s['n_wines']} wines afetados")

    with open(CSV_STORES, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["dominio", "nome", "pais", "plataforma", "criterio", "n_wines"])
        writer.writeheader()
        for s in stores_a_criar:
            writer.writerow({k: s.get(k, "") for k in writer.fieldnames})
    print(f"  CSV: {CSV_STORES}")

    # ══════════════════════════════════════════════════════════════════════════
    # EXECUTAR STORES
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n--- EXECUTANDO: INSERIR {len(stores_a_criar)} STORES ---")
    ts = datetime.now(timezone.utc)
    novos_store_ids = {}

    for s in stores_a_criar:
        try:
            store_url = f"https://{s['dominio']}"
            r.execute("""
                INSERT INTO stores (dominio, nome, url, pais, descoberta_em, atualizada_em)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (dominio) DO NOTHING
                RETURNING id
            """, (s["dominio"], s["nome"], store_url, s["pais"], ts, ts))
            result = r.fetchone()
            if result:
                novos_store_ids[s["dominio"]] = result[0]
                print(f"  INSERIDO: {s['dominio']} -> store_id={result[0]}")
            else:
                # Ja existia (race condition)
                r.execute("SELECT id FROM stores WHERE dominio = %s", (s["dominio"],))
                existing = r.fetchone()
                if existing:
                    novos_store_ids[s["dominio"]] = existing[0]
                    print(f"  JA EXISTIA: {s['dominio']} -> store_id={existing[0]}")
        except Exception as ex:
            print(f"  ERRO ao inserir {s['dominio']}: {ex}")
            rc.rollback()

    rc.commit()
    print(f"  Stores criados: {len(novos_store_ids)}")

    # Atualizar domain_to_store
    domain_to_store.update(novos_store_ids)

    # ══════════════════════════════════════════════════════════════════════════
    # DRY-RUN + EXECUCAO: WINE_SOURCES
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n--- RESOLVER WINE_SOURCES DO BUCKET B ---")

    ws_inserts = []
    ws_rejeitados = []

    for dom, wines in dominios_faltantes.items():
        store_id = domain_to_store.get(dom)
        if not store_id:
            for w in wines:
                ws_rejeitados.append({**w, "dominio": dom, "motivo": "store nao criado"})
            continue

        for w in wines:
            ws_inserts.append({
                "render_wine_id": w["wine_id"],
                "tipo": w["tipo"],
                "store_id": store_id,
                "url": w["url"],
                "preco": w["preco"],
                "moeda": w["moeda"],
                "dominio": dom,
                "clean_id": w["clean_id"],
                "pais": w["pais"],
                "loja_nome": w["loja_nome"],
            })

    # Dedup por (wine_id, store_id, url)
    seen = set()
    ws_deduped = []
    for ws in ws_inserts:
        key = (ws["render_wine_id"], ws["store_id"], ws["url"])
        if key not in seen:
            seen.add(key)
            ws_deduped.append(ws)
    ws_inserts = ws_deduped

    n_new = sum(1 for w in ws_inserts if w["tipo"] == "new")
    n_matched = sum(1 for w in ws_inserts if w["tipo"] == "matched")
    print(f"  Wine_sources prontos: {len(ws_inserts)} (new={n_new}, matched={n_matched})")
    print(f"  Rejeitados: {len(ws_rejeitados)}")

    # CSV
    with open(CSV_WS, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "render_wine_id", "tipo", "store_id", "dominio", "url", "preco", "moeda",
            "clean_id", "pais", "loja_nome",
        ])
        writer.writeheader()
        for ws in ws_inserts:
            writer.writerow({k: ws.get(k, "") for k in writer.fieldnames})
    print(f"  CSV: {CSV_WS}")

    # Listar todos os 30 wines
    print(f"\n--- TODOS OS WINES BUCKET B ---")
    wine_ids_vistos = set()
    for i, ws in enumerate(ws_inserts, 1):
        if ws["render_wine_id"] in wine_ids_vistos:
            continue
        wine_ids_vistos.add(ws["render_wine_id"])
        r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (ws["render_wine_id"],))
        wine = r.fetchone()
        nome = f"{wine[1]} - {(wine[0] or '')[:30]}" if wine else "???"
        print(f"  [{len(wine_ids_vistos):>2}] wine_id={ws['render_wine_id']} | {ws['tipo']} | {nome}")
        print(f"       {ws['dominio']} | store={ws['store_id']} | {(ws['url'] or '')[:55]}")

    # EXECUTAR
    print(f"\n--- EXECUTANDO: INSERIR {len(ws_inserts)} WINE_SOURCES ---")
    ts_ws = datetime.now(timezone.utc)
    values = [
        (ws["render_wine_id"], ws["store_id"], ws["url"], ws["preco"], ws["moeda"], True, ts_ws, ts_ws)
        for ws in ws_inserts
    ]

    try:
        r.execute("SAVEPOINT bucket_b_ws")
        execute_values(
            r,
            """INSERT INTO wine_sources
                   (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
               VALUES %s
               ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING""",
            values,
        )
        ws_inseridos = r.rowcount
        r.execute("RELEASE SAVEPOINT bucket_b_ws")
        rc.commit()
        print(f"  Wine_sources inseridos: {ws_inseridos}")
    except Exception as ex:
        print(f"  ERRO: {ex}")
        r.execute("ROLLBACK TO SAVEPOINT bucket_b_ws")
        rc.commit()
        print(f"  Rollback. Nenhum wine_source alterado.")
        l.close(); lc.close(); r.close(); rc.close()
        return

    # ══════════════════════════════════════════════════════════════════════════
    # VALIDACAO FINAL
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}")
    print(f"VALIDACAO FINAL")
    print(f"{'=' * 80}")

    r.execute("""
        SELECT COUNT(*) FROM wines w
        LEFT JOIN wine_sources ws ON ws.wine_id = w.id
        WHERE w.vivino_id IS NULL AND ws.id IS NULL
    """)
    new_sem_depois = r.fetchone()[0]

    matched_sem_depois = 0
    for i in range(0, len(all_matched_vids), 1000):
        chunk = all_matched_vids[i:i+1000]
        r.execute("""SELECT COUNT(*) FROM unnest(%s::int[]) AS vid
                     JOIN wines w ON w.id = vid
                     WHERE NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)""", (chunk,))
        matched_sem_depois += r.fetchone()[0]

    print(f"\n  New sem source:     {new_sem_antes:,} -> {new_sem_depois:,} (delta: {new_sem_antes - new_sem_depois})")
    print(f"  Matched sem source: {matched_sem_antes:,} -> {matched_sem_depois:,} (delta: {matched_sem_antes - matched_sem_depois})")
    print(f"  Stores criados:     {len(novos_store_ids)}")
    print(f"  Wine_sources:       {ws_inseridos}")

    print(f"\n  Dominios tratados:")
    for dom, sid in novos_store_ids.items():
        n = len(dominios_faltantes.get(dom, []))
        print(f"    {dom:<45} store_id={sid} | {n} wines")

    # Status final dos 30 wines
    print(f"\n  Status final dos {len(wine_ids_vistos)} wines:")
    for wid in sorted(wine_ids_vistos):
        r.execute("SELECT COUNT(*) FROM wine_sources WHERE wine_id = %s", (wid,))
        src_cnt = r.fetchone()[0]
        status = "OK" if src_cnt > 0 else "SEM SOURCE"
        r.execute("SELECT nome, produtor, vivino_id FROM wines WHERE id = %s", (wid,))
        w = r.fetchone()
        tipo = "matched" if w[2] else "new"
        print(f"    wine_id={wid} | {tipo} | {src_cnt} sources | {status} | {w[1]} - {(w[0] or '')[:30]}")

    # Queries de revert
    print(f"\n  QUERIES DE REVERT:")
    print(f"    -- Stores:")
    for dom in novos_store_ids:
        print(f"    DELETE FROM stores WHERE dominio = '{dom}';")
    print(f"    -- Wine_sources:")
    print(f"    DELETE FROM wine_sources WHERE descoberto_em = '{ts_ws}';")

    # Backlog not_wine
    print(f"\n  BACKLOG NOT_WINE VAZADO:")
    print(f"    wine_id=2249411 ('Windows 11 PRO + Office') — registrado, nao tratado neste bucket")

    # Erros
    if ws_rejeitados:
        print(f"\n  REJEITADOS ({len(ws_rejeitados)}):")
        for rej in ws_rejeitados:
            print(f"    wine_id={rej['wine_id']} | {rej['dominio']} | {rej['motivo']}")
    else:
        print(f"\n  Erros/rollback: NENHUM")

    l.close(); lc.close()
    r.close(); rc.close()
    print("\nFim.")


if __name__ == "__main__":
    main()
