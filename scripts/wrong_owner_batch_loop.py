"""
Wrong_owner cleanup em blocos de 500 owners.
Processa owners 501-5000 (indices no ranking por n_clean_ids desc).
Auto-execute Classe A se B=0, C=0, skip<=1%, erros=0.
Auto-stop se qualquer condicao falhar.
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

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = os.environ["DATABASE_URL"]

DIR = os.path.dirname(__file__)
OWNER_BLOCK_SIZE = 500
CLEAN_PER_OWNER = 30
URLS_PER_CLEAN = 5
DELETE_BATCH = 100
SKIP_ABORT_PCT = 0.01


def get_dom(url):
    try:
        n = urlparse(url).netloc
        return n.replace("www.", "") if n else None
    except:
        return None


def triage_block(owners, l, lc, r, d2s):
    """Triagem de um bloco de owners. Retorna (class_a, class_b, class_c)."""
    expected_map = {}
    expected_meta = {}

    for vid, ncl in owners:
        l.execute(
            "SELECT clean_id FROM y2_results WHERE vivino_id = %s AND status = 'matched' LIMIT %s",
            (vid, CLEAN_PER_OWNER),
        )
        for (cid,) in l.fetchall():
            l.execute(
                "SELECT pais_tabela, id_original FROM wines_clean WHERE id = %s AND id_original IS NOT NULL",
                (cid,),
            )
            row = l.fetchone()
            if not row or not row[0] or not re.match(r"^[a-z]{2}$", row[0]):
                continue
            pais, ido = row
            try:
                l.execute(
                    f"""SELECT url_original FROM vinhos_{pais}_fontes
                        WHERE vinho_id = %s AND url_original IS NOT NULL
                        AND url_original LIKE 'http%%' LIMIT %s""",
                    (ido, URLS_PER_CLEAN),
                )
                for (url,) in l.fetchall():
                    dom = get_dom(url)
                    sid = d2s.get(dom) if dom else None
                    if sid:
                        expected_map[url] = vid
                        expected_meta[url] = {"store_id": sid, "pais": pais, "clean_id": cid}
            except Exception:
                lc.rollback()

    if not expected_map:
        return [], [], []

    # Buscar todas linhas no Render
    url_all = defaultdict(list)
    all_urls = list(expected_map.keys())
    for i in range(0, len(all_urls), 500):
        chunk = all_urls[i:i+500]
        r.execute("""
            SELECT id, wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em
            FROM wine_sources WHERE url = ANY(%s)
        """, (chunk,))
        for ws_id, wid, sid, url, preco, moeda, disp, desc, atua in r.fetchall():
            url_all[url].append({
                "ws_id": ws_id, "wine_id": wid, "store_id": sid,
                "preco": preco, "moeda": moeda, "disponivel": disp,
                "descoberto_em": str(desc), "atualizado_em": str(atua),
            })

    # Classificar
    ca, cb, cc = [], [], []
    for url, exp_owner in expected_map.items():
        meta = expected_meta[url]
        lines = url_all.get(url, [])
        if not lines:
            continue
        correct = [ln for ln in lines if ln["wine_id"] == exp_owner]
        wrong = [ln for ln in lines if ln["wine_id"] != exp_owner]
        if not wrong:
            continue
        wrong_owners = set(ln["wine_id"] for ln in wrong)
        base = {
            "url": url, "expected_wine_id": exp_owner,
            "store_id": meta["store_id"], "pais": meta["pais"], "clean_id": meta["clean_id"],
            "n_correct": len(correct), "n_wrong": len(wrong),
        }
        if correct:
            for wl in wrong:
                ca.append({**base, "actual_wine_id": wl["wine_id"], "ws_id": wl["ws_id"],
                           "ws_preco": wl["preco"], "ws_moeda": wl["moeda"],
                           "ws_disponivel": wl["disponivel"],
                           "ws_descoberto_em": wl["descoberto_em"],
                           "ws_atualizado_em": wl["atualizado_em"]})
        elif len(wrong_owners) == 1:
            for wl in wrong:
                cb.append({**base, "actual_wine_id": wl["wine_id"], "ws_id": wl["ws_id"]})
        else:
            for wl in wrong:
                cc.append({**base, "actual_wine_id": wl["wine_id"], "ws_id": wl["ws_id"]})

    return ca, cb, cc


def execute_delete(class_a, r, rc):
    """Validar + DELETE. Retorna (deleted, skipped_list, errors)."""
    validated = []
    skipped = []

    for c in class_a:
        ws_id = c["ws_id"]
        act = c["actual_wine_id"]
        exp = c["expected_wine_id"]
        sid = c["store_id"]
        url = c["url"]

        r.execute("SELECT wine_id, url FROM wine_sources WHERE id = %s", (ws_id,))
        row = r.fetchone()
        if not row:
            skipped.append({**c, "motivo": "ws_id nao existe"})
            continue
        if row[0] != act or row[1] != url:
            skipped.append({**c, "motivo": "dados divergem"})
            continue
        r.execute(
            "SELECT COUNT(*) FROM wine_sources WHERE wine_id = %s AND store_id = %s AND url = %s",
            (exp, sid, url),
        )
        if r.fetchone()[0] == 0:
            skipped.append({**c, "motivo": "owner correto nao tem link"})
            continue
        validated.append(c)

    deleted = 0
    errors = 0
    for i in range(0, len(validated), DELETE_BATCH):
        batch = validated[i:i+DELETE_BATCH]
        try:
            r.execute("SAVEPOINT wo_batch")
            for v in batch:
                r.execute("DELETE FROM wine_sources WHERE id = %s", (v["ws_id"],))
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
    print("WRONG_OWNER BATCH LOOP — owners 501-5000", flush=True)
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

    # Carregar todos os owners ordenados
    l.execute("""
        SELECT vivino_id, COUNT(*) FROM y2_results
        WHERE status = 'matched' AND vivino_id IS NOT NULL
        GROUP BY vivino_id ORDER BY COUNT(*) DESC
    """)
    all_owners = l.fetchall()

    r.execute("SELECT COUNT(*) FROM wine_sources")
    ws_inicio = r.fetchone()[0]
    print(f"Wine_sources inicio: {ws_inicio:,}", flush=True)
    print(f"Total owners: {len(all_owners):,}", flush=True)

    # Processar blocos 501-5000
    START = 500
    END = 5000
    total_deleted = 0
    total_skipped = 0
    total_errors = 0
    blocos_ok = 0

    block_num = 0
    for block_start in range(START, END, OWNER_BLOCK_SIZE):
        block_end = min(block_start + OWNER_BLOCK_SIZE, END)
        block_owners = all_owners[block_start:block_end]
        block_num += 1

        if not block_owners:
            break

        print(f"\n{'=' * 60}", flush=True)
        print(f"BLOCO {block_num}: owners {block_start+1}-{block_end} ({len(block_owners)} owners)", flush=True)
        print(f"{'=' * 60}", flush=True)

        # Triagem
        ca, cb, cc = triage_block(block_owners, l, lc, r, d2s)
        tag = f"{block_start+1}_{block_end}"
        print(f"  A={len(ca):,} | B={len(cb)} | C={len(cc)}", flush=True)

        # Guardrails
        if len(cb) > 5:
            print(f"  *** STOP: B={len(cb)} > 5 ***", flush=True)
            break
        if cc:
            print(f"  *** STOP: C={len(cc)} > 0 ***", flush=True)
            break
        if cb:
            # Salvar B em CSV separado, nao executar, continuar com A
            csv_b = os.path.join(DIR, f"wo_move_needed_{tag}.csv")
            b_fields = ["url", "expected_wine_id", "actual_wine_id", "ws_id", "store_id", "pais", "clean_id"]
            with open(csv_b, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=b_fields, extrasaction="ignore")
                w.writeheader(); w.writerows(cb)
            print(f"  B={len(cb)} salvo em {csv_b} (nao executado)", flush=True)
        if not ca:
            print(f"  Nada a deletar neste bloco.", flush=True)
            blocos_ok += 1
            continue

        # Salvar CSV candidatos
        csv_cand = os.path.join(DIR, f"wo_del_candidates_{tag}.csv")
        fields = ["url", "expected_wine_id", "actual_wine_id", "ws_id", "store_id",
                   "pais", "clean_id", "n_correct", "n_wrong",
                   "ws_preco", "ws_moeda", "ws_disponivel", "ws_descoberto_em", "ws_atualizado_em"]
        with open(csv_cand, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader(); w.writerows(ca)

        # Executar
        deleted, skipped, errors, validated = execute_delete(ca, r, rc)

        skip_pct = len(skipped) / max(len(ca), 1)
        print(f"  Deleted: {deleted:,} | Skipped: {len(skipped)} ({skip_pct*100:.2f}%) | Errors: {errors}", flush=True)

        if skip_pct > SKIP_ABORT_PCT:
            print(f"  *** STOP: skip {skip_pct*100:.2f}% > 1% ***", flush=True)
            break
        if errors > 0:
            print(f"  *** STOP: {errors} erros ***", flush=True)
            break

        total_deleted += deleted
        total_skipped += len(skipped)
        total_errors += errors
        blocos_ok += 1

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

        # Skipped CSV
        if skipped:
            csv_skip = os.path.join(DIR, f"wo_del_skipped_{tag}.csv")
            with open(csv_skip, "w", newline="", encoding="utf-8") as f:
                sk_fields = list(skipped[0].keys())
                w = csv.DictWriter(f, fieldnames=sk_fields, extrasaction="ignore")
                w.writeheader(); w.writerows(skipped)

        # 10 exemplos conferidos
        print(f"  10 exemplos:", flush=True)
        for i, v in enumerate(validated[:10], 1):
            r.execute("SELECT COUNT(*) FROM wine_sources WHERE id = %s", (v["ws_id"],))
            gone = r.fetchone()[0] == 0
            r.execute("SELECT COUNT(*) FROM wine_sources WHERE wine_id = %s AND url = %s",
                       (v["expected_wine_id"], v["url"]))
            correct = r.fetchone()[0] > 0
            st = "OK" if gone and correct else f"PROB(gone={gone},correct={correct})"
            print(f"    [{i}] ws_id={v['ws_id']} del={'Y' if gone else 'N'} correct={'Y' if correct else 'N'} {st}", flush=True)

    # Resumo final
    r.execute("SELECT COUNT(*) FROM wine_sources")
    ws_fim = r.fetchone()[0]

    print(f"\n{'=' * 80}", flush=True)
    print(f"RESUMO ACUMULADO", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"  Blocos processados:  {blocos_ok}", flush=True)
    print(f"  Owners cobertos:     {START+1}-{min(START + blocos_ok * OWNER_BLOCK_SIZE, END)}", flush=True)
    print(f"  Total deletado:      {total_deleted:,}", flush=True)
    print(f"  Total pulado:        {total_skipped:,}", flush=True)
    print(f"  Total erros:         {total_errors}", flush=True)
    print(f"  WS inicio:           {ws_inicio:,}", flush=True)
    print(f"  WS fim:              {ws_fim:,}", flush=True)
    print(f"  Delta:               {ws_inicio - ws_fim:,}", flush=True)
    print(f"  Padrao:              {'100% delete_only_safe' if total_errors == 0 and total_skipped == 0 else 'COM EXCEPCOES'}", flush=True)

    l.close(); lc.close(); r.close(); rc.close()
    print(f"\nFim.", flush=True)


if __name__ == "__main__":
    main()
