"""
Demanda 3 -- Extract operacional da cauda Vivino (wines com vivino_id IS NULL).

READ-ONLY. Nenhuma escrita em producao.

Uso:
  python scripts/extract_tail_base.py

Artefatos gerados:
  reports/tail_base_extract_2026-04-10.csv.gz
  reports/tail_base_summary_2026-04-10.md

Estrategia:
  1. Agrega wine_sources por wine_id no servidor (GROUP BY) e baixa o
     resultado por cursor server-side com fetchmany. Carrega no Python
     {wine_id: (count, distinct_stores)}. Memoria estimada ~150MB.
  2. Faz stream da cauda (wines WHERE vivino_id IS NULL) por cursor
     server-side, faz LEFT JOIN com a agregacao em memoria, escreve
     CSV.gz incrementalmente.
  3. Roda QA cruzando totais com Etapa 1 (snapshot oficial).
  4. Verifica semantica de wines.total_fontes vs contagem live.

Propriedades:
  - idempotente (sobrescreve artefatos)
  - sem loop por item (agregacao previa, LEFT JOIN em memoria)
  - retry em SSL drop transitorio
  - nunca chama rollback() em conexao fechada
"""

import csv
import gzip
import os
import sys
import time
import psycopg2
from datetime import datetime

# --------------- configuracao ---------------

MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 2

# Numeros oficiais da Etapa 1 (para QA cruzado)
ETAPA1 = {
    "wines_sem_vivino_id":  779_383,
    "cauda_sem_sources":      8_071,
    "cauda_com_sources":    771_312,
}

# --------------- conexoes ---------------

def get_render_url():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))
            url = os.getenv("DATABASE_URL", "")
        except Exception:
            pass
    return url


def connect_render():
    url = get_render_url()
    if not url:
        raise RuntimeError("DATABASE_URL nao encontrada (.env ou env var).")
    return psycopg2.connect(
        url,
        options='-c statement_timeout=300000',
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        connect_timeout=30,
    )


def safe_close(conn):
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass


# --------------- helpers ---------------

def fmt(n):
    if n is None:
        return "ERRO"
    return f"{n:,}"


# --------------- etapa 1: agregacao wine_sources ---------------

def fetch_wine_sources_agg():
    """
    Roda no servidor:
        SELECT wine_id, COUNT(*), COUNT(DISTINCT store_id)
        FROM wine_sources
        GROUP BY wine_id
    Resultado vem por cursor server-side em batches de 50k.
    Retorna dict {wine_id: (count, distinct_stores)}.
    Retry em SSL drop. Reaborda do zero em cada tentativa.
    """
    print("[1/3] Agregando wine_sources por wine_id (server-side)...")
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        conn = None
        agg = {}
        try:
            conn = connect_render()
            cur = conn.cursor(name=f'ws_agg_{attempt}_{int(time.time())}')
            cur.itersize = 50_000
            cur.execute("""
                SELECT wine_id, COUNT(*), COUNT(DISTINCT store_id)
                FROM wine_sources
                GROUP BY wine_id
            """)
            total = 0
            while True:
                rows = cur.fetchmany(50_000)
                if not rows:
                    break
                for wid, cnt, dscnt in rows:
                    agg[wid] = (cnt, dscnt)
                total += len(rows)
                print(f"      ... {total:,} grupos lidos")
            cur.close()
            conn.close()
            print(f"    OK: {len(agg):,} wine_ids com sources")
            return agg
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_error = e
            print(f"    tentativa {attempt}/{MAX_RETRIES} falhou (conexao): {type(e).__name__}: {e}")
            safe_close(conn)
            agg = {}
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SEC * attempt)
        except Exception as e:
            last_error = e
            print(f"    erro nao-transitorio: {type(e).__name__}: {e}")
            safe_close(conn)
            break
    raise RuntimeError(f"fetch_wine_sources_agg falhou apos {MAX_RETRIES} tentativas. Ultimo erro: {last_error}")


# --------------- etapa 2: stream cauda + escreve CSV ---------------

CSV_HEADER = [
    "render_wine_id",
    "nome",
    "produtor",
    "safra",
    "tipo",
    "preco_min",
    "moeda",
    "wine_sources_count_live",
    "stores_count_live",
    "has_sources",
    "no_source_flag",
    "total_fontes_raw",  # valor cru de wines.total_fontes (para QA, nao para uso operacional)
]


