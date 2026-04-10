"""
Corrigir new sem source — bucket C (URL relativa + loja unica + store existe).

Escopo restrito:
  - Apenas new wines (vivino_id IS NULL) sem wine_source
  - Apenas URLs RELATIVAS com dados_extras.loja resolvivel de forma unica
  - Apenas dominios que ja existem em stores
  - NAO mexe em matched, NAO mexe em wrong_owner
  - NAO mexe em bucket B, D, E

Regras:
  - Para cada wine, tenta TODAS fontes de TODOS clean_ids antes de rejeitar
  - Nome normalizado da loja, desempate por pais/plataforma
  - So aceita resolucao unica (nunca ambigua)
  - Reconstrui URL absoluta: https://{dominio}{path_relativo}
  - store_id tem que existir em stores

Uso:
    python corrigir_new_bucket_c.py                # dry-run (default)
    python corrigir_new_bucket_c.py --executar      # execucao real
"""
import argparse
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
from psycopg2.extras import execute_values

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = os.environ["DATABASE_URL"]

LIXO_PREFIXES = ("javascript:", "tel:", "mailto:", "#", "data:", "blob:")
LIXO_EXATOS = {"false", "true", "null", "undefined", "none", "nan", ""}
CSV_PATH = os.path.join(os.path.dirname(__file__), "correcao_new_bucket_c.csv")


def normalizar_nome(nome):
    if not nome:
        return ""
    return re.sub(r"[^a-z0-9 ]", "", nome.strip().lower()).strip()


def extrair_dominio(url_raw):
    if not url_raw:
        return None
    s = url_raw.strip()
    if not s.startswith("http://") and not s.startswith("https://"):
        s = "https://" + s
    try:
        parsed = urlparse(s)
        netloc = parsed.netloc
        if not netloc:
            return None
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return None


def is_url_lixo(url):
    if not url:
        return True
    s = url.strip().lower()
    if s in LIXO_EXATOS:
        return True
    return any(s.startswith(p) for p in LIXO_PREFIXES)


def is_url_absoluta(url):
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False


def resolver_loja(nome_loja, mercado_pais, fonte_plataforma, lojas_por_nome):
    key = normalizar_nome(nome_loja)
    if not key:
        return None, "nome vazio", 0

    candidatos = lojas_por_nome.get(key, [])
    if len(candidatos) == 0:
        return None, "nome nao encontrado", 0
    if len(candidatos) == 1:
        return candidatos[0], "match exato unico", 1

    # Desempate por pais
    if mercado_pais:
        mp = mercado_pais.strip().lower()
        por_pais = [c for c in candidatos if (c["pais"] or "").lower() == mp]
        if len(por_pais) == 1:
            return por_pais[0], f"desempate por pais={mercado_pais}", 1
        if len(por_pais) > 1:
            candidatos = por_pais

    # Desempate por plataforma
    if fonte_plataforma and len(candidatos) > 1:
        fp = fonte_plataforma.strip().lower()
        por_plat = [c for c in candidatos if (c["plataforma"] or "").lower() == fp]
        if len(por_plat) == 1:
            return por_plat[0], f"desempate por plataforma={fonte_plataforma}", 1

    return None, f"ambiguo ({len(candidatos)} candidatos)", len(candidatos)


