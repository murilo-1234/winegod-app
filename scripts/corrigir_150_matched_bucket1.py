"""
Corrigir matched sem source — bucket 1 (URL relativa + loja unica + store existe).

Escopo restrito:
  - Apenas matched wines (vivino_id IS NOT NULL) sem wine_source
  - Apenas URLs RELATIVAS com dados_extras.loja resolvivel de forma unica
  - Apenas dominios que ja existem em stores
  - NAO inclui URLs absolutas (essas sao outro bucket)
  - NAO mexe em new, NAO mexe em wrong_owner

Regras:
  - Para cada wine, tenta TODAS as fontes de TODOS os clean_ids antes de rejeitar
  - Pega a primeira fonte valida e resolvida de forma unica
  - So rejeita o wine depois de esgotar tudo
  - Extracao de dominio usa urlparse robusto, nunca split manual

Uso:
    python corrigir_150_matched_bucket1.py                # dry-run (default)
    python corrigir_150_matched_bucket1.py --executar      # execucao real
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
CSV_PATH = os.path.join(os.path.dirname(__file__), "correcao_150_matched_bucket1.csv")


def normalizar_nome(nome):
    if not nome:
        return ""
    return re.sub(r"[^a-z0-9 ]", "", nome.strip().lower()).strip()


def extrair_dominio(url_raw):
    """
    Extrai dominio de uma url_normalizada de lojas_scraping.
    Usa urlparse robusto — nunca split manual.
    Remove apenas www.
    """
    if not url_raw:
        return None
    s = url_raw.strip()
    # Se nao tem scheme, prefixar https://
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


def is_url_relativa(url):
    """True se a URL nao tem scheme+netloc (e relativa)."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return not (parsed.scheme and parsed.netloc)
    except Exception:
        return True


def is_url_lixo(url):
    if not url:
        return True
    return any(url.strip().lower().startswith(p) for p in LIXO_PREFIXES)


def resolver_loja(nome_loja, mercado_pais, fonte_plataforma, lojas_por_nome):
    """
    Resolver nome da loja em lojas_scraping.
    Retorna (loja_match, criterio) ou (None, motivo).
    Nunca retorna ambiguo — so retorna match quando resolve de forma unica.
    """
    key = normalizar_nome(nome_loja)
    if not key:
        return None, "nome vazio"

    candidatos = lojas_por_nome.get(key, [])

    if len(candidatos) == 0:
        return None, "nome nao encontrado"

    if len(candidatos) == 1:
        return candidatos[0], "match exato unico"

    # >1 candidato — desempatar por pais
    if mercado_pais:
        mp = mercado_pais.strip().lower()
        por_pais = [c for c in candidatos if (c["pais"] or "").lower() == mp]
        if len(por_pais) == 1:
            return por_pais[0], f"desempate por pais={mercado_pais}"
        if len(por_pais) > 1:
            candidatos = por_pais

    # Desempatar por plataforma
    if fonte_plataforma and len(candidatos) > 1:
        fp = fonte_plataforma.strip().lower()
        por_plat = [c for c in candidatos if (c["plataforma"] or "").lower() == fp]
        if len(por_plat) == 1:
            return por_plat[0], f"desempate por plataforma={fonte_plataforma}"

    # Ainda ambiguo — NAO resolver
    return None, f"ambiguo ({len(candidatos)} candidatos)"