def stream_cauda_to_csv(agg, csv_path):
    """
    Stream wines WHERE vivino_id IS NULL (cauda) por cursor server-side,
    LEFT JOIN com agg em memoria, escreve CSV.gz incremental.

    Retorna stats: (rows_written, ids_seen_set, totals).
    """
    print("[2/3] Streaming cauda para CSV.gz...")
    sql = """
        SELECT id, nome, produtor, safra, tipo, preco_min, moeda, total_fontes
        FROM wines
        WHERE vivino_id IS NULL
        ORDER BY id
    """

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        conn = None
        rows_written = 0
        ids_seen = set()
        sum_has_sources = 0
        sum_no_source = 0
        invalid_stores_gt_count = 0  # stores_count > sources_count (invariante violada)
        total_fontes_match = 0
        total_fontes_mismatch = 0
        total_fontes_null = 0
        try:
            conn = connect_render()
            cur = conn.cursor(name=f'cauda_stream_{attempt}_{int(time.time())}')
            cur.itersize = 25_000
            cur.execute(sql)

            with gzip.open(csv_path, 'wt', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADER)
                while True:
                    rows = cur.fetchmany(25_000)
                    if not rows:
                        break
                    for row in rows:
                        wid, nome, produtor, safra, tipo, preco_min, moeda, total_fontes = row
                        wsc, stc = agg.get(wid, (0, 0))
                        has = 1 if wsc > 0 else 0
                        no = 0 if has else 1

                        # invariante: stores <= wine_sources
                        if stc > wsc:
                            invalid_stores_gt_count += 1

                        # comparacao total_fontes_raw vs live
                        if total_fontes is None:
                            total_fontes_null += 1
                        elif total_fontes == wsc:
                            total_fontes_match += 1
                        else:
                            total_fontes_mismatch += 1

                        writer.writerow([
                            wid, nome, produtor, safra, tipo,
                            preco_min if preco_min is not None else "",
                            moeda if moeda is not None else "",
                            wsc, stc, has, no,
                            total_fontes if total_fontes is not None else "",
                        ])
                        rows_written += 1
                        ids_seen.add(wid)
                        sum_has_sources += has
                        sum_no_source += no

                    if rows_written % 100_000 == 0 or rows_written < 100_000:
                        print(f"      ... {rows_written:,} linhas escritas")

            cur.close()
            conn.close()
            print(f"    OK: {rows_written:,} linhas no CSV")
            return {
                "rows_written": rows_written,
                "ids_seen_count": len(ids_seen),
                "sum_has_sources": sum_has_sources,
                "sum_no_source": sum_no_source,
                "invalid_stores_gt_count": invalid_stores_gt_count,
                "total_fontes_match": total_fontes_match,
                "total_fontes_mismatch": total_fontes_mismatch,
                "total_fontes_null": total_fontes_null,
            }
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_error = e
            print(f"    tentativa {attempt}/{MAX_RETRIES} falhou (conexao): {type(e).__name__}: {e}")
            safe_close(conn)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SEC * attempt)
        except Exception as e:
            last_error = e
            print(f"    erro nao-transitorio: {type(e).__name__}: {e}")
            safe_close(conn)
            break
    raise RuntimeError(f"stream_cauda_to_csv falhou apos {MAX_RETRIES} tentativas. Ultimo erro: {last_error}")


# --------------- etapa 3: gerar summary ---------------

