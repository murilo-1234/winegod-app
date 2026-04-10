"""
Triagem wrong_owner v3 — READ-ONLY, multiplicidade real.

Chave: (url, store_id, actual_wine_id, ws_id)
Nao colapsa duplicatas.
Classifica em:
  A. delete_only_safe — owner correto ja tem o link, copias extras em errados
  B. move_needed — owner correto NAO tem, exatamente 1 errado
  C. ambiguous_multilayer — 2+ errados ou conflito
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
CSV_A = os.path.join(DIR, "wrong_owner_delete_only_candidates.csv")
CSV_B = os.path.join(DIR, "wrong_owner_move_needed_candidates.csv")
CSV_C = os.path.join(DIR, "wrong_owner_ambiguous_candidates.csv")

LIMIT_OWNERS = 500
CLEAN_PER_OWNER = 30
URLS_PER_CLEAN = 5


def get_dom(url):
    try:
        n = urlparse(url).netloc
        return n.replace("www.", "") if n else None
    except:
        return None


def main():
    print("=" * 80, flush=True)
    print("TRIAGEM WRONG_OWNER v3 — READ-ONLY, MULTIPLICIDADE REAL", flush=True)
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

    # Top owners
    l.execute("""
        SELECT vivino_id, COUNT(*) FROM y2_results
        WHERE status = 'matched' AND vivino_id IS NOT NULL
        GROUP BY vivino_id ORDER BY COUNT(*) DESC LIMIT %s
    """, (LIMIT_OWNERS,))
    owners = l.fetchall()
    print(f"Processando {len(owners)} owners", flush=True)

    # Fase 1: Coletar expected URLs com owner canonico
    # expected_map[url] = expected_owner_id
    expected_map = {}
    expected_meta = {}  # url -> {store_id, pais, clean_id}

    for idx, (vid, ncl) in enumerate(owners):
        if (idx + 1) % 100 == 0:
            print(f"  Fase1: {idx+1}/{len(owners)} | URLs: {len(expected_map):,}", flush=True)

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

    print(f"Expected URLs: {len(expected_map):,}", flush=True)

    # Fase 2: Para cada expected URL, buscar TODAS as linhas em wine_sources
    print("\nFase 2: Buscar todas linhas reais no Render...", flush=True)

    # Por URL: quais wine_ids possuem?
    # url -> [(ws_id, wine_id, store_id, preco, moeda, disponivel, descoberto_em, atualizado_em)]
    url_all_owners = defaultdict(list)

    all_urls = list(expected_map.keys())
    BATCH = 500
    for i in range(0, len(all_urls), BATCH):
        if (i // BATCH) % 10 == 0:
            print(f"  {i:,}/{len(all_urls):,}", flush=True)
        chunk = all_urls[i:i + BATCH]
        r.execute("""
            SELECT id, wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em
            FROM wine_sources
            WHERE url = ANY(%s)
        """, (chunk,))
        for ws_id, wid, sid, url, preco, moeda, disp, desc, atua in r.fetchall():
            url_all_owners[url].append({
                "ws_id": ws_id,
                "wine_id": wid,
                "store_id": sid,
                "preco": preco,
                "moeda": moeda,
                "disponivel": disp,
                "descoberto_em": str(desc),
                "atualizado_em": str(atua),
            })

    print(f"URLs com resultados no Render: {len(url_all_owners):,}", flush=True)

    # Fase 3: Classificar
    print("\nFase 3: Classificar...", flush=True)

    class_a = []  # delete_only_safe
    class_b = []  # move_needed
    class_c = []  # ambiguous

    for url, expected_owner in expected_map.items():
        meta = expected_meta[url]
        lines = url_all_owners.get(url, [])

        if not lines:
            # URL nao existe no Render — nada a limpar
            continue

        # Separar: owner correto vs owners errados
        correct_lines = [ln for ln in lines if ln["wine_id"] == expected_owner]
        wrong_lines = [ln for ln in lines if ln["wine_id"] != expected_owner]

        if not wrong_lines:
            # Todas as linhas estao no owner correto — nada a fazer
            continue

        wrong_owners = set(ln["wine_id"] for ln in wrong_lines)
        has_correct = len(correct_lines) > 0

        entry_base = {
            "url": url,
            "expected_wine_id": expected_owner,
            "store_id": meta["store_id"],
            "pais": meta["pais"],
            "clean_id": meta["clean_id"],
            "n_correct": len(correct_lines),
            "n_wrong": len(wrong_lines),
            "n_wrong_owners": len(wrong_owners),
        }

        if has_correct:
            # Classe A: owner correto ja tem, copias erradas existem
            for wl in wrong_lines:
                class_a.append({
                    **entry_base,
                    "actual_wine_id": wl["wine_id"],
                    "ws_id": wl["ws_id"],
                    "ws_preco": wl["preco"],
                    "ws_moeda": wl["moeda"],
                    "ws_disponivel": wl["disponivel"],
                    "ws_descoberto_em": wl["descoberto_em"],
                    "ws_atualizado_em": wl["atualizado_em"],
                })
        elif len(wrong_owners) == 1:
            # Classe B: owner correto ausente, exatamente 1 errado
            for wl in wrong_lines:
                class_b.append({
                    **entry_base,
                    "actual_wine_id": wl["wine_id"],
                    "ws_id": wl["ws_id"],
                    "ws_preco": wl["preco"],
                    "ws_moeda": wl["moeda"],
                    "ws_disponivel": wl["disponivel"],
                    "ws_descoberto_em": wl["descoberto_em"],
                    "ws_atualizado_em": wl["atualizado_em"],
                })
        else:
            # Classe C: ambiguo
            for wl in wrong_lines:
                class_c.append({
                    **entry_base,
                    "actual_wine_id": wl["wine_id"],
                    "ws_id": wl["ws_id"],
                    "ws_preco": wl["preco"],
                    "ws_moeda": wl["moeda"],
                })

    # ══════════════════════════════════════════════════════════════════════════
    # RESULTADO
    # ══════════════════════════════════════════════════════════════════════════
    ws_ids_a = set(c["ws_id"] for c in class_a)
    ws_ids_b = set(c["ws_id"] for c in class_b)
    receptores_a = set(c["actual_wine_id"] for c in class_a)
    receptores_b = set(c["actual_wine_id"] for c in class_b)
    receptores_c = set(c["actual_wine_id"] for c in class_c)

    print(f"\n{'=' * 80}", flush=True)
    print(f"RESULTADO", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"  Classe A (delete_only_safe):     {len(class_a):,} linhas | {len(ws_ids_a):,} ws.id unicos | {len(receptores_a):,} receptores", flush=True)
    print(f"  Classe B (move_needed):          {len(class_b):,} linhas | {len(ws_ids_b):,} ws.id unicos | {len(receptores_b):,} receptores", flush=True)
    print(f"  Classe C (ambiguous):            {len(class_c):,} linhas | {len(receptores_c):,} receptores", flush=True)
    print(f"  Total receptores contaminados:   {len(receptores_a | receptores_b | receptores_c):,}", flush=True)

    # CSVs
    fields_ab = [
        "url", "expected_wine_id", "actual_wine_id", "ws_id", "store_id",
        "pais", "clean_id", "n_correct", "n_wrong", "n_wrong_owners",
        "ws_preco", "ws_moeda", "ws_disponivel", "ws_descoberto_em", "ws_atualizado_em",
    ]
    fields_c = [
        "url", "expected_wine_id", "actual_wine_id", "ws_id", "store_id",
        "pais", "clean_id", "n_correct", "n_wrong", "n_wrong_owners",
        "ws_preco", "ws_moeda",
    ]

    for path, data, fields in [(CSV_A, class_a, fields_ab), (CSV_B, class_b, fields_ab), (CSV_C, class_c, fields_c)]:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)
        print(f"  CSV: {path} ({len(data):,} linhas)", flush=True)

    # Verificar os 5 casos do piloto anterior
    print(f"\n--- VERIFICACAO DOS 5 ERROS DO PILOTO ANTERIOR ---", flush=True)
    pilot_errors = [
        ("https://elitevinho.com.br/uvas/malbec/vinho-rose-corder", 824156, 2274488),
        ("https://www.vinoselkiosco.com/tienda/sibaris-gran-reser", 1296639, 2264431),
        ("https://www.bswliquor.com/products/keep-calm-thrive-cab", 188807, 1688155),
        ("https://www.bswliquor.com/products/d-reserve-cabernet-s", 188807, 214473),
        ("https://winechateau.com/products/the-little-sheep-of-fr", 820094, 688447),
    ]
    for url_prefix, exp, old_act in pilot_errors:
        # Buscar todas as linhas desta URL no Render
        r.execute("SELECT wine_id, id FROM wine_sources WHERE url LIKE %s", (url_prefix + "%",))
        all_wids = r.fetchall()
        on_correct = [wid for wid, _ in all_wids if wid == exp]
        on_wrong = [(wid, wsid) for wid, wsid in all_wids if wid != exp]
        print(f"  URL: {url_prefix[:55]}", flush=True)
        print(f"    Expected: {exp} | On correct: {len(on_correct)} | On wrong: {len(on_wrong)} owners errados: {[w for w, _ in on_wrong]}", flush=True)

    # 20 exemplos classe A
    print(f"\n--- 20 EXEMPLOS CLASSE A (delete_only_safe) ---", flush=True)
    for i, c in enumerate(class_a[:20], 1):
        r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (c["expected_wine_id"],))
        ew = r.fetchone()
        r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (c["actual_wine_id"],))
        aw = r.fetchone()
        en = f"{ew[1]} - {(ew[0] or '')[:20]}" if ew else "???"
        an = f"{aw[1]} - {(aw[0] or '')[:20]}" if aw else "???"
        print(f"  [{i:>2}] ws_id={c['ws_id']} | {c['url'][:50]}", flush=True)
        print(f"       ESP: {c['expected_wine_id']} | {en} (has {c['n_correct']} correct)", flush=True)
        print(f"       DEL: {c['actual_wine_id']} | {an} (1 of {c['n_wrong']} wrong)", flush=True)

    # 20 exemplos classe B
    if class_b:
        print(f"\n--- 20 EXEMPLOS CLASSE B (move_needed) ---", flush=True)
        for i, c in enumerate(class_b[:20], 1):
            r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (c["expected_wine_id"],))
            ew = r.fetchone()
            r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (c["actual_wine_id"],))
            aw = r.fetchone()
            en = f"{ew[1]} - {(ew[0] or '')[:20]}" if ew else "???"
            an = f"{aw[1]} - {(aw[0] or '')[:20]}" if aw else "???"
            print(f"  [{i:>2}] ws_id={c['ws_id']} | {c['url'][:50]}", flush=True)
            print(f"       MOVE: {c['actual_wine_id']} ({an}) -> {c['expected_wine_id']} ({en})", flush=True)

    print(f"\nREAD-ONLY — nenhum dado alterado.", flush=True)
    l.close(); lc.close(); r.close(); rc.close()


if __name__ == "__main__":
    main()
