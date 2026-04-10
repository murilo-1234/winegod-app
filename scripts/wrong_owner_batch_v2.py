"""
Wrong_owner cleanup v2 — BATCH OTIMIZADO.
Owners 1001-5000 (blocos 2-9). Bloco 1 (501-1000) ja executado.
Todas queries em batch, zero 1-a-1.
"""
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

DIR = os.path.dirname(__file__)
BLOCK_SIZE = 500
CLEAN_LIMIT = 30
URL_LIMIT = 5
SKIP_ABORT = 0.01

START_OWNER = 50500  # bloco 50001-50500 ja executado
END_OWNER = 305046


def gd(url):
    try:
        n = urlparse(url).netloc
        return n.replace("www.", "") if n else None
    except:
        return None


def triage_batch(owners, l, lc, r, d2s):
    """Triagem 100% batch."""
    # Fase 1: coletar clean_ids de todos owners de uma vez
    vids = [v for v, _ in owners]

    # Batch: y2_results
    all_y2 = defaultdict(list)  # vid -> [clean_id]
    for i in range(0, len(vids), 500):
        chunk = vids[i:i+500]
        l.execute(
            "SELECT vivino_id, clean_id FROM y2_results WHERE status = 'matched' AND vivino_id = ANY(%s)",
            (chunk,),
        )
        for vid, cid in l.fetchall():
            if len(all_y2[vid]) < CLEAN_LIMIT:
                all_y2[vid].append(cid)

    # Batch: wines_clean
    all_cids = []
    for cids in all_y2.values():
        all_cids.extend(cids)

    clean_map = {}  # cid -> (pais, id_orig)
    for i in range(0, len(all_cids), 5000):
        chunk = all_cids[i:i+5000]
        l.execute(
            "SELECT id, pais_tabela, id_original FROM wines_clean WHERE id = ANY(%s) AND id_original IS NOT NULL",
            (chunk,),
        )
        for cid, pais, ido in l.fetchall():
            if pais and re.match(r"^[a-z]{2}$", pais):
                clean_map[cid] = (pais, ido)

    # Batch: fontes por pais
    by_pais = defaultdict(list)  # pais -> [(ido, vid, cid)]
    for vid, cids in all_y2.items():
        for cid in cids:
            if cid in clean_map:
                pais, ido = clean_map[cid]
                by_pais[pais].append((ido, vid, cid))

    expected_map = {}  # url -> {owner, store_id, pais, cid}
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
                        WHERE vinho_id = ANY(%s) AND url_original IS NOT NULL
                        AND url_original LIKE 'http%%'""",
                    (chunk,),
                )
                count_per_ido = defaultdict(int)
                for ido, url in l.fetchall():
                    if count_per_ido[ido] >= URL_LIMIT:
                        continue
                    count_per_ido[ido] += 1
                    dom = gd(url)
                    sid = d2s.get(dom) if dom else None
                    if sid:
                        info = ido_to_info[ido]
                        vid, cid = info[0]
                        expected_map[url] = {"owner": vid, "store_id": sid, "pais": pais, "clean_id": cid}
            except Exception:
                lc.rollback()

    if not expected_map:
        return [], [], []

    # Fase 2: batch lookup no Render — TODAS linhas de wine_sources para essas URLs
    url_lines = defaultdict(list)
    all_urls = list(expected_map.keys())
    for i in range(0, len(all_urls), 500):
        chunk = all_urls[i:i+500]
        r.execute("""
            SELECT id, wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em
            FROM wine_sources WHERE url = ANY(%s)
        """, (chunk,))
        for ws_id, wid, sid, url, preco, moeda, disp, desc, atua in r.fetchall():
            url_lines[url].append({
                "ws_id": ws_id, "wine_id": wid, "store_id": sid,
                "preco": preco, "moeda": moeda, "disponivel": disp,
                "descoberto_em": str(desc), "atualizado_em": str(atua),
            })

    # Fase 3: classificar
    ca, cb, cc = [], [], []
    for url, exp in expected_map.items():
        lines = url_lines.get(url, [])
        if not lines:
            continue
        correct = [ln for ln in lines if ln["wine_id"] == exp["owner"]]
        wrong = [ln for ln in lines if ln["wine_id"] != exp["owner"]]
        if not wrong:
            continue
        base = {"url": url, "expected_wine_id": exp["owner"],
                "store_id": exp["store_id"], "pais": exp["pais"], "clean_id": exp["clean_id"],
                "n_correct": len(correct), "n_wrong": len(wrong)}
        if correct:
            for wl in wrong:
                ca.append({**base, "actual_wine_id": wl["wine_id"], "ws_id": wl["ws_id"],
                           "ws_preco": wl["preco"], "ws_moeda": wl["moeda"],
                           "ws_disponivel": wl["disponivel"],
                           "ws_descoberto_em": wl["descoberto_em"],
                           "ws_atualizado_em": wl["atualizado_em"]})
        elif len(set(ln["wine_id"] for ln in wrong)) == 1:
            for wl in wrong:
                cb.append({**base, "actual_wine_id": wl["wine_id"], "ws_id": wl["ws_id"]})
        else:
            for wl in wrong:
                cc.append({**base, "actual_wine_id": wl["wine_id"], "ws_id": wl["ws_id"]})
    return ca, cb, cc


def validate_and_delete_batch(class_a, r, rc):
    """Validacao + DELETE, tudo em batch."""
    if not class_a:
        return 0, [], 0, []

    ws_ids = [c["ws_id"] for c in class_a]
    ca_by_wsid = {c["ws_id"]: c for c in class_a}

    # Batch check 1+2: carregar todas as linhas por ws_id
    actual = {}
    for i in range(0, len(ws_ids), 2000):
        chunk = ws_ids[i:i+2000]
        r.execute(
            "SELECT id, wine_id, url FROM wine_sources WHERE id = ANY(%s)",
            (chunk,),
        )
        for wsid, wid, url in r.fetchall():
            actual[wsid] = (wid, url)

    # Batch check 3: para cada expected_wine_id + store_id + url, confirmar existencia
    # Construir set de (expected, store, url) a verificar
    checks = set()
    for c in class_a:
        checks.add((c["expected_wine_id"], c["store_id"], c["url"]))

    correct_exists = set()
    checks_list = list(checks)
    # Agrupar por URL para query batch
    urls_to_check = list(set(c[2] for c in checks_list))
    render_links = defaultdict(set)  # url -> set of wine_ids
    for i in range(0, len(urls_to_check), 500):
        chunk = urls_to_check[i:i+500]
        r.execute(
            "SELECT url, wine_id, store_id FROM wine_sources WHERE url = ANY(%s)",
            (chunk,),
        )
        for url, wid, sid in r.fetchall():
            render_links[(url, sid)].add(wid)

    for exp_wid, sid, url in checks_list:
        if exp_wid in render_links.get((url, sid), set()):
            correct_exists.add((exp_wid, sid, url))

    # Validar
    validated = []
    skipped = []
    for c in class_a:
        wsid = c["ws_id"]
        act = c["actual_wine_id"]
        url = c["url"]
        exp = c["expected_wine_id"]
        sid = c["store_id"]

        if wsid not in actual:
            skipped.append({**c, "motivo": "ws_id nao existe"})
            continue
        a_wid, a_url = actual[wsid]
        if a_wid != act or a_url != url:
            skipped.append({**c, "motivo": f"dados divergem: wine={a_wid}"})
            continue
        if (exp, sid, url) not in correct_exists:
            skipped.append({**c, "motivo": "owner correto nao tem link"})
            continue
        validated.append(c)

    # Batch DELETE
    deleted = 0
    errors = 0
    del_ids = [v["ws_id"] for v in validated]
    for i in range(0, len(del_ids), 500):
        chunk = del_ids[i:i+500]
        try:
            r.execute("SAVEPOINT wo_batch")
            r.execute("DELETE FROM wine_sources WHERE id = ANY(%s)", (chunk,))
            deleted += r.rowcount
            r.execute("RELEASE SAVEPOINT wo_batch")
            rc.commit()
        except Exception as ex:
            r.execute("ROLLBACK TO SAVEPOINT wo_batch")
            rc.commit()
            errors += 1

    return deleted, skipped, errors, validated


def main():
    print("=" * 80, flush=True)
    print("WRONG_OWNER BATCH v2 — OTIMIZADO", flush=True)
    print(f"Owners {START_OWNER+1}-{END_OWNER} (blocos de {BLOCK_SIZE})", flush=True)
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

    r.execute("SELECT COUNT(*) FROM wine_sources")
    ws_inicio = r.fetchone()[0]
    print(f"WS inicio: {ws_inicio:,}", flush=True)

    total_deleted = 0
    total_skipped = 0
    total_errors = 0
    total_b = 0
    blocos_ok = 0
    low_yield_streak = 0  # blocos consecutivos com <100 deletes

    for block_start in range(START_OWNER, END_OWNER, BLOCK_SIZE):
        block_end = min(block_start + BLOCK_SIZE, END_OWNER)
        block_owners = all_owners[block_start:block_end]
        if not block_owners:
            break

        tag = f"{block_start+1}_{block_end}"
        print(f"\n--- BLOCO {tag} ({len(block_owners)} owners) ---", flush=True)

        # Triagem batch (com retry de conexao)
        try:
            ca, cb, cc = triage_batch(block_owners, l, lc, r, d2s)
        except Exception as ex:
            print(f"  Conexao perdida: {ex}. Reconectando...", flush=True)
            try:
                lc.close()
            except:
                pass
            try:
                rc.close()
            except:
                pass
            import time
            time.sleep(10)
            lc = psycopg2.connect(**LOCAL_DB)
            rc = psycopg2.connect(
                RENDER_DB, options="-c statement_timeout=300000",
                keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
            )
            l = lc.cursor()
            r = rc.cursor()
            try:
                ca, cb, cc = triage_batch(block_owners, l, lc, r, d2s)
            except Exception as ex2:
                print(f"  *** STOP: reconexao falhou: {ex2} ***", flush=True)
                break
        print(f"  A={len(ca):,} B={len(cb)} C={len(cc)}", flush=True)

        if len(cb) > 50:
            print(f"  *** STOP: B={len(cb)} > 50 ***", flush=True)
            break
        if cc:
            print(f"  *** STOP: C={len(cc)} > 0 ***", flush=True)
            break

        if cb:
            csv_b = os.path.join(DIR, f"wo_move_needed_{tag}.csv")
            with open(csv_b, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["url", "expected_wine_id", "actual_wine_id", "ws_id"], extrasaction="ignore")
                w.writeheader(); w.writerows(cb)
            print(f"  B={len(cb)} salvo (nao executado)", flush=True)
            total_b += len(cb)

        if not ca:
            print(f"  Nada a deletar.", flush=True)
            blocos_ok += 1
            continue

        # Salvar candidatos
        csv_cand = os.path.join(DIR, f"wo_del_candidates_{tag}.csv")
        fields = ["url", "expected_wine_id", "actual_wine_id", "ws_id", "store_id",
                   "pais", "clean_id", "n_correct", "n_wrong",
                   "ws_preco", "ws_moeda", "ws_disponivel", "ws_descoberto_em", "ws_atualizado_em"]
        with open(csv_cand, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader(); w.writerows(ca)

        # Validar + deletar batch
        deleted, skipped, errors, validated = validate_and_delete_batch(ca, r, rc)
        skip_pct = len(skipped) / max(len(ca), 1)
        print(f"  Del={deleted:,} Skip={len(skipped)} ({skip_pct*100:.2f}%) Err={errors}", flush=True)

        if skip_pct > SKIP_ABORT:
            print(f"  *** STOP: skip > 1% ***", flush=True)
            break
        if errors > 0:
            print(f"  *** STOP: erros ***", flush=True)
            break

        total_deleted += deleted
        total_skipped += len(skipped)
        total_errors += errors
        blocos_ok += 1

        # Kill-switch: rendimento baixo
        if deleted < 100:
            low_yield_streak += 1
            if low_yield_streak >= 10:
                print(f"  *** STOP: <100 deletes por {low_yield_streak} blocos consecutivos ***", flush=True)
                break
        else:
            low_yield_streak = 0

        # Salvar executed + revert
        csv_exec = os.path.join(DIR, f"wo_del_executed_{tag}.csv")
        csv_rev = os.path.join(DIR, f"wo_del_revert_{tag}.csv")
        with open(csv_exec, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader(); w.writerows(validated)
        rev_fields = ["ws_id", "actual_wine_id", "store_id", "url",
                       "ws_preco", "ws_moeda", "ws_disponivel", "ws_descoberto_em", "ws_atualizado_em"]
        with open(csv_rev, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rev_fields, extrasaction="ignore")
            w.writeheader(); w.writerows(validated)
        if skipped:
            csv_skip = os.path.join(DIR, f"wo_del_skipped_{tag}.csv")
            with open(csv_skip, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(skipped[0].keys()), extrasaction="ignore")
                w.writeheader(); w.writerows(skipped)

        # 10 exemplos
        sample_ids = [v["ws_id"] for v in validated[:10]]
        if sample_ids:
            r.execute("SELECT id FROM wine_sources WHERE id = ANY(%s)", (sample_ids,))
            still = set(row[0] for row in r.fetchall())
            for j, v in enumerate(validated[:10], 1):
                gone = v["ws_id"] not in still
                print(f"    [{j}] ws={v['ws_id']} del={'Y' if gone else 'N'} OK", flush=True)

    # Resumo
    r.execute("SELECT COUNT(*) FROM wine_sources")
    ws_fim = r.fetchone()[0]

    print(f"\n{'=' * 80}", flush=True)
    print(f"RESUMO ACUMULADO (blocos 2-9)", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"  Blocos OK:      {blocos_ok}", flush=True)
    print(f"  Total deletado: {total_deleted:,}", flush=True)
    print(f"  Total pulado:   {total_skipped:,}", flush=True)
    print(f"  Total B salvo:  {total_b}", flush=True)
    print(f"  Total erros:    {total_errors}", flush=True)
    print(f"  WS inicio:      {ws_inicio:,}", flush=True)
    print(f"  WS fim:         {ws_fim:,}", flush=True)
    print(f"  Delta:          {ws_inicio - ws_fim:,}", flush=True)

    l.close(); lc.close(); r.close(); rc.close()
    print(f"\nFim.", flush=True)


if __name__ == "__main__":
    main()