def render_summary(stats, agg, csv_path, summary_path, ts):
    rows_written = stats["rows_written"]
    ids_seen_count = stats["ids_seen_count"]
    sum_has = stats["sum_has_sources"]
    sum_no = stats["sum_no_source"]
    invalid = stats["invalid_stores_gt_count"]
    tf_match = stats["total_fontes_match"]
    tf_mismatch = stats["total_fontes_mismatch"]
    tf_null = stats["total_fontes_null"]

    # checks
    check_total_rows = (rows_written == ETAPA1["wines_sem_vivino_id"])
    check_unique_ids = (ids_seen_count == rows_written)
    check_no_source = (sum_no == ETAPA1["cauda_sem_sources"])
    check_has_sources = (sum_has == ETAPA1["cauda_com_sources"])
    check_invariant = (invalid == 0)
    check_disjoint = (sum_has + sum_no == rows_written)
    check_no_vivino = True  # sera verificado por amostragem abaixo

    all_ok = all([
        check_total_rows, check_unique_ids, check_no_source,
        check_has_sources, check_invariant, check_disjoint,
    ])

    # Decisao sobre total_fontes_raw
    tf_total_non_null = tf_match + tf_mismatch
    if tf_total_non_null > 0:
        tf_match_pct = tf_match / tf_total_non_null * 100
    else:
        tf_match_pct = 0.0

    if tf_null == rows_written:
        tf_status = "BLOQUEADO -- 100% NULL"
        tf_decision = "wines.total_fontes nao tem valor populado em nenhum item da cauda. Coluna inutilizavel para esta etapa. Use wine_sources_count_live."
    elif tf_match == tf_total_non_null and tf_total_non_null > 0:
        tf_status = "VERIFICADO"
        tf_decision = f"wines.total_fontes bate exatamente com COUNT(*) FROM wine_sources em 100% dos casos nao-nulos ({fmt(tf_match)}/{fmt(tf_total_non_null)}). Semantica verificada: total_fontes = numero de wine_sources do wine_id. Mas a coluna esta NULL em {fmt(tf_null)} itens, entao use wine_sources_count_live como fonte primaria."
    elif tf_match_pct >= 95:
        tf_status = "PARCIAL -- alta concordancia"
        tf_decision = f"wines.total_fontes bate com COUNT(*) FROM wine_sources em {tf_match_pct:.2f}% dos casos nao-nulos ({fmt(tf_match)}/{fmt(tf_total_non_null)}). Discrepancia em {fmt(tf_mismatch)} itens, NULL em {fmt(tf_null)}. NAO usar como fonte primaria; usar wine_sources_count_live."
    else:
        tf_status = "BLOQUEADO -- semantica nao verificada"
        tf_decision = f"wines.total_fontes diverge da contagem live em {fmt(tf_mismatch)} de {fmt(tf_total_non_null)} casos nao-nulos ({100-tf_match_pct:.2f}% de discrepancia). Semantica nao confirmada. NAO usar. Usar wine_sources_count_live."

    lines = []
    lines.append("# Tail Base Extract -- Summary (Demanda 3)")
    lines.append("")
    lines.append(f"Data execucao: {ts}")
    lines.append("Executor: `scripts/extract_tail_base.py`")
    lines.append("Fonte: Render (live, read-only)")
    lines.append(f"Artefato CSV: `{os.path.basename(csv_path)}` (gzip)")
    lines.append("")

    lines.append("## Proveniencia")
    lines.append("")
    lines.append("- Banco: Render PostgreSQL (DATABASE_URL via backend/.env)")
    lines.append("- Modo: read-only, nenhuma escrita feita")
    lines.append("- Conexao: psycopg2 com keepalives e statement_timeout=300s")
    lines.append("- Estrategia: agregacao server-side de wine_sources (`GROUP BY wine_id`) +")
    lines.append("  cursor server-side da cauda (`WHERE vivino_id IS NULL`) com LEFT JOIN em memoria")
    lines.append("- Sem loop por item, sem consulta por wine_id")
    lines.append("")

    lines.append("## Conteudo do Extract")
    lines.append("")
    lines.append(f"- Total de linhas: **{fmt(rows_written)}**")
    lines.append(f"- render_wine_id distintos: **{fmt(ids_seen_count)}**")
    lines.append(f"- has_sources = 1: **{fmt(sum_has)}**")
    lines.append(f"- no_source_flag = 1: **{fmt(sum_no)}**")
    lines.append("")

    lines.append("## Colunas do CSV")
    lines.append("")
    lines.append("| coluna | origem | definicao |")
    lines.append("|---|---|---|")
    lines.append("| `render_wine_id` | `wines.id` | chave primaria do vinho no Render |")
    lines.append("| `nome` | `wines.nome` | nome do vinho (raw) |")
    lines.append("| `produtor` | `wines.produtor` | produtor (raw) |")
    lines.append("| `safra` | `wines.safra` | safra (varchar) |")
    lines.append("| `tipo` | `wines.tipo` | tipo (tinto/branco/etc) |")
    lines.append("| `preco_min` | `wines.preco_min` | preco minimo registrado em wines (numeric) |")
    lines.append("| `moeda` | `wines.moeda` | moeda associada ao preco_min |")
    lines.append("| `wine_sources_count_live` | `COUNT(*) FROM wine_sources WHERE wine_id = w.id` | numero de linhas em wine_sources para esse wine, contado live nesta execucao |")
    lines.append("| `stores_count_live` | `COUNT(DISTINCT store_id) FROM wine_sources WHERE wine_id = w.id` | numero de stores distintas que tem esse wine, contado live |")
    lines.append("| `has_sources` | derivado | `1` se `wine_sources_count_live > 0`, senao `0` |")
    lines.append("| `no_source_flag` | derivado | `1` se `wine_sources_count_live = 0`, senao `0` |")
    lines.append("| `total_fontes_raw` | `wines.total_fontes` | valor cru da coluna no Render. **Nao usar como fonte primaria.** Ver secao total_fontes abaixo. |")
    lines.append("")

    lines.append("## QA -- Cruzamento com Etapa 1")
    lines.append("")
    lines.append("| check | esperado (Etapa 1) | obtido (Demanda 3) | resultado |")
    lines.append("|---|---|---|---|")
    lines.append(f"| total de linhas do extract | {fmt(ETAPA1['wines_sem_vivino_id'])} | {fmt(rows_written)} | {'OK' if check_total_rows else 'FALHOU'} |")
    lines.append(f"| render_wine_id unicos = total | {fmt(rows_written)} | {fmt(ids_seen_count)} | {'OK' if check_unique_ids else 'FALHOU'} |")
    lines.append(f"| SUM(no_source_flag) | {fmt(ETAPA1['cauda_sem_sources'])} | {fmt(sum_no)} | {'OK' if check_no_source else 'FALHOU'} |")
    lines.append(f"| SUM(has_sources) | {fmt(ETAPA1['cauda_com_sources'])} | {fmt(sum_has)} | {'OK' if check_has_sources else 'FALHOU'} |")
    lines.append(f"| has + no = total (particao) | {fmt(rows_written)} | {fmt(sum_has + sum_no)} | {'OK' if check_disjoint else 'FALHOU'} |")
    lines.append(f"| stores_count_live <= wine_sources_count_live (invariante) | violacoes = 0 | violacoes = {fmt(invalid)} | {'OK' if check_invariant else 'FALHOU'} |")
    lines.append("")

    lines.append("## QA -- Filtro de cauda (vivino_id IS NULL)")
    lines.append("")
    lines.append("A query do extract usa `WHERE vivino_id IS NULL` no proprio SELECT, portanto **nenhum item do extract pode ter `vivino_id IS NOT NULL`** por construcao. Esta condicao e estrutural (filtro SQL), nao requer verificacao por amostragem.")
    lines.append("")

    lines.append("## QA -- total_fontes (decisao documentada)")
    lines.append("")
    lines.append(f"- itens com `total_fontes = wine_sources_count_live`: **{fmt(tf_match)}**")
    lines.append(f"- itens com `total_fontes != wine_sources_count_live`: **{fmt(tf_mismatch)}**")
    lines.append(f"- itens com `total_fontes IS NULL`: **{fmt(tf_null)}**")
    lines.append(f"- concordancia entre nao-nulos: **{tf_match_pct:.2f}%**")
    lines.append("")
    lines.append(f"**Status: {tf_status}**")
    lines.append("")
    lines.append(tf_decision)
    lines.append("")

    lines.append("## Veredito")
    lines.append("")
    if all_ok:
        lines.append("**EXTRACT VALIDO.** Todos os checks de QA passaram. A base operacional da cauda esta pronta para a proxima demanda (enriquecimento, candidatos, etc).")
    else:
        lines.append("**EXTRACT COM FALHAS DE QA.** Pelo menos um check nao bateu. Investigar antes de prosseguir.")
    lines.append("")

    lines.append("## Reexecucao")
    lines.append("")
    lines.append("```bash")
    lines.append("cd C:\\winegod-app")
    lines.append("python scripts/extract_tail_base.py")
    lines.append("```")
    lines.append("")
    lines.append("O script e idempotente: cada rodada sobrescreve `tail_base_extract_2026-04-10.csv.gz` e `tail_base_summary_2026-04-10.md`. Sem efeito colateral em producao.")
    lines.append("")

    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")

    return all_ok


# --------------- main ---------------

def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Demanda 3 -- Extract operacional da cauda -- {ts}")
    print("=" * 60)

    report_dir = os.path.join(os.path.dirname(__file__), '..', 'reports')
    os.makedirs(report_dir, exist_ok=True)
    csv_path = os.path.join(report_dir, 'tail_base_extract_2026-04-10.csv.gz')
    summary_path = os.path.join(report_dir, 'tail_base_summary_2026-04-10.md')

    # Etapa 1: agregacao
    agg = fetch_wine_sources_agg()

    # Etapa 2: stream da cauda + CSV
    stats = stream_cauda_to_csv(agg, csv_path)

    # Etapa 3: summary
    print("[3/3] Gerando summary...")
    all_ok = render_summary(stats, agg, csv_path, summary_path, ts)
    print(f"    OK: {summary_path}")

    print()
    print(f"CSV:     {csv_path}")
    print(f"Summary: {summary_path}")
    print()
    if all_ok:
        print("=== DEMANDA 3 COMPLETA -- QA OK ===")
    else:
        print("=== DEMANDA 3 COMPLETA -- QA COM FALHAS ===")
        sys.exit(2)


if __name__ == "__main__":
    main()
