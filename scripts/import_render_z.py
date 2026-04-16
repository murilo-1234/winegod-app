"""
Chat Z — Importar Vinhos Classificados pro Render (V2)

Fases:
  --check       Sanity check (conecta + mostra estatisticas)
  --fase 1      Wine Sources dos Matched (score >= 0.5)
  --fase 2      Vinhos Novos (new) com anti-duplicata
  --fase 3      Enriquecer vinhos existentes (score >= 0.7)
  --fase all    Todas as fases em sequencia

Flags:
  --dry-run     Simula sem INSERT/UPDATE
  --limite N    Processar no maximo N registros
"""

import psycopg2
from psycopg2.extras import execute_values
from urllib.parse import urlparse
from datetime import datetime, timezone
import json, time, sys, argparse, os, hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import os
import _env

# Guardrails de owner (scripts/ esta no mesmo diretorio)
sys.path.insert(0, os.path.dirname(__file__))
from guardrails_owner import is_producer_valid, has_type_conflict
from pre_ingest_filter import should_skip_wine

# ============================================================
# CONEXOES
# ============================================================

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")

# CRITICO: ?sslmode=require e OBRIGATORIO. Render recusa conexao sem SSL.
RENDER_DB = os.environ["DATABASE_URL"]

BATCH_SIZE = 1000

# Thresholds de matching (3 estados)
THRESHOLD_AUTO = 0.7      # auto-match confiável → wine_sources direto
THRESHOLD_SOURCES = 0.5   # wine_sources aceito (Fase 1) mas não enriquece
THRESHOLD_QUARANTINE = 0.5  # abaixo disso = quarentena, não importar
# Resumo:
#   >= 0.7  → auto-match + enriquecimento (Fase 1 + Fase 3)
#   0.5-0.7 → sources OK, sem enriquecimento (Fase 1 only)
#   < 0.5   → quarentena, sem auto-link


def conectar_render():
    """Conecta ao Render com keepalive pra evitar desconexao."""
    conn = psycopg2.connect(
        RENDER_DB,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    return conn


# ============================================================
# SETUP DE INDICES
# ============================================================

def setup_indices(render_cur, render_conn):
    """Criar indices UNIQUE necessarios pro ON CONFLICT funcionar."""
    print("Criando indices no Render...")

    # Indice pra wine_sources — evitar duplicatas de fonte
    # WHERE url IS NOT NULL: NULLs no PostgreSQL nao violam UNIQUE, criando duplicatas silenciosas
    render_cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_wine_store_url
        ON wine_sources(wine_id, store_id, url)
        WHERE url IS NOT NULL
    """)

    # Indice pra wines — evitar duplicatas ao reimportar vinhos novos
    render_cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_wines_hash_dedup
        ON wines(hash_dedup)
        WHERE hash_dedup IS NOT NULL AND hash_dedup != ''
    """)

    render_conn.commit()
    print("  Indices OK")

# ============================================================
# PRE-CARREGAMENTO
# ============================================================

def carregar_mapas_base(render_cur):
    """Carrega mapas que todas as fases precisam."""
    # 1. Set de wines.id validos no Render (1.72M, ~50MB RAM)
    # IMPORTANTE: y2_results.vivino_id armazena wines.id do Render (nao vivino_id real).
    # vivino_match.id local = wines.id do Render (1:1).
    # Entao basta um set pra validar que o wine_id existe.
    print("Carregando wines.id do Render...")
    render_cur.execute("SELECT id FROM wines")
    valid_wine_ids = set(row[0] for row in render_cur)
    print(f"  {len(valid_wine_ids):,} wines no Render")

    # 2. Mapa dominio -> store_id (12.7K, ~1MB RAM)
    print("Carregando dominio -> store_id do Render...")
    render_cur.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
    domain_to_store = {row[0]: row[1] for row in render_cur}
    print(f"  {len(domain_to_store):,} lojas")

    return valid_wine_ids, domain_to_store


