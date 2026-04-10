INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# Chat Z — Importar Vinhos Classificados pro Render (V2)

## CONTEXTO

WineGod.ai e uma IA sommelier. O banco de producao (Render PostgreSQL, 15GB) tem 1.72M vinhos importados do Vivino, 12.7K lojas e 66K wine_sources. Usa 2.6GB atualmente.

O pipeline de classificacao (Chat Y) processou 3.96M vinhos de lojas de 50 paises usando 7 IAs. Resultado no banco LOCAL:

- **1.38M matched** — vinhos que casaram com o Vivino (tem `vivino_id`, score 0.2-1.0)
- **762K new** — vinhos reais que nao existem no Vivino
- Campos normalizados: pais=ISO 2 letras, cor=tinto/branco/etc, regiao=Title Case, safra=4 digitos, ABV=numerico

## PRINCIPIO FUNDAMENTAL

**Dados do Vivino NUNCA sao sobrescritos.** Campos que ja tem valor no Render ficam intactos. So preenchemos campos NULL.

## TAREFA

Criar `scripts/import_render_z.py` com sanity check + 3 fases + anti-duplicata.

---

## ARQUITETURA DO SCRIPT

```
--check       → Fase 0 (conecta + carrega mapas) → mostra estatisticas → PARA
--fase 1      → Fase 0 → Fase 1
--fase 2      → Fase 0 + carrega render_by_prod → Fase 2
--fase 3      → Fase 0 → Fase 3
--fase all    → Fase 0 + carrega render_by_prod → Fase 1 → Fase 2 → Fase 3
--dry-run     → qualquer fase, simula sem INSERT/UPDATE
--limite N    → processar no maximo N registros (pra teste)
```

---

## FASE 0 — Conexoes, Setup e Pre-carregamento

### Conexoes

```python
import psycopg2
from psycopg2.extras import execute_values
from urllib.parse import urlparse
from datetime import datetime, timezone
import json, time, sys, argparse, os

LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")

# CRITICO: ?sslmode=require e OBRIGATORIO. Render recusa conexao sem SSL.
RENDER_DB = "<DATABASE_URL_FROM_ENV>"

BATCH_SIZE = 1000
```

### Setup de indices (roda ANTES de qualquer insert)

```python
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
```

### Pre-carregamento base (Fases 1, 2, 3)

```python
def carregar_mapas_base(render_cur):
    """Carrega mapas que todas as fases precisam."""
    # 1. Mapa vivino_id → wine_id (1.72M, ~130MB RAM)
    print("Carregando vivino_id → wine_id do Render...")
    render_cur.execute("SELECT vivino_id, id FROM wines WHERE vivino_id IS NOT NULL")
    vivino_to_wine = {row[0]: row[1] for row in render_cur}
    print(f"  {len(vivino_to_wine):,} vinhos com vivino_id")

    # 2. Mapa dominio → store_id (12.7K, ~1MB RAM)
    print("Carregando dominio → store_id do Render...")
    render_cur.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
    domain_to_store = {row[0]: row[1] for row in render_cur}
    print(f"  {len(domain_to_store):,} lojas")

    return vivino_to_wine, domain_to_store
```

### Pre-carregamento extra (SO Fase 2 — evitar gastar RAM se rodar so Fase 1 ou 3)

```python
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
```

---

## FUNCOES AUXILIARES

```python
def get_domain(url):
    """'https://www.gourmetmax.com.ar/path' → 'gourmetmax.com.ar'"""
    try:
        d = urlparse(url).netloc
        return d.replace('www.', '') if d else None
    except:
        return None

def uva_to_jsonb(uva_text):
    """'pinot noir, merlot' → '["Pinot Noir", "Merlot"]'"""
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

STOPWORDS = frozenset({"de","du","la","le","les","des","del","di","the","and","et"})

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
```

---

## MODO --check (Sanity Check)

Roda ANTES de qualquer import. Mostra estatisticas pra validar que os dados fazem sentido.