def tentar_resolver_wine(wine_id, hash_dedup, l, lc, lojas_por_nome, domain_to_store):
    """
    Tenta TODAS fontes de TODOS clean_ids.
    So aceita: URL relativa + loja unica + store existe.
    Ignora URLs absolutas (ja tratadas no bucket A).
    """
    l.execute(
        "SELECT id, pais_tabela, id_original FROM wines_clean WHERE hash_dedup = %s AND id_original IS NOT NULL",
        (hash_dedup,),
    )
    origens = l.fetchall()
    if not origens:
        return None, "hash nao encontrado"

    motivos = defaultdict(int)

    for clean_id, pais, id_orig in origens:
        if not pais or not re.match(r"^[a-z]{2}$", pais):
            motivos["pais invalido"] += 1
            continue

        try:
            l.execute(
                f"""SELECT url_original, preco, moeda, fonte, mercado, dados_extras
                    FROM vinhos_{pais}_fontes WHERE vinho_id = %s""",
                (id_orig,),
            )
            fontes_rows = l.fetchall()
        except Exception:
            lc.rollback()
            motivos["erro ao ler fontes"] += 1
            continue

        if not fontes_rows:
            motivos["sem registro em fontes"] += 1
            continue

        for url, preco, moeda, fonte, mercado, extras in fontes_rows:
            if not url:
                motivos["url NULL"] += 1
                continue
            if is_url_lixo(url):
                motivos["path lixo"] += 1
                continue
            # Pular absolutas — bucket A ja tratou
            if is_url_absoluta(url):
                motivos["URL absoluta (bucket A)"] += 1
                continue

            # URL relativa — resolver loja
            loja_nome = None
            if extras and isinstance(extras, dict):
                loja_nome = extras.get("loja", "").strip()

            if not loja_nome:
                motivos["URL relativa sem dados_extras.loja"] += 1
                continue

            loja_match, criterio, n_cand = resolver_loja(loja_nome, mercado, fonte, lojas_por_nome)

            if loja_match is None:
                motivos[f"loja: {criterio}"] += 1
                continue

            dom = extrair_dominio(loja_match["url"])
            if not dom:
                motivos["dominio nao extraivel"] += 1
                continue

            store_id = domain_to_store.get(dom)
            if not store_id:
                motivos[f"dominio nao em stores ({dom})"] += 1
                continue

            # SUCESSO — reconstruir URL absoluta com barra segura
            if url.startswith("/"):
                url_absoluta = f"https://{dom}{url}"
            else:
                url_absoluta = f"https://{dom}/{url}"
            return {
                "render_wine_id": wine_id,
                "clean_id": clean_id,
                "pais": pais,
                "id_orig": id_orig,
                "loja_resolvida": loja_nome,
                "dominio": dom,
                "url_relativa": url,
                "url_absoluta": url_absoluta,
                "store_id": store_id,
                "preco": preco,
                "moeda": moeda,
                "fonte": fonte,
                "criterio": criterio,
            }, None

    # Esgotou tudo
    motivo_principal = max(motivos, key=motivos.get) if motivos else "sem fontes"
    return None, motivo_principal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--executar", action="store_true", help="Executar INSERTs (default: dry-run)")
    args = parser.parse_args()

    is_dry_run = not args.executar

    print("=" * 80)
    print("CORRECAO NEW BUCKET C: URL relativa + loja unica + store existe")
    if is_dry_run:
        print("MODO: DRY-RUN (nenhum INSERT sera feito)")
    else:
        print("MODO: EXECUCAO REAL")
    print("=" * 80)

    # Conexoes
    print("\nConectando...")
    lc = psycopg2.connect(**LOCAL_DB)
    rc = psycopg2.connect(
        RENDER_DB, options="-c statement_timeout=300000",
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )
    l = lc.cursor()
    r = rc.cursor()

    # Indices
    print("Carregando indices...")
    l.execute("""
        SELECT id, nome, url_normalizada, pais_codigo, plataforma
        FROM lojas_scraping WHERE url_normalizada IS NOT NULL AND nome IS NOT NULL
    """)
    lojas_por_nome = defaultdict(list)
    for lid, nome, url, pais, plat in l.fetchall():
        key = normalizar_nome(nome)
        if key:
            lojas_por_nome[key].append({"id": lid, "url": url, "pais": pais, "plataforma": plat})
    print(f"  lojas: {len(lojas_por_nome):,} nomes")

    r.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
    domain_to_store = {row[0]: row[1] for row in r.fetchall()}
    print(f"  stores: {len(domain_to_store):,} dominios")

    # Snapshot
    r.execute("""
        SELECT COUNT(*) FROM wines w
        LEFT JOIN wine_sources ws ON ws.wine_id = w.id
        WHERE w.vivino_id IS NULL AND ws.id IS NULL
    """)
    new_sem_antes = r.fetchone()[0]
    print(f"\n  New sem source ANTES: {new_sem_antes:,}")

    # Buscar new sem source
    print("\nBuscando new sem source...")
    r.execute("""
        SELECT w.id, w.hash_dedup
        FROM wines w
        LEFT JOIN wine_sources ws ON ws.wine_id = w.id
        WHERE w.vivino_id IS NULL AND w.hash_dedup IS NOT NULL AND ws.id IS NULL
        ORDER BY w.id
    """)
    wines = r.fetchall()
    total = len(wines)
    print(f"  Total: {total:,}")

    # Resolver cada wine
    print(f"Resolvendo {total:,} wines...")
    inserts = []
    motivos_rejeicao = defaultdict(int)

    for idx, (wine_id, hash_dedup) in enumerate(wines):
        if (idx + 1) % 500 == 0:
            print(f"  {idx + 1:,}/{total:,} | bucket_c={len(inserts)}")

        resultado, motivo = tentar_resolver_wine(wine_id, hash_dedup, l, lc, lojas_por_nome, domain_to_store)

        if resultado:
            inserts.append(resultado)
        else:
            motivos_rejeicao[motivo] += 1

    # ── Relatorio ─────────────────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print(f"RESULTADO")
    print(f"{'=' * 80}")
    print(f"  New sem source analisados:  {total:,}")
    print(f"  Prontos para INSERT (C):    {len(inserts):,}")
    print(f"  Rejeitados:                 {total - len(inserts):,}")
    print(f"\n  Motivos de rejeicao:")
    for motivo in sorted(motivos_rejeicao, key=lambda x: -motivos_rejeicao[x]):
        print(f"    {motivos_rejeicao[motivo]:>6,}  {motivo}")

    # CSV
    print(f"\n  Gerando CSV: {CSV_PATH}")
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "render_wine_id", "clean_id", "pais", "loja_resolvida", "dominio",
            "url_relativa", "url_absoluta", "store_id", "preco", "moeda", "fonte", "criterio",
        ])
        writer.writeheader()
        for row in inserts:
            writer.writerow({k: row.get(k, "") for k in writer.fieldnames})
    print(f"  CSV escrito: {len(inserts)} linhas")

    # 20 exemplos
    print(f"\n{'=' * 80}")
    print(f"20 EXEMPLOS AUDITAVEIS")
    print(f"{'=' * 80}")
    for i, e in enumerate(inserts[:20], 1):
        r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (e["render_wine_id"],))
        wine = r.fetchone()
        nome = f"{wine[1]} - {(wine[0] or '')[:35]}" if wine else "???"
        print(f"\n  [{i:>2}] wine_id={e['render_wine_id']} | {nome}")
        print(f"       clean_id={e['clean_id']} | pais={e['pais']}")
        print(f"       loja: {e['loja_resolvida']}")
        print(f"       dominio: {e['dominio']} -> store_id={e['store_id']}")
        print(f"       URL relativa:  {e['url_relativa'][:70]}")
        print(f"       URL absoluta:  {e['url_absoluta'][:70]}")
        print(f"       preco: {e['preco']} {e['moeda']} | fonte: {e['fonte']}")
        print(f"       criterio: {e['criterio']}")

    # Contagem final
    print(f"\n{'=' * 80}")
    print(f"CONTAGEM FINAL")
    print(f"{'=' * 80}")
    print(f"  INSERTs esperados:  {len(inserts)}")

    existe = 0
    for e in inserts:
        r.execute(
            "SELECT COUNT(*) FROM wine_sources WHERE wine_id = %s AND store_id = %s AND url = %s",
            (e["render_wine_id"], e["store_id"], e["url_absoluta"]),
        )
        if r.fetchone()[0] > 0:
            existe += 1
    print(f"  Ja existentes (ON CONFLICT): {existe}")
    print(f"  INSERTs efetivos esperados:  {len(inserts) - existe}")

    # Execucao
    if is_dry_run:
        print(f"\n  DRY-RUN: nenhum INSERT realizado.")
        print(f"  Para executar: python {os.path.basename(__file__)} --executar")
    else:
        print(f"\n  Executando {len(inserts)} INSERTs...")
        ts = datetime.now(timezone.utc)
        values = [
            (e["render_wine_id"], e["store_id"], e["url_absoluta"], e["preco"], e["moeda"], True, ts, ts)
            for e in inserts
        ]

        try:
            r.execute("SAVEPOINT correcao_bucket_c")
            execute_values(
                r,
                """INSERT INTO wine_sources
                       (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
                   VALUES %s
                   ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING""",
                values,
            )
            inseridos = r.rowcount
            r.execute("RELEASE SAVEPOINT correcao_bucket_c")
            rc.commit()
            print(f"  INSERTs realizados: {inseridos}")
        except Exception as ex:
            print(f"  ERRO: {ex}")
            r.execute("ROLLBACK TO SAVEPOINT correcao_bucket_c")
            rc.commit()
            print(f"  Rollback feito. Nenhum dado alterado.")
            l.close(); lc.close(); r.close(); rc.close()
            return

        # Validacao
        r.execute("""
            SELECT COUNT(*) FROM wines w
            LEFT JOIN wine_sources ws ON ws.wine_id = w.id
            WHERE w.vivino_id IS NULL AND ws.id IS NULL
        """)
        new_sem_depois = r.fetchone()[0]
        print(f"\n  New sem source ANTES:  {new_sem_antes:,}")
        print(f"  New sem source DEPOIS: {new_sem_depois:,}")
        print(f"  Delta:                 {new_sem_antes - new_sem_depois:,}")

        # Timestamp para revert
        print(f"\n  Timestamp: {ts}")
        print(f"  REVERT: DELETE FROM wine_sources WHERE descoberto_em = '{ts}';")

        # 20 conferidos no Render
        print(f"\n  20 exemplos conferidos no Render:")
        for i, e in enumerate(inserts[:20], 1):
            r.execute("""
                SELECT ws.url, s.dominio, ws.preco, ws.moeda
                FROM wine_sources ws JOIN stores s ON s.id = ws.store_id
                WHERE ws.wine_id = %s AND ws.descoberto_em = %s
                LIMIT 1
            """, (e["render_wine_id"], ts))
            src = r.fetchone()
            r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (e["render_wine_id"],))
            wine = r.fetchone()
            nome = f"{wine[1]} - {(wine[0] or '')[:30]}" if wine else "???"
            if src:
                print(f"  [{i:>2}] wine_id={e['render_wine_id']} | {nome}")
                print(f"       {src[1]} | {(src[0] or '')[:55]} | {src[2]} {src[3]}")
            else:
                print(f"  [{i:>2}] wine_id={e['render_wine_id']} | {nome} | *** NAO ENCONTRADO ***")

    l.close(); lc.close()
    r.close(); rc.close()
    print("\nFim.")


if __name__ == "__main__":
    main()