def tentar_resolver_wine(vid, cids, l, lc, lojas_por_nome, domain_to_store):
    """
    Tenta resolver UM wine percorrendo TODOS os clean_ids e TODAS as fontes.
    Retorna (insert_dict, None) se achou, ou (None, motivos_coletados) se esgotou tudo.

    Regra: so aceita URLs RELATIVAS com loja resolvida. Ignora absolutas (outro bucket).
    """
    motivos = defaultdict(int)

    for cid in cids:
        l.execute("SELECT pais_tabela, id_original, nome_original FROM wines_clean WHERE id = %s", (cid,))
        row = l.fetchone()
        if not row or not row[0] or not re.match(r"^[a-z]{2}$", row[0]):
            motivos["clean_id sem pais valido"] += 1
            continue
        pais, id_orig, nome_orig = row

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

            # Pular URLs absolutas — esse script so trata relativas
            if not is_url_relativa(url):
                motivos["URL absoluta (fora do escopo bucket 1)"] += 1
                continue

            # URL relativa — precisa de dados_extras.loja
            loja_nome = None
            if extras and isinstance(extras, dict):
                loja_nome = extras.get("loja", "").strip()

            if not loja_nome:
                motivos["URL relativa sem dados_extras.loja"] += 1
                continue

            loja_match, criterio = resolver_loja(loja_nome, mercado, fonte, lojas_por_nome)

            if loja_match is None:
                motivos[f"loja: {criterio}"] += 1
                continue

            # Extrair dominio robusto
            dom = extrair_dominio(loja_match["url"])
            if not dom:
                motivos["dominio nao extraivel da loja"] += 1
                continue

            store_id = domain_to_store.get(dom)
            if not store_id:
                motivos[f"dominio resolvido mas nao em stores ({dom})"] += 1
                continue

            # SUCESSO — montar insert
            url_absoluta = f"https://{dom}{url}"
            return {
                "render_wine_id": vid,
                "clean_id": cid,
                "pais": pais,
                "loja_resolvida": loja_nome,
                "dominio": dom,
                "url_relativa": url,
                "url_absoluta": url_absoluta,
                "store_id": store_id,
                "preco": preco,
                "moeda": moeda,
                "criterio": criterio,
            }, None

    # Esgotou tudo
    return None, motivos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--executar", action="store_true", help="Executar INSERTs (default: dry-run)")
    args = parser.parse_args()

    is_dry_run = not args.executar

    print("=" * 80)
    print("CORRECAO MATCHED BUCKET 1: URL relativa + loja unica + store existe")
    if is_dry_run:
        print("MODO: DRY-RUN (nenhum INSERT sera feito)")
    else:
        print("MODO: EXECUCAO REAL")
    print("=" * 80)

    # ── Conexoes ──────────────────────────────────────────────────────────────
    print("\nConectando...")
    lc = psycopg2.connect(**LOCAL_DB)
    rc = psycopg2.connect(
        RENDER_DB,
        options="-c statement_timeout=300000",
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    l = lc.cursor()
    r = rc.cursor()

    # ── Carregar indices ──────────────────────────────────────────────────────
    print("Carregando indices...")

    l.execute("""
        SELECT id, nome, url_normalizada, pais_codigo, plataforma
        FROM lojas_scraping
        WHERE url_normalizada IS NOT NULL AND nome IS NOT NULL
    """)
    lojas_por_nome = defaultdict(list)
    for lid, nome, url, pais, plat in l.fetchall():
        key = normalizar_nome(nome)
        if key:
            lojas_por_nome[key].append({
                "id": lid, "url": url, "pais": pais, "plataforma": plat, "nome_orig": nome,
            })
    print(f"  lojas_scraping: {len(lojas_por_nome):,} nomes unicos")

    r.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
    domain_to_store = {row[0]: row[1] for row in r.fetchall()}
    print(f"  stores: {len(domain_to_store):,} dominios")

    # ── Passo 1: Achar matched sem source ─────────────────────────────────────
    print("\nPasso 1: Identificar matched sem source...")
    l.execute("""SELECT DISTINCT vivino_id FROM y2_results WHERE status = 'matched' AND vivino_id IS NOT NULL""")
    all_vids = [row[0] for row in l.fetchall()]

    sem_source_vids = []
    for i in range(0, len(all_vids), 1000):
        chunk = all_vids[i : i + 1000]
        r.execute(
            """SELECT w.id FROM unnest(%s::int[]) AS vid
               JOIN wines w ON w.id = vid
               WHERE NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)""",
            (chunk,),
        )
        sem_source_vids.extend([row[0] for row in r.fetchall()])
    print(f"  Matched sem source: {len(sem_source_vids)}")

    # ── Passo 2: Resolver cada wine (tentando TODAS fontes de TODOS clean_ids) ─
    print("Passo 2: Resolver URLs e stores (exaustivo)...")

    inserts = []
    motivos_globais = defaultdict(int)
    wines_rejeitados = 0

    for vid in sem_source_vids:
        l.execute("SELECT clean_id FROM y2_results WHERE vivino_id = %s AND status = 'matched'", (vid,))
        cids = [row[0] for row in l.fetchall()]

        resultado, motivos = tentar_resolver_wine(vid, cids, l, lc, lojas_por_nome, domain_to_store)

        if resultado:
            inserts.append(resultado)
        else:
            wines_rejeitados += 1
            if motivos:
                # Pegar o motivo dominante para este wine
                motivo_principal = max(motivos, key=motivos.get)
                motivos_globais[motivo_principal] += 1
            else:
                motivos_globais["sem clean_ids"] += 1

    # ── Passo 3: Relatorio ────────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print(f"RESULTADO")
    print(f"{'=' * 80}")
    print(f"\n  Matched sem source analisados:  {len(sem_source_vids)}")
    print(f"  Prontos para INSERT (bucket 1):  {len(inserts)}")
    print(f"  Rejeitados (apos esgotar tudo):  {wines_rejeitados}")
    print(f"  Esperado anterior:               150")
    print(f"  Diferenca:                       {len(inserts) - 150:+d}")
    print(f"\n  Motivos de rejeicao (motivo dominante por wine):")
    for motivo in sorted(motivos_globais, key=lambda x: -motivos_globais[x]):
        print(f"    {motivos_globais[motivo]:>5}  {motivo}")

    # ── Passo 4: CSV ──────────────────────────────────────────────────────────
    print(f"\n  Gerando CSV: {CSV_PATH}")
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "render_wine_id", "clean_id", "pais", "loja_resolvida", "dominio",
            "url_relativa", "url_absoluta", "store_id", "preco", "moeda", "criterio",
        ])
        writer.writeheader()
        for row in inserts:
            writer.writerow(row)
    print(f"  CSV escrito: {len(inserts)} linhas")

    # ── Passo 5: 20 exemplos auditaveis ───────────────────────────────────────
    print(f"\n{'=' * 80}")
    print(f"20 EXEMPLOS AUDITAVEIS")
    print(f"{'=' * 80}")

    for i, e in enumerate(inserts[:20], 1):
        r.execute("SELECT nome, produtor FROM wines WHERE id = %s", (e["render_wine_id"],))
        wine = r.fetchone()
        wine_nome = f"{wine[1]} - {(wine[0] or '')[:40]}" if wine else "???"

        print(f"\n  [{i:>2}] wine_id={e['render_wine_id']} | {wine_nome}")
        print(f"       clean_id={e['clean_id']} | pais={e['pais']}")
        print(f"       loja: {e['loja_resolvida']}")
        print(f"       dominio: {e['dominio']} -> store_id={e['store_id']}")
        print(f"       URL relativa:  {e['url_relativa'][:70]}")
        print(f"       URL absoluta:  {e['url_absoluta'][:70]}")
        print(f"       preco: {e['preco']} {e['moeda']}")
        print(f"       criterio: {e['criterio']}")

    # ── Passo 6: Contagem final ───────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print(f"CONTAGEM FINAL")
    print(f"{'=' * 80}")
    print(f"  INSERTs esperados:  {len(inserts)}")

    # Verificar duplicatas
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

    # ── Passo 7: Executar (se --executar) ─────────────────────────────────────
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
            r.execute("SAVEPOINT correcao_bucket1")
            execute_values(
                r,
                """INSERT INTO wine_sources
                       (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
                   VALUES %s
                   ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING""",
                values,
            )
            inseridos = r.rowcount
            r.execute("RELEASE SAVEPOINT correcao_bucket1")
            rc.commit()
            print(f"  INSERTs realizados: {inseridos}")
        except Exception as ex:
            print(f"  ERRO: {ex}")
            r.execute("ROLLBACK TO SAVEPOINT correcao_bucket1")
            rc.commit()
            print(f"  Rollback feito. Nenhum dado alterado.")
            l.close(); lc.close(); r.close(); rc.close()
            return

        # Validacao pos-execucao
        r.execute("""
            SELECT COUNT(*) FROM wines w
            WHERE w.vivino_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)
            AND w.id = ANY(%s)
        """, ([e["render_wine_id"] for e in inserts],))
        ainda_sem = r.fetchone()[0]
        print(f"\n  Validacao:")
        print(f"    Wines corrigidos:    {len(inserts) - ainda_sem}")
        print(f"    Ainda sem source:    {ainda_sem}")

    l.close(); lc.close()
    r.close(); rc.close()
    print("\nFim.")


if __name__ == "__main__":
    main()