```python
def run_check(local_cur, render_cur, vivino_to_wine, domain_to_store):
    print("=" * 60)
    print("SANITY CHECK")
    print("=" * 60)

    # 1. y2_results por status
    local_cur.execute("SELECT status, COUNT(*) FROM y2_results GROUP BY status ORDER BY COUNT(*) DESC")
    print("\n[LOCAL] y2_results por status:")
    for status, count in local_cur.fetchall():
        print(f"  {status or 'NULL'}: {count:,}")

    # 2. Matched por faixa de score
    local_cur.execute("SELECT COUNT(*) FROM y2_results WHERE status = 'matched' AND match_score >= 0.5")
    m05 = local_cur.fetchone()[0]
    local_cur.execute("SELECT COUNT(*) FROM y2_results WHERE status = 'matched' AND match_score >= 0.7")
    m07 = local_cur.fetchone()[0]
    print(f"\n[LOCAL] Matched score >= 0.5 (Fase 1): {m05:,}")
    print(f"[LOCAL] Matched score >= 0.7 (Fase 3): {m07:,}")

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
    found = sum(1 for vid in sample if vid in vivino_to_wine)
    print(f"\n[CROSS] Amostra 1000 vivino_ids: {found} encontrados no Render ({found/10:.0f}%)")
    if found < 800:
        print("  ⚠️  ALERTA: menos de 80% dos vivino_ids encontrados! Verificar se o banco Render esta atualizado.")

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
```

---

## FASE 1 — Wine Sources dos Matched (score >= 0.5 → wine_sources)

**Input:** ~1.0M registros matched com score >= 0.5
**Output:** wine_sources no Render

Para cada vinho matched:
1. Buscar `wine_id` via `vivino_to_wine[vivino_id]`
2. JOIN com `wines_clean` pra pegar `fontes`, `preco_min`, `moeda`
3. Parsear `fontes` (JSON) → extrair URL → extrair dominio → buscar `store_id`
4. INSERT batch em `wine_sources` com ON CONFLICT DO NOTHING

### Paginacao: cursor-based (NAO usar OFFSET)

```python
def fase1(local_cur, render_cur, render_conn, vivino_to_wine, domain_to_store, limite=None, dry_run=False):
    print("\n" + "=" * 60)
    print("FASE 1 — Wine Sources dos Matched (score >= 0.5)")
    print("=" * 60)

    # Contar total
    local_cur.execute("""
        SELECT COUNT(*) FROM y2_results y
        JOIN wines_clean wc ON wc.id = y.clean_id
        WHERE y.status = 'matched' AND y.match_score >= 0.5
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

    while True:
        if limite and processados >= limite:
            break

        batch_limit = min(BATCH_SIZE, (limite - processados) if limite else BATCH_SIZE)

        # CURSOR-BASED: WHERE y.id > last_id ORDER BY y.id
        # O(1) constante — NAO degrada como OFFSET
        local_cur.execute("""
            SELECT y.id, y.vivino_id, y.clean_id, wc.fontes, wc.preco_min, wc.moeda
            FROM y2_results y
            JOIN wines_clean wc ON wc.id = y.clean_id
            WHERE y.status = 'matched' AND y.match_score >= 0.5
            AND y.id > %s
            ORDER BY y.id
            LIMIT %s
        """, (last_id, batch_limit))

        rows = local_cur.fetchall()
        if not rows:
            break

        last_id = rows[-1][0]  # maior y.id do batch
        batch_values = []
        ts = agora_utc()

        for row in rows:
            y_id, vivino_id, clean_id, fontes_text, preco_min, moeda = row
            processados += 1

            # Buscar wine_id no Render
            wine_id = vivino_to_wine.get(vivino_id)
            if not wine_id:
                sem_vivino += 1
                continue

            # Parsear fontes
            fontes = parse_fontes(fontes_text)
            if not fontes:
                sem_fontes += 1
                continue

            for fonte in fontes:
                url = fonte.get('url') or fonte.get('link')
                if not url:
                    continue
                dominio = get_domain(url)
                if not dominio:
                    continue
                store_id = domain_to_store.get(dominio)
                if not store_id:
                    sem_loja += 1
                    continue

                batch_values.append((wine_id, store_id, url, preco_min, moeda, True, ts, ts))

        # INSERT batch com execute_values
        if batch_values and not dry_run:
            execute_values(render_cur, """
                INSERT INTO wine_sources (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
                VALUES %s
                ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING
            """, batch_values)
            sources_criados += render_cur.rowcount  # rowcount = linhas realmente inseridas (exclui conflicts)
            render_conn.commit()

        progresso(1, processados, total, inicio, sources=sources_criados, sem_vivino=sem_vivino, sem_fontes=sem_fontes)

    print(f"\n\nFase 1 concluida: {processados:,} processados | {sources_criados:,} sources criados | {sem_vivino:,} sem vivino_id | {sem_fontes:,} sem fontes | {sem_loja:,} sem loja")
    return sources_criados
```

