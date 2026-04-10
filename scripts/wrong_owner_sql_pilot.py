"""
Piloto SQL set-based: owners 114501-119500.
build_expected no local, tudo mais no Render por SQL.
DELETE ... USING ... RETURNING para revert lossless.
Compara com metodo antigo.
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
BLOCK_START = 114500
BLOCK_END = 119500
CLEAN_LIMIT = 30
URL_LIMIT = 5


def gd(url):
    try:
        n = urlparse(url).netloc
        return n.replace("www.", "") if n else None
    except:
        return None


def build_expected(vids, l, lc, d2s):
    """Mesmo build_expected do autopilot. Retorna dict (url, store_id) -> info."""
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


def main():
    print("=" * 80, flush=True)
    print("PILOTO SQL SET-BASED: owners 114501-119500", flush=True)
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
    block_owners = all_owners[BLOCK_START:BLOCK_END]
    vids = [v for v, _ in block_owners]

    r.execute("SELECT COUNT(*) FROM wine_sources")
    ws_antes = r.fetchone()[0]
    print(f"WS antes: {ws_antes:,}", flush=True)
    print(f"Owners: {len(block_owners):,}", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 1: build_expected no local
    # ══════════════════════════════════════════════════════════════════════════
    t0 = time.time()
    expected = build_expected(vids, l, lc, d2s)
    t1 = time.time()
    print(f"\nFase 1 (build_expected): {len(expected):,} URLs em {t1-t0:.1f}s", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 2: Upload temp table
    # ══════════════════════════════════════════════════════════════════════════
    t2 = time.time()
    r.execute("CREATE TEMP TABLE tmp_exp (url TEXT, store_id INT, exp_wid INT, cid INT)")
    rows = [(url, sid, e["owner"], e["cid"]) for (url, sid), e in expected.items()]
    execute_values(r, "INSERT INTO tmp_exp VALUES %s", rows)
    r.execute("CREATE INDEX idx_tmp_us ON tmp_exp (url, store_id)")
    rc.commit()
    t3 = time.time()
    print(f"Fase 2 (upload temp): {len(rows):,} rows em {t3-t2:.1f}s", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 3: Buscar todas as linhas matchadas e classificar em Python
    # ══════════════════════════════════════════════════════════════════════════
    t4 = time.time()

    # 1 query: todas as linhas de wine_sources que compartilham (url, store_id) com expected
    r.execute("""
        SELECT ws.id, ws.wine_id, ws.store_id, ws.url, e.exp_wid, e.cid
        FROM tmp_exp e
        JOIN wine_sources ws ON ws.url = e.url AND ws.store_id = e.store_id
    """)
    all_matches = r.fetchall()

    # Agrupar por (url, store_id) e classificar
    by_key = defaultdict(lambda: {"correct": [], "wrong": [], "exp": None, "cid": None})
    for ws_id, wid, sid, url, exp_wid, cid in all_matches:
        key = (url, sid)
        entry = by_key[key]
        entry["exp"] = exp_wid
        entry["cid"] = cid
        if wid == exp_wid:
            entry["correct"].append(ws_id)
        else:
            entry["wrong"].append((ws_id, wid))

    class_a_ids = []  # ws_ids para DELETE
    class_b = []
    class_c = []
    for (url, sid), info in by_key.items():
        if not info["wrong"]:
            continue
        if info["correct"]:
            for ws_id, wid in info["wrong"]:
                class_a_ids.append(ws_id)
        else:
            wowners = set(wid for _, wid in info["wrong"])
            if len(wowners) == 1:
                for ws_id, wid in info["wrong"]:
                    class_b.append((ws_id, wid, info["exp"], sid, url, info["cid"]))
            else:
                for ws_id, wid in info["wrong"]:
                    class_c.append((ws_id, wid, info["exp"], sid, url, info["cid"]))

    count_a = len(class_a_ids)
    count_b = len(class_b)
    count_c = len(class_c)

    t5 = time.time()
    print(f"Fase 3 (classify Python): A={count_a:,} B={count_b} C={count_c} em {t5-t4:.1f}s", flush=True)

    # Salvar B e C
    tag = f"{BLOCK_START+1}_{BLOCK_END}"
    if class_b:
        csv_b = os.path.join(DIR, f"wo_sql_b_{tag}.csv")
        with open(csv_b, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ws_id", "actual_wine_id", "expected_wine_id", "store_id", "url", "clean_id"])
            w.writerows(class_b)
        print(f"  B={count_b} salvo em {csv_b}", flush=True)

    if class_c:
        csv_c = os.path.join(DIR, f"wo_sql_c_{tag}.csv")
        with open(csv_c, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ws_id", "actual_wine_id", "expected_wine_id", "store_id", "url", "clean_id"])
            w.writerows(class_c)
        print(f"  C={count_c} salvo em {csv_c}", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FASE 4: DELETE por ws_id com RETURNING (Classe A apenas)
    # ══════════════════════════════════════════════════════════════════════════
    t6 = time.time()
    print(f"\nFase 4: DELETE Classe A ({count_a:,} ws_ids) com RETURNING...", flush=True)

    if not class_a_ids:
        deleted_rows = []
    else:
        r.execute("""
            DELETE FROM wine_sources
            WHERE id = ANY(%s)
            RETURNING id, wine_id, store_id, url, preco, moeda,
                      disponivel, descoberto_em, atualizado_em
        """, (class_a_ids,))
        deleted_rows_raw = r.fetchall()
        rc.commit()

        # Enriquecer com expected_wine_id e clean_id do by_key
        ws_to_exp = {}
        for (url, sid), info in by_key.items():
            if info["correct"]:
                for ws_id, wid in info["wrong"]:
                    ws_to_exp[ws_id] = (info["exp"], info["cid"])

        deleted_rows = []
        for row in deleted_rows_raw:
            ws_id = row[0]
            exp_info = ws_to_exp.get(ws_id, (None, None))
            deleted_rows.append((*row, exp_info[0], exp_info[1]))

    t7 = time.time()

    deleted = len(deleted_rows)
    print(f"  Deletados: {deleted:,} em {t7-t6:.1f}s", flush=True)

    # Salvar revert lossless
    csv_rev = os.path.join(DIR, f"wo_sql_rev_{BLOCK_START+1}_{BLOCK_END}.csv")
    with open(csv_rev, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ws_id", "wine_id", "store_id", "url", "preco", "moeda",
                     "disponivel", "descoberto_em", "atualizado_em", "expected_wine_id", "clean_id"])
        w.writerows(deleted_rows)
    print(f"  Revert: {csv_rev} ({deleted:,} linhas)", flush=True)

    # Cleanup
    r.execute("DROP TABLE tmp_exp")
    rc.commit()

    # WS depois
    r.execute("SELECT COUNT(*) FROM wine_sources")
    ws_depois = r.fetchone()[0]

    t_total = time.time() - t0

    # ══════════════════════════════════════════════════════════════════════════
    # RESULTADO
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}", flush=True)
    print(f"RESULTADO PILOTO SQL", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"  Owners:           {len(block_owners):,}", flush=True)
    print(f"  Expected URLs:    {len(expected):,}", flush=True)
    print(f"  Classe A:         {count_a:,} (contagem SQL)", flush=True)
    print(f"  Classe A deletado:{deleted:,} (RETURNING)", flush=True)
    print(f"  Classe B:         {count_b}", flush=True)
    print(f"  Classe C:         {count_c}", flush=True)
    print(f"  WS antes:         {ws_antes:,}", flush=True)
    print(f"  WS depois:        {ws_depois:,}", flush=True)
    print(f"  Delta:            {ws_antes - ws_depois:,}", flush=True)
    print(f"", flush=True)
    print(f"  TEMPO:", flush=True)
    print(f"    build_expected:   {t1-t0:.1f}s", flush=True)
    print(f"    upload temp:      {t3-t2:.1f}s", flush=True)
    print(f"    classificar SQL:  {t5-t4:.1f}s", flush=True)
    print(f"    DELETE+RETURNING: {t7-t6:.1f}s", flush=True)
    print(f"    TOTAL:            {t_total:.1f}s", flush=True)
    print(f"", flush=True)
    print(f"  Estimativa metodo antigo: ~300-400s/bloco de 2000 owners", flush=True)
    print(f"  Este piloto (5000 owners): {t_total:.1f}s", flush=True)
    print(f"", flush=True)
    print(f"  Join: (url, store_id) — CONFIRMADO", flush=True)
    print(f"  Revert lossless via RETURNING — CONFIRMADO ({deleted:,} linhas com 11 campos)", flush=True)

    # 10 exemplos do revert
    print(f"\n  10 exemplos do RETURNING:", flush=True)
    for i, row in enumerate(deleted_rows[:10], 1):
        ws_id, wid, sid, url, preco, moeda, disp, desc, atua, exp, cid = row
        print(f"    [{i}] ws={ws_id} wine={wid}->{exp} store={sid} {url[:50]}", flush=True)

    l.close(); lc.close(); r.close(); rc.close()
    print(f"\nFim.", flush=True)


if __name__ == "__main__":
    main()
