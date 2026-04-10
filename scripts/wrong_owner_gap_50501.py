"""
Fechar gap wrong_owner: owners 50501-52500.
Metodo SQL validado: build_expected local, classify Python, DELETE RETURNING.
"""
import csv, os, re, sys, time
from collections import defaultdict
from urllib.parse import urlparse
import os
import _env

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2
from psycopg2.extras import execute_values

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = os.environ["DATABASE_URL"]

DIR = os.path.dirname(__file__)
START = 50500
END = 52500
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
    print("FECHAR GAP: owners 50501-52500", flush=True)
    print("=" * 80, flush=True)

    lc = psycopg2.connect(**LOCAL_DB)
    rc = psycopg2.connect(
        RENDER_DB, options="-c statement_timeout=600000",
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
    block_owners = all_owners[START:END]
    vids = [v for v, _ in block_owners]

    r.execute("SELECT COUNT(*) FROM wine_sources")
    ws_antes = r.fetchone()[0]
    print(f"WS antes: {ws_antes:,}", flush=True)
    print(f"Owners: {len(block_owners):,}", flush=True)

    # Fase 1: build_expected
    t0 = time.time()
    all_y2 = defaultdict(list)
    for i in range(0, len(vids), 1000):
        chunk = vids[i:i+1000]
        l.execute("SELECT vivino_id, clean_id FROM y2_results WHERE status = 'matched' AND vivino_id = ANY(%s)", (chunk,))
        for vid, cid in l.fetchall():
            if len(all_y2[vid]) < CLEAN_LIMIT:
                all_y2[vid].append(cid)

    all_cids = [c for cs in all_y2.values() for c in cs]
    clean_map = {}
    for i in range(0, len(all_cids), 5000):
        chunk = all_cids[i:i+5000]
        l.execute("SELECT id, pais_tabela, id_original FROM wines_clean WHERE id = ANY(%s) AND id_original IS NOT NULL", (chunk,))
        for cid, pais, ido in l.fetchall():
            if pais and re.match(r"^[a-z]{2}$", pais):
                clean_map[cid] = (pais, ido)

    by_pais = defaultdict(list)
    for vid, cids in all_y2.items():
        for cid in cids:
            if cid in clean_map:
                pais, ido = clean_map[cid]
                by_pais[pais].append((ido, vid, cid))

    expected = {}
    for pais, items in by_pais.items():
        idos = list(set(ido for ido, _, _ in items))
        ido_info = defaultdict(list)
        for ido, vid, cid in items:
            ido_info[ido].append((vid, cid))
        for i in range(0, len(idos), 1000):
            chunk = idos[i:i+1000]
            try:
                l.execute(
                    f"""SELECT vinho_id, url_original FROM vinhos_{pais}_fontes
                        WHERE vinho_id = ANY(%s) AND url_original IS NOT NULL AND url_original LIKE 'http%%'""",
                    (chunk,),
                )
                cnt = defaultdict(int)
                for ido, url in l.fetchall():
                    if cnt[ido] >= URL_LIMIT:
                        continue
                    cnt[ido] += 1
                    dom = gd(url)
                    sid = d2s.get(dom) if dom else None
                    if sid:
                        vid, cid = ido_info[ido][0]
                        expected[(url, sid)] = {"owner": vid, "store_id": sid, "pais": pais, "cid": cid}
            except Exception:
                lc.rollback()

    t1 = time.time()
    print(f"\nFase 1 (build_expected): {len(expected):,} URLs em {t1-t0:.1f}s", flush=True)

    # Fase 2: upload temp + classify
    t2 = time.time()
    r.execute("CREATE TEMP TABLE tmp_exp (url TEXT, store_id INT, exp_wid INT, cid INT)")
    rows = [(url, sid, e["owner"], e["cid"]) for (url, sid), e in expected.items()]
    execute_values(r, "INSERT INTO tmp_exp VALUES %s", rows)
    r.execute("CREATE INDEX idx_tmp_us ON tmp_exp (url, store_id)")
    rc.commit()

    r.execute("""
        SELECT ws.id, ws.wine_id, ws.store_id, ws.url, e.exp_wid, e.cid
        FROM tmp_exp e JOIN wine_sources ws ON ws.url = e.url AND ws.store_id = e.store_id
    """)
    all_matches = r.fetchall()

    by_key = defaultdict(lambda: {"correct": [], "wrong": [], "exp": None, "cid": None})
    for ws_id, wid, sid, url, exp_wid, cid in all_matches:
        entry = by_key[(url, sid)]
        entry["exp"] = exp_wid
        entry["cid"] = cid
        if wid == exp_wid:
            entry["correct"].append(ws_id)
        else:
            entry["wrong"].append((ws_id, wid))

    class_a_ids = []
    ws_to_exp = {}
    class_b = []
    class_c = []
    for (url, sid), info in by_key.items():
        if not info["wrong"]:
            continue
        if info["correct"]:
            for ws_id, wid in info["wrong"]:
                class_a_ids.append(ws_id)
                ws_to_exp[ws_id] = (info["exp"], info["cid"])
        else:
            wowners = set(wid for _, wid in info["wrong"])
            bucket = class_b if len(wowners) == 1 else class_c
            for ws_id, wid in info["wrong"]:
                bucket.append((ws_id, wid, info["exp"], sid, url, info["cid"]))

    t3 = time.time()
    tag = "50501_52500"
    print(f"Fase 2 (classify): A={len(class_a_ids):,} B={len(class_b)} C={len(class_c)} em {t3-t2:.1f}s", flush=True)

    # Salvar B
    if class_b:
        csv_b = os.path.join(DIR, f"wo_sql_b_{tag}.csv")
        with open(csv_b, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ws_id", "actual_wine_id", "expected_wine_id", "store_id", "url", "clean_id"])
            w.writerows(class_b)
        print(f"  B={len(class_b)} salvo em {csv_b}", flush=True)

    # Salvar C
    if class_c:
        csv_c = os.path.join(DIR, f"wo_sql_c_{tag}.csv")
        with open(csv_c, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ws_id", "actual_wine_id", "expected_wine_id", "store_id", "url", "clean_id"])
            w.writerows(class_c)
        print(f"  C={len(class_c)} salvo em {csv_c}", flush=True)

    # Fase 3: DELETE RETURNING
    t4 = time.time()
    if class_a_ids:
        r.execute("""
            DELETE FROM wine_sources WHERE id = ANY(%s)
            RETURNING id, wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em
        """, (class_a_ids,))
        deleted_raw = r.fetchall()
        rc.commit()

        revert_rows = []
        for row in deleted_raw:
            exp_info = ws_to_exp.get(row[0], (None, None))
            revert_rows.append((*row, exp_info[0], exp_info[1]))

        csv_rev = os.path.join(DIR, f"wo_sql_rev_{tag}.csv")
        with open(csv_rev, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ws_id", "wine_id", "store_id", "url", "preco", "moeda",
                         "disponivel", "descoberto_em", "atualizado_em", "expected_wine_id", "clean_id"])
            w.writerows(revert_rows)
        print(f"  Revert: {csv_rev} ({len(revert_rows):,} linhas)", flush=True)
    else:
        deleted_raw = []
        revert_rows = []

    t5 = time.time()

    # Cleanup
    r.execute("DROP TABLE tmp_exp")
    rc.commit()

    r.execute("SELECT COUNT(*) FROM wine_sources")
    ws_depois = r.fetchone()[0]

    # Resultado
    print(f"\n{'=' * 80}", flush=True)
    print(f"RESULTADO — GAP 50501-52500 FECHADO", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"  Classe A deletado: {len(deleted_raw):,}", flush=True)
    print(f"  Classe B salvo:    {len(class_b)}", flush=True)
    print(f"  Classe C salvo:    {len(class_c)}", flush=True)
    print(f"  WS antes:          {ws_antes:,}", flush=True)
    print(f"  WS depois:         {ws_depois:,}", flush=True)
    print(f"  Delta:             {ws_antes - ws_depois:,}", flush=True)
    print(f"  Tempo total:       {t5-t0:.1f}s", flush=True)
    print(f"  Gap 50501-52500:   FECHADO", flush=True)

    l.close(); lc.close(); r.close(); rc.close()
    print(f"\nFim.", flush=True)


if __name__ == "__main__":
    main()