---

## FASE 2 — Vinhos Novos (762K → verificar duplicata → wines + wine_sources)

**Input:** registros com `status = 'new'`
**Output:** novos wines + wine_sources no Render

**ANTI-DUPLICATA em 2 niveis:**
1. `check_exists_in_render()` — match exato de produtor no dict (O(1)). Se achou → cria wine_source no vinho existente
2. `ON CONFLICT (hash_dedup) DO NOTHING` — se rodar 2x, nao duplica vinhos que tem hash
3. Vinhos sem hash_dedup: o check_exists evita a maioria. Duplicatas residuais sao aceitaveis e podem ser limpas depois

### Abordagem: INSERT individual com RETURNING id + batch wine_sources

A Fase 2 usa INSERT individual pra wines (com RETURNING id) e acumula wine_sources em mini-batches.
INSERT individual garante 100% de mapeamento wine_id → fontes, sem logica complexa de lookup.
Estimativa: ~200-500K vinhos novos reais × ~100ms latencia = **~5.5-14h**.

```python
WS_MINI_BATCH = 100  # acumular wine_sources e inserir a cada 100

def fase2(local_cur, render_cur, render_conn, vivino_to_wine, domain_to_store, render_by_prod, limite=None, dry_run=False):
    print("\n" + "=" * 60)
    print("FASE 2 — Vinhos Novos com Anti-Duplicata")
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
    ws_buffer = []  # buffer pra batch insert de wine_sources

    def flush_ws_buffer():
        """Insere wine_sources acumulados no buffer."""
        nonlocal sources_criados, ws_buffer
        if not ws_buffer or dry_run:
            ws_buffer = []
            return
        execute_values(render_cur, """
            INSERT INTO wine_sources (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
            VALUES %s
            ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING
        """, ws_buffer)
        sources_criados += render_cur.rowcount
        ws_buffer = []

    def add_wine_sources(wine_id, fontes, preco_min, moeda, ts):
        """Adiciona fontes de um vinho ao buffer. Flush automatico a cada WS_MINI_BATCH."""
        for fonte in fontes:
            url = fonte.get('url') or fonte.get('link')
            if not url:
                continue
            dominio = get_domain(url)
            store_id = domain_to_store.get(dominio) if dominio else None
            if not store_id:
                continue
            ws_buffer.append((wine_id, store_id, url, preco_min, moeda, True, ts, ts))
        if len(ws_buffer) >= WS_MINI_BATCH:
            flush_ws_buffer()

    while True:
        if limite and processados >= limite:
            break

        batch_limit = min(BATCH_SIZE, (limite - processados) if limite else BATCH_SIZE)

        local_cur.execute("""
            SELECT y.id, y.prod_banco, y.vinho_banco, y.pais, y.cor, y.safra, y.uva,
                y.regiao, y.subregiao, y.abv, y.harmonizacao, y.clean_id,
                wc.nome_limpo, wc.nome_normalizado, wc.produtor_extraido,
                wc.preco_min, wc.preco_max, wc.moeda, wc.url_imagem, wc.fontes,
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

        for row in rows:
            (y_id, prod_banco, vinho_banco, pais, cor, safra, uva,
             regiao, subregiao, abv, harmonizacao, clean_id,
             nome_limpo, nome_normalizado, produtor_extraido,
             preco_min, preco_max, moeda, url_imagem, fontes_text,
             total_fontes, hash_dedup, ean_gtin) = row
            processados += 1

            fontes = parse_fontes(fontes_text)

            # 1. Verificar se ja existe no Render (match exato produtor + overlap nome)
            existing_wine_id = check_exists_in_render(prod_banco, vinho_banco, render_by_prod) if prod_banco else None

            if existing_wine_id is not None:
                # Vinho ja existe → so criar wine_sources
                encontrados_render += 1
                add_wine_sources(existing_wine_id, fontes, preco_min, moeda, ts)
            else:
                # Vinho novo → INSERT individual com RETURNING id
                if not nome_limpo:
                    pulados += 1
                    continue

                abv_float = None
                if abv:
                    try:
                        abv_float = float(str(abv).replace('%', '').replace(',', '.').strip())
                    except:
                        pass

                if dry_run:
                    continue

                # SAVEPOINT isola erros individuais sem desfazer inserts anteriores do batch.
                # Sem SAVEPOINT, 1 erro faz rollback de TODOS os inserts que funcionaram.
                render_cur.execute("SAVEPOINT wine_insert")
                try:
                    render_cur.execute("""
                        INSERT INTO wines (nome, nome_normalizado, produtor, produtor_normalizado,
                            safra, tipo, pais, regiao, sub_regiao,
                            uvas, teor_alcoolico, harmonizacao, imagem_url,
                            preco_min, preco_max, moeda, total_fontes, hash_dedup, ean_gtin,
                            descoberto_em, atualizado_em)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (hash_dedup) WHERE hash_dedup IS NOT NULL AND hash_dedup != '' DO NOTHING
                        RETURNING id
                    """, (nome_limpo, nome_normalizado, produtor_extraido, prod_banco,
                          safra, cor, pais, regiao, subregiao,
                          uva_to_jsonb(uva), abv_float, harmonizacao, url_imagem,
                          preco_min, preco_max, moeda, total_fontes, hash_dedup, ean_gtin,
                          ts, ts))

                    result = render_cur.fetchone()
                    if result:
                        new_wine_id = result[0]
                        criados += 1
                        # Criar wine_sources imediatamente (wine_id garantido)
                        add_wine_sources(new_wine_id, fontes, preco_min, moeda, ts)
                    else:
                        # ON CONFLICT — vinho ja existia por hash_dedup
                        duplicatas_hash += 1

                    render_cur.execute("RELEASE SAVEPOINT wine_insert")

                except Exception as e:
                    print(f"\n  ERRO insert wine clean_id={clean_id}: {e}")
                    render_cur.execute("ROLLBACK TO SAVEPOINT wine_insert")
                    continue

                # Atualizar render_by_prod com wine_id REAL (nao placeholder)
                # Se usasse -1 e o mesmo produtor+vinho aparecesse de novo,
                # add_wine_sources(-1, ...) causaria FK violation.
                if prod_banco and result:
                    if prod_banco not in render_by_prod:
                        render_by_prod[prod_banco] = []
                    render_by_prod[prod_banco].append((new_wine_id, nome_normalizado or ""))

        # Flush wine_sources restantes + COMMIT a cada batch
        flush_ws_buffer()
        if not dry_run:
            render_conn.commit()

        progresso(2, processados, total, inicio, criados=criados, existentes=encontrados_render, dup_hash=duplicatas_hash)

    # Flush final
    flush_ws_buffer()
    if not dry_run:
        render_conn.commit()

    print(f"\n\nFase 2 concluida: {processados:,} processados | {criados:,} criados | {encontrados_render:,} ja existiam | {duplicatas_hash:,} dup hash | {sources_criados:,} sources | {pulados:,} pulados")
    return criados
```

