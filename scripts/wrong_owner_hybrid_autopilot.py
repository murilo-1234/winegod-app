"""
Wrong_owner hybrid autopilot: owners 52501-305046.
Blocos de 2000 owners. Expected do local, classificacao por SQL join no Render.
Executa apenas Classe A. Salva B em CSV. Kill-switches obrigatorios.
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
START = 104500  # ja fez ate 104500
END = 305046
BLOCK = 2000
CLEAN_LIMIT = 30
URL_LIMIT = 5
SKIP_ABORT = 0.01
LOW_YIELD_LIMIT = 10  # blocos consecutivos com <100 deletes


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
        RENDER_DB, options="-c statement_timeout=300000",
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )


def build_expected(vids, l, lc, d2s):
    """Reconstruir expected URLs no local. Retorna dict url -> {owner, store_id, pais, cid}."""
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

    expected = {}  # chave = (url, store_id)
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


def classify_hybrid(expected, r, rc):
    """Upload expected para temp table, classificar por SQL join em (url, store_id)."""
    r.execute("CREATE TEMP TABLE tmp_exp (url TEXT, store_id INT, exp_wid INT, cid INT)")
    rows = [(url, e["store_id"], e["owner"], e["cid"]) for (url, sid), e in expected.items()]
    if not rows:
        r.execute("DROP TABLE tmp_exp")
        return [], [], []
    execute_values(r, "INSERT INTO tmp_exp VALUES %s", rows)
    r.execute("CREATE INDEX idx_tmp_url_sid ON tmp_exp (url, store_id)")
    rc.commit()

    # JOIN por (url, store_id) — nao so url
    r.execute("""
        SELECT ws.id, ws.wine_id, ws.store_id, ws.url, ws.preco, ws.moeda,
               ws.disponivel, ws.descoberto_em, ws.atualizado_em,
               e.exp_wid, e.cid
        FROM tmp_exp e
        JOIN wine_sources ws ON ws.url = e.url AND ws.store_id = e.store_id
    """)
    all_matches = r.fetchall()

    # Agrupar por (url, store_id)
    by_key = defaultdict(lambda: {"correct": [], "wrong": [], "exp": None, "sid": None, "cid": None})
    for ws_id, wid, sid, url, preco, moeda, disp, desc, atua, exp_wid, cid in all_matches:
        key = (url, sid)
        entry = by_key[key]
        entry["exp"] = exp_wid
        entry["sid"] = sid
        entry["cid"] = cid
        if wid == exp_wid:
            entry["correct"].append(ws_id)
        else:
            entry["wrong"].append({
                "ws_id": ws_id, "wid": wid,
                "preco": preco, "moeda": moeda, "disp": disp,
                "desc": str(desc), "atua": str(atua),
            })

    ca, cb, cc = [], [], []
    for (url, sid), info in by_key.items():
        if not info["wrong"]:
            continue
        base = {"expected": info["exp"], "store_id": sid, "url": url, "cid": info["cid"]}
        if info["correct"]:
            for wl in info["wrong"]:
                ca.append({**base, "ws_id": wl["ws_id"], "actual": wl["wid"],
                           "ws_preco": wl["preco"], "ws_moeda": wl["moeda"],
                           "ws_disponivel": wl["disp"],
                           "ws_descoberto_em": wl["desc"], "ws_atualizado_em": wl["atua"]})
        else:
            wowners = set(wl["wid"] for wl in info["wrong"])
            bucket = cb if len(wowners) == 1 else cc
            for wl in info["wrong"]:
                bucket.append({**base, "ws_id": wl["ws_id"], "actual": wl["wid"],
                               "ws_preco": wl["preco"], "ws_moeda": wl["moeda"],
                               "ws_disponivel": wl["disp"],
                               "ws_descoberto_em": wl["desc"], "ws_atualizado_em": wl["atua"]})

    r.execute("DROP TABLE tmp_exp")
    rc.commit()
    return ca, cb, cc


def validate_and_delete(ca, r, rc):
    """Batch validate + delete. Retorna (deleted, skipped, errors, validated)."""
    if not ca:
        return 0, [], 0, []

    ws_ids = [c["ws_id"] for c in ca]

    # Batch check: ws_id still exists with correct data (incluindo store_id)
    actual = {}
    for i in range(0, len(ws_ids), 2000):
        chunk = ws_ids[i:i+2000]
        r.execute("SELECT id, wine_id, store_id, url FROM wine_sources WHERE id = ANY(%s)", (chunk,))
        for wsid, wid, sid, url in r.fetchall():
            actual[wsid] = (wid, sid, url)

    # Batch check: expected owner has the link (por url + store_id)
    keys_check = list(set((c["url"], c["store_id"]) for c in ca))
    render_links = defaultdict(set)
    urls_batch = list(set(k[0] for k in keys_check))
    for i in range(0, len(urls_batch), 500):
        chunk = urls_batch[i:i+500]
        r.execute("SELECT url, wine_id, store_id FROM wine_sources WHERE url = ANY(%s)", (chunk,))
        for url, wid, sid in r.fetchall():
            render_links[(url, sid)].add(wid)

    correct_exists = set()
    for c in ca:
        if c["expected"] in render_links.get((c["url"], c["store_id"]), set()):
            correct_exists.add(c["ws_id"])

    validated = []
    skipped = []
    for c in ca:
        wsid = c["ws_id"]
        if wsid not in actual:
            skipped.append({**c, "motivo": "ws_id gone"})
            continue
        a_wid, a_sid, a_url = actual[wsid]
        if a_wid != c["actual"] or a_url != c["url"] or a_sid != c["store_id"]:
            skipped.append({**c, "motivo": f"data mismatch: wine={a_wid} store={a_sid}"})
            continue
        if wsid not in correct_exists:
            skipped.append({**c, "motivo": "correct owner missing"})
            continue
        validated.append(c)

    deleted = 0
    errors = 0
    del_ids = [v["ws_id"] for v in validated]
    for i in range(0, len(del_ids), 500):
        chunk = del_ids[i:i+500]
        try:
            r.execute("SAVEPOINT wo")
            r.execute("DELETE FROM wine_sources WHERE id = ANY(%s)", (chunk,))
            deleted += r.rowcount
            r.execute("RELEASE SAVEPOINT wo")
            rc.commit()
        except Exception:
            r.execute("ROLLBACK TO SAVEPOINT wo")
            rc.commit()
            errors += 1

    return deleted, skipped, errors, validated


def main():
    print("=" * 80, flush=True)
    print(f"WRONG_OWNER HYBRID AUTOPILOT: owners {START+1}-{END}", flush=True)
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
    total_skip = 0
    total_err = 0
    total_b = 0
    blocos_ok = 0
    low_streak = 0

    for bs in range(START, END, BLOCK):
        be = min(bs + BLOCK, END)
        owners = all_owners[bs:be]
        if not owners:
            break

        tag = f"{bs+1}_{be}"
        vids = [v for v, _ in owners]

        # Reconnect if needed
        try:
            l.execute("SELECT 1")
        except Exception:
            lc = connect_local()
            l = lc.cursor()
        try:
            r.execute("SELECT 1")
        except Exception:
            rc = connect_render()
            r = rc.cursor()

        t0 = time.time()

        try:
            expected = build_expected(vids, l, lc, d2s)
        except Exception as ex:
            print(f"\n--- BLOCO {tag}: ERRO local: {ex}. Reconectando... ---", flush=True)
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
                print(f"  *** STOP: {low_streak} blocos vazios consecutivos ***", flush=True)
                break
            blocos_ok += 1
            continue

        try:
            ca, cb, cc = classify_hybrid(expected, r, rc)
        except Exception as ex:
            print(f"\n--- BLOCO {tag}: ERRO Render: {ex}. Reconectando... ---", flush=True)
            time.sleep(10)
            rc = connect_render(); r = rc.cursor()
            try:
                ca, cb, cc = classify_hybrid(expected, r, rc)
            except Exception as ex2:
                print(f"  *** STOP: {ex2} ***", flush=True)
                break

        print(f"\n--- BLOCO {tag} A={len(ca):,} B={len(cb)} C={len(cc)} exp={len(expected):,} ---", flush=True)

        if len(cc) > 10:
            print(f"  *** STOP: C={len(cc)} > 10 ***", flush=True)
            break

        if cc:
            csv_c = os.path.join(DIR, f"wo_hybrid_c_{tag}.csv")
            with open(csv_c, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["ws_id", "actual", "expected", "store_id", "url", "cid"], extrasaction="ignore")
                w.writeheader(); w.writerows(cc)
            print(f"  C={len(cc)} salvo (nao executado)", flush=True)

        if cb:
            csv_b = os.path.join(DIR, f"wo_hybrid_b_{tag}.csv")
            with open(csv_b, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["ws_id", "actual", "expected", "store_id", "url", "cid"], extrasaction="ignore")
                w.writeheader(); w.writerows(cb)
            total_b += len(cb)

        if not ca:
            low_streak += 1
            if low_streak >= LOW_YIELD_LIMIT:
                print(f"  *** STOP: {low_streak} blocos com <100 deletes ***", flush=True)
                break
            blocos_ok += 1
            continue

        try:
            deleted, skipped, errors, validated = validate_and_delete(ca, r, rc)
        except Exception as ex:
            print(f"  ERRO validate_and_delete: {ex}. Reconectando...", flush=True)
            time.sleep(10)
            rc = connect_render(); r = rc.cursor()
            try:
                deleted, skipped, errors, validated = validate_and_delete(ca, r, rc)
            except Exception as ex2:
                print(f"  *** STOP: {ex2} ***", flush=True)
                break
        skip_pct = len(skipped) / max(len(ca), 1)
        t1 = time.time()
        print(f"  Del={deleted:,} Skip={len(skipped)} Err={errors} ({t1-t0:.0f}s)", flush=True)

        if errors > 0:
            print(f"  *** STOP: errors ***", flush=True)
            break
        if skip_pct > SKIP_ABORT:
            print(f"  *** STOP: skip {skip_pct*100:.1f}% ***", flush=True)
            break

        total_del += deleted
        total_skip += len(skipped)
        total_err += errors
        blocos_ok += 1

        if deleted < 100:
            low_streak += 1
            if low_streak >= LOW_YIELD_LIMIT:
                print(f"  *** STOP: {low_streak} blocos com <100 deletes ***", flush=True)
                break
        else:
            low_streak = 0

        # Salvar revert lossless
        csv_rev = os.path.join(DIR, f"wo_hybrid_rev_{tag}.csv")
        rev_fields = ["ws_id", "actual", "store_id", "url",
                       "ws_preco", "ws_moeda", "ws_disponivel",
                       "ws_descoberto_em", "ws_atualizado_em", "expected"]
        with open(csv_rev, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rev_fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(validated)

    # Resumo
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
    print(f"  Total pulado:   {total_skip:,}", flush=True)
    print(f"  Total B salvo:  {total_b:,}", flush=True)
    print(f"  Total erros:    {total_err}", flush=True)
    print(f"  WS inicio:      {ws_inicio:,}", flush=True)
    print(f"  WS fim:         {ws_fim:,}", flush=True)
    print(f"  Delta:          {ws_inicio - ws_fim:,}", flush=True)
    print(f"  Low yield stop: {'SIM' if low_streak >= LOW_YIELD_LIMIT else 'NAO'}", flush=True)

    l.close(); lc.close(); r.close(); rc.close()
    print(f"\nFim.", flush=True)


if __name__ == "__main__":
    main()
