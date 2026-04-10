"""
Teste de amostra estratificada: 50 vinhos para validar logica de reconciliacao de wine_sources.

Grupos:
  1. 10 matched sem link (y2_results.status='matched', vivino_id != NULL, sem wine_source)
  2. 20 new sem link - Cat A (hash existe no local, tem fontes)
  3. 5 new sem link - Cat C (hash NAO existe no local)
  4. 5 new sem link - Cat D (dominio nao existe em stores)
  5. 5 wines receptores com links excedentes (possivelmente roubados de outros)
  6. 5 controles positivos (wines com muitos links, ja corretos)

Para cada vinho, testa a cadeia completa:
  hash_dedup -> wines_clean -> pais_tabela + id_original -> vinhos_XX_fontes -> stores.dominio
"""

import os
import re
import sys
from urllib.parse import urlparse
import _env

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2

LOCAL_DB = dict(
    host="localhost",
    port=5432,
    dbname="winegod_db",
    user="postgres",
    password="postgres123",
)

RENDER_DB = os.environ["DATABASE_URL"]


def conectar_render():
    return psycopg2.connect(
        RENDER_DB,
        options="-c statement_timeout=300000",
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )


def conectar_local():
    return psycopg2.connect(**LOCAL_DB)


def get_domain(url):
    try:
        d = urlparse(url).netloc
        return d.replace("www.", "") if d else None
    except Exception:
        return None


def resolver_matched_via_y2(local_cur, vivino_id, domain_to_store):
    """Resolve um matched wine via y2_results.vivino_id -> clean_id -> wines_clean -> fontes."""
    local_cur.execute(
        "SELECT clean_id FROM y2_results WHERE vivino_id = %s AND status = 'matched'",
        (str(vivino_id),),
    )
    clean_ids = [r[0] for r in local_cur.fetchall()]
    if not clean_ids:
        return [], [], [], []

    origens = []
    for cid in clean_ids:
        local_cur.execute(
            "SELECT id, pais_tabela, id_original FROM wines_clean WHERE id = %s AND id_original IS NOT NULL",
            (cid,),
        )
        origens.extend(local_cur.fetchall())

    return _resolver_fontes_de_origens(local_cur, origens, domain_to_store)


def _resolver_fontes_de_origens(local_cur, origens, domain_to_store):
    """Dado origens [(id, pais_tabela, id_original)], resolve URLs finais."""
    fontes_todas = []
    fontes_com_store = []
    fontes_sem_store = []

    for clean_id, pais_tabela, id_original in origens:
        if not pais_tabela or not re.match(r"^[a-z]{2}$", pais_tabela):
            continue
        tabela = f"vinhos_{pais_tabela}_fontes"
        try:
            local_cur.execute(
                f"SELECT url_original, preco, moeda FROM {tabela} WHERE vinho_id = %s AND url_original IS NOT NULL",
                (id_original,),
            )
            for url, preco, moeda in local_cur.fetchall():
                dominio = get_domain(url)
                store_id = domain_to_store.get(dominio) if dominio else None
                entry = {
                    "clean_id": clean_id,
                    "pais": pais_tabela,
                    "id_original": id_original,
                    "url": url[:120],
                    "dominio": dominio,
                    "store_id": store_id,
                    "preco": preco,
                    "moeda": moeda,
                }
                fontes_todas.append(entry)
                if store_id:
                    fontes_com_store.append(entry)
                else:
                    fontes_sem_store.append(entry)
        except Exception:
            pass

    return origens, fontes_todas, fontes_com_store, fontes_sem_store


def resolver_fontes_locais(local_cur, hash_dedup, domain_to_store):
    """Resolve um hash_dedup ate URLs finais."""
    local_cur.execute(
        "SELECT id, pais_tabela, id_original FROM wines_clean WHERE hash_dedup = %s AND id_original IS NOT NULL",
        (hash_dedup,),
    )
    origens = local_cur.fetchall()
    if not origens:
        return [], [], [], []
    return _resolver_fontes_de_origens(local_cur, origens, domain_to_store)