---

## FASE 3 — Enriquecer Vinhos Existentes (score >= 0.7 → UPDATE wines)

**Input:** ~613K registros matched com score >= 0.7 que tenham pelo menos 1 campo util
**Output:** campos NULL preenchidos nos wines do Render

**REGRA: So preenche campos NULL. NUNCA sobrescreve.**

```python
def fase3(local_cur, render_cur, render_conn, vivino_to_wine, limite=None, dry_run=False):
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

            wine_id = vivino_to_wine.get(vivino_id)
            if not wine_id:
                sem_vivino += 1
                continue

            abv_float = None
            if abv:
                try:
                    abv_float = float(str(abv).replace('%', '').replace(',', '.').strip())
                except:
                    pass

            uvas_jsonb = uva_to_jsonb(uva)

            batch_updates.append((wine_id, cor, pais, regiao, subregiao, uvas_jsonb, abv_float, harmonizacao, url_imagem))

        if dry_run or not batch_updates:
            progresso(3, processados, total, inicio, atualizados=atualizados, sem_vivino=sem_vivino)
            continue

        # BATCH UPDATE via mogrify + FROM VALUES
        # 1 round-trip de rede por batch de 1000, em vez de 1000 round-trips individuais.
        # Reduz de ~17h (UPDATE individual) pra ~10-15 minutos.
        # COALESCE: so preenche campos NULL. NUNCA sobrescreve dados existentes.
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

        # COMMIT a cada batch
        render_conn.commit()

        progresso(3, processados, total, inicio, atualizados=atualizados, sem_vivino=sem_vivino)

    print(f"\n\nFase 3 concluida: {processados:,} processados | {atualizados:,} atualizados | {sem_vivino:,} sem vivino_id")
    return atualizados
```

