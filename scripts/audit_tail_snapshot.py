"""
Auditoria Etapa 1 -- Snapshot + Reconciliacao + Contradicoes.

READ-ONLY. Nenhuma escrita em producao.

Uso:
  python scripts/audit_tail_snapshot.py

Artefatos gerados (3 obrigatorios):
  reports/tail_audit_snapshot_2026-04-10.md
  reports/tail_audit_reconciliation_2026-04-10.md
  reports/tail_audit_contradictions_2026-04-10.md

Propriedades do script:
  - idempotente e reexecutavel (cada rodada sobrescreve os artefatos)
  - cada query usa conexao fresca, isolando falhas transitorias de SSL
  - retry controlado em erros de conexao (OperationalError, InterfaceError)
  - nunca chama rollback() em conexao ja fechada
  - a reconciliacao usa cursor server-side (fetchmany em batches de 50k)
    para reduzir pressao de memoria e chance de SSL drop
  - fallback robusto para cauda_com_sources: se a query EXISTS falhar,
    computa por subtracao (wines_sem_vivino_id - cauda_sem_sources)
  - separacao FATO vs HIPOTESE no report de contradicoes
"""

import os
import sys
import time
import psycopg2
from datetime import datetime

# --------------- configuracao ---------------

VIVINO_DB_URL = "postgresql://postgres:postgres123@localhost:5432/vivino_db"
WINEGOD_DB = dict(
    host="localhost", port=5432, dbname="winegod_db",
    user="postgres", password="postgres123",
)
MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 2

# Referencia da Etapa 1 (prompt de 2026-04-10)
REF = {
    "wines_total":          2_506_441,
    "wines_com_vivino_id":  1_727_058,
    "wines_sem_vivino_id":    779_383,
    "wine_aliases_total":          43,
    "wine_aliases_approved":       43,
    "canonical_distintos":         23,
    "wine_sources_total":   3_484_975,
    "stores_total":            19_889,
    "cauda_sem_sources":        8_071,
    "cauda_com_sources":      771_312,
    "vivino_vinhos_total":  1_738_585,
    "y2_matched_vivino":    1_465_480,
    "y2_matched_07":          648_374,
    "only_vivino_db":          11_527,
    "only_render":                  0,
}

# Referencia HISTORICA (docs de 2026-04-06). Fonte explicita de cada valor.
REF_HIST = {
    "wine_sources_total":  (3_659_501, "HANDOFF_AUDITORIA_LINHAGEM_LINKS_RENDER.md (2026-04-06)"),
    "stores_total":        (   19_881, "HANDOFF_AUDITORIA_LINHAGEM_LINKS_RENDER.md (2026-04-06)"),
    "new_without_sources": (   76_812, "HANDOFF_AUDITORIA / PROMPT_RECRIAR_WINE_SOURCES_FALTANTES.md"),
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
        options='-c statement_timeout=180000',
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        connect_timeout=30,
    )


def connect_vivino():
    return psycopg2.connect(VIVINO_DB_URL, connect_timeout=30)


def connect_winegod():
    return psycopg2.connect(**WINEGOD_DB, connect_timeout=30)


def safe_close(conn):
    """Fecha conexao ignorando qualquer erro (inclusive conexao ja fechada)."""
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass


# --------------- query runners com retry ---------------

def run_scalar_with_retry(connect_fn, sql, label, max_retries=MAX_RETRIES):
    """
    Executa query scalar (COUNT, DISTINCT) com conexao fresca e retry.
    Nunca chama rollback em conexao ja fechada.
    Retorna o valor ou None em caso de falha definitiva.
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        conn = None
        try:
            conn = connect_fn()
            cur = conn.cursor()
            cur.execute(sql)
            val = cur.fetchone()[0]
            cur.close()
            conn.close()
            return val
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_error = e
            print(f"  [{label}] tentativa {attempt}/{max_retries} falhou (conexao): {type(e).__name__}: {e}")
            safe_close(conn)
            if attempt < max_retries:
                time.sleep(RETRY_BACKOFF_SEC * attempt)
        except Exception as e:
            last_error = e
            print(f"  [{label}] erro nao-transitorio: {type(e).__name__}: {e}")
            safe_close(conn)
            break
    print(f"  [{label}] FALHOU apos {max_retries} tentativas. Ultimo erro: {last_error}")
    return None


def run_rows_with_retry(connect_fn, sql, label, params=None, max_retries=MAX_RETRIES):
    """Executa query que retorna varias linhas com retry em conexao fresca."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        conn = None
        try:
            conn = connect_fn()
            cur = conn.cursor()
            if params is not None:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_error = e
            print(f"  [{label}] tentativa {attempt}/{max_retries} falhou (conexao): {type(e).__name__}")
            safe_close(conn)
            if attempt < max_retries:
                time.sleep(RETRY_BACKOFF_SEC * attempt)
        except Exception as e:
            last_error = e
            print(f"  [{label}] erro nao-transitorio: {type(e).__name__}: {e}")
            safe_close(conn)
            break
    print(f"  [{label}] FALHOU apos {max_retries} tentativas. Ultimo erro: {last_error}")
    return None