def carregar_fontes_locais(local_cur):
    """
    Carrega fontes de TODAS as tabelas vinhos_XX_fontes.
    Retorna dict: clean_id -> [(url, preco, moeda)]

    MAPEAMENTO CORRETO:
    - wines_clean.pais_tabela = 'br' indica tabela vinhos_br
    - wines_clean.id_original = vinhos_br.id
    - vinhos_br_fontes.vinho_id = vinhos_br.id = wines_clean.id_original
    - Entao: clean_id -> (pais_tabela, id_original) -> vinhos_XX_fontes
    """
    print("Carregando fontes locais (mapeamento via pais_tabela + id_original)...")

    # 1. Carregar mapa: (pais_tabela, id_original) -> clean_id
    print("  Carregando mapa wines_clean (pais_tabela, id_original) -> clean_id...")
    local_cur.execute("SELECT id, pais_tabela, id_original FROM wines_clean WHERE id_original IS NOT NULL")
    # Inverso: pra cada tabela de fontes, queremos (pais, id_original) -> clean_id
    orig_to_clean = {}  # (pais, id_original) -> clean_id
    for clean_id, pais, id_orig in local_cur:
        orig_to_clean[(pais, id_orig)] = clean_id
    print(f"  {len(orig_to_clean):,} mapeamentos carregados")

    # 2. Descobrir tabelas de fontes
    local_cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name LIKE 'vinhos_%_fontes'
        ORDER BY table_name
    """)
    tabelas = [r[0] for r in local_cur.fetchall()]
    print(f"  {len(tabelas)} tabelas de fontes")

    # 3. Carregar fontes e mapear pra clean_id
    fontes_map = {}  # clean_id -> [(url, preco, moeda)]
    total = 0
    total_sem_map = 0

    for t in tabelas:
        pais = t.replace('vinhos_', '').replace('_fontes', '')
        local_cur.execute(f"SELECT vinho_id, url_original, preco, moeda FROM {t} WHERE url_original IS NOT NULL")
        for vinho_id, url, preco, moeda in local_cur:
            clean_id = orig_to_clean.get((pais, vinho_id))
            if clean_id is None:
                total_sem_map += 1
                continue
            if clean_id not in fontes_map:
                fontes_map[clean_id] = []
            fontes_map[clean_id].append((url, preco, moeda))
            total += 1

    print(f"  {total:,} fontes mapeadas | {len(fontes_map):,} vinhos com fontes | {total_sem_map:,} sem mapeamento")
    return fontes_map


def carregar_mapa_produtores(render_cur):
    """Carrega produtores do Render pra dedup da Fase 2. ~200MB RAM."""
    print("Carregando produtores Render pra dedup...")
    render_cur.execute("""
        SELECT id, produtor_normalizado, nome_normalizado
        FROM wines
        WHERE produtor_normalizado IS NOT NULL AND produtor_normalizado != ''
    """)
    render_by_prod = {}
    for wid, prod, nome in render_cur:
        if prod not in render_by_prod:
            render_by_prod[prod] = []
        render_by_prod[prod].append((wid, nome or ""))
    print(f"  {len(render_by_prod):,} produtores unicos no Render")
    return render_by_prod

# ============================================================
# FUNCOES AUXILIARES
# ============================================================

def gerar_hash_dedup(nome_normalizado, produtor_normalizado, safra):
    """Gera hash_dedup fallback quando wines_clean.hash_dedup esta NULL."""
    chave = f"{produtor_normalizado or ''}|{nome_normalizado or ''}|{safra or ''}"
    return hashlib.md5(chave.encode()).hexdigest()


def get_domain(url):
    """'https://www.gourmetmax.com.ar/path' -> 'gourmetmax.com.ar'"""
    try:
        d = urlparse(url).netloc
        return d.replace('www.', '') if d else None
    except:
        return None


def uva_to_jsonb(uva_text):
    """'pinot noir, merlot' -> '["Pinot Noir", "Merlot"]'"""
    if not uva_text:
        return None
    parts = [u.strip().title() for u in uva_text.split(',') if u.strip()]
    return json.dumps(parts) if parts else None


def parse_fontes(fontes_text):
    """Retorna lista de dicts [{url, loja}] ou [] se vazio."""
    if not fontes_text or fontes_text == '[]':
        return []
    try:
        return json.loads(fontes_text)
    except:
        return []


def agora_utc():
    """Timestamp UTC atual. NUNCA usar string 'NOW()' — execute_values insere como texto literal."""
    return datetime.now(timezone.utc)


STOPWORDS = frozenset({"de", "du", "la", "le", "les", "des", "del", "di", "the", "and", "et"})


def make_word_set(text):
    """Cria set de palavras significativas (>= 3 chars, sem stopwords)."""
    if not text:
        return frozenset()
    return frozenset(w for w in text.lower().split() if len(w) >= 3 and w not in STOPWORDS)


def check_exists_in_render(prod, nome, render_by_prod):
    """
    Verifica se vinho ja existe no Render por match EXATO de produtor + overlap de nome.
    Retorna wine_id ou None.

    IMPORTANTE: usa APENAS lookup exato no dict (O(1)).
    NAO iterar sobre todos os produtores — isso e O(N) e trava o script.
    """
    candidates = render_by_prod.get(prod)
    if not candidates:
        return None

    nome_words = make_word_set(nome)
    if not nome_words:
        return None

    best_id = None
    best_score = 0
    for wid, wnome in candidates:
        wnome_words = make_word_set(wnome)
        if not wnome_words:
            continue
        overlap = len(nome_words & wnome_words)
        total_w = max(len(nome_words), len(wnome_words))
        score = overlap / total_w if total_w > 0 else 0
        if score > best_score:
            best_score = score
            best_id = wid

    return best_id if best_score >= 0.5 else None


def progresso(fase, processados, total, inicio, **extras):
    """Mostra progresso com velocidade e ETA."""
    elapsed = time.time() - inicio
    vel = processados / elapsed if elapsed > 0 else 0
    eta_seg = (total - processados) / vel if vel > 0 else 0
    eta_min = eta_seg / 60
    pct = processados / total * 100 if total > 0 else 0
    extra_str = " | ".join(f"{k}={v:,}" for k, v in extras.items())
    if extra_str:
        extra_str = " | " + extra_str
    print(f"\rFase {fase}: {processados:,} / {total:,} ({pct:.1f}%) | {vel:.0f}/seg | ETA {eta_min:.0f}min{extra_str}", end="", flush=True)

# ============================================================
# MODO --check (Sanity Check)
# ============================================================

def run_check(local_cur, render_cur, valid_wine_ids, domain_to_store):
    print("=" * 60)
    print("SANITY CHECK")
    print("=" * 60)

    # 1. y2_results por status
    local_cur.execute("SELECT status, COUNT(*) FROM y2_results GROUP BY status ORDER BY COUNT(*) DESC")
    print("\n[LOCAL] y2_results por status:")
    for status, count in local_cur.fetchall():
        print(f"  {status or 'NULL'}: {count:,}")

    # 2. Matched por faixa de score (3 estados)
    local_cur.execute("SELECT COUNT(*) FROM y2_results WHERE status = 'matched' AND match_score >= %s", (THRESHOLD_AUTO,))
    m_auto = local_cur.fetchone()[0]
    local_cur.execute("SELECT COUNT(*) FROM y2_results WHERE status = 'matched' AND match_score >= %s AND match_score < %s",
                      (THRESHOLD_SOURCES, THRESHOLD_AUTO))
    m_sources = local_cur.fetchone()[0]
    local_cur.execute("SELECT COUNT(*) FROM y2_results WHERE status = 'matched' AND match_score < %s", (THRESHOLD_QUARANTINE,))
    m_quarantine = local_cur.fetchone()[0]
    print(f"\n[LOCAL] Auto-match (>= {THRESHOLD_AUTO}): {m_auto:,} — Fase 1 + Fase 3")
    print(f"[LOCAL] Sources only ({THRESHOLD_SOURCES}-{THRESHOLD_AUTO}): {m_sources:,} — Fase 1 only")
    print(f"[LOCAL] Quarentena (< {THRESHOLD_QUARANTINE}): {m_quarantine:,} — SEM auto-link")

    # 3. Novos
    local_cur.execute("SELECT COUNT(*) FROM y2_results WHERE status = 'new'")
    novos = local_cur.fetchone()[0]
    print(f"[LOCAL] Novos (Fase 2): {novos:,}")

    # 4. Quantos vivino_ids locais existem no Render (amostra)
    local_cur.execute("""
        SELECT DISTINCT vivino_id FROM y2_results
        WHERE status = 'matched' AND vivino_id IS NOT NULL
        LIMIT 1000
    """)
    sample = [r[0] for r in local_cur.fetchall()]
    found = sum(1 for vid in sample if vid in valid_wine_ids)
    print(f"\n[CROSS] Amostra 1000 vivino_ids: {found} encontrados no Render ({found/10:.0f}%)")
    if found < 800:
        print("  ALERTA: menos de 80% dos vivino_ids encontrados! Verificar se o banco Render esta atualizado.")

    # 5. Render estado atual
    render_cur.execute("SELECT COUNT(*) FROM wines")
    total_wines = render_cur.fetchone()[0]
    render_cur.execute("SELECT COUNT(*) FROM wine_sources")
    total_ws = render_cur.fetchone()[0]
    render_cur.execute("SELECT COUNT(*) FROM stores")
    total_stores = render_cur.fetchone()[0]
    print(f"\n[RENDER] Wines: {total_wines:,} | Wine Sources: {total_ws:,} | Stores: {total_stores:,}")

    # 6. Lojas com fontes
    local_cur.execute("""
        SELECT COUNT(DISTINCT wc.id) FROM y2_results y
        JOIN wines_clean wc ON wc.id = y.clean_id
        WHERE y.status IN ('matched', 'new')
        AND wc.fontes IS NOT NULL AND wc.fontes != '[]'
    """)
    com_fontes = local_cur.fetchone()[0]
    print(f"[LOCAL] Vinhos com fontes (vao gerar wine_sources): {com_fontes:,}")

    print("\n" + "=" * 60)
    print("Check completo. Analise os numeros. Se OK, rodar --fase 1/2/3/all")
    print("=" * 60)

# ============================================================
# FASE 1 — Wine Sources dos Matched (score >= 0.5)
# ============================================================

def fase1(local_cur, render_cur, render_conn, valid_wine_ids, domain_to_store, fontes_map, limite=None, dry_run=False):
    print("\n" + "=" * 60)
    print("FASE 1 — Wine Sources dos Matched (score >= 0.5)")
    print("=" * 60)

    # Contar total
    local_cur.execute("""
        SELECT COUNT(*) FROM y2_results
        WHERE status = 'matched' AND match_score >= 0.5
    """)
    total = local_cur.fetchone()[0]
    if limite:
        total = min(total, limite)
    print(f"Total a processar: {total:,}")

    inicio = time.time()
    last_id = 0
    processados = 0
    sources_criados = 0
    sem_vivino = 0
    sem_fontes = 0
    sem_loja = 0
    rejeitado_owner = 0
    rejeitado_tipo = 0

    while True:
        if limite and processados >= limite:
            break

        batch_limit = min(BATCH_SIZE, (limite - processados) if limite else BATCH_SIZE)

        # CURSOR-BASED: WHERE id > last_id ORDER BY id
        # Traz prod_banco, vivino_produtor, cor para validacao de guardrails
        local_cur.execute("""
            SELECT id, vivino_id, clean_id, prod_banco, vivino_produtor, cor
            FROM y2_results
            WHERE status = 'matched' AND match_score >= 0.5
            AND id > %s
            ORDER BY id
            LIMIT %s
        """, (last_id, batch_limit))

        rows = local_cur.fetchall()
        if not rows:
            break

        last_id = rows[-1][0]
        batch_values = []
        ts = agora_utc()

        for row in rows:
            y_id, vivino_id, clean_id, prod_banco, vivino_produtor, cor = row
            processados += 1

            # Guardrail: rejeitar produtor invalido (vazio, curto, generico)
            prod_ok, prod_reason = is_producer_valid(prod_banco)
            if not prod_ok:
                rejeitado_owner += 1
                continue

            # Guardrail: rejeitar conflito de tipo tinto/branco
            # cor do y2_results usa T=tinto, B=branco; vivino usa tipo completo
            # Verificar se cor da loja conflita com o produtor Vivino matcheado
            if cor and vivino_produtor:
                cor_loja = "tinto" if cor == "T" else ("branco" if cor == "B" else None)
                if cor_loja and has_type_conflict(cor_loja, vivino_produtor):
                    rejeitado_tipo += 1
                    continue

            # vivino_id = wines.id do Render
            wine_id = vivino_id if vivino_id in valid_wine_ids else None
            if not wine_id:
                sem_vivino += 1
                continue

            # Buscar fontes reais (vinhos_XX_fontes)
            fontes = fontes_map.get(clean_id)
            if not fontes:
                sem_fontes += 1
                continue

            for url, preco, moeda in fontes:
                if not url:
                    continue
                dominio = get_domain(url)
                if not dominio:
                    continue
                store_id = domain_to_store.get(dominio)
                if not store_id:
                    sem_loja += 1
                    continue

                batch_values.append((wine_id, store_id, url, preco, moeda, True, ts, ts))

        # INSERT batch com execute_values
        if batch_values and not dry_run:
            execute_values(render_cur, """
                INSERT INTO wine_sources (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
                VALUES %s
                ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING
            """, batch_values)
            sources_criados += render_cur.rowcount
            render_conn.commit()

        progresso(1, processados, total, inicio, sources=sources_criados, sem_vivino=sem_vivino, sem_fontes=sem_fontes)

    print(f"\n\nFase 1 concluida: {processados:,} processados | {sources_criados:,} sources criados")
    print(f"  sem vivino_id: {sem_vivino:,} | sem fontes: {sem_fontes:,} | sem loja: {sem_loja:,}")
    print(f"  rejeitado owner: {rejeitado_owner:,} | rejeitado tipo: {rejeitado_tipo:,}")
    return sources_criados

# ============================================================
# FASE 2 — Vinhos Novos com Anti-Duplicata
# ============================================================

def _processar_batch_fase2(batch_data, domain_to_store, dry_run, worker_id):
    """Worker: processa 1 batch de wines no Render. Cada worker tem sua propria conexao."""
    wines_to_insert, hash_to_fontes, hash_to_prod, existing_sources, ts = batch_data

    r_conn = conectar_render()
    r_cur = r_conn.cursor()

    result = {"criados": 0, "dup_hash": 0, "sources": 0, "erros": 0, "prod_updates": []}

    for tentativa in range(3):
        try:
            # === BATCH INSERT wines ===
            if wines_to_insert:
                execute_values(r_cur, """
                    INSERT INTO wines (nome, nome_normalizado, produtor, produtor_normalizado,
                        safra, tipo, pais, regiao, sub_regiao,
                        uvas, teor_alcoolico, harmonizacao, imagem_url,
                        preco_min, preco_max, moeda, total_fontes, hash_dedup, ean_gtin,
                        descoberto_em, atualizado_em)
                    VALUES %s
                    ON CONFLICT (hash_dedup) WHERE hash_dedup IS NOT NULL AND hash_dedup != '' DO NOTHING
                """, wines_to_insert, template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")
                batch_inserted = r_cur.rowcount
                result["criados"] = batch_inserted
                result["dup_hash"] = len(wines_to_insert) - batch_inserted

                # === Buscar IDs dos wines recem-inseridos ===
                if hash_to_fontes or hash_to_prod:
                    all_hashes = list(set(list(hash_to_fontes.keys()) + list(hash_to_prod.keys())))
                    for i in range(0, len(all_hashes), 1000):
                        chunk = all_hashes[i:i+1000]
                        r_cur.execute(
                            "SELECT id, hash_dedup, produtor_normalizado, nome_normalizado FROM wines WHERE hash_dedup = ANY(%s)",
                            (chunk,)
                        )
                        for wid, hd, prod, nome in r_cur.fetchall():
                            fontes_for_wine = hash_to_fontes.get(hd, [])
                            for url, preco, moeda_f in fontes_for_wine:
                                if url:
                                    existing_sources.append((wid, url, preco, moeda_f))
                            prod_info = hash_to_prod.get(hd)
                            if prod_info:
                                result["prod_updates"].append((prod_info[0], wid, prod_info[1]))

            # === BATCH INSERT wine_sources ===
            if existing_sources:
                ws_values = []
                for wine_id, url, preco, moeda_f in existing_sources:
                    dominio = get_domain(url)
                    store_id = domain_to_store.get(dominio) if dominio else None
                    if not store_id:
                        continue
                    ws_values.append((wine_id, store_id, url, preco, moeda_f, True, ts, ts))
                if ws_values:
                    execute_values(r_cur, """
                        INSERT INTO wine_sources (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
                        VALUES %s
                        ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING
                    """, ws_values)
                    result["sources"] = r_cur.rowcount

            r_conn.commit()
            break

        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"\n  [W{worker_id}] CONEXAO PERDIDA (tentativa {tentativa+1}/3): {e}")
            try:
                r_conn.close()
            except:
                pass
            time.sleep(5)
            r_conn = conectar_render()
            r_cur = r_conn.cursor()

        except Exception as e:
            print(f"\n  [W{worker_id}] ERRO batch: {e}")
            try:
                r_conn.rollback()
            except:
                pass
            result["erros"] = len(wines_to_insert) if wines_to_insert else 0
            break

    r_cur.close()
    r_conn.close()
    return result


def fase2(local_cur, render_cur, render_conn, valid_wine_ids, domain_to_store, fontes_map, render_by_prod, limite=None, dry_run=False, workers=1):
    print("\n" + "=" * 60)
    print(f"FASE 2 — Vinhos Novos com Anti-Duplicata (BATCH, {workers} workers)")
    print("=" * 60)

    # Contar total
    local_cur.execute("SELECT COUNT(*) FROM y2_results WHERE status = 'new'")
    total = local_cur.fetchone()[0]
    if limite:
        total = min(total, limite)
    print(f"Total a processar: {total:,}")

    inicio = time.time()
    last_id = 0
    processados = 0
    criados = 0
    encontrados_render = 0
    sources_criados = 0
    pulados = 0
    duplicatas_hash = 0
    bloqueado_not_wine = 0
    erros = 0

    executor = ThreadPoolExecutor(max_workers=workers)
    pending_futures = []

    while True:
        if limite and processados >= limite:
            break

        batch_limit = min(BATCH_SIZE, (limite - processados) if limite else BATCH_SIZE)

        local_cur.execute("""
            SELECT y.id, y.prod_banco, y.vinho_banco, y.pais, y.cor, y.safra, y.uva,
                y.regiao, y.subregiao, y.abv, y.harmonizacao, y.clean_id,
                wc.nome_limpo, wc.nome_normalizado, wc.produtor_extraido,
                wc.preco_min, wc.preco_max, wc.moeda, wc.url_imagem,
                wc.total_fontes, wc.hash_dedup, wc.ean_gtin
            FROM y2_results y
            JOIN wines_clean wc ON wc.id = y.clean_id
            WHERE y.status = 'new'
            AND y.id > %s
            ORDER BY y.id
            LIMIT %s
        """, (last_id, batch_limit))

        rows = local_cur.fetchall()
        if not rows:
            break

        last_id = rows[-1][0]
        ts = agora_utc()

        # Preparar batch
        wines_to_insert = []
        hash_to_fontes = {}
        hash_to_prod = {}
        existing_sources = []

        for row in rows:
            (y_id, prod_banco, vinho_banco, pais, cor, safra, uva,
             regiao, subregiao, abv, harmonizacao, clean_id,
             nome_limpo, nome_normalizado, produtor_extraido,
             preco_min, preco_max, moeda, url_imagem,
             total_fontes, hash_dedup, ean_gtin) = row
            processados += 1

            fontes = fontes_map.get(clean_id, [])
            nome_candidato = nome_limpo or vinho_banco or ""
            produtor_candidato = produtor_extraido or prod_banco or ""
            skip_not_wine, _skip_reason = should_skip_wine(nome_candidato, produtor_candidato)
            if skip_not_wine:
                bloqueado_not_wine += 1
                continue

            existing_wine_id = check_exists_in_render(prod_banco, vinho_banco, render_by_prod) if prod_banco else None

            if existing_wine_id is not None:
                encontrados_render += 1
                for url, preco, moeda_f in fontes:
                    if url:
                        existing_sources.append((existing_wine_id, url, preco, moeda_f))
            else:
                if not nome_limpo:
                    pulados += 1
                    continue

                abv_float = None
                if abv:
                    try:
                        abv_float = float(str(abv).replace('%', '').replace(',', '.').strip())
                        if abv_float > 100 or abv_float < 0:
                            abv_float = None  # ABV invalido
                    except:
                        pass

                hash_final = hash_dedup if hash_dedup else gerar_hash_dedup(nome_normalizado, prod_banco, safra)
                pais_safe = pais[:2] if pais and len(pais) > 2 else pais
                safra_safe = safra[:20] if safra and len(safra) > 20 else safra
                moeda_safe = moeda[:20] if moeda and len(moeda) > 20 else moeda

                # Sanitizar precos (NUMERIC(10,2) = max 99999999.99)
                preco_min_safe = preco_min if preco_min is not None and preco_min < 99999999 else None
                preco_max_safe = preco_max if preco_max is not None and preco_max < 99999999 else None

                wines_to_insert.append((
                    nome_limpo, nome_normalizado, produtor_extraido, prod_banco,
                    safra_safe, cor, pais_safe, regiao, subregiao,
                    uva_to_jsonb(uva), abv_float, harmonizacao, url_imagem,
                    preco_min_safe, preco_max_safe, moeda_safe, total_fontes, hash_final, ean_gtin,
                    ts, ts
                ))

                if fontes:
                    hash_to_fontes[hash_final] = fontes
                if prod_banco:
                    hash_to_prod[hash_final] = (prod_banco, nome_normalizado or "")

        if dry_run:
            progresso(2, processados, total, inicio, criados=criados, existentes=encontrados_render, dup_hash=duplicatas_hash, not_wine=bloqueado_not_wine)
            continue

        # Submeter batch pro worker
        batch_data = (wines_to_insert, hash_to_fontes, hash_to_prod, existing_sources, ts)
        worker_id = len(pending_futures) % workers
        fut = executor.submit(_processar_batch_fase2, batch_data, domain_to_store, dry_run, worker_id)
        pending_futures.append(fut)

        # Coletar resultados de futures completos (nao bloqueia se nao estiverem prontos)
        still_pending = []
        for f in pending_futures:
            if f.done():
                res = f.result()
                criados += res["criados"]
                duplicatas_hash += res["dup_hash"]
                sources_criados += res["sources"]
                erros += res["erros"]
                for pb, wid, nn in res["prod_updates"]:
                    if pb not in render_by_prod:
                        render_by_prod[pb] = []
                    render_by_prod[pb].append((wid, nn))
            else:
                still_pending.append(f)
        pending_futures = still_pending

        # Se tem muitos futures pendentes, esperar o mais antigo
        while len(pending_futures) >= workers * 2:
            f = pending_futures.pop(0)
            res = f.result()
            criados += res["criados"]
            duplicatas_hash += res["dup_hash"]
            sources_criados += res["sources"]
            erros += res["erros"]
            for pb, wid, nn in res["prod_updates"]:
                if pb not in render_by_prod:
                    render_by_prod[pb] = []
                render_by_prod[pb].append((wid, nn))

        progresso(2, processados, total, inicio, criados=criados, existentes=encontrados_render, dup_hash=duplicatas_hash, not_wine=bloqueado_not_wine)

    # Esperar todos os futures restantes
    for f in pending_futures:
        res = f.result()
        criados += res["criados"]
        duplicatas_hash += res["dup_hash"]
        sources_criados += res["sources"]
        erros += res["erros"]
        for pb, wid, nn in res["prod_updates"]:
            if pb not in render_by_prod:
                render_by_prod[pb] = []
            render_by_prod[pb].append((wid, nn))

    executor.shutdown(wait=True)

    print(f"\n\nFase 2 concluida: {processados:,} processados | {criados:,} criados | {encontrados_render:,} ja existiam | {duplicatas_hash:,} dup hash | {sources_criados:,} sources | {bloqueado_not_wine:,} bloqueados_not_wine | {pulados:,} pulados | {erros:,} erros")
    return criados

# ============================================================
# FASE 3 — Enriquecer Vinhos Existentes (score >= 0.7)
# ============================================================

def fase3(local_cur, render_cur, render_conn, valid_wine_ids, limite=None, dry_run=False):
    print("\n" + "=" * 60)
    print("FASE 3 — Enriquecer Vinhos Existentes (score >= 0.7)")
    print("=" * 60)

    # Contar total
    local_cur.execute("""
        SELECT COUNT(*) FROM y2_results y
        JOIN wines_clean wc ON wc.id = y.clean_id
        WHERE y.status = 'matched' AND y.match_score >= 0.7
        AND (y.cor IS NOT NULL OR y.pais IS NOT NULL OR y.regiao IS NOT NULL
             OR y.uva IS NOT NULL OR y.abv IS NOT NULL OR y.harmonizacao IS NOT NULL)
    """)
    total = local_cur.fetchone()[0]
    if limite:
        total = min(total, limite)
    print(f"Total a processar: {total:,}")
    print(f"Estimativa: ~10-15 minutos (batch UPDATE via CTE, {total // BATCH_SIZE} batches)")

    inicio = time.time()
    last_id = 0
    processados = 0
    atualizados = 0
    sem_vivino = 0
    sem_dados = 0

    while True:
        if limite and processados >= limite:
            break

        batch_limit = min(BATCH_SIZE, (limite - processados) if limite else BATCH_SIZE)

        local_cur.execute("""
            SELECT y.id, y.vivino_id, y.cor, y.pais, y.regiao, y.subregiao,
                y.uva, y.abv, y.harmonizacao, wc.url_imagem
            FROM y2_results y
            JOIN wines_clean wc ON wc.id = y.clean_id
            WHERE y.status = 'matched' AND y.match_score >= 0.7
            AND (y.cor IS NOT NULL OR y.pais IS NOT NULL OR y.regiao IS NOT NULL
                 OR y.uva IS NOT NULL OR y.abv IS NOT NULL OR y.harmonizacao IS NOT NULL)
            AND y.id > %s
            ORDER BY y.id
            LIMIT %s
        """, (last_id, batch_limit))

        rows = local_cur.fetchall()
        if not rows:
            break

        last_id = rows[-1][0]

        # Preparar batch de updates
        batch_updates = []
        ts = agora_utc()

        for row in rows:
            (y_id, vivino_id, cor, pais, regiao, subregiao,
             uva, abv, harmonizacao, url_imagem) = row
            processados += 1

            wine_id = vivino_id if vivino_id in valid_wine_ids else None
            if not wine_id:
                sem_vivino += 1
                continue

            abv_float = None
            if abv:
                try:
                    abv_float = float(str(abv).replace('%', '').replace(',', '.').strip())
                    if abv_float > 100 or abv_float < 0:
                        abv_float = None
                except:
                    pass

            uvas_jsonb = uva_to_jsonb(uva)
            pais_safe = pais[:2] if pais and len(pais) > 2 else pais

            batch_updates.append((wine_id, cor, pais_safe, regiao, subregiao, uvas_jsonb, abv_float, harmonizacao, url_imagem))

        if dry_run or not batch_updates:
            progresso(3, processados, total, inicio, atualizados=atualizados, sem_vivino=sem_vivino)
            continue

        # BATCH UPDATE via mogrify + FROM VALUES com retry
        for tentativa in range(3):
            try:
                values_str = ",".join(
                    render_cur.mogrify("(%s,%s,%s,%s,%s,%s,%s,%s,%s)", v).decode()
                    for v in batch_updates
                )
                render_cur.execute(f"""
                    UPDATE wines w SET
                        tipo = COALESCE(w.tipo, v.tipo),
                        pais = COALESCE(w.pais, v.pais),
                        regiao = COALESCE(w.regiao, v.regiao),
                        sub_regiao = COALESCE(w.sub_regiao, v.sub_regiao),
                        uvas = COALESCE(w.uvas, v.uvas::jsonb),
                        teor_alcoolico = COALESCE(w.teor_alcoolico, v.abv::numeric),
                        harmonizacao = COALESCE(w.harmonizacao, v.harmonizacao),
                        imagem_url = COALESCE(w.imagem_url, v.imagem_url),
                        atualizado_em = {render_cur.mogrify("%s", (ts,)).decode()}
                    FROM (VALUES {values_str}) AS v(wine_id, tipo, pais, regiao, sub_regiao, uvas, abv, harmonizacao, imagem_url)
                    WHERE w.id = v.wine_id::integer
                    AND (w.tipo IS NULL OR w.pais IS NULL OR w.regiao IS NULL OR w.uvas IS NULL
                         OR w.teor_alcoolico IS NULL OR w.harmonizacao IS NULL OR w.imagem_url IS NULL)
                """)
                atualizados += render_cur.rowcount
                render_conn.commit()
                break

            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                print(f"\n  CONEXAO PERDIDA (tentativa {tentativa+1}/3): {e}")
                try:
                    render_conn.close()
                except:
                    pass
                time.sleep(5)
                render_conn = conectar_render()
                render_cur = render_conn.cursor()
                print("  Reconectado ao Render")

            except Exception as e:
                print(f"\n  ERRO batch update: {e}")
                try:
                    render_conn.rollback()
                except:
                    pass
                break

        progresso(3, processados, total, inicio, atualizados=atualizados, sem_vivino=sem_vivino)

    print(f"\n\nFase 3 concluida: {processados:,} processados | {atualizados:,} atualizados | {sem_vivino:,} sem vivino_id")
    return atualizados

# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Chat Z — Importar vinhos classificados pro Render")
    parser.add_argument("--check", action="store_true", help="Sanity check (mostra estatisticas)")
    parser.add_argument("--fase", type=str, choices=["1", "2", "3", "all"], help="Fase a executar")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem INSERT/UPDATE")
    parser.add_argument("--limite", type=int, help="Processar no maximo N registros")
    parser.add_argument("--workers", type=int, default=4, help="Workers paralelos pra Fase 2 (default: 4)")
    args = parser.parse_args()

    if not args.check and not args.fase:
        parser.print_help()
        sys.exit(1)

    print("=" * 60)
    print("CHAT Z — Import Render V2")
    print(f"Modo: {'CHECK' if args.check else f'FASE {args.fase}'}")
    if args.dry_run:
        print("*** DRY RUN — nenhum dado sera inserido/atualizado ***")
    if args.limite:
        print(f"Limite: {args.limite:,} registros")
    print("=" * 60)

    # Conectar
    print("\nConectando ao banco LOCAL...")
    local_conn = psycopg2.connect(**LOCAL_DB)
    local_cur = local_conn.cursor()
    print("  LOCAL OK")

    print("Conectando ao Render...")
    render_conn = conectar_render()
    render_cur = render_conn.cursor()
    print("  RENDER OK")

    # Setup indices
    setup_indices(render_cur, render_conn)

    # Carregar mapas base
    valid_wine_ids, domain_to_store = carregar_mapas_base(render_cur)

    # Carregar fontes locais (Fase 1, 2 e all)
    fontes_map = None
    if args.fase in ("1", "2", "all"):
        fontes_map = carregar_fontes_locais(local_cur)

    # Carregar mapa de produtores (so se Fase 2 ou all)
    render_by_prod = None
    if args.fase in ("2", "all"):
        render_by_prod = carregar_mapa_produtores(render_cur)

    # Executar
    if args.check:
        run_check(local_cur, render_cur, valid_wine_ids, domain_to_store)

    elif args.fase == "1":
        fase1(local_cur, render_cur, render_conn, valid_wine_ids, domain_to_store, fontes_map, args.limite, args.dry_run)

    elif args.fase == "2":
        fase2(local_cur, render_cur, render_conn, valid_wine_ids, domain_to_store, fontes_map, render_by_prod, args.limite, args.dry_run, args.workers)

    elif args.fase == "3":
        fase3(local_cur, render_cur, render_conn, valid_wine_ids, args.limite, args.dry_run)

    elif args.fase == "all":
        fase1(local_cur, render_cur, render_conn, valid_wine_ids, domain_to_store, fontes_map, args.limite, args.dry_run)
        fase2(local_cur, render_cur, render_conn, valid_wine_ids, domain_to_store, fontes_map, render_by_prod, args.limite, args.dry_run, args.workers)
        fase3(local_cur, render_cur, render_conn, valid_wine_ids, args.limite, args.dry_run)

    # Fechar conexoes
    local_cur.close()
    local_conn.close()
    render_cur.close()
    render_conn.close()
    print("\nConexoes fechadas. Fim.")


if __name__ == "__main__":
    main()