**NOTA: Fase 3 usa batch UPDATE via `mogrify` + `FROM VALUES`. 1 round-trip de rede por batch de 1000, em vez de 1000 round-trips individuais. Reduz de ~17h pra ~10-15 minutos.**

---

## CREDENCIAIS

```python
LOCAL_DB = dict(host="localhost", port=5432, dbname="winegod_db", user="postgres", password="postgres123")
RENDER_DB = "<DATABASE_URL_FROM_ENV>"
```

## SCHEMAS RENDER (referencia)

```sql
-- wines (1.72M registros)
CREATE TABLE wines (
    id SERIAL PRIMARY KEY,
    hash_dedup VARCHAR,
    nome TEXT, nome_normalizado TEXT,
    produtor TEXT, produtor_normalizado TEXT,
    safra VARCHAR, tipo VARCHAR, pais VARCHAR, pais_nome VARCHAR,
    regiao TEXT, sub_regiao TEXT,
    uvas JSONB,              -- ["Pinot Noir", "Merlot"]
    teor_alcoolico NUMERIC,
    volume_ml INTEGER, ean_gtin VARCHAR, imagem_url TEXT, descricao TEXT, harmonizacao TEXT,
    vivino_id BIGINT, vivino_rating NUMERIC, vivino_reviews INTEGER, vivino_url TEXT,
    preco_min NUMERIC, preco_max NUMERIC, moeda VARCHAR,
    total_fontes INTEGER, fontes JSONB,
    descoberto_em TIMESTAMPTZ, atualizado_em TIMESTAMPTZ,
    winegod_score NUMERIC, winegod_score_type VARCHAR,
    winegod_score_components JSONB, nota_wcf NUMERIC, confianca_nota NUMERIC
);

-- stores (12.7K) — chave: dominio
CREATE TABLE stores (id SERIAL PRIMARY KEY, nome TEXT, url TEXT, dominio TEXT, pais VARCHAR, ...);

-- wine_sources (66K)
CREATE TABLE wine_sources (
    id SERIAL PRIMARY KEY,
    wine_id INTEGER REFERENCES wines(id),
    store_id INTEGER REFERENCES stores(id),
    url TEXT, preco NUMERIC, preco_anterior NUMERIC, moeda VARCHAR,
    disponivel BOOLEAN, em_promocao BOOLEAN,
    descoberto_em TIMESTAMPTZ, atualizado_em TIMESTAMPTZ
);
```

## SCHEMAS LOCAL (referencia)

```sql
-- y2_results: id, clean_id, status (matched/new), prod_banco, vinho_banco, pais, cor, safra,
--   uva, regiao, subregiao, abv, harmonizacao, vivino_id, match_score, fonte_llm

-- wines_clean: id (=clean_id), nome_limpo, nome_normalizado, produtor_extraido,
--   preco_min, preco_max, moeda, url_imagem, fontes (JSON text), total_fontes, hash_dedup, ean_gtin
```

## ESTIMATIVA DE TEMPO

| Fase | Volume | Metodo | Tempo estimado |
|---|---|---|---|
| --check | - | queries | ~30 segundos |
| Fase 1 | ~1M items | batch INSERT wine_sources | **30min - 1h** |
| Fase 2 | ~762K items (~200-500K novos reais) | INSERT individual + mini-batch sources | **5 - 14h** |
| Fase 3 | ~613K items | batch UPDATE via CTE | **10 - 15 minutos** |

