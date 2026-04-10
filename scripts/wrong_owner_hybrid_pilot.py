"""
Piloto comparativo: metodo atual vs hibrido no bloco 50501-52500.
READ-ONLY — nenhum delete.
"""
import os, re, sys, csv, time
from collections import defaultdict
from urllib.parse import urlparse
import _env

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2
from psycopg2.extras import execute_values

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = os.environ["DATABASE_URL"]

BLOCK_START = 50500
BLOCK_END = 52500
CLEAN_LIMIT = 30
URL_LIMIT = 5


def gd(url):
    try:
        n = urlparse(url).netloc
        return n.replace("www.", "") if n else None
    except:
        return None


def main():
    print("=" * 80, flush=True)
    print("PILOTO COMPARATIVO: METODO ATUAL vs HIBRIDO", flush=True)
    print(f"Owners {BLOCK_START+1}-{BLOCK_END} (2000 owners)", flush=True)
    print("=" * 80, flush=True)

    lc = psycopg2.connect(**LOCAL_DB)
    rc = psycopg2.connect(
        RENDER_DB, options="-c statement_timeout=300000",
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )
    l = lc.cursor()
    r = rc.cursor()

    r.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
    d2s = {row[0]: row[1] for row in r.fetchall()}

    l.execute("""
        SELECT vivino_id, COUNT(*) FROM y2_results
        WHERE status = 'matched' AND vivino_id IS NOT NULL
        GROUP BY vivino_id ORDER BY COUNT(*) DESC
    """)
    all_owners = l.fetchall()
    block_owners = all_owners[BLOCK_START:BLOCK_END]
    vids = [v for v, _ in block_owners]
    print(f"Owners no bloco: {len(block_owners)}", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 1: Reconstruir expected no LOCAL (igual ao v2, mas batch maior)
    # ══════════════════════════════════════════════════════════════════════════
    t0 = time.time()
    print("\nFASE 1: Reconstruir expected URLs no LOCAL...", flush=True)

    # Batch y2_results
    all_y2 = defaultdict(list)
    for i in range(0, len(vids), 1000):
        chunk = vids[i:i+1000]
        l.execute("SELECT vivino_id, clean_id FROM y2_results WHERE status = 'matched' AND vivino_id = ANY(%s)", (chunk,))
        for vid, cid in l.fetchall():
            if len(all_y2[vid]) < CLEAN_LIMIT:
                all_y2[vid].append(cid)

    # Batch wines_clean
    all_cids = [cid for cids in all_y2.values() for cid in cids]
    clean_map = {}
    for i in range(0, len(all_cids), 5000):
        chunk = all_cids[i:i+5000]
        l.execute("SELECT id, pais_tabela, id_original FROM wines_clean WHERE id = ANY(%s) AND id_original IS NOT NULL", (chunk,))
        for cid, pais, ido in l.fetchall():
            if pais and re.match(r"^[a-z]{2}$", pais):
                clean_map[cid] = (pais, ido)

    # Batch fontes por pais
    by_pais = defaultdict(list)
    for vid, cids in all_y2.items():
        for cid in cids:
            if cid in clean_map:
                pais, ido = clean_map[cid]
                by_pais[pais].append((ido, vid, cid))

    expected = {}  # url -> {owner, store_id, pais, cid}
    for pais, items in by_pais.items():
        idos = list(set(ido for ido, _, _ in items))
        ido_to_info = defaultdict(list)
        for ido, vid, cid in items:
            ido_to_info[ido].append((vid, cid))
        for i in range(0, len(idos), 1000):
            chunk = idos[i:i+1000]
            try:
                l.execute(
                    f"""SELECT vinho_id, url_original FROM vinhos_{pais}_fontes
                        WHERE vinho_id = ANY(%s) AND url_original IS NOT NULL AND url_original LIKE 'http%%'""",
                    (chunk,),
                )
                count_per = defaultdict(int)
                for ido, url in l.fetchall():
                    if count_per[ido] >= URL_LIMIT:
                        continue
                    count_per[ido] += 1
                    dom = gd(url)
                    sid = d2s.get(dom) if dom else None
                    if sid:
                        info = ido_to_info[ido]
                        vid, cid = info[0]
                        expected[url] = {"owner": vid, "store_id": sid, "pais": pais, "cid": cid}
            except Exception:
                lc.rollback()

    t1 = time.time()
    print(f"  Expected URLs: {len(expected):,} ({t1-t0:.1f}s)", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 2: Subir expected para tabela temporaria no Render
    # ══════════════════════════════════════════════════════════════════════════
    print("\nFASE 2: Subir expected para tabela temporaria no Render...", flush=True)
    t2 = time.time()

    r.execute("CREATE TEMP TABLE tmp_expected (url TEXT, store_id INT, expected_wine_id INT, clean_id INT)")
    rows = [(url, e["store_id"], e["owner"], e["cid"]) for url, e in expected.items()]
    execute_values(r, "INSERT INTO tmp_expected VALUES %s", rows)
    r.execute("CREATE INDEX idx_tmp_exp_url ON tmp_expected (url)")
    rc.commit()

    t3 = time.time()
    print(f"  Inseridos na temp: {len(rows):,} ({t3-t2:.1f}s)", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 3: Classificar por SQL join no Render
    # ══════════════════════════════════════════════════════════════════════════
    print("\nFASE 3: Classificar por SQL...", flush=True)
    t4 = time.time()

    # Passo 1: buscar TODAS as linhas de wine_sources que compartilham URL com tmp_expected
    r.execute("""
        SELECT ws.id, ws.wine_id, ws.store_id, ws.url, e.expected_wine_id, e.clean_id
        FROM tmp_expected e
        JOIN wine_sources ws ON ws.url = e.url
    """)
    all_matches = r.fetchall()
    print(f"  Linhas matchadas no Render: {len(all_matches):,}", flush=True)

    # Classificar em Python (mais rapido que subqueries correlacionadas)
    # Agrupar por URL
    by_url = defaultdict(lambda: {"correct": [], "wrong": [], "expected": None, "store": None, "cid": None})
    for ws_id, wid, sid, url, exp_wid, cid in all_matches:
        entry = by_url[url]
        entry["expected"] = exp_wid
        entry["store"] = sid
        entry["cid"] = cid
        if wid == exp_wid:
            entry["correct"].append(ws_id)
        else:
            entry["wrong"].append((ws_id, wid))

    class_a_hybrid = []
    class_b_hybrid = []
    class_c_hybrid = []

    for url, info in by_url.items():
        if not info["wrong"]:
            continue
        if info["correct"]:
            # Classe A: owner correto tem, wrong sao copias
            for ws_id, wid in info["wrong"]:
                class_a_hybrid.append((ws_id, wid, info["expected"], info["store"], url, info["cid"]))
        else:
            wrong_owners = set(wid for _, wid in info["wrong"])
            if len(wrong_owners) == 1:
                # Classe B: 1 owner errado, correto ausente
                for ws_id, wid in info["wrong"]:
                    class_b_hybrid.append((ws_id, wid, info["expected"], info["store"], url, info["cid"]))
            else:
                # Classe C: ambiguo
                for ws_id, wid in info["wrong"]:
                    class_c_hybrid.append((ws_id, wid, info["expected"], info["store"], url, info["cid"]))

    t5 = time.time()
    print(f"  Classificacao SQL: {t5-t4:.1f}s", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 4: Rodar metodo atual (v2) no mesmo bloco para comparar
    # ══════════════════════════════════════════════════════════════════════════
    print("\nFASE 4: Rodar metodo atual (v2) para comparacao...", flush=True)
    t6 = time.time()

    # Buscar todas linhas no Render para as expected URLs
    url_lines = defaultdict(list)
    all_urls = list(expected.keys())
    for i in range(0, len(all_urls), 500):
        chunk = all_urls[i:i+500]
        r.execute("""
            SELECT id, wine_id, store_id, url FROM wine_sources WHERE url = ANY(%s)
        """, (chunk,))
        for ws_id, wid, sid, url in r.fetchall():
            url_lines[url].append({"ws_id": ws_id, "wine_id": wid, "store_id": sid})

    ca_v2, cb_v2, cc_v2 = [], [], []
    for url, exp in expected.items():
        lines = url_lines.get(url, [])
        if not lines:
            continue
        correct = [ln for ln in lines if ln["wine_id"] == exp["owner"]]
        wrong = [ln for ln in lines if ln["wine_id"] != exp["owner"]]
        if not wrong:
            continue
        if correct:
            for wl in wrong:
                ca_v2.append(wl["ws_id"])
        elif len(set(ln["wine_id"] for ln in wrong)) == 1:
            for wl in wrong:
                cb_v2.append(wl["ws_id"])
        else:
            for wl in wrong:
                cc_v2.append(wl["ws_id"])

    t7 = time.time()
    print(f"  Metodo v2: {t7-t6:.1f}s", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # COMPARACAO
    # ══════════════════════════════════════════════════════════════════════════
    hybrid_a_ids = set(row[0] for row in class_a_hybrid)
    hybrid_b_ids = set(row[0] for row in class_b_hybrid)
    hybrid_c_ids = set(row[0] for row in class_c_hybrid)
    v2_a_ids = set(ca_v2)
    v2_b_ids = set(cb_v2)
    v2_c_ids = set(cc_v2)

    print(f"\n{'=' * 80}", flush=True)
    print(f"COMPARACAO", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"  {'':20} {'Hibrido':>10} {'V2 atual':>10} {'Match':>8}", flush=True)
    print(f"  {'Classe A':20} {len(hybrid_a_ids):>10,} {len(v2_a_ids):>10,} {'SIM' if hybrid_a_ids == v2_a_ids else 'NAO':>8}", flush=True)
    print(f"  {'Classe B':20} {len(hybrid_b_ids):>10,} {len(v2_b_ids):>10,} {'SIM' if hybrid_b_ids == v2_b_ids else 'NAO':>8}", flush=True)
    print(f"  {'Classe C':20} {len(hybrid_c_ids):>10,} {len(v2_c_ids):>10,} {'SIM' if hybrid_c_ids == v2_c_ids else 'NAO':>8}", flush=True)

    # Divergencias
    a_only_hybrid = hybrid_a_ids - v2_a_ids
    a_only_v2 = v2_a_ids - hybrid_a_ids
    if a_only_hybrid or a_only_v2:
        print(f"\n  Divergencias Classe A:", flush=True)
        print(f"    So no hibrido: {len(a_only_hybrid)}", flush=True)
        print(f"    So no v2:      {len(a_only_v2)}", flush=True)
        for wsid in list(a_only_hybrid)[:5]:
            print(f"      hybrid-only ws_id={wsid}", flush=True)
        for wsid in list(a_only_v2)[:5]:
            print(f"      v2-only ws_id={wsid}", flush=True)

    # Timing
    print(f"\n  TEMPO:", flush=True)
    print(f"    Local (reconstruir expected):  {t1-t0:.1f}s", flush=True)
    print(f"    Upload temp table:             {t3-t2:.1f}s", flush=True)
    print(f"    SQL classificacao (hibrido):   {t5-t4:.1f}s", flush=True)
    print(f"    V2 classificacao (batch):      {t7-t6:.1f}s", flush=True)
    print(f"    TOTAL hibrido:                 {t5-t0:.1f}s", flush=True)
    print(f"    TOTAL v2:                      {t1-t0 + t7-t6:.1f}s", flush=True)

    # Cleanup
    r.execute("DROP TABLE tmp_expected")
    rc.commit()

    print(f"\nREAD-ONLY — nenhum dado alterado.", flush=True)
    l.close(); lc.close(); r.close(); rc.close()


if __name__ == "__main__":
    main()
