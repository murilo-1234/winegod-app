"""
Triagem wrong_owner — READ-ONLY.
Identifica wine_sources no Render que estao no wine_id errado,
comparando linhagem canonica local vs actual.

Foco: matched wines (y2_results.vivino_id = wines.id no Render).
Metodo:
  1. Para cada matched owner no y2, reconstruir expected URLs do local
  2. Buscar essas URLs no Render (em qualquer wine_id)
  3. Se a URL existe mas em outro wine_id -> wrong_owner com prova forte
  4. Gerar CSV de candidatos para piloto

NAO executa nenhum DELETE, UPDATE ou INSERT.
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


def get_domain(url):
    if not url:
        return None
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc
        if not netloc:
            return None
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return None


def main():
    print("=" * 80)
    print("TRIAGEM WRONG_OWNER — READ-ONLY")
    print("=" * 80)

    lc = psycopg2.connect(**LOCAL_DB)
    rc = psycopg2.connect(
        RENDER_DB, options="-c statement_timeout=300000",
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )
    l = lc.cursor()
    r = rc.cursor()

    # Carregar domain_to_store
    r.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
    domain_to_store = {row[0]: row[1] for row in r.fetchall()}

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 1: Quantificacao com prova forte
    # ══════════════════════════════════════════════════════════════════════════
    # Estrategia: amostrar matched owners com muitos clean_ids (alto risco de
    # wrong_owner), reconstruir expected URLs, buscar no Render.
    #
    # Para escalar: processar os top matched owners por n_clean_ids primeiro,
    # depois ampliar. Isso acha os piores casos rapido.

    print("\nCarregando matched owners do y2...")
    l.execute("""
        SELECT vivino_id, COUNT(*) as cnt
        FROM y2_results
        WHERE status = 'matched' AND vivino_id IS NOT NULL
        GROUP BY vivino_id
        ORDER BY COUNT(*) DESC
    """)
    all_owners = l.fetchall()
    print(f"  Total matched owners: {len(all_owners):,}")

    # Processar em ordem de risco (mais clean_ids = mais chance de wrong_owner)
    # Limitar a owners com >= 3 clean_ids para velocidade
    owners_high_risk = [(v, c) for v, c in all_owners if c >= 3]
    print(f"  Owners com >= 3 clean_ids (alto risco): {len(owners_high_risk):,}")

    wrong_owner_cases = []
    owners_processados = 0
    owners_com_wrong = 0
    total_expected = 0
    total_wrong = 0
    total_correct = 0
    total_missing = 0

    # Processar top 5000 owners (por n_clean_ids desc)
    LIMITE_OWNERS = 5000
    print(f"\n  Processando top {LIMITE_OWNERS} owners...")

    for owner_idx, (vivino_id, n_clean) in enumerate(owners_high_risk[:LIMITE_OWNERS]):
        if (owner_idx + 1) % 500 == 0:
            print(f"    {owner_idx + 1:,}/{min(LIMITE_OWNERS, len(owners_high_risk)):,} | wrong={total_wrong:,} | correct={total_correct:,} | missing={total_missing:,}")

        owners_processados += 1

        # 1a. Reconstruir expected URLs para este owner
        l.execute("SELECT clean_id FROM y2_results WHERE vivino_id = %s AND status = 'matched'", (vivino_id,))
        cids = [row[0] for row in l.fetchall()]

        expected_urls = {}  # url -> {store_id, pais, ...}
        for cid in cids:
            l.execute("SELECT pais_tabela, id_original FROM wines_clean WHERE id = %s AND id_original IS NOT NULL", (cid,))
            row = l.fetchone()
            if not row or not row[0] or not re.match(r"^[a-z]{2}$", row[0]):
                continue
            pais, id_orig = row
            try:
                l.execute(
                    f"SELECT url_original FROM vinhos_{pais}_fontes WHERE vinho_id = %s AND url_original IS NOT NULL",
                    (id_orig,),
                )
                for (url,) in l.fetchall():
                    dom = get_domain(url)
                    store_id = domain_to_store.get(dom) if dom else None
                    if store_id and url.startswith("http"):
                        expected_urls[url] = {"store_id": store_id, "pais": pais, "clean_id": cid}
            except Exception:
                lc.rollback()

        if not expected_urls:
            continue

        total_expected += len(expected_urls)

        # 1b. Buscar essas URLs no Render
        urls_list = list(expected_urls.keys())
        # Buscar em chunks
        for i in range(0, len(urls_list), 100):
            chunk = urls_list[i:i+100]
            r.execute(
                "SELECT url, wine_id FROM wine_sources WHERE url = ANY(%s)",
                (chunk,),
            )
            actual = {row[0]: row[1] for row in r.fetchall()}

            for url in chunk:
                exp = expected_urls[url]
                if url in actual:
                    actual_wine_id = actual[url]
                    if actual_wine_id == vivino_id:
                        total_correct += 1
                    else:
                        total_wrong += 1
                        wrong_owner_cases.append({
                            "url": url,
                            "expected_wine_id": vivino_id,
                            "actual_wine_id": actual_wine_id,
                            "store_id": exp["store_id"],
                            "pais": exp["pais"],
                            "clean_id": exp["clean_id"],
                        })
                else:
                    total_missing += 1

        if any(url in [c["url"] for c in wrong_owner_cases[-len(expected_urls):]] for url in expected_urls):
            owners_com_wrong += 1

    # Contar owners unicos com wrong
    owners_wrong_set = set(c["actual_wine_id"] for c in wrong_owner_cases)
    expected_owners_set = set(c["expected_wine_id"] for c in wrong_owner_cases)

    print(f"\n{'=' * 80}")
    print(f"RESULTADO BLOCO 1 — QUANTIFICACAO")
    print(f"{'=' * 80}")
    print(f"  Owners processados:        {owners_processados:,}")
    print(f"  Expected URLs analisadas:  {total_expected:,}")
    print(f"  URLs no owner CORRETO:     {total_correct:,} ({total_correct/max(total_expected,1)*100:.1f}%)")
    print(f"  URLs no owner ERRADO:      {total_wrong:,} ({total_wrong/max(total_expected,1)*100:.1f}%)")
    print(f"  URLs FALTANDO no Render:   {total_missing:,} ({total_missing/max(total_expected,1)*100:.1f}%)")
    print(f"  Wines receptores contaminados: {len(owners_wrong_set):,}")
    print(f"  Wines doadores afetados:       {len(expected_owners_set):,}")

    # 30 exemplos
    print(f"\n{'=' * 80}")
    print(f"30 EXEMPLOS AUDITAVEIS")
    print(f"{'=' * 80}")
    for i, c in enumerate(wrong_owner_cases[:30], 1):
        # Nomes dos wines
        r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (c["expected_wine_id"],))
        exp_wine = r.fetchone()
        exp_nome = f"{exp_wine[1]} - {(exp_wine[0] or '')[:30]}" if exp_wine else "???"

        r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (c["actual_wine_id"],))
        act_wine = r.fetchone()
        act_nome = f"{act_wine[1]} - {(act_wine[0] or '')[:30]}" if act_wine else "???"

        print(f"\n  [{i:>2}] URL: {c['url'][:65]}")
        print(f"       ESPERADO: wine_id={c['expected_wine_id']} | {exp_nome}")
        print(f"       ACTUAL:   wine_id={c['actual_wine_id']} | {act_nome}")
        print(f"       store_id={c['store_id']} | pais={c['pais']} | clean_id={c['clean_id']}")

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 2: CSV piloto
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}")
    print(f"BLOCO 2 — CSV PILOTO")
    print(f"{'=' * 80}")

    # Dedup e filtrar apenas prova forte
    seen = set()
    pilot = []
    for c in wrong_owner_cases:
        key = (c["url"], c["actual_wine_id"])
        if key not in seen:
            seen.add(key)
            pilot.append(c)

    print(f"  Casos com prova forte (deduped): {len(pilot):,}")

    # CSV completo
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "url", "expected_wine_id", "actual_wine_id", "store_id", "pais", "clean_id",
        ])
        writer.writeheader()
        writer.writerows(pilot)
    print(f"  CSV: {CSV_PATH}")
    print(f"  Total linhas: {len(pilot):,}")

    # Piloto sugerido
    pilot_size = min(500, len(pilot))
    print(f"\n  Piloto sugerido: {pilot_size} linhas (primeiros por owner com mais clean_ids)")
    print(f"  Por que e seguro:")
    print(f"    - Cada caso tem prova forte: URL canonica do local encontrada no Render em outro wine_id")
    print(f"    - A operacao seria: DELETE wine_source do wine errado + INSERT no wine correto")
    print(f"    - ON CONFLICT DO NOTHING protege contra duplicatas")
    print(f"    - Revert: re-INSERT no wine_id antigo usando o CSV como fonte")

    print(f"\n  Estrategia de revert:")
    print(f"    1. Salvar snapshot antes (wine_id_antigo, store_id, url) do CSV")
    print(f"    2. Se precisar reverter:")
    print(f"       DELETE FROM wine_sources WHERE wine_id = expected AND url = X;")
    print(f"       INSERT INTO wine_sources (wine_id, store_id, url, ...) VALUES (actual_antigo, ...);")
    print(f"    3. O CSV tem todos os campos para revert completo")

    l.close(); lc.close()
    r.close(); rc.close()
    print("\nFim. READ-ONLY — nenhum dado alterado.")


if __name__ == "__main__":
    main()