Fase 2 e a mais lenta porque cada vinho novo precisa de INSERT individual com RETURNING id (latencia de rede ~100ms por INSERT). Isso e necessario pra garantir o mapeamento correto wine_id → wine_sources.

## ESPECIFICACOES TECNICAS

- **Batch size:** 1000 registros por iteracao
- **Paginacao:** cursor-based (`WHERE id > last_id ORDER BY id`). NUNCA usar OFFSET
- **Batch INSERT:** `execute_values` do psycopg2.extras (NAO INSERT individual na Fase 1)
- **Commit:** a cada batch. NUNCA acumular transacao gigante
- **Timestamps:** `datetime.now(timezone.utc)`. NUNCA string `"NOW()"`
- **Idempotente:** ON CONFLICT DO NOTHING em wine_sources e wines (hash_dedup)
- **Progresso:** `Fase 1: 50,000 / 1,000,000 (5%) | 120/seg | ETA 132min | sources=42,000`
- **Erro individual:** logar e continuar (nao abortar por 1 registro)
- **Anti-duplicata Fase 2:** match exato de produtor via dict (O(1)). NUNCA iterar todos os produtores

## INTERFACE DO SCRIPT

```bash
# Sanity check (rodar PRIMEIRO)
python scripts/import_render_z.py --check

# Teste com 100
python scripts/import_render_z.py --fase 1 --limite 100
python scripts/import_render_z.py --fase 2 --limite 100
python scripts/import_render_z.py --fase 3 --limite 100

# Dry run (simula sem inserir)
python scripts/import_render_z.py --fase 1 --limite 100 --dry-run

# Producao
python scripts/import_render_z.py --fase 1
python scripts/import_render_z.py --fase 2
python scripts/import_render_z.py --fase 3

# Tudo
python scripts/import_render_z.py --fase all
```

## O QUE NAO FAZER

- **NAO modificar schema** de tabelas existentes no Render (exceto CREATE INDEX)
- **NAO deletar dados** existentes
- **NAO sobrescrever** campos que ja tem valor (usar COALESCE)
- **NAO criar lojas novas** — se a loja nao esta em `stores`, pular
- **NAO importar** status not_wine, duplicate, spirit, error — so matched e new
- **NAO usar string "NOW()"** — usar `datetime.now(timezone.utc)`
- **NAO usar OFFSET** pra paginacao — usar `WHERE id > last_id`
- **NAO iterar todos os produtores** pra dedup — usar lookup exato no dict
- **NAO acumular transacao gigante** — commit a cada batch
- **NAO fazer git commit/push**
- **NAO modificar app.py** nem arquivos do backend/frontend

## COMO TESTAR

```bash
# 1. Sanity check
python scripts/import_render_z.py --check

# 2. Dry run
python scripts/import_render_z.py --fase 1 --limite 100 --dry-run

# 3. Teste real com 100 (cada fase)
python scripts/import_render_z.py --fase 1 --limite 100
python scripts/import_render_z.py --fase 2 --limite 100
python scripts/import_render_z.py --fase 3 --limite 100

# 4. Verificar no Render
python -c "
import psycopg2
c = psycopg2.connect('<DATABASE_URL_FROM_ENV>')
cur = c.cursor()
cur.execute('SELECT COUNT(*) FROM wine_sources')
print(f'Wine sources: {cur.fetchone()[0]:,}')
cur.execute('SELECT COUNT(*) FROM wines')
print(f'Wines total: {cur.fetchone()[0]:,}')
c.close()
"

# 5. Rodar Fase 1 de novo (deve dar 0 novos — idempotente)
python scripts/import_render_z.py --fase 1 --limite 100
# Esperar: sources=0 (todos ja existem)
```

## ENTREGAVEL

1. Script `scripts/import_render_z.py` funcional
2. `--check` mostra estatisticas sem inserir
3. Testado com `--limite 100` em cada fase (sem erros)
4. Testado idempotencia: rodar 2x da mesma coisa, resultado identico
5. Relatorio no terminal: wine_sources criados, wines novos, enriquecidos, duplicatas evitadas, pulados, velocidade, ETA
