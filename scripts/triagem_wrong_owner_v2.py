"""
Triagem wrong_owner v2 — READ-ONLY, otimizado para velocidade.
Processa top 5000 matched owners, batch de URLs no Render.
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

CSV_PATH = os.path.join(os.path.dirname(__file__), "wrong_owner_pilot_candidates.csv")
LIMITE_OWNERS = 5000
CLEAN_PER_OWNER = 100  # max clean_ids por owner
URLS_PER_CLEAN = 50    # max URLs por clean_id


def get_dom(url):
    try:
        n = urlparse(url).netloc
        return n.replace("www.", "") if n else None
    except:
        return None


def main():
    print("=" * 80, flush=True)
    print("TRIAGEM WRONG_OWNER v2 — READ-ONLY", flush=True)
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
    print(f"Stores: {len(d2s):,}", flush=True)

    # Top owners por n_clean_ids
    l.execute("""
        SELECT vivino_id, COUNT(*) FROM y2_results
        WHERE status = 'matched' AND vivino_id IS NOT NULL
        GROUP BY vivino_id ORDER BY COUNT(*) DESC
    """)
    all_owners = l.fetchall()
    owners_to_process = all_owners[:LIMITE_OWNERS]
    print(f"Owners total: {len(all_owners):,} | Processando: {len(owners_to_process):,}", flush=True)

    # Fase 1: Reconstruir expected URLs para todos os owners
    print("\nFase 1: Reconstruir expected URLs...", flush=True)
    # expected_by_url[url] = expected_wine_id
    expected_by_url = {}
    # expected_by_owner[owner] = set of urls
    expected_by_owner = defaultdict(set)

    for idx, (vid, ncl) in enumerate(owners_to_process):
        if (idx + 1) % 500 == 0:
            print(f"  {idx+1:,}/{len(owners_to_process):,} | URLs coletadas: {len(expected_by_url):,}", flush=True)

        l.execute(
            "SELECT clean_id FROM y2_results WHERE vivino_id = %s AND status = 'matched' LIMIT %s",
            (vid, CLEAN_PER_OWNER),
        )
        cids = [row[0] for row in l.fetchall()]

        for cid in cids:
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
                        WHERE vinho_id = %s AND url_original IS NOT NULL AND url_original LIKE 'http%%'
                        LIMIT %s""",
                    (ido, URLS_PER_CLEAN),
                )
                for (url,) in l.fetchall():
                    dom = get_dom(url)
                    sid = d2s.get(dom) if dom else None
                    if sid:
                        expected_by_url[url] = {"owner": vid, "store_id": sid, "pais": pais, "clean_id": cid}
                        expected_by_owner[vid].add(url)
            except Exception:
                lc.rollback()

    print(f"  Expected URLs totais: {len(expected_by_url):,}", flush=True)
    print(f"  Owners com URLs: {len(expected_by_owner):,}", flush=True)

    # Fase 2: Buscar URLs em batch no Render
    print("\nFase 2: Buscar URLs no Render (batch)...", flush=True)
    all_urls = list(expected_by_url.keys())

    correct = 0
    wrong_cases = []
    missing = 0

    BATCH = 500
    for i in range(0, len(all_urls), BATCH):
        if (i // BATCH) % 20 == 0:
            print(f"  {i:,}/{len(all_urls):,} | correct={correct:,} wrong={len(wrong_cases):,} missing={missing:,}", flush=True)

        chunk = all_urls[i:i+BATCH]
        r.execute("SELECT url, wine_id FROM wine_sources WHERE url = ANY(%s)", (chunk,))
        actual = {row[0]: row[1] for row in r.fetchall()}

        for url in chunk:
            exp = expected_by_url[url]
            if url in actual:
                if actual[url] == exp["owner"]:
                    correct += 1
                else:
                    wrong_cases.append({
                        "url": url,
                        "expected_wine_id": exp["owner"],
                        "actual_wine_id": actual[url],
                        "store_id": exp["store_id"],
                        "pais": exp["pais"],
                        "clean_id": exp["clean_id"],
                    })
            else:
                missing += 1

    # Resultados
    total = correct + len(wrong_cases) + missing
    print(f"\n{'=' * 80}", flush=True)
    print(f"RESULTADO", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"  Owners processados:        {len(owners_to_process):,}", flush=True)
    print(f"  Expected URLs analisadas:  {total:,}", flush=True)
    print(f"  URLs no owner CORRETO:     {correct:,} ({correct/max(total,1)*100:.1f}%)", flush=True)
    print(f"  URLs no owner ERRADO:      {len(wrong_cases):,} ({len(wrong_cases)/max(total,1)*100:.1f}%)", flush=True)
    print(f"  URLs FALTANDO no Render:   {missing:,} ({missing/max(total,1)*100:.1f}%)", flush=True)

    owners_wrong = set(c["actual_wine_id"] for c in wrong_cases)
    owners_expected = set(c["expected_wine_id"] for c in wrong_cases)
    print(f"  Wines receptores contaminados: {len(owners_wrong):,}", flush=True)
    print(f"  Wines doadores afetados:       {len(owners_expected):,}", flush=True)

    # 30 exemplos
    print(f"\n30 EXEMPLOS:", flush=True)
    for i, c in enumerate(wrong_cases[:30], 1):
        r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (c["expected_wine_id"],))
        ew = r.fetchone()
        r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (c["actual_wine_id"],))
        aw = r.fetchone()
        en = f"{ew[1]} - {(ew[0] or '')[:25]}" if ew else "???"
        an = f"{aw[1]} - {(aw[0] or '')[:25]}" if aw else "???"
        print(f"  [{i:>2}] {c['url'][:60]}", flush=True)
        print(f"       ESPERADO: {c['expected_wine_id']} | {en}", flush=True)
        print(f"       ACTUAL:   {c['actual_wine_id']} | {an}", flush=True)

    # CSV
    seen = set()
    deduped = []
    for c in wrong_cases:
        key = (c["url"], c["actual_wine_id"])
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "url", "expected_wine_id", "actual_wine_id", "store_id", "pais", "clean_id",
        ])
        writer.writeheader()
        writer.writerows(deduped)

    print(f"\nCSV: {CSV_PATH}", flush=True)
    print(f"Linhas (deduped): {len(deduped):,}", flush=True)
    print(f"Piloto sugerido: primeiros 500", flush=True)
    print(f"\nREAD-ONLY — nenhum dado alterado.", flush=True)

    l.close(); lc.close()
    r.close(); rc.close()


if __name__ == "__main__":
    main()
