"""
Recriar wine_sources faltantes para ~76,812 vinhos novos no Render.

Causa: check_exists_in_render redirecionou links para wines errados.
Solucao: hash_dedup direto, sem check_exists_in_render.

Uso:
    python recriar_wine_sources_faltantes.py --piloto        # 500 wines, execucao real
    python recriar_wine_sources_faltantes.py --piloto --dry-run  # 500 wines, sem INSERT
    python recriar_wine_sources_faltantes.py                 # todos os ~76K wines
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import execute_values
import os
import _env

# ── Conexoes ──────────────────────────────────────────────────────────────────

LOCAL_DB = dict(
    host="localhost",
    port=5432,
    dbname="winegod_db",
    user="postgres",
    password="postgres123",
)

RENDER_DB = os.environ["DATABASE_URL"]


def conectar_render():
    return psycopg2.connect(
        RENDER_DB,
        options="-c statement_timeout=120000",
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )


def conectar_local():
    return psycopg2.connect(**LOCAL_DB)


def get_domain(url):
    try:
        d = urlparse(url).netloc
        return d.replace("www.", "") if d else None
    except Exception:
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main(args):
    print("Conectando ao banco LOCAL...")
    local_conn = conectar_local()
    local_cur = local_conn.cursor()

    print("Conectando ao banco RENDER...")
    render_conn = conectar_render()
    render_cur = render_conn.cursor()

    # ── Passo 0: Validacao pre-execucao ──────────────────────────────────────

    print("\n=== PASSO 0: Validacao pre-execucao ===")

    render_cur.execute("""
        SELECT COUNT(*) FROM wines w
        WHERE w.vivino_id IS NULL
        AND NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)
    """)
    wines_sem_source_count = render_cur.fetchone()[0]
    print(f"Wines novos sem source (Render): {wines_sem_source_count:,}")

    render_cur.execute("SELECT COUNT(*) FROM stores WHERE dominio IS NOT NULL")
    stores_count = render_cur.fetchone()[0]
    print(f"Stores com dominio (Render):     {stores_count:,}")

    local_cur.execute("SELECT COUNT(*) FROM wines_clean")
    wines_clean_count = local_cur.fetchone()[0]
    print(f"wines_clean (Local):             {wines_clean_count:,}")

    # Checar divergencia >20%
    esperado_sem_source = 76812
    esperado_stores = 19881
    esperado_clean = 3962334

    divergencias = []
    if abs(wines_sem_source_count - esperado_sem_source) / esperado_sem_source > 0.20:
        divergencias.append(f"wines_sem_source: {wines_sem_source_count:,} (esperado ~{esperado_sem_source:,})")
    if abs(stores_count - esperado_stores) / esperado_stores > 0.20:
        divergencias.append(f"stores: {stores_count:,} (esperado ~{esperado_stores:,})")
    if abs(wines_clean_count - esperado_clean) / esperado_clean > 0.20:
        divergencias.append(f"wines_clean: {wines_clean_count:,} (esperado ~{esperado_clean:,})")

    if divergencias:
        print("\n*** DIVERGENCIA >20% DETECTADA ***")
        for d in divergencias:
            print(f"  - {d}")
        print("PARANDO. Verifique os dados antes de continuar.")
        sys.exit(1)

    # ── Passo 1: Carregar domain_to_store do Render ──────────────────────────

    print("\n=== PASSO 1: Carregar domain_to_store ===")
    render_cur.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
    domain_to_store = {row[0]: row[1] for row in render_cur.fetchall()}
    print(f"Stores carregadas: {len(domain_to_store):,}")

    # ── Passo 2: Buscar wines sem source ─────────────────────────────────────

    print("\n=== PASSO 2: Buscar wines novos sem source ===")
    query = """
        SELECT w.id, w.hash_dedup
        FROM wines w
        WHERE w.vivino_id IS NULL
        AND w.hash_dedup IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)
        ORDER BY w.id
    """
    if args.piloto:
        query += " LIMIT 500"
        print("(MODO PILOTO: limitado a 500 wines)")
    elif args.limite > 0:
        query += f" LIMIT {args.limite}"
        print(f"(LIMITE: {args.limite:,} wines)")

    render_cur.execute(query)
    wines_sem_source = render_cur.fetchall()
    print(f"Wines a processar: {len(wines_sem_source):,}")

    if not wines_sem_source:
        print("Nenhum wine sem source encontrado. Nada a fazer.")
        local_cur.close()
        local_conn.close()
        render_cur.close()
        render_conn.close()
        return

    # ── Passo 3: Carregar hash_to_origins filtrado ───────────────────────────

    print("\n=== PASSO 3: Resolver hashes no banco local ===")
    hashes_necessarios = [h for _, h in wines_sem_source]
    print(f"Hashes a resolver: {len(hashes_necessarios):,}")

    hash_to_origins = {}
    for i in range(0, len(hashes_necessarios), 5000):
        chunk = hashes_necessarios[i : i + 5000]
        local_cur.execute(
            """
            SELECT hash_dedup, pais_tabela, id_original
            FROM wines_clean
            WHERE hash_dedup = ANY(%s) AND id_original IS NOT NULL
            """,
            (chunk,),
        )
        for hdp, pais, id_orig in local_cur.fetchall():
            if hdp not in hash_to_origins:
                hash_to_origins[hdp] = []
            hash_to_origins[hdp].append((pais, id_orig))

    print(f"Hashes resolvidos: {len(hash_to_origins):,}")

    # ── Passo 4: Processar em batches ────────────────────────────────────────

    print(f"\n=== PASSO 4: Processar em batches de {args.batch_size} ===")
    if args.dry_run:
        print("*** DRY RUN: nenhum INSERT sera realizado ***")

    BATCH_SIZE = args.batch_size
    ts = datetime.now(timezone.utc)

    total = len(wines_sem_source)
    processados = 0
    hash_resolvidos = 0
    sem_hash_local = 0
    sem_fonte_local = 0
    tabela_inexistente = 0
    sem_store = 0
    links_tentados = 0
    links_inseridos_aprox = 0
    erros_batch = 0
    erros_linha = 0

    for batch_start in range(0, total, BATCH_SIZE):
        batch = wines_sem_source[batch_start : batch_start + BATCH_SIZE]
        ws_values = []

        for render_wine_id, hash_dedup in batch:
            processados += 1

            # 4a. Resolver hash no local
            origins = hash_to_origins.get(hash_dedup)
            if origins is None:
                sem_hash_local += 1
                continue
            hash_resolvidos += 1

            # 4b. Para cada origem, buscar fontes
            wine_tem_fonte = False
            for pais_tabela, id_original in origins:
                if not pais_tabela or not re.match(r"^[a-z]{2}$", pais_tabela):
                    tabela_inexistente += 1
                    continue
                tabela_fontes = f"vinhos_{pais_tabela}_fontes"
                try:
                    local_cur.execute(
                        f"SELECT url_original, preco, moeda FROM {tabela_fontes} WHERE vinho_id = %s AND url_original IS NOT NULL",
                        (id_original,),
                    )
                    fontes = local_cur.fetchall()
                except Exception as e:
                    local_conn.rollback()
                    tabela_inexistente += 1
                    continue

                if not fontes:
                    continue
                wine_tem_fonte = True

                # 4c. Para cada fonte, resolver store e montar valor
                for url, preco, moeda in fontes:
                    if not url:
                        continue
                    dominio = get_domain(url)
                    if not dominio:
                        continue
                    store_id = domain_to_store.get(dominio)
                    if not store_id:
                        sem_store += 1
                        continue

                    ws_values.append(
                        (render_wine_id, store_id, url, preco, moeda, True, ts, ts)
                    )
                    links_tentados += 1

            if not wine_tem_fonte:
                sem_fonte_local += 1

        # 4d. INSERT batch com SAVEPOINT e fallback granular
        if ws_values and not args.dry_run:
            try:
                render_cur.execute("SAVEPOINT batch_sp")
                execute_values(
                    render_cur,
                    """
                    INSERT INTO wine_sources
                        (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
                    VALUES %s
                    ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING
                    """,
                    ws_values,
                )
                links_inseridos_aprox += render_cur.rowcount
                render_cur.execute("RELEASE SAVEPOINT batch_sp")
                render_conn.commit()
            except Exception as e:
                print(f"  ERRO batch {batch_start}: {e}")
                render_cur.execute("ROLLBACK TO SAVEPOINT batch_sp")
                render_conn.commit()
                erros_batch += 1

                # Fallback: inserir linha a linha
                print(f"  Fallback: inserindo {len(ws_values)} linhas individualmente...")
                for row in ws_values:
                    try:
                        render_cur.execute("SAVEPOINT row_sp")
                        render_cur.execute(
                            """
                            INSERT INTO wine_sources
                                (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING
                            """,
                            row,
                        )
                        links_inseridos_aprox += render_cur.rowcount
                        render_cur.execute("RELEASE SAVEPOINT row_sp")
                    except Exception as e2:
                        render_cur.execute("ROLLBACK TO SAVEPOINT row_sp")
                        erros_linha += 1
                render_conn.commit()

        # Log de progresso
        if processados % 5000 == 0 or processados == total:
            dry_tag = " [DRY RUN]" if args.dry_run else ""
            print(
                f"  {processados:,}/{total:,}"
                f" | hash_ok={hash_resolvidos:,}"
                f" | sem_hash={sem_hash_local:,}"
                f" | sem_fonte={sem_fonte_local:,}"
                f" | sem_store={sem_store:,}"
                f" | inseridos~={links_inseridos_aprox:,}"
                f" | erros_batch={erros_batch:,}"
                f" | erros_linha={erros_linha:,}"
                f"{dry_tag}"
            )

    # ── Validacao de sanidade (piloto) ───────────────────────────────────────

    if args.piloto:
        print("\n=== VALIDACAO PILOTO ===")
        ratio_hash = hash_resolvidos / processados if processados else 0
        ratio_sem_fonte = sem_fonte_local / processados if processados else 0
        print(f"hash_resolvidos/processados: {ratio_hash:.2%} (esperado >= 90%)")
        print(f"sem_fonte_local/processados: {ratio_sem_fonte:.2%} (esperado <= 10%)")
        print(f"erros_batch: {erros_batch} (esperado: 0)")

        problemas = []
        if ratio_hash < 0.90:
            problemas.append(f"hash_resolvidos muito baixo: {ratio_hash:.2%}")
        if ratio_sem_fonte > 0.10:
            problemas.append(f"sem_fonte_local muito alto: {ratio_sem_fonte:.2%}")
        if erros_batch > 0:
            problemas.append(f"erros_batch > 0: {erros_batch}")

        if problemas:
            print("\n*** PILOTO COM PROBLEMAS ***")
            for p in problemas:
                print(f"  - {p}")
            print("INVESTIGUE antes de rodar completo.")
        else:
            print("\nPiloto OK. Pode rodar completo com autorizacao do usuario.")

    # ── Passo 5: Resumo final ────────────────────────────────────────────────

    modo = "DRY RUN — nenhum insert realizado" if args.dry_run else "EXECUCAO REAL"
    print(f"""
=== RESULTADO FINAL ({modo}) ===
Processados:          {processados:,}
Hash resolvidos:      {hash_resolvidos:,}
Sem hash local:       {sem_hash_local:,}
Sem fonte local:      {sem_fonte_local:,}
Tabela inexistente:   {tabela_inexistente:,}
Sem store:            {sem_store:,}
Links tentados:       {links_tentados:,}
Links inseridos (~):  {links_inseridos_aprox:,}  (rowcount aproximado)
Erros de batch:       {erros_batch:,}
Erros de linha:       {erros_linha:,}
""")

    # ── Passo 6: Validacao pos-execucao ──────────────────────────────────────

    if not args.dry_run:
        print("=== PASSO 6: Validacao pos-execucao ===")
        render_cur.execute("""
            SELECT COUNT(*) FROM wines w
            WHERE w.vivino_id IS NULL
            AND NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)
        """)
        sem_source_depois = render_cur.fetchone()[0]
        print(f"Wines novos sem source ANTES:  {wines_sem_source_count:,}")
        print(f"Wines novos sem source DEPOIS: {sem_source_depois:,}")
        print(f"Delta (corrigidos):            {wines_sem_source_count - sem_source_depois:,}")

        render_cur.execute("""
            SELECT COUNT(*) FROM wine_sources ws
            JOIN wines w ON w.id = ws.wine_id
            WHERE w.vivino_id IS NULL
        """)
        print(f"Wine sources de novos DEPOIS:  {render_cur.fetchone()[0]:,}")
    else:
        print("DRY RUN: validacao pos-execucao pulada (nenhum insert foi realizado)")

    # ── Cleanup ──────────────────────────────────────────────────────────────

    local_cur.close()
    local_conn.close()
    render_cur.close()
    render_conn.close()
    print("\nConexoes fechadas. Fim.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recriar wine_sources faltantes no Render")
    parser.add_argument("--piloto", action="store_true", help="Roda apenas para 500 wines")
    parser.add_argument("--limite", type=int, default=0, help="Limitar a N wines (0 = sem limite)")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem INSERT")
    parser.add_argument("--batch-size", type=int, default=500, help="Tamanho do batch (default: 500)")
    args = parser.parse_args()
    main(args)