def main():
    print("=" * 80)
    print("TESTE AMOSTRA ESTRATIFICADA - 50 VINHOS")
    print("=" * 80)

    print("\nConectando LOCAL...")
    local_conn = conectar_local()
    local_cur = local_conn.cursor()

    print("Conectando RENDER...")
    render_conn = conectar_render()
    render_cur = render_conn.cursor()

    # Carregar domain_to_store
    render_cur.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
    domain_to_store = {row[0]: row[1] for row in render_cur.fetchall()}
    print(f"Stores carregadas: {len(domain_to_store):,}")

    resultados = {}
    totais = {"ok": 0, "sem_hash": 0, "sem_fontes": 0, "sem_store": 0, "links_total": 0}

    # ── GRUPO 1: 10 matched sem link ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print("GRUPO 1: Matched sem link (vivino_id != NULL, sem wine_source)")
    print("=" * 60)

    render_cur.execute("""
        SELECT w.id, w.hash_dedup, w.nome, w.produtor, w.pais_nome, w.vivino_id
        FROM wines w
        LEFT JOIN wine_sources ws ON ws.wine_id = w.id
        WHERE w.vivino_id IS NOT NULL
        AND w.hash_dedup IS NOT NULL
        AND ws.id IS NULL
        ORDER BY RANDOM()
        LIMIT 10
    """)
    grupo1 = render_cur.fetchall()
    print(f"  Selecionados: {len(grupo1)}")

    for i, (wid, hdp, nome, prod, pais, vivino_id) in enumerate(grupo1, 1):
        # Matched: resolver via y2_results.vivino_id -> clean_id -> fontes
        origens, fontes, com_store, sem_store = resolver_matched_via_y2(local_cur, vivino_id, domain_to_store)
        # Fallback: tentar por hash_dedup se y2 nao achou
        if not origens:
            origens, fontes, com_store, sem_store = resolver_fontes_locais(local_cur, hdp, domain_to_store)
        status = "OK" if com_store else ("SEM_STORE" if fontes else ("SEM_FONTES" if not origens else "SEM_FONTES_TABELA"))
        if com_store:
            totais["ok"] += 1
            totais["links_total"] += len(com_store)
        elif fontes:
            totais["sem_store"] += 1
        elif not origens:
            totais["sem_hash"] += 1
        else:
            totais["sem_fontes"] += 1

        print(f"\n  [{i}] wine_id={wid} | vivino_id={vivino_id}")
        print(f"      {prod} - {nome[:60]}")
        print(f"      pais={pais} | hash={hdp[:20]}...")
        print(f"      origens_local={len(origens)} | fontes={len(fontes)} | com_store={len(com_store)} | sem_store={len(sem_store)}")
        print(f"      STATUS: {status}")
        if com_store:
            for f in com_store[:3]:
                print(f"        -> {f['dominio']} (store={f['store_id']}) {f['url'][:80]}")
            if len(com_store) > 3:
                print(f"        ... e mais {len(com_store) - 3} links")

    # ── GRUPO 2: 20 new sem link - Cat A (hash resolvivel) ───────────────────
    print("\n" + "=" * 60)
    print("GRUPO 2: New sem link - Cat A (hash existe no local, tem fontes)")
    print("=" * 60)

    # Buscar 80 candidatos e filtrar os que tem hash no local (cat A)
    render_cur.execute("""
        SELECT w.id, w.hash_dedup, w.nome, w.produtor, w.pais_nome
        FROM wines w
        LEFT JOIN wine_sources ws ON ws.wine_id = w.id
        WHERE w.vivino_id IS NULL
        AND w.hash_dedup IS NOT NULL
        AND ws.id IS NULL
        ORDER BY RANDOM()
        LIMIT 80
    """)
    candidatos_new = render_cur.fetchall()

    grupo2 = []
    for wid, hdp, nome, prod, pais in candidatos_new:
        if len(grupo2) >= 20:
            break
        origens, fontes, com_store, sem_store = resolver_fontes_locais(local_cur, hdp, domain_to_store)
        if com_store:  # Cat A: tem hash, tem fontes, tem store
            grupo2.append((wid, hdp, nome, prod, pais, origens, fontes, com_store, sem_store))

    print(f"  Selecionados: {len(grupo2)} (de {len(candidatos_new)} candidatos)")

    for i, (wid, hdp, nome, prod, pais, origens, fontes, com_store, sem_store) in enumerate(grupo2, 1):
        totais["ok"] += 1
        totais["links_total"] += len(com_store)
        print(f"\n  [{i}] wine_id={wid}")
        print(f"      {prod} - {nome[:60]}")
        print(f"      pais={pais} | hash={hdp[:20]}...")
        print(f"      origens={len(origens)} | fontes={len(fontes)} | com_store={len(com_store)} | sem_store={len(sem_store)}")
        print(f"      STATUS: OK")
        for f in com_store[:2]:
            print(f"        -> {f['dominio']} (store={f['store_id']}) preco={f['preco']} {f['moeda']}")
        if len(com_store) > 2:
            print(f"        ... e mais {len(com_store) - 2} links")

    # ── GRUPO 3: 5 new sem link - Cat C (hash NAO no local) ──────────────────
    print("\n" + "=" * 60)
    print("GRUPO 3: New sem link - Cat C (hash NAO existe no local)")
    print("=" * 60)

    grupo3_restantes = []
    for wid, hdp, nome, prod, pais in candidatos_new:
        if len(grupo3_restantes) >= 5:
            break
        origens, fontes, com_store, sem_store = resolver_fontes_locais(local_cur, hdp, domain_to_store)
        if not origens:  # Cat C: hash nao existe no local
            grupo3_restantes.append((wid, hdp, nome, prod, pais))
            totais["sem_hash"] += 1

    # Se nao achou nos candidatos ja buscados, buscar mais
    if len(grupo3_restantes) < 5:
        render_cur.execute("""
            SELECT w.id, w.hash_dedup, w.nome, w.produtor, w.pais_nome
            FROM wines w
            LEFT JOIN wine_sources ws ON ws.wine_id = w.id
            WHERE w.vivino_id IS NULL
            AND w.hash_dedup IS NOT NULL
            AND ws.id IS NULL
            ORDER BY RANDOM()
            LIMIT 200
        """)
        mais_candidatos = render_cur.fetchall()
        for wid, hdp, nome, prod, pais in mais_candidatos:
            if len(grupo3_restantes) >= 5:
                break
            origens, _, _, _ = resolver_fontes_locais(local_cur, hdp, domain_to_store)
            if not origens:
                grupo3_restantes.append((wid, hdp, nome, prod, pais))
                totais["sem_hash"] += 1

    print(f"  Selecionados: {len(grupo3_restantes)}")
    for i, (wid, hdp, nome, prod, pais) in enumerate(grupo3_restantes, 1):
        print(f"\n  [{i}] wine_id={wid}")
        print(f"      {prod} - {nome[:60]}")
        print(f"      pais={pais} | hash={hdp[:20]}...")
        print(f"      STATUS: SEM_HASH_LOCAL (irrecuperavel sem investigacao)")

    # ── GRUPO 4: 5 new sem link - Cat D (dominio nao em stores) ──────────────
    print("\n" + "=" * 60)
    print("GRUPO 4: New sem link - Cat D (dominio nao existe em stores)")
    print("=" * 60)

    grupo4 = []
    render_cur.execute("""
        SELECT w.id, w.hash_dedup, w.nome, w.produtor, w.pais_nome
        FROM wines w
        LEFT JOIN wine_sources ws ON ws.wine_id = w.id
        WHERE w.vivino_id IS NULL
        AND w.hash_dedup IS NOT NULL
        AND ws.id IS NULL
        ORDER BY RANDOM()
        LIMIT 300
    """)
    candidatos_d = render_cur.fetchall()

    for wid, hdp, nome, prod, pais in candidatos_d:
        if len(grupo4) >= 5:
            break
        origens, fontes, com_store, sem_store = resolver_fontes_locais(local_cur, hdp, domain_to_store)
        if fontes and not com_store:  # Cat D: tem fontes mas nenhum dominio resolvido
            grupo4.append((wid, hdp, nome, prod, pais, origens, fontes, sem_store))
            totais["sem_store"] += 1

    print(f"  Selecionados: {len(grupo4)}")
    for i, (wid, hdp, nome, prod, pais, origens, fontes, sem_store) in enumerate(grupo4, 1):
        print(f"\n  [{i}] wine_id={wid}")
        print(f"      {prod} - {nome[:60]}")
        print(f"      pais={pais} | hash={hdp[:20]}...")
        print(f"      origens={len(origens)} | fontes={len(fontes)} | dominios_sem_store:")
        for f in sem_store[:5]:
            print(f"        X {f['dominio']} -> SEM STORE")
        print(f"      STATUS: SEM_STORE (dominio precisa ser adicionado em stores)")

    # ── GRUPO 5: 5 wines receptores com links excedentes ─────────────────────
    print("\n" + "=" * 60)
    print("GRUPO 5: Wines com links excedentes (possivelmente roubados)")
    print("=" * 60)

    render_cur.execute("""
        SELECT w.id, w.nome, w.produtor, w.pais_nome,
               COUNT(ws.id) as num_sources,
               LENGTH(w.produtor) as prod_len
        FROM wines w
        JOIN wine_sources ws ON ws.wine_id = w.id
        WHERE w.vivino_id IS NULL
        AND LENGTH(w.produtor) <= 10
        GROUP BY w.id, w.nome, w.produtor, w.pais_nome
        HAVING COUNT(ws.id) >= 20
        ORDER BY COUNT(ws.id) DESC
        LIMIT 5
    """)
    grupo5 = render_cur.fetchall()
    print(f"  Selecionados: {len(grupo5)}")

    for i, (wid, nome, prod, pais, num_src, prod_len) in enumerate(grupo5, 1):
        # Buscar os dominios dos links
        render_cur.execute("""
            SELECT s.dominio, COUNT(*)
            FROM wine_sources ws
            JOIN stores s ON s.id = ws.store_id
            WHERE ws.wine_id = %s
            GROUP BY s.dominio
            ORDER BY COUNT(*) DESC
            LIMIT 5
        """, (wid,))
        dominios = render_cur.fetchall()

        print(f"\n  [{i}] wine_id={wid} | {num_src} sources | produtor_len={prod_len}")
        print(f"      {prod} - {nome[:60]}")
        print(f"      pais={pais}")
        print(f"      SUSPEITO: produtor curto com muitos links")
        for dom, cnt in dominios:
            print(f"        {dom}: {cnt} links")

    # ── GRUPO 6: 5 controles positivos ───────────────────────────────────────
    print("\n" + "=" * 60)
    print("GRUPO 6: Controles positivos (wines corretos com muitos links)")
    print("=" * 60)

    render_cur.execute("""
        SELECT w.id, w.nome, w.produtor, w.pais_nome,
               COUNT(ws.id) as num_sources
        FROM wines w
        JOIN wine_sources ws ON ws.wine_id = w.id
        WHERE w.vivino_id IS NULL
        AND LENGTH(w.produtor) > 15
        GROUP BY w.id, w.nome, w.produtor, w.pais_nome
        HAVING COUNT(ws.id) BETWEEN 5 AND 30
        ORDER BY RANDOM()
        LIMIT 5
    """)
    grupo6 = render_cur.fetchall()
    print(f"  Selecionados: {len(grupo6)}")

    for i, (wid, nome, prod, pais, num_src) in enumerate(grupo6, 1):
        # Verificar no local se os links batem
        render_cur.execute("SELECT hash_dedup FROM wines WHERE id = %s", (wid,))
        row = render_cur.fetchone()
        hdp = row[0] if row else None

        links_render = num_src
        links_local = 0
        if hdp:
            origens, fontes, com_store, _ = resolver_fontes_locais(local_cur, hdp, domain_to_store)
            links_local = len(com_store)

        match_pct = round(links_local / links_render * 100, 1) if links_render > 0 else 0

        print(f"\n  [{i}] wine_id={wid} | {num_src} sources no Render")
        print(f"      {prod} - {nome[:60]}")
        print(f"      pais={pais}")
        print(f"      Links Render={links_render} | Links Local={links_local} | Match={match_pct}%")
        if match_pct >= 80:
            print(f"      STATUS: SAUDAVEL (links batem)")
        else:
            print(f"      STATUS: DIVERGENTE (Render tem mais que local)")

    # ── RESUMO ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("RESUMO DA AMOSTRA")
    print("=" * 80)
    print(f"  Grupo 1 (matched sem link):    {len(grupo1)} vinhos")
    print(f"  Grupo 2 (new Cat A - OK):      {len(grupo2)} vinhos")
    print(f"  Grupo 3 (new Cat C - sem hash):{len(grupo3_restantes)} vinhos")
    print(f"  Grupo 4 (new Cat D - sem store):{len(grupo4)} vinhos")
    print(f"  Grupo 5 (suspeitos excedentes):{len(grupo5)} vinhos")
    print(f"  Grupo 6 (controles positivos): {len(grupo6)} vinhos")
    total_amostra = len(grupo1) + len(grupo2) + len(grupo3_restantes) + len(grupo4) + len(grupo5) + len(grupo6)
    print(f"  TOTAL:                         {total_amostra} vinhos")
    print()
    print(f"  Recuperaveis (OK):             {totais['ok']}")
    print(f"  Sem hash no local:             {totais['sem_hash']}")
    print(f"  Sem fontes na tabela:          {totais['sem_fontes']}")
    print(f"  Sem store (dominio novo):      {totais['sem_store']}")
    print(f"  Links totais recuperaveis:     {totais['links_total']}")
    print()

    taxa_ok = round(totais["ok"] / max(len(grupo1) + len(grupo2), 1) * 100, 1)
    print(f"  Taxa de recuperacao (G1+G2):   {taxa_ok}%")
    if taxa_ok >= 80:
        print("  >>> RESULTADO: BOM para prosseguir com piloto de 500")
    elif taxa_ok >= 60:
        print("  >>> RESULTADO: ACEITAVEL, mas investigar falhas antes do piloto")
    else:
        print("  >>> RESULTADO: RUIM, revisar logica antes de continuar")

    # Cleanup
    local_cur.close()
    local_conn.close()
    render_cur.close()
    render_conn.close()


if __name__ == "__main__":
    main()