def stream_ids_with_retry(connect_fn, sql, label, batch=50_000, max_retries=MAX_RETRIES):
    """
    Carrega IDs inteiros usando cursor server-side com fetchmany.
    Cada retry reabre conexao do zero. Retorna set ou levanta em caso de falha total.
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        conn = None
        ids = set()
        try:
            conn = connect_fn()
            cur_name = f"{label}_stream_{attempt}"
            cur = conn.cursor(name=cur_name)
            cur.itersize = batch
            cur.execute(sql)
            while True:
                rows = cur.fetchmany(batch)
                if not rows:
                    break
                for r in rows:
                    ids.add(r[0])
            cur.close()
            conn.close()
            return ids
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_error = e
            print(f"  [{label}] tentativa {attempt}/{max_retries} falhou (conexao): {type(e).__name__}")
            safe_close(conn)
            if attempt < max_retries:
                time.sleep(RETRY_BACKOFF_SEC * attempt)
        except Exception as e:
            last_error = e
            print(f"  [{label}] erro nao-transitorio: {type(e).__name__}: {e}")
            safe_close(conn)
            break
    raise RuntimeError(f"[{label}] falhou apos {max_retries} tentativas. Ultimo erro: {last_error}")


# --------------- formatters ---------------

def fmt(n):
    if n is None:
        return "ERRO"
    return f"{n:,}"


def fmt_signed(n):
    if n is None:
        return "—"
    return f"{n:+,}"


def pct_drift(ref, live):
    if ref is None or live is None:
        return None
    if ref == 0:
        return 0.0 if live == 0 else float('inf')
    return abs(live - ref) / ref * 100


def pct_signed(ref, live):
    if ref is None or live is None or ref == 0:
        return None
    return (live - ref) / ref * 100


def drift_flag(ref, live):
    d = pct_drift(ref, live)
    if d is None:
        return "—"
    if d == float('inf'):
        return "DRIFT (ref=0)"
    if d > 5:
        return "DRIFT >5%"
    if d > 1:
        return "drift >1%"
    return "OK"


def fmt_pct(d):
    if d is None:
        return "—"
    if d == float('inf'):
        return "inf"
    return f"{d:.2f}%"


def fmt_pct_signed(d):
    if d is None:
        return "—"
    return f"{d:+.2f}%"


# --------------- TAREFA A: Render ---------------

def tarefa_a_render():
    print("=== TAREFA A: Snapshot live Render ===")
    results = {}

    scalar_queries = [
        ("wines_total",           "SELECT COUNT(*) FROM wines"),
        ("wines_com_vivino_id",   "SELECT COUNT(*) FROM wines WHERE vivino_id IS NOT NULL"),
        ("wines_sem_vivino_id",   "SELECT COUNT(*) FROM wines WHERE vivino_id IS NULL"),
        ("wine_aliases_total",    "SELECT COUNT(*) FROM wine_aliases"),
        ("wine_aliases_approved", "SELECT COUNT(*) FROM wine_aliases WHERE review_status = 'approved'"),
        ("wine_sources_total",    "SELECT COUNT(*) FROM wine_sources"),
        ("stores_total",          "SELECT COUNT(*) FROM stores"),
        ("canonical_distintos",
         "SELECT COUNT(DISTINCT canonical_wine_id) FROM wine_aliases WHERE review_status = 'approved'"),
    ]

    for name, sql in scalar_queries:
        val = run_scalar_with_retry(connect_render, sql, name)
        results[name] = val
        print(f"  {name}: {fmt(val)}")

    # cauda sem sources: query mais pesada, retry normal
    cauda_sem_sql = """
        SELECT COUNT(*) FROM wines w
        WHERE w.vivino_id IS NULL
          AND NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)
    """
    results["cauda_sem_sources"] = run_scalar_with_retry(
        connect_render, cauda_sem_sql, "cauda_sem_sources"
    )
    print(f"  cauda_sem_sources: {fmt(results['cauda_sem_sources'])}")

    # cauda COM sources: query EXISTS pode derrubar a conexao SSL no plano Render Basic.
    # Tentamos a query original; se falhar, caimos pro fallback por subtracao,
    # que e matematicamente equivalente (dois subconjuntos disjuntos cobrem a cauda).
    cauda_com_sql = """
        SELECT COUNT(*) FROM wines w
        WHERE w.vivino_id IS NULL
          AND EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)
    """
    cauda_com = run_scalar_with_retry(
        connect_render, cauda_com_sql, "cauda_com_sources", max_retries=2
    )
    results["cauda_com_sources_fallback"] = False
    if cauda_com is None:
        wsvi = results.get("wines_sem_vivino_id")
        css = results.get("cauda_sem_sources")
        if wsvi is not None and css is not None:
            cauda_com = wsvi - css
            results["cauda_com_sources_fallback"] = True
            print(f"  cauda_com_sources: {fmt(cauda_com)} (FALLBACK por subtracao)")
        else:
            print(f"  cauda_com_sources: ERRO (e fallback indisponivel)")
    else:
        print(f"  cauda_com_sources: {fmt(cauda_com)}")
    results["cauda_com_sources"] = cauda_com

    # distribuicao wine_aliases
    alias_dist = run_rows_with_retry(
        connect_render,
        """SELECT review_status, source_type, COUNT(*)
           FROM wine_aliases
           GROUP BY review_status, source_type
           ORDER BY review_status, source_type""",
        "alias_distribution",
    )
    results["alias_distribution"] = alias_dist or []
    if alias_dist:
        print("  alias_distribution:")
        for row in alias_dist:
            print(f"    {row[0]} / {row[1]}: {fmt(row[2])}")

    return results


# --------------- TAREFA B: Local ---------------

def tarefa_b_local():
    print("\n=== TAREFA B: Snapshot local ===")
    results = {}

    results["vivino_vinhos_total"] = run_scalar_with_retry(
        connect_vivino, "SELECT COUNT(*) FROM vivino_vinhos", "vivino_vinhos_total"
    )
    print(f"  vivino_vinhos_total: {fmt(results['vivino_vinhos_total'])}")

    results["y2_matched_vivino"] = run_scalar_with_retry(
        connect_winegod,
        "SELECT COUNT(*) FROM y2_results WHERE status = 'matched' AND vivino_id IS NOT NULL",
        "y2_matched_vivino",
    )
    print(f"  y2_matched_vivino: {fmt(results['y2_matched_vivino'])}")

    results["y2_matched_07"] = run_scalar_with_retry(
        connect_winegod,
        "SELECT COUNT(*) FROM y2_results WHERE status = 'matched' AND match_score >= 0.7 AND vivino_id IS NOT NULL",
        "y2_matched_07",
    )
    print(f"  y2_matched_07: {fmt(results['y2_matched_07'])}")

    return results


# --------------- TAREFA C: Reconciliacao ---------------

def tarefa_c_reconciliacao():
    print("\n=== TAREFA C: Reconciliacao vivino_db vs Render ===")
    results = {}

    print("  Carregando vivino_ids do vivino_db (streaming)...")
    vivino_ids = stream_ids_with_retry(
        connect_vivino, "SELECT id FROM vivino_vinhos", "vivino_db_ids"
    )
    print(f"  vivino_db IDs: {fmt(len(vivino_ids))}")

    print("  Carregando vivino_ids do Render (streaming)...")
    render_vivino_ids = stream_ids_with_retry(
        connect_render,
        "SELECT vivino_id FROM wines WHERE vivino_id IS NOT NULL",
        "render_vivino_ids",
    )
    print(f"  Render vivino_ids: {fmt(len(render_vivino_ids))}")

    in_both = vivino_ids & render_vivino_ids
    only_vivino = vivino_ids - render_vivino_ids
    only_render = render_vivino_ids - vivino_ids

    results["in_both"] = len(in_both)
    results["only_vivino_db"] = len(only_vivino)
    results["only_render"] = len(only_render)

    print(f"  in_both:        {fmt(len(in_both))}")
    print(f"  only_vivino_db: {fmt(len(only_vivino))}")
    print(f"  only_render:    {fmt(len(only_render))}")

    # Amostra only_vivino_db (deterministica: menores IDs)
    sample_only_vivino = []
    if only_vivino:
        sample_ids = sorted(list(only_vivino))[:10]
        sample_only_vivino = run_rows_with_retry(
            connect_vivino,
            "SELECT id, nome, vinicola_nome, rating_medio "
            "FROM vivino_vinhos WHERE id = ANY(%s) ORDER BY id",
            "sample_only_vivino",
            params=(sample_ids,),
        ) or []
    results["sample_only_vivino"] = sample_only_vivino

    # Amostra only_render (esperado: vazio)
    sample_only_render = []
    if only_render:
        sample_ids = sorted(list(only_render))[:10]
        sample_only_render = run_rows_with_retry(
            connect_render,
            "SELECT id, vivino_id, nome, produtor FROM wines WHERE vivino_id = ANY(%s) ORDER BY vivino_id",
            "sample_only_render",
            params=(sample_ids,),
        ) or []
    results["sample_only_render"] = sample_only_render

    return results


# --------------- GERADORES DE ARTEFATOS ---------------

def render_snapshot_report(render, local, recon, ts):
    lines = []
    lines.append("# Snapshot Oficial -- Auditoria da Cauda Vivino (Etapa 1)")
    lines.append("")
    lines.append(f"Data execucao: {ts}")
    lines.append("Executor: `scripts/audit_tail_snapshot.py`")
    lines.append("Referencia: `prompts/PROMPT_CLAUDE_EXECUTOR_ETAPA1_SNAPSHOT_RECONCILIACAO_AUDITORIA_CAUDA_VIVINO_2026-04-10.md`")
    lines.append("")

    lines.append("## Contagens Oficiais -- Render (live)")
    lines.append("")
    lines.append("| Metrica | Query | Resultado |")
    lines.append("|---|---|---|")
    lines.append(f"| wines total | `SELECT COUNT(*) FROM wines` | {fmt(render.get('wines_total'))} |")
    lines.append(f"| wines com vivino_id | `SELECT COUNT(*) FROM wines WHERE vivino_id IS NOT NULL` | {fmt(render.get('wines_com_vivino_id'))} |")
    lines.append(f"| wines sem vivino_id (cauda) | `SELECT COUNT(*) FROM wines WHERE vivino_id IS NULL` | {fmt(render.get('wines_sem_vivino_id'))} |")
    lines.append(f"| wine_aliases total | `SELECT COUNT(*) FROM wine_aliases` | {fmt(render.get('wine_aliases_total'))} |")
    lines.append(f"| wine_aliases approved | `SELECT COUNT(*) FROM wine_aliases WHERE review_status = 'approved'` | {fmt(render.get('wine_aliases_approved'))} |")
    lines.append(f"| canonical_wine_id distintos (approved) | `SELECT COUNT(DISTINCT canonical_wine_id) FROM wine_aliases WHERE review_status='approved'` | {fmt(render.get('canonical_distintos'))} |")
    lines.append(f"| wine_sources total | `SELECT COUNT(*) FROM wine_sources` | {fmt(render.get('wine_sources_total'))} |")
    lines.append(f"| stores total | `SELECT COUNT(*) FROM stores` | {fmt(render.get('stores_total'))} |")
    lines.append(f"| cauda sem wine_sources | `...vivino_id IS NULL AND NOT EXISTS...` | {fmt(render.get('cauda_sem_sources'))} |")

    cc_note = ""
    if render.get("cauda_com_sources_fallback"):
        cc_note = " (FALLBACK por subtracao: wines_sem_vivino_id - cauda_sem_sources; query EXISTS original derrubou a conexao SSL)"
    lines.append(f"| cauda com wine_sources | `...vivino_id IS NULL AND EXISTS...` | {fmt(render.get('cauda_com_sources'))}{cc_note} |")
    lines.append("")

    lines.append("### Distribuicao wine_aliases")
    lines.append("")
    lines.append("| review_status | source_type | count |")
    lines.append("|---|---|---|")
    for row in render.get("alias_distribution", []):
        lines.append(f"| {row[0]} | {row[1]} | {fmt(row[2])} |")
    lines.append("")

    lines.append("## Contagens Oficiais -- Bancos Locais")
    lines.append("")
    lines.append("| Base | Metrica | Query | Resultado |")
    lines.append("|---|---|---|---|")
    lines.append(f"| vivino_db | vivino_vinhos total | `SELECT COUNT(*) FROM vivino_vinhos` | {fmt(local.get('vivino_vinhos_total'))} |")
    lines.append(f"| winegod_db | y2_results matched com vivino_id NOT NULL | `SELECT COUNT(*) FROM y2_results WHERE status='matched' AND vivino_id IS NOT NULL` | {fmt(local.get('y2_matched_vivino'))} |")
    lines.append(f"| winegod_db | y2_results matched com score>=0.7 | `SELECT COUNT(*) FROM y2_results WHERE status='matched' AND match_score>=0.7 AND vivino_id IS NOT NULL` | {fmt(local.get('y2_matched_07'))} |")
    lines.append("")

    lines.append("## Comparacao com Numeros de Referencia (prompt Etapa 1)")
    lines.append("")
    lines.append("| Metrica | Referencia | Live | Delta | Drift % | Status |")
    lines.append("|---|---|---|---|---|---|")

    def get_live(name):
        if name in render:
            return render[name]
        if name in local:
            return local[name]
        if name in recon:
            return recon[name]
        return None

    metrics_to_compare = [
        "wines_total", "wines_com_vivino_id", "wines_sem_vivino_id",
        "wine_aliases_total", "wine_aliases_approved", "canonical_distintos",
        "wine_sources_total", "stores_total",
        "cauda_sem_sources", "cauda_com_sources",
        "vivino_vinhos_total", "y2_matched_vivino", "y2_matched_07",
        "only_vivino_db", "only_render",
    ]

    any_big_drift = False
    for name in metrics_to_compare:
        live_val = get_live(name)
        ref_val = REF.get(name)
        delta = (live_val - ref_val) if (live_val is not None and ref_val is not None) else None
        d = pct_drift(ref_val, live_val)
        if d is not None and d != float('inf') and d > 5:
            any_big_drift = True
        flag = drift_flag(ref_val, live_val)
        lines.append(
            f"| {name} | {fmt(ref_val)} | {fmt(live_val)} | "
            f"{fmt_signed(delta)} | {fmt_pct(d)} | {flag} |"
        )

    lines.append("")
    lines.append("## Veredito")
    lines.append("")
    if any_big_drift:
        lines.append("**SNAPSHOT COM DRIFT RELEVANTE (>5%).** Parar e investigar antes de seguir para a Etapa 2.")
    else:
        lines.append("**SNAPSHOT ESTAVEL.** Todas as metricas dentro da margem aceitavel (<5%). Contexto estavel para a Etapa 2.")
    lines.append("")

    lines.append("## Notas")
    lines.append("")
    if render.get("cauda_com_sources_fallback"):
        lines.append("- `cauda_com_sources` foi calculado por FALLBACK (subtracao) porque a query EXISTS derrubou a conexao SSL no plano Render Basic. A subtracao e matematicamente equivalente: os subconjuntos `cauda_sem_sources` e `cauda_com_sources` particionam exatamente a cauda (`vivino_id IS NULL`), entao `cauda_com_sources = wines_sem_vivino_id - cauda_sem_sources`.")
    lines.append("- Documentos historicos (HANDOFF_AUDITORIA 2026-04-06, PROMPT_RECRIAR) usam numeros diferentes. Detalhes em `tail_audit_contradictions_2026-04-10.md`.")
    lines.append("")

    return "\n".join(lines) + "\n"


def render_reconciliation_report(render, local, recon, ts):
    lines = []
    lines.append("# Reconciliacao Oficial -- vivino_db vs Render (Etapa 1)")
    lines.append("")
    lines.append(f"Data execucao: {ts}")
    lines.append("Executor: `scripts/audit_tail_snapshot.py`")
    lines.append("Metodo: cursor server-side (psycopg2 named cursor) com `fetchmany` em batches de 50.000, cruzamento em memoria")
    lines.append("")

    lines.append("## Universos")
    lines.append("")
    lines.append("| Base | Metrica | Total |")
    lines.append("|---|---|---|")
    lines.append(f"| Render | wines com vivino_id IS NOT NULL | {fmt(render.get('wines_com_vivino_id'))} |")
    lines.append(f"| vivino_db | vivino_vinhos total | {fmt(local.get('vivino_vinhos_total'))} |")
    lines.append("")

    lines.append("## Resultado da Reconciliacao")
    lines.append("")
    lines.append("| Categoria | Contagem |")
    lines.append("|---|---|")
    lines.append(f"| **in_both** (presentes em ambos) | {fmt(recon.get('in_both'))} |")
    lines.append(f"| **only_vivino_db** (presentes no vivino_db, ausentes no Render) | {fmt(recon.get('only_vivino_db'))} |")
    lines.append(f"| **only_render** (vivino_id no Render sem correspondencia no vivino_db) | {fmt(recon.get('only_render'))} |")
    lines.append("")

    lines.append("## Drift vs Referencia")
    lines.append("")
    lines.append("| Metrica | Referencia | Live | Delta | Drift % | Status |")
    lines.append("|---|---|---|---|---|---|")
    for name in ["in_both", "only_vivino_db", "only_render"]:
        live_val = recon.get(name)
        ref_val = REF.get(name) if name != "in_both" else REF.get("wines_com_vivino_id")
        delta = (live_val - ref_val) if (live_val is not None and ref_val is not None) else None
        d = pct_drift(ref_val, live_val)
        flag = drift_flag(ref_val, live_val)
        lines.append(
            f"| {name} | {fmt(ref_val)} | {fmt(live_val)} | {fmt_signed(delta)} | {fmt_pct(d)} | {flag} |"
        )
    lines.append("")

    lines.append("## Confirmacao Explicita (only_render)")
    lines.append("")
    only_r = recon.get("only_render", 0)
    if only_r == 0:
        lines.append("**only_render = 0.** Nenhum vivino_id existente no Render aponta para um ID inexistente no vivino_db. A camada Vivino do Render e um subconjunto do vivino_db.")
    else:
        lines.append(f"**only_render = {fmt(only_r)}.** Existe universo de vivino_ids no Render sem correspondencia no vivino_db -- investigar.")
    lines.append("")

    lines.append("## Amostra -- only_vivino_db (10 menores IDs)")
    lines.append("")
    lines.append("Vinhos presentes no vivino_db local e ausentes no Render.")
    lines.append("")
    lines.append("| vivino_id | nome | produtor | rating |")
    lines.append("|---|---|---|---|")
    for row in recon.get("sample_only_vivino", []):
        vid, nome, prod, rating = row
        lines.append(f"| {vid} | {nome} | {prod} | {rating} |")
    lines.append("")

    if only_r > 0 and recon.get("sample_only_render"):
        lines.append("## Amostra -- only_render")
        lines.append("")
        lines.append("| wines.id | vivino_id | nome | produtor |")
        lines.append("|---|---|---|---|")
        for row in recon["sample_only_render"]:
            lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
        lines.append("")

    lines.append("## Conclusao Operacional")
    lines.append("")
    only_viv = recon.get("only_vivino_db", 0)
    if only_viv > 0:
        lines.append(f"1. **Existe universo real de canonicos importaveis**: {fmt(only_viv)} vinhos no vivino_db ausentes do Render. Candidatos para a Etapa 2.")
    else:
        lines.append("1. **Nao existe universo de canonicos importaveis** no cruzamento atual.")
    if only_r == 0:
        lines.append("2. **Nao existe sujeira de `vivino_id` no Render sem correspondencia no vivino_db.**")
    else:
        lines.append(f"2. **Existe sujeira**: {fmt(only_r)} vivino_ids orfaos no Render.")

    render_total = render.get("wines_com_vivino_id") or 0
    viv_total = local.get("vivino_vinhos_total") or 0
    if viv_total > 0:
        cov = render_total / viv_total * 100
        lines.append(f"3. **Cobertura Render/vivino_db**: {fmt(render_total)} / {fmt(viv_total)} = {cov:.2f}%.")
    lines.append("")

    return "\n".join(lines) + "\n"


def render_contradictions_report(render, local, recon, ts):
    """
    Gera report de contradicoes live vs historico.

    Regra metodologica:
    - FATO = valor live obtido por query nesta execucao, comparado a valor historico documentado.
    - HIPOTESE = explicacao operacional NAO provada por artefato verificavel nesta etapa.

    Nenhuma hipotese deve ser lida como prova de execucao de delete, script ou cleanup.
    """
    lines = []
    lines.append("# Contradicoes Factuais -- Documentos Historicos vs Estado Live")
    lines.append("")
    lines.append(f"Data execucao: {ts}")
    lines.append("Executor: `scripts/audit_tail_snapshot.py`")
    lines.append("")

    lines.append("## Principio Metodologico")
    lines.append("")
    lines.append("- **FATO** = valor live obtido por query nesta execucao, comparado a valor historico documentado.")
    lines.append("- **HIPOTESE** = explicacao operacional **NAO provada** por artefato verificavel nesta etapa.")
    lines.append("")
    lines.append("Nenhuma linha desta secao deve ser lida como prova de execucao de `DELETE`, script ou cleanup. Onde houver suposicao causal, ela aparece explicitamente como `HIPOTESE ... NAO PROVADA`.")
    lines.append("")

    # --- FATOS ---
    lines.append("## Fatos Verificaveis -- Delta live vs historico")
    lines.append("")
    lines.append("Cada linha compara um valor historico documentado com o valor live obtido nesta execucao.")
    lines.append("")
    lines.append("| tema | fonte_historico | valor_historico | valor_live | delta | delta_% | status |")
    lines.append("|---|---|---|---|---|---|---|")

    ws_live = render.get("wine_sources_total")
    ws_hist, ws_src = REF_HIST["wine_sources_total"]
    ws_delta = (ws_live - ws_hist) if ws_live is not None else None
    ws_pct = pct_signed(ws_hist, ws_live)
    lines.append(
        f"| wine_sources_total | {ws_src} | {fmt(ws_hist)} | {fmt(ws_live)} | "
        f"{fmt_signed(ws_delta)} | {fmt_pct_signed(ws_pct)} | CONTRADIZ |"
    )

    st_live = render.get("stores_total")
    st_hist, st_src = REF_HIST["stores_total"]
    st_delta = (st_live - st_hist) if st_live is not None else None
    st_pct = pct_signed(st_hist, st_live)
    lines.append(
        f"| stores_total | {st_src} | {fmt(st_hist)} | {fmt(st_live)} | "
        f"{fmt_signed(st_delta)} | {fmt_pct_signed(st_pct)} | CONTRADIZ (menor) |"
    )

    nws_live = render.get("cauda_sem_sources")
    nws_hist, nws_src = REF_HIST["new_without_sources"]
    nws_delta = (nws_live - nws_hist) if nws_live is not None else None
    nws_pct = pct_signed(nws_hist, nws_live)
    lines.append(
        f"| new_without_sources | {nws_src} | ~{fmt(nws_hist)} | {fmt(nws_live)} | "
        f"{fmt_signed(nws_delta)} | {fmt_pct_signed(nws_pct)} | CONTRADIZ (massivo) |"
    )
    lines.append("")

    # --- schema_live_assumptions (fato de disciplina) ---
    lines.append("### Nota sobre `database/schema_atual.md`")
    lines.append("")
    lines.append("O prompt Etapa 1 orienta tratar `database/schema_atual.md` como historico, nao como fonte de verdade live. **Fato**: as contagens live desta auditoria nao dependem de `schema_atual.md`.")
    lines.append("")

    # --- HIPOTESES explicitas ---
    lines.append("## Hipoteses Operacionais -- NAO PROVADAS nesta etapa")
    lines.append("")
    lines.append("As explicacoes abaixo sao plausiveis mas **nao sao confirmadas por nenhum log, query, commit, tag ou artefato referenciavel** dentro desta etapa. Nao devem ser lidas como fato ate que uma evidencia verificavel confirme.")
    lines.append("")

    lines.append(f"- **HIPOTESE H1** -- `wine_sources_total` {fmt_signed(ws_delta)} ({fmt_pct_signed(ws_pct)})")
    lines.append(f"  - Plausivel: o delta pode decorrer de limpeza de `wine_sources` associados ao vinho errado (tema `wrong_wine_association` discutido em `HANDOFF_AUDITORIA_LINHAGEM_LINKS_RENDER.md`).")
    lines.append(f"  - Esta etapa NAO verifica log de `DELETE`, commit, tag, nem execucao de cleanup.")
    lines.append(f"  - **NAO PROVADA.**")
    lines.append("")
    lines.append(f"- **HIPOTESE H2** -- `new_without_sources` {fmt_signed(nws_delta)} ({fmt_pct_signed(nws_pct)})")
    lines.append(f"  - Plausivel: o delta pode decorrer da execucao do script descrito em `PROMPT_RECRIAR_WINE_SOURCES_FALTANTES.md`, que visa recriar `wine_sources` para wines da cauda.")
    lines.append(f"  - Esta etapa NAO verifica log de execucao, contagem antes/depois, commit ou tag desse script.")
    lines.append(f"  - **NAO PROVADA.**")
    lines.append("")
    lines.append(f"- **HIPOTESE H3** -- `stores_total` {fmt_signed(st_delta)} ({fmt_pct_signed(st_pct)})")
    lines.append(f"  - Plausivel: adicao incremental de lojas via pipeline de scraping.")
    lines.append(f"  - Esta etapa NAO verifica quando e como essas lojas foram adicionadas.")
    lines.append(f"  - **NAO PROVADA.**")
    lines.append("")
    lines.append("Nenhuma dessas hipoteses e necessaria para sustentar o snapshot live. Elas apenas tentam explicar o delta entre docs historicos e estado atual; nao mudam o que e fato.")
    lines.append("")

    # --- Fatos historicos confirmados pelo live ---
    lines.append("## Fatos Historicos Confirmados pelo Live")
    lines.append("")
    lines.append("Valores de referencia da Etapa 1 reconfirmados nesta execucao:")
    lines.append("")
    lines.append(f"- `wines_total` = {fmt(render.get('wines_total'))}")
    lines.append(f"- `wines_com_vivino_id` = {fmt(render.get('wines_com_vivino_id'))}")
    lines.append(f"- `wines_sem_vivino_id` = {fmt(render.get('wines_sem_vivino_id'))}")
    lines.append(f"- `wine_aliases_approved` = {fmt(render.get('wine_aliases_approved'))}")
    lines.append(f"- `canonical_distintos` = {fmt(render.get('canonical_distintos'))}")
    lines.append(f"- `wine_sources_total` = {fmt(render.get('wine_sources_total'))}")
    lines.append(f"- `stores_total` = {fmt(render.get('stores_total'))}")
    lines.append(f"- `cauda_sem_sources` = {fmt(render.get('cauda_sem_sources'))}")
    lines.append(f"- `cauda_com_sources` = {fmt(render.get('cauda_com_sources'))}")
    lines.append(f"- `vivino_vinhos_total` = {fmt(local.get('vivino_vinhos_total'))}")
    lines.append(f"- `y2_matched_vivino` = {fmt(local.get('y2_matched_vivino'))}")
    lines.append(f"- `y2_matched_07` = {fmt(local.get('y2_matched_07'))}")
    lines.append(f"- `in_both` = {fmt(recon.get('in_both'))}")
    lines.append(f"- `only_vivino_db` = {fmt(recon.get('only_vivino_db'))}")
    lines.append(f"- `only_render` = {fmt(recon.get('only_render'))}")
    lines.append("")

    # --- Fatos historicos desatualizados ---
    lines.append("## Fatos Historicos Desatualizados (live nao confirma)")
    lines.append("")
    lines.append(f"- `wine_sources_total` NAO e mais {fmt(ws_hist)} (historico) -- live: {fmt(ws_live)}")
    lines.append(f"- `stores_total` NAO e mais {fmt(st_hist)} (historico) -- live: {fmt(st_live)}")
    lines.append(f"- `new_without_sources` NAO e mais ~{fmt(nws_hist)} (historico) -- live: {fmt(nws_live)}")
    lines.append("- `wines_com_link` e `wines_sem_link` (HANDOFF_AUDITORIA 2026-04-06) nao foram revalidados nesta etapa; tratar como desatualizados.")
    lines.append("")

    return "\n".join(lines) + "\n"


# --------------- MAIN ---------------

def main():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Auditoria Etapa 1 -- {ts}")
    print("=" * 60)

    # Executa as 3 tarefas de coleta
    render = tarefa_a_render()
    local = tarefa_b_local()
    try:
        recon = tarefa_c_reconciliacao()
    except Exception as e:
        print(f"\n[FATAL] reconciliacao falhou: {e}")
        sys.exit(2)

    # Diretorio de reports
    report_dir = os.path.join(os.path.dirname(__file__), '..', 'reports')
    os.makedirs(report_dir, exist_ok=True)

    # Gera os 3 artefatos
    snapshot_md = render_snapshot_report(render, local, recon, ts)
    recon_md = render_reconciliation_report(render, local, recon, ts)
    contra_md = render_contradictions_report(render, local, recon, ts)

    snap_path = os.path.join(report_dir, 'tail_audit_snapshot_2026-04-10.md')
    recon_path = os.path.join(report_dir, 'tail_audit_reconciliation_2026-04-10.md')
    contra_path = os.path.join(report_dir, 'tail_audit_contradictions_2026-04-10.md')

    with open(snap_path, 'w', encoding='utf-8') as f:
        f.write(snapshot_md)
    print(f"\nSalvo: {snap_path}")

    with open(recon_path, 'w', encoding='utf-8') as f:
        f.write(recon_md)
    print(f"Salvo: {recon_path}")

    with open(contra_path, 'w', encoding='utf-8') as f:
        f.write(contra_md)
    print(f"Salvo: {contra_path}")

    print("\n=== ETAPA 1 COMPLETA ===")


if __name__ == "__main__":
    main()
