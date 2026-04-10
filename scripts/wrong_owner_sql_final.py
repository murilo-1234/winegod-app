"""
Wrong_owner SQL autopilot final: owners 119501-305046.
build_expected local, classify Python, DELETE RETURNING no Render.
Blocos de 5000 owners.
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
START = 119500
END = 305046
BLOCK = 5000
CLEAN_LIMIT = 30
URL_LIMIT = 5
LOW_YIELD_LIMIT = 5  # blocos com <100 deletes


def gd(url):
    try:
        n = urlparse(url).netloc
        return n.replace("www.", "") if n else None
    except:
        return None


def connect_local():
    return psycopg2.connect(**LOCAL_DB)


def connect_render():
    return psycopg2.connect(
        RENDER_DB, options="-c statement_timeout=600000",
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )


def build_expected(vids, l, lc, d2s):
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
    return expected


def process_block(expected, r, rc, tag):
    """Upload, classify, delete, return (deleted, count_a, count_b, count_c, revert_rows)."""
    r.execute("CREATE TEMP TABLE tmp_exp (url TEXT, store_id INT, exp_wid INT, cid INT)")
    rows = [(url, sid, e["owner"], e["cid"]) for (url, sid), e in expected.items()]
    if not rows:
        r.execute("DROP TABLE tmp_exp")
        return 0, 0, 0, 0, []
    execute_values(r, "INSERT INTO tmp_exp VALUES %s", rows)
    r.execute("CREATE INDEX idx_tmp_us ON tmp_exp (url, store_id)")
    rc.commit()

    # Fetch all matches
    r.execute("""
        SELECT ws.id, ws.wine_id, ws.store_id, ws.url, e.exp_wid, e.cid
        FROM tmp_exp e JOIN wine_sources ws ON ws.url = e.url AND ws.store_id = e.store_id
    """)
    all_matches = r.fetchall()

    # Classify in Python
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

    # Save B
    if class_b:
        csv_b = os.path.join(DIR, f"wo_sql_b_{tag}.csv")
        with open(csv_b, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ws_id", "actual_wine_id", "expected_wine_id", "store_id", "url", "clean_id"])
            w.writerows(class_b)

    # Save C
    if class_c:
        csv_c = os.path.join(DIR, f"wo_sql_c_{tag}.csv")
        with open(csv_c, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ws_id", "actual_wine_id", "expected_wine_id", "store_id", "url", "clean_id"])
            w.writerows(class_c)

    # DELETE with RETURNING
    revert_rows = []
    deleted = 0
    if class_a_ids:
        r.execute("""
            DELETE FROM wine_sources WHERE id = ANY(%s)
            RETURNING id, wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em
        """, (class_a_ids,))
        raw = r.fetchall()
        rc.commit()
        deleted = len(raw)
        for row in raw:
            exp_info = ws_to_exp.get(row[0], (None, None))
            revert_rows.append((*row, exp_info[0], exp_info[1]))

    # Save revert
    if revert_rows:
        csv_rev = os.path.join(DIR, f"wo_sql_rev_{tag}.csv")
        with open(csv_rev, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ws_id", "wine_id", "store_id", "url", "preco", "moeda",
                         "disponivel", "descoberto_em", "atualizado_em", "expected_wine_id", "clean_id"])
            w.writerows(revert_rows)

    r.execute("DROP TABLE tmp_exp")
    rc.commit()

    return deleted, len(class_a_ids), len(class_b), len(class_c), revert_rows


def main():
    print("=" * 80, flush=True)
    print(f"WRONG_OWNER SQL AUTOPILOT: owners {START+1}-{END}", flush=True)
    print("=" * 80, flush=True)

    lc = connect_local()
    rc = connect_render()
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

    r.execute("SELECT COUNT(*) FROM wine_sources")
    ws_inicio = r.fetchone()[0]
    print(f"WS inicio: {ws_inicio:,}", flush=True)

    total_del = 0
    total_b = 0
    total_c = 0
    blocos_ok = 0
    low_streak = 0

    for bs in range(START, END, BLOCK):
        be = min(bs + BLOCK, END)
        owners = all_owners[bs:be]
        if not owners:
            break

        tag = f"{bs+1}_{be}"
        vids = [v for v, _ in owners]
        t0 = time.time()

        # Reconnect check
        try:
            l.execute("SELECT 1")
        except Exception:
            lc = connect_local(); l = lc.cursor()
        try:
            r.execute("SELECT 1")
        except Exception:
            rc = connect_render(); r = rc.cursor()

        # Build expected
        try:
            expected = build_expected(vids, l, lc, d2s)
        except Exception as ex:
            print(f"\n--- BLOCO {tag}: ERRO local: {ex}. Reconectando ---", flush=True)
            time.sleep(10)
            lc = connect_local(); l = lc.cursor()
            try:
                expected = build_expected(vids, l, lc, d2s)
            except Exception as ex2:
                print(f"  *** STOP: {ex2} ***", flush=True)
                break

        if not expected:
            print(f"\n--- BLOCO {tag}: 0 expected ---", flush=True)
            low_streak += 1
            if low_streak >= LOW_YIELD_LIMIT:
                print(f"  *** STOP: {low_streak} blocos vazios ***", flush=True)
                break
            blocos_ok += 1
            continue

        # Process
        try:
            deleted, ca, cb, cc, revert = process_block(expected, r, rc, tag)
        except Exception as ex:
            print(f"\n--- BLOCO {tag}: ERRO Render: {ex}. Reconectando ---", flush=True)
            time.sleep(10)
            rc = connect_render(); r = rc.cursor()
            try:
                deleted, ca, cb, cc, revert = process_block(expected, r, rc, tag)
            except Exception as ex2:
                print(f"  *** STOP: {ex2} ***", flush=True)
                break

        t1 = time.time()
        print(f"\n--- BLOCO {tag} A={ca:,}(del={deleted:,}) B={cb} C={cc} ({t1-t0:.0f}s) ---", flush=True)

        # Kill-switches
        if cc > 10:
            print(f"  *** STOP: C={cc} > 10 ***", flush=True)
            break
        if ca > 0 and abs(deleted - ca) > max(ca * 0.01, 20):
            print(f"  *** STOP: divergencia A={ca} vs del={deleted} ***", flush=True)
            break

        total_del += deleted
        total_b += cb
        total_c += cc
        blocos_ok += 1

        if deleted < 100:
            low_streak += 1
            if low_streak >= LOW_YIELD_LIMIT:
                print(f"  *** STOP: {low_streak} blocos com <100 del ***", flush=True)
                break
        else:
            low_streak = 0

    # Final
    try:
        r.execute("SELECT COUNT(*) FROM wine_sources")
        ws_fim = r.fetchone()[0]
    except Exception:
        ws_fim = ws_inicio - total_del

    print(f"\n{'=' * 80}", flush=True)
    print(f"RESUMO FINAL", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"  Blocos OK:      {blocos_ok}", flush=True)
    print(f"  Total deletado: {total_del:,}", flush=True)
    print(f"  Total B salvo:  {total_b:,}", flush=True)
    print(f"  Total C salvo:  {total_c}", flush=True)
    print(f"  WS inicio:      {ws_inicio:,}", flush=True)
    print(f"  WS fim:         {ws_fim:,}", flush=True)
    print(f"  Delta:          {ws_inicio - ws_fim:,}", flush=True)
    print(f"  Low yield stop: {'SIM' if low_streak >= LOW_YIELD_LIMIT else 'NAO'}", flush=True)

    l.close(); lc.close(); r.close(); rc.close()
    print(f"\nFim.", flush=True)


if __name__ == "__main__":
    main()
