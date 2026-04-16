# Plano de Execucao Definitivo: `nota_wcf v2`

**Data:** 2026-04-16
**Status:** AGUARDANDO APROVACAO
**Versao:** 3.1 (correcao de 3 bloqueadores de producao identificados em revisao final)

---

## 0. Objetivo

Implementar a `nota_wcf v2` como camada canonica unica de nota no winegod-app, separando:

- nota exibida
- fonte interna da nota
- selo publico de confianca
- metrica publica de volume de ratings

Ao final, backend, score, Baco, resolver, share, search, compare e frontend consomem a mesma semantica. Nenhum consumer calcula regra paralela. Nenhum script de import reintroduz classificacao antiga.

## 0.1. Escopo fechado

Entra:
- Backend de resolucao de nota (note_v2.py)
- Materializacao da Cascata B e delta_contextual
- Alinhamento do score batch e incremental
- Higiene dos scripts WCF que gravam classificacao derivada
- Auditoria e ajuste de SELECTs dos consumers
- Ajuste de prompt/contrato do Baco
- Ajuste de tipos e renderizacao no frontend
- Migrations, testes e validacao
- Rollout coordenado com rollback

NAO entra:
- Completar scraping massivo faltante (repo `winegod`)
- Enrichment de `pais` (repo `winegod`)
- Redesign visual amplo da UI
- Recalibracao de produto alem do ja fechado
- Clamp progressivo (descartado nesta versao)
- `uvas` como refinador (adiado)
- Endpoint administrativo de reload de cache

---

## 1. Auditoria tecnica: o que existe HOJE vs o que precisa existir

### 1.1. `display.py` (runtime da nota)

Estado atual (5 regras):
```
Regra 1: nota_wcf + sample >= 25 + vivino > 0  -> clamp(wcf, viv +/- 0.30) -> verified
Regra 2: nota_wcf + sample >= 1  + vivino > 0  -> clamp(wcf, viv +/- 0.30) -> estimated
Regra 3: vivino > 0                             -> vivino direto            -> estimated
Regra 4: nota_wcf + confianca >= 0.75           -> nota_wcf bruta           -> estimated/ai
Regra 5: nada                                   -> null
```

Divergencias com a spec v2:
- Clamp simetrico (+/-0.30). Spec pede assimetrico (-0.30/+0.20).
- Selo vem do sample WCF, nao do `total_ratings` publico.
- Nao existe `contextual` como tipo.
- Nao existe `display_note_source` na saida.
- Nao existe shrinkage (nota_base ponderada).
- Nao existe delta contextual para vinhos com Vivino e WCF raso.
- Nao existe `public_ratings_count` nem `public_ratings_bucket`.
- Regra 4 (AI/confianca) nao esta na spec v2 — manter como fallback residual.

### 1.2. `calc_score.py` e `calc_score_incremental.py`

Estado atual:
```
compute_nota_base:
  sample >= 25 + vivino > 0 -> clamp(wcf, viv +/- 0.30)
  vivino > 0                -> vivino direto
  senao                     -> null

winegod_score_type:
  sample >= 100 + vivino > 0 -> "verified"
  sample >= 25  + vivino > 0 -> "estimated"
  vivino > 0                 -> "estimated"
  senao                      -> null
```

Divergencias: threshold para verified e 100 (deveria vir de total_ratings). Clamp simetrico. Nenhum shrinkage. Nota diverge de display para sample 1-24. Micro-ajustes NAO mudam.

### 1.3. Scripts WCF que gravam classificacao derivada

7 scripts gravam `winegod_score_type` com semantica ANTIGA (review count):

| Script | Logica |
|---|---|
| `scripts/calc_wcf_fast.py` | reviews >= 100 -> "verified", >= 1 -> "estimated", else "none" |
| `scripts/calc_wcf.py` | idem |
| `scripts/upload_wcf_render.py` | idem |
| `scripts/upload_wcf_remaining.py` | idem |
| `scripts/upload_wcf_batched_remaining.py` | idem (via staging table) |
| `scripts/calc_wcf_batched.py` | idem (via staging table) |
| `scripts/calc_wcf_step5.py` | hardcoded "estimated" para todos |

Se qualquer um rodar depois de `calc_score.py`, sobrescreve `winegod_score_type` com logica antiga. Isso contamina a consistencia que a v2 quer estabelecer.

### 1.4. `baco_system.py`

So conhece `verified` e `estimated`. Nao entende `contextual`. Nao menciona `public_ratings_bucket`.

### 1.5. `resolver.py`

Chama `resolve_display()` para derivar status. `_derive_item_status` funciona sem mudanca (contextual retorna display_note nao-null = `confirmed_with_note`). Contexto enviado ao Claude nao expoe `public_ratings_bucket`.

### 1.6. Consumers com SELECT incompleto (CRITICO)

Os SELECTs dos consumers NAO trazem todos os campos necessarios para a note_v2:

| Campo | search.py | share.py | compare.py | details.py |
|---|---|---|---|---|
| `vivino_reviews` | NAO | NAO | NAO | SIM (SELECT *) |
| `pais` (tecnico) | NAO (so pais_nome) | NAO (so pais_nome) | NAO (so pais_nome) | SIM |
| `sub_regiao` | NAO | NAO | NAO | SIM |
| `tipo` | SIM | SIM | SIM | SIM |
| `produtor` | SIM | SIM | SIM | SIM |

Se note_v2 depende de `vivino_reviews` para `public_ratings_count`, e de `pais`/`sub_regiao` para bucket lookup, os vinhos vindos de search/share/compare vao degradar silenciosamente: sem bucket visual, sem cascata degraus 1-3.

### 1.7. Frontend (bug em producao)

- `types.ts`: `nota_tipo: "verified" | "estimated"` — sem null, sem contextual.
- `ScoreBadge.tsx`: `nota.toFixed(2)` direto — crash se null.
- `c/[id]/page.tsx`: `toWineData` converte null -> 0 e null type -> "estimated", gerando `~0.00`.

### 1.8. Schema do banco

Colunas existentes: `nota_wcf`, `nota_wcf_sample_size` (nao documentada nos schema docs), `vivino_rating`, `vivino_reviews`, `confianca_nota`, `winegod_score`, `winegod_score_type`, `winegod_score_components`, `pais`, `pais_nome`, `regiao`, `sub_regiao`, `tipo`.

Colunas possivelmente necessarias: `public_ratings_count` (depende do Gate 0).

### 1.9. Contrato canonico do payload v2

```
display_note           float | None     -- nota final
display_note_type      str | None       -- 'verified' | 'estimated' | 'contextual' | None
display_note_source    str              -- 'wcf_direct' | 'wcf_shrunk' | 'vivino_contextual_delta'
                                           | 'vivino_fallback' | 'contextual' | 'ai' | 'none'
public_ratings_count   int | None       -- contador publico bruto
public_ratings_bucket  str | None       -- '25+' | '50+' | '100+' | '200+' | '300+' | '500+' | None
wcf_sample_size        int | None       -- nota_wcf_sample_size passthrough
context_bucket_key     str | None       -- chave do bucket usado
context_bucket_level   str | None       -- nivel do bucket
context_bucket_n       int | None       -- feeders no bucket
context_bucket_stddev  float | None     -- stddev do bucket
```

### 1.10. Matriz de campos minimos por consumer

| Consumer | Campos que PRECISA trazer do banco para note_v2 funcionar |
|---|---|
| search.py | adicionar: `vivino_reviews`, `pais`, `sub_regiao` |
| models_share.py | adicionar: `vivino_reviews`, `pais`, `sub_regiao` |
| compare.py | adicionar: `vivino_reviews`, `pais`, `sub_regiao` |
| details.py | OK (SELECT *) |
| resolver.py | depende de search.py — herda os campos |
| calc_score.py | query propria — ja traz `vivino_reviews`; adicionar `pais`, `sub_regiao` |
| calc_score_incremental.py | idem |

---

## FASE 1: Gate 0 — decisao sobre contador publico

**Objetivo:** confirmar se `wines.vivino_reviews` pode ser tratado como `public_ratings_count` canonico.

**Queries (SELECT-only, todas com LIMIT):**
```sql
SELECT COUNT(*), COUNT(vivino_reviews), MIN(vivino_reviews), MAX(vivino_reviews)
FROM wines WHERE vivino_rating > 0 LIMIT 1;

SELECT COUNT(*) FROM wines
WHERE vivino_rating > 0 AND (vivino_reviews IS NULL OR vivino_reviews = 0);

SELECT COUNT(*) FROM wines
WHERE vivino_reviews >= 25 AND nota_wcf_sample_size < 25 AND vivino_rating > 0;

SELECT id, nome, vivino_rating, vivino_reviews, nota_wcf, nota_wcf_sample_size
FROM wines WHERE vivino_rating > 0 AND vivino_reviews IS NOT NULL
ORDER BY vivino_reviews DESC LIMIT 20;
```

**Decisao:**
- Se `vivino_reviews` e confiavel -> usar direto como `public_ratings_count` (alias runtime, sem migration).
- Se nao -> criar coluna `public_ratings_count` + migration idempotente + backfill.

**Criterio de saida:** decisao formal documentada, contrato do contador fechado.

---

## FASE 2: Modelo de dados e migrations

### 2.1. Migration para `wine_context_buckets`

Nome: proximo numero real disponivel no historico do repo (nao inventar sequencia).

```sql
CREATE TABLE IF NOT EXISTS wine_context_buckets (
    id SERIAL PRIMARY KEY,
    bucket_level VARCHAR(30) NOT NULL,
    bucket_key TEXT NOT NULL,
    bucket_n INTEGER NOT NULL DEFAULT 0,
    nota_base NUMERIC(4,3),
    bucket_stddev NUMERIC(4,3),
    delta_contextual NUMERIC(4,3),
    delta_n INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(bucket_level, bucket_key)
);

CREATE INDEX idx_wcb_level_key ON wine_context_buckets(bucket_level, bucket_key);
```

- Tabela nova, aditiva. Nenhum dado existente tocado.
- Delta contextual fica DENTRO da tabela (mesma granularidade que bucket, mesmo rebuild).

### 2.2. Migration para `public_ratings_count` (condicional)

Apenas se o Gate 0 reprovar `vivino_reviews` como contador publico confiavel.

Se reprovar, existem 2 cenarios possiveis e cada um tem caminho diferente:

**Cenario A: `vivino_reviews` existe mas tem semantica diferente de `total_ratings` publico.**
Por exemplo, se `vivino_reviews` no Render armazena o numero de reviews textuais (nao o total de ratings), os valores podem ser sistematicamente menores que o total_ratings real.

Caminho: cruzar com a base local `vivino_vinhos.total_ratings` (que tem a contagem publica real). Se houver cobertura suficiente:
```sql
ALTER TABLE wines ADD COLUMN IF NOT EXISTS public_ratings_count INTEGER;
-- Backfill a partir da fonte confiavel (vivino_vinhos), NAO de vivino_reviews:
UPDATE wines w
SET public_ratings_count = vv.total_ratings
FROM vivino_vinhos vv
WHERE w.vivino_id = vv.id
  AND vv.total_ratings IS NOT NULL;
```

**Cenario B: nenhuma fonte local confiavel disponivel para o total de ratings publicos.**
Se nem `vivino_reviews` nem `vivino_vinhos.total_ratings` forem confiaveis, o selo publico NAO pode ser implementado como especificado. Neste caso:
- Criar a coluna `public_ratings_count` vazia.
- Documentar que o selo publico fica inoperante ate que uma fonte confiavel seja obtida (scraping direcionado de total_ratings, ou enrichment).
- A note_v2 deve tratar `public_ratings_count = NULL` como "sem evidencia publica suficiente" e resolver selo apenas por WCF sample size + contexto.
- Isso NAO bloqueia o resto da v2 (shrinkage, cascata, clamp, delta). Bloqueia apenas a separacao selo/fonte para os 309k.
- Registrar como pendencia operacional no relatorio final.

Em NENHUM cenario a solucao e copiar uma fonte considerada nao confiavel para a coluna canonica nova. Se o Gate 0 reprovar `vivino_reviews`, `UPDATE SET public_ratings_count = vivino_reviews` esta proibido.

### 2.3. Atualizar docs de schema

Documentar `nota_wcf_sample_size` (existe no banco, ausente dos docs) e a nova tabela.

**Criterio de saida:** migrations prontas, idempotentes e aditivas.

---

## FASE 3: Materializacao da Cascata B

**Script:** `C:\winegod-app\scripts\rebuild_context_buckets.py`

### 3.1. Estrategia de rebuild: staging + swap atomico

NAO usar TRUNCATE (cria janela de bucket vazio se o rebuild falhar no meio).

Estrategia:
1. Criar tabela staging `wine_context_buckets_new` com mesma estrutura.
2. Popular staging.
3. Dentro de uma transacao: renomear `wine_context_buckets` para `_old`, renomear `_new` para `wine_context_buckets`, dropar `_old`.
4. Se qualquer passo falhar, a tabela original continua intacta.

Alternativa mais simples: `INSERT ... ON CONFLICT (bucket_level, bucket_key) DO UPDATE SET ...` que e idempotente e sem janela vazia.

### 3.2. Feeders

- APENAS vinhos com `nota_wcf IS NOT NULL AND nota_wcf_sample_size > 0`.
- NUNCA reciclar nota contextual como insumo.

### 3.3. Cascata B — 4 degraus

```
1. sub_regiao + tipo  (min_feeders=10)
2. regiao + tipo      (min_feeders=10)
3. pais + tipo        (min_feeders=10)
4. produtor + tipo    (min_feeders=2)
```

Usar `pais` (tecnico, canonico), nunca `pais_nome`.

### 3.4. Calculo por bucket

- `nota_base` = media ponderada (peso = `min(nota_wcf_sample_size, 50)`)
- `bucket_stddev` = desvio padrao da `nota_wcf` dos feeders
- `delta_contextual` = mediana de `(nota_wcf_shrunk - vivino_rating)` do cohort confiavel
- Cohort confiavel: `vivino_rating > 0 AND nota_wcf_sample_size >= 25 AND vivino_reviews >= 75`
- Minimo de 5 vinhos no cohort para aceitar delta

Logica do delta (pseudocodigo):
```python
def calc_delta(feeders, bucket_nota_base):
    cohort = [w for w in feeders
              if w.vivino_rating > 0
              and w.nota_wcf_sample_size >= 25
              and w.vivino_reviews >= 75]
    if len(cohort) < 5:
        return None, 0
    deltas = []
    for w in cohort:
        n = w.nota_wcf_sample_size
        shrunk = (n / (n + 20)) * w.nota_wcf + (20 / (n + 20)) * bucket_nota_base
        deltas.append(shrunk - w.vivino_rating)
    return median(deltas), len(cohort)
```

**Criterio de saida:** rebuild reproduzivel, logs por nivel, dados consistentes.

---

## FASE 4: Nucleo canonico `note_v2.py`

**Arquivo:** `C:\winegod-app\backend\services\note_v2.py`

### 4.1. Principio de design

- Funcoes puras para resolucao de nota — sem dependencia de Flask ou DB.
- `bucket_lookup_fn` injetavel: em producao usa `BucketCache.lookup`, em testes usa mock.
- Cache separado da logica central.
- Dois modos de operacao do cache:
  - **Web runtime:** lazy load. Se nao carregou, nota funciona com menos contexto (sem bucket/delta), mas nao crasheia o chat.
  - **Batch scripts:** fail-fast. Se `load()` falha, o script aborta com erro claro. Nunca processar 1.7M vinhos sem buckets silenciosamente.

### 4.2. Arquitetura interna

```
note_v2.py
  |
  +-- resolve_note_v2(wine, bucket_lookup_fn)  <- funcao publica principal
  |     |
  |     +-- _resolve_seal(pub_count, vivino, nota_wcf, sample)
  |     +-- _resolve_note_value(nota_wcf, vivino, sample, pub_count, wine, bucket_lookup_fn)
  |     +-- _compute_ratings_bucket(pub_count)
  |     +-- _get_public_ratings_count(wine)
  |
  +-- _shrinkage(nota_wcf, nota_base, n)       <- funcao pura
  +-- _clamp(value, min_val, max_val)          <- funcao pura
  |
  +-- BucketCache                              <- classe separada para I/O
        +-- load()                             <- le do banco; raise em falha
        +-- lookup(wine) -> bucket | None      <- cascata B
        +-- ensure_loaded()                    <- fail-fast para batch
```

### 4.3. Resolucao do selo (`_resolve_seal`)

```python
def _resolve_seal(pub_count, vivino, nota_wcf, sample):
    # Vinho com nota publica do Vivino
    if vivino is not None and vivino > 0 and pub_count is not None:
        if pub_count >= 75:
            return "verified"      # SEMPRE, independente do sample WCF
        if pub_count >= 25:
            return "estimated"

    # Vinho sem nota publica suficiente, mas com WCF proprio
    if nota_wcf is not None and sample is not None and sample > 0:
        return "estimated"

    # Placeholder — refinado para "contextual" ou None apos resolucao da nota
    return None
```

### 4.4. Resolucao da nota numerica (`_resolve_note_value`)

```python
def _resolve_note_value(nota_wcf, vivino, sample, pub_count, wine, bucket_lookup_fn):
    nwcf = float(nota_wcf) if nota_wcf is not None else None
    vr = float(vivino) if vivino is not None and vivino > 0 else None
    ss = int(sample) if sample is not None else 0
    conf = float(wine.get("confianca_nota")) if wine.get("confianca_nota") is not None else None

    bucket = bucket_lookup_fn(wine) if bucket_lookup_fn else None

    # ============================================================
    # BLOCO A: Vinho COM Vivino
    # ============================================================
    if vr is not None:

        # A1: WCF robusto (sample >= 25) -> WCF v2 com shrinkage + clamp
        if nwcf is not None and ss >= 25:
            if bucket and bucket.get("nota_base") is not None:
                nota = _shrinkage(nwcf, bucket["nota_base"], ss)
                source = "wcf_shrunk"
            else:
                nota = nwcf
                source = "wcf_direct"
            nota = _clamp(nota, vr - 0.30, vr + 0.20)
            return nota, source, bucket

        # A2: WCF raso (sample < 25) -> Vivino como ancora + delta contextual
        if bucket and bucket.get("delta_contextual") is not None:
            nota = vr + bucket["delta_contextual"]
            # nota_base como freio
            nb = bucket.get("nota_base")
            if nb is not None and nota > nb + 0.50:
                nota = nb + 0.50
            nota = _clamp(nota, vr - 0.30, vr + 0.20)
            return nota, "vivino_contextual_delta", bucket

        # A3: Sem contexto suficiente -> Vivino direto com 2 casas
        return vr, "vivino_fallback", None

    # ============================================================
    # BLOCO B: Vinho SEM Vivino
    # ============================================================

    # B1: Tem WCF proprio
    if nwcf is not None and ss > 0:
        if bucket and bucket.get("nota_base") is not None:
            nota = _shrinkage(nwcf, bucket["nota_base"], ss)
            source = "wcf_shrunk"
        else:
            nota = nwcf
            source = "wcf_direct"
        return nota, source, bucket

    # B2: Contextual puro (n=0, sem WCF, sem Vivino, mas com bucket)
    if bucket and bucket.get("nota_base") is not None:
        nota = bucket["nota_base"]
        stddev = bucket.get("bucket_stddev")
        if stddev is not None:
            nota = nota - 0.5 * stddev  # penalidade contextual
        return nota, "contextual", bucket

    # B3: Fallback AI (confianca >= 0.75, sem contexto — regra residual)
    if nwcf is not None and conf is not None and conf >= 0.75:
        return nwcf, "ai", None

    # B4: Nada
    return None, "none", None
```

### 4.5. Funcoes auxiliares puras

```python
def _shrinkage(nota_wcf, nota_base, n, k=20):
    return (n / (n + k)) * nota_wcf + (k / (n + k)) * nota_base

def _clamp(value, min_val, max_val):
    return max(min_val, min(value, max_val))

def _compute_ratings_bucket(pub_count):
    if pub_count is None or pub_count < 25:
        return None
    if pub_count >= 500: return "500+"
    if pub_count >= 300: return "300+"
    if pub_count >= 200: return "200+"
    if pub_count >= 100: return "100+"
    if pub_count >= 50:  return "50+"
    return "25+"

def _get_public_ratings_count(wine):
    # Ajustar conforme decisao do Gate 0
    return wine.get("vivino_reviews")
```

### 4.6. Montagem final do payload

```python
def resolve_note_v2(wine, bucket_lookup_fn=None):
    nota_wcf = wine.get("nota_wcf")
    vivino = wine.get("vivino_rating")
    sample = wine.get("nota_wcf_sample_size")
    pub_count = _get_public_ratings_count(wine)

    seal = _resolve_seal(pub_count, vivino, nota_wcf, sample)
    note, source, bucket_used = _resolve_note_value(
        nota_wcf, vivino, sample, pub_count, wine, bucket_lookup_fn
    )

    # Ajuste final do selo
    if source == "contextual" and seal is None:
        seal = "contextual"
    if note is None:
        seal = None
        source = "none"

    return {
        "display_note": round(note, 2) if note is not None else None,
        "display_note_type": seal,
        "display_note_source": source,
        "public_ratings_count": pub_count,
        "public_ratings_bucket": _compute_ratings_bucket(pub_count),
        "wcf_sample_size": sample,
        "context_bucket_key": bucket_used.get("bucket_key") if bucket_used else None,
        "context_bucket_level": bucket_used.get("bucket_level") if bucket_used else None,
        "context_bucket_n": bucket_used.get("bucket_n") if bucket_used else None,
        "context_bucket_stddev": bucket_used.get("bucket_stddev") if bucket_used else None,
    }
```

### 4.7. BucketCache (camada de I/O)

```python
class BucketCache:
    def __init__(self):
        self._cache = {}
        self._loaded = False

    def load(self):
        """Carrega buckets em memoria. ~5k-20k registros = ~2MB.
        Raise em falha de conexao (fail-fast para batch).
        """
        rows = db.execute("SELECT * FROM wine_context_buckets")
        self._cache = {}
        for row in rows:
            self._cache[(row["bucket_level"], row["bucket_key"])] = {
                "bucket_level": row["bucket_level"],
                "bucket_key": row["bucket_key"],
                "nota_base": float(row["nota_base"]) if row["nota_base"] else None,
                "bucket_stddev": float(row["bucket_stddev"]) if row["bucket_stddev"] else None,
                "delta_contextual": float(row["delta_contextual"]) if row["delta_contextual"] else None,
                "delta_n": row["delta_n"],
                "bucket_n": row["bucket_n"],
            }
        self._loaded = True

    def ensure_loaded(self):
        """Fail-fast para batch: raise se nao conseguir carregar."""
        if not self._loaded:
            self.load()  # propaga excecao se DB inacessivel
        if not self._cache:
            raise RuntimeError("BucketCache vazio apos load — abortar batch")

    def lookup(self, wine):
        """Cascata B: retorna melhor bucket ou None."""
        if not self._loaded:
            return None  # web runtime: graceful degradation
        tipo = (wine.get("tipo") or "").strip().lower()
        if not tipo:
            return None

        sub_regiao = (wine.get("sub_regiao") or "").strip().lower()
        regiao = (wine.get("regiao") or "").strip().lower()
        pais = (wine.get("pais") or "").strip().lower()
        vinicola = (wine.get("produtor") or wine.get("vinicola") or "").strip().lower()

        if sub_regiao:
            b = self._cache.get(("sub_regiao_tipo", f"{sub_regiao}_{tipo}"))
            if b and b["bucket_n"] >= 10:
                return b
        if regiao:
            b = self._cache.get(("regiao_tipo", f"{regiao}_{tipo}"))
            if b and b["bucket_n"] >= 10:
                return b
        if pais:
            b = self._cache.get(("pais_tipo", f"{pais}_{tipo}"))
            if b and b["bucket_n"] >= 10:
                return b
        if vinicola:
            b = self._cache.get(("vinicola_tipo", f"{vinicola}_{tipo}"))
            if b and b["bucket_n"] >= 2:
                return b

        return None

# Singleton para web runtime
_bucket_cache = BucketCache()

def get_bucket_lookup():
    """Web runtime: lazy load."""
    if not _bucket_cache._loaded:
        try:
            _bucket_cache.load()
        except Exception as e:
            print(f"[note_v2] BucketCache load failed: {e}", flush=True)
    return _bucket_cache.lookup
```

**Criterio de saida:** engine unica, pura, testavel, com enumeracoes fechadas.

---

## FASE 5: Auditoria e ajuste dos consumers backend

### 5.1. Ajuste de SELECTs

Adicionar `vivino_reviews`, `pais`, `sub_regiao` a:

**`backend/tools/search.py`** — `_WINE_COLUMNS`:
```python
# ANTES:
# id, nome, produtor, safra, tipo, pais_nome, regiao,
# vivino_rating, preco_min, preco_max, moeda,
# winegod_score, winegod_score_type, nota_wcf, nota_wcf_sample_size, confianca_nota

# DEPOIS (adicionar 3 campos):
# id, nome, produtor, safra, tipo, pais_nome, pais, regiao, sub_regiao,
# vivino_rating, vivino_reviews, preco_min, preco_max, moeda,
# winegod_score, winegod_score_type, nota_wcf, nota_wcf_sample_size, confianca_nota
```

Mesma mudanca em `get_similar_wines()`.

**`backend/db/models_share.py`** — query de `get_share()`:
```python
# Adicionar: pais, sub_regiao, vivino_reviews
```

**`backend/tools/compare.py`** — `compare_wines()` e `get_recommendations()`:
```python
# Adicionar: pais, sub_regiao, vivino_reviews
```

**`backend/tools/details.py`** — OK, usa `SELECT *`.

### 5.2. `display.py` — substituir logica antiga

```python
from services.note_v2 import resolve_note_v2, get_bucket_lookup

def resolve_display(wine):
    v2 = resolve_note_v2(wine, bucket_lookup_fn=get_bucket_lookup())

    preco_min = wine.get("preco_min")
    winegod_score = wine.get("winegod_score")
    has_price = preco_min is not None and float(preco_min) > 0
    score = round(float(winegod_score), 2) if winegod_score is not None and has_price else None

    return {
        "display_note": v2["display_note"],
        "display_note_type": v2["display_note_type"],
        "display_note_source": v2["display_note_source"],
        "display_score": score,
        "display_score_available": score is not None,
        "public_ratings_bucket": v2["public_ratings_bucket"],
    }
```

Preservar funcao `_resolve_note` antiga renomeada como `_resolve_note_legacy` para rollback.

### 5.3. `resolver.py` — expor bucket no contexto

Nas funcoes `format_resolved_context` e `_build_batch_resolved_context`, adicionar bucket:
```python
d = resolve_display(w)
bucket_str = d.get("public_ratings_bucket", "")
# Incluir "| Avaliacoes: 200+" quando disponivel
```

`_derive_item_status` nao precisa mudar: contextual com display_note nao-null = confirmed_with_note.

**Criterio de saida:** nenhum consumer depende de logica paralela ou payload incompleto.

---

## FASE 6: Score batch e incremental

### 6.1. Refatorar `calc_score.py`

```python
from services.note_v2 import resolve_note_v2, BucketCache

# Fail-fast: abortar se buckets nao carregarem
_cache = BucketCache()
_cache.ensure_loaded()

def compute_nota_base(wine_row):
    v2 = resolve_note_v2(wine_row, bucket_lookup_fn=_cache.lookup)
    return v2["display_note"]

def compute_nota_base_source(wine_row):
    v2 = resolve_note_v2(wine_row, bucket_lookup_fn=_cache.lookup)
    return v2["display_note_source"]
```

- A formula do score (nota + micro + 0.35*ln(ref/price)) NAO muda.
- Os micro-ajustes NAO mudam.
- `winegod_score_type` passa a ser derivado de `v2["display_note_type"]`.
- A query do batch precisa adicionar `pais` e `sub_regiao` ao SELECT.

### 6.2. Mesmas mudancas para `calc_score_incremental.py`

**Criterio de saida:** score e display usam a mesma base numerica. Batch e incremental produzem resultado identico.

---

## FASE 7: Higiene dos scripts WCF

### 7.1. Objetivo

Os 7 scripts devem:
- CONTINUAR gravando dados brutos: `nota_wcf`, `nota_wcf_sample_size`, `confianca_nota`
- PARAR de gravar `winegod_score_type`

A classificacao derivada e responsabilidade exclusiva do pipeline de score (calc_score).

### 7.2. Mudanca por script

| Script | Mudanca |
|---|---|
| `calc_wcf_fast.py` | Remover `winegod_score_type` do UPDATE |
| `calc_wcf.py` | Remover `winegod_score_type` do UPDATE |
| `upload_wcf_render.py` | Remover `winegod_score_type` do UPDATE |
| `upload_wcf_remaining.py` | Remover `winegod_score_type` do UPDATE/staging |
| `upload_wcf_batched_remaining.py` | Remover `winegod_score_type` do UPDATE/staging |
| `calc_wcf_batched.py` | Remover `winegod_score_type` do UPDATE/staging |
| `calc_wcf_step5.py` | Remover `winegod_score_type` do UPDATE |

A funcao `score_type()` pode ser removida de todos eles.

### 7.3. Scripts read-only (sem mudanca)

- `validate_score_after.py`, `score_report.py`, `baseline_score_report.py` — leem apenas, nao contaminam.
- `_dry_run.sql` — usa ROLLBACK, nao persiste.

**Criterio de saida:** nenhuma rotina de import reintroduz `winegod_score_type` por fora da note_v2.

---

## FASE 8: Baco e contexto de chat

### 8.1. `baco_system.py` — secao NOTAS E SCORES

```
## NOTAS E SCORES
Os dados de cada vinho incluem campos canonicos:
- `display_note`: nota de qualidade ja resolvida
- `display_note_type`: "verified", "estimated" ou "contextual"
- `display_note_source`: fonte interna (NAO expor ao usuario)
- `display_score`: custo-beneficio (pode ser null)
- `display_score_available`: true/false
- `public_ratings_bucket`: faixa publica de avaliacoes ("25+", "50+", ..., "500+")

Regras de apresentacao:
- Nota verified: "4.18 estrelas" — sem disclaimer.
  "Esse Malbec tem nota 4.18 -- os avaliadores mais experientes concordam."
- Nota estimated: "~3.85 estrelas" — com til, confiante sem pedir desculpa.
  "Nota estimada: ~3.85. Palpite educado de quem entende."
- Nota contextual: "~3.70 estrelas" — com til, linguagem segura sem parecer erro.
  "Esse eu ainda nao provei pessoalmente, mas pelo perfil da regiao e do estilo,
  estimo uns ~3.70. Quando mais gente provar, a nota fica mais precisa."
  NAO: "Nao tenho dados" ou "nota nao confiavel".
- Bucket de ratings: quando relevante, usar a faixa.
  "Mais de 200 avaliacoes publicas" ou "amplamente avaliado, com 500+ opinioes".
  NUNCA numero exato.
```

### 8.2. `BACO_SYSTEM_PROMPT_SHORT`

Adaptar com as mesmas instrucoes condensadas.

**Criterio de saida:** sem quebra de prompt, linguagem consistente com semantica nova.

---

## FASE 9: Frontend e share

### 9.1. `frontend/lib/types.ts`

```typescript
// ANTES:
nota: number
nota_tipo: "verified" | "estimated"

// DEPOIS:
nota: number | null
nota_tipo: "verified" | "estimated" | "contextual" | null
nota_bucket?: string | null
```

### 9.2. `frontend/components/wine/ScoreBadge.tsx`

```typescript
// ANTES:
interface ScoreBadgeProps {
  nota: number
  tipo: "verified" | "estimated"
}

// DEPOIS:
interface ScoreBadgeProps {
  nota: number | null
  tipo: "verified" | "estimated" | "contextual" | null
}

// Guard contra null:
if (nota === null || nota === undefined) {
  return null  // nao renderizar badge
}

// contextual -> til + opacidade reduzida (como estimated)
// estimated -> til + opacidade 60%
// verified -> opacidade 100%
```

### 9.3. `frontend/app/c/[id]/page.tsx`

```typescript
// ANTES:
nota: w.display_note ?? 0,
nota_tipo: w.display_note_type === "verified" ? "verified" : "estimated",

// DEPOIS:
nota: w.display_note,                           // null fica null
nota_tipo: w.display_note_type,                 // contextual fica contextual
nota_bucket: w.public_ratings_bucket ?? null,
```

Nos componentes:
```typescript
{wine.nota !== null && (
  <ScoreBadge nota={wine.nota} tipo={wine.nota_tipo} />
)}
```

### 9.4. `ShareWine` interface

```typescript
display_note_type: "verified" | "estimated" | "contextual" | null
public_ratings_bucket: string | null
```

### 9.5. Varrer outros componentes

Checar se ha outros cards, listas ou comparacoes que assumem nota sempre numerica. Ajustar conforme necessario.

**Criterio de saida:** sem crash, sem `~0.00`, suporte correto a contextual e ausencia de nota.

---

## FASE 10: Testes

**Arquivo principal:** `C:\winegod-app\backend\tests\test_note_v2.py`

### 10.1. Testes de selo (8 casos)

```python
def test_seal_verified_75_plus_low_sample():
    wine = {"vivino_rating": 4.2, "vivino_reviews": 100, "nota_wcf": 3.9, "nota_wcf_sample_size": 5}
    assert resolve_note_v2(wine)["display_note_type"] == "verified"

def test_seal_verified_75_plus_high_sample():
    wine = {"vivino_rating": 4.2, "vivino_reviews": 200, "nota_wcf": 4.1, "nota_wcf_sample_size": 50}
    assert resolve_note_v2(wine)["display_note_type"] == "verified"

def test_seal_estimated_25_to_74():
    wine = {"vivino_rating": 4.0, "vivino_reviews": 50}
    assert resolve_note_v2(wine)["display_note_type"] == "estimated"

def test_seal_low_public_not_verified():
    wine = {"vivino_rating": 4.0, "vivino_reviews": 10, "nota_wcf": 4.0, "nota_wcf_sample_size": 50}
    assert resolve_note_v2(wine)["display_note_type"] != "verified"

def test_seal_no_vivino_with_wcf():
    wine = {"nota_wcf": 4.0, "nota_wcf_sample_size": 50}
    assert resolve_note_v2(wine)["display_note_type"] == "estimated"

def test_seal_contextual():
    # Com bucket mockado
    wine = {"tipo": "tinto", "pais": "AR"}
    result = resolve_note_v2(wine, bucket_fn_that_returns_bucket)
    assert result["display_note_type"] == "contextual"

def test_seal_none():
    wine = {}
    assert resolve_note_v2(wine)["display_note_type"] is None

def test_sample_size_does_not_override_public_seal():
    wine = {"vivino_rating": 4.0, "vivino_reviews": 200, "nota_wcf": 3.5, "nota_wcf_sample_size": 3}
    assert resolve_note_v2(wine)["display_note_type"] == "verified"
```

### 10.2. Testes de fonte (6 casos)

```python
def test_source_wcf_with_vivino():        # sample >= 25 + vivino -> wcf_shrunk/direct
def test_source_vivino_delta():           # sample < 25 + vivino + delta -> vivino_contextual_delta
def test_source_vivino_fallback():        # sample < 25 + vivino + sem delta -> vivino_fallback
def test_source_wcf_no_vivino():          # sem vivino + WCF -> wcf_shrunk/direct
def test_source_contextual_pure():        # sem vivino + sem WCF + bucket -> contextual
def test_source_none():                   # nada -> none
```

### 10.3. Testes de clamp

```python
def test_clamp_upper():  # nao passa vivino + 0.20
def test_clamp_lower():  # nao desce abaixo de vivino - 0.30
```

### 10.4. Testes de shrinkage

```python
def test_shrinkage_50_50():           # n=20, k=20 -> 50/50
def test_shrinkage_high_sample():     # n=100, WCF domina ~83%
```

### 10.5. Testes de bucket publico

```python
def test_bucket_ranges():
    assert _compute_ratings_bucket(10) is None
    assert _compute_ratings_bucket(24) is None
    assert _compute_ratings_bucket(25) == "25+"
    assert _compute_ratings_bucket(50) == "50+"
    assert _compute_ratings_bucket(100) == "100+"
    assert _compute_ratings_bucket(200) == "200+"
    assert _compute_ratings_bucket(300) == "300+"
    assert _compute_ratings_bucket(500) == "500+"
    assert _compute_ratings_bucket(10000) == "500+"
```

### 10.6. Testes de preservacao de dados

```python
def test_no_data_mutation():
    wine = {"vivino_rating": 4.2, "vivino_reviews": 10000, "nota_wcf": 4.0, "nota_wcf_sample_size": 50}
    resolve_note_v2(wine)
    assert wine["vivino_reviews"] == 10000  # NAO truncado
```

### 10.7. Testes de consistencia display vs score

```python
def test_score_uses_same_note_as_display():
    wine = {full fields including vivino_reviews, pais, sub_regiao, tipo...}
    v2 = resolve_note_v2(wine, bucket_fn)
    display = resolve_display(wine)
    assert v2["display_note"] == display["display_note"]
```

### 10.8. Testes de integracao

```python
def test_contextual_confirmed_with_note():      # resolver nao quebra
def test_share_contextual_passthrough():         # share passa contextual
def test_search_contextual_passthrough():        # search passa contextual
def test_compare_contextual_passthrough():       # compare passa contextual
def test_ai_fallback_still_works():              # fallback AI residual
```

### 10.9. Testes de higiene WCF

```python
# Verificar que os scripts WCF ajustados nao gravam winegod_score_type
def test_wcf_fast_no_score_type_write():
    # Inspecionar SQL gerado ou mockar DB e verificar campos do UPDATE
```

### 10.10. Testes de frontend

```
# Manuais ou via Playwright/Cypress:
# - Vinho sem nota: nao renderiza ScoreBadge (sem ~0.00)
# - Vinho contextual: renderiza com til
# - Vinho verified: renderiza sem til
# - Vinho estimated: renderiza com til
```

**Criterio de saida:** cobertura dos casos centrais, regressoes de integracao, e higiene WCF.

---

## FASE 11: Validacao operacional

### 11.1. Queries SQL (somente leitura)

```sql
-- V1: Os 309k -> verificar que selo = verified
SELECT id, nome, vivino_rating, vivino_reviews, nota_wcf, nota_wcf_sample_size
FROM wines WHERE vivino_reviews >= 75 AND nota_wcf_sample_size < 25 AND vivino_rating > 0
ORDER BY vivino_reviews DESC LIMIT 20;

-- V2: WCF robusto -> verificar shrinkage + clamp
SELECT id, nome, vivino_rating, nota_wcf, nota_wcf_sample_size
FROM wines WHERE nota_wcf_sample_size >= 50 AND vivino_rating > 0 LIMIT 20;

-- V3: Sem vivino com WCF -> estimated
SELECT id, nome, nota_wcf, nota_wcf_sample_size
FROM wines WHERE vivino_rating IS NULL AND nota_wcf IS NOT NULL AND nota_wcf_sample_size > 0 LIMIT 20;

-- V4: Distribuicao por bucket visual
SELECT CASE
  WHEN vivino_reviews >= 500 THEN '500+'
  WHEN vivino_reviews >= 300 THEN '300+'
  WHEN vivino_reviews >= 200 THEN '200+'
  WHEN vivino_reviews >= 100 THEN '100+'
  WHEN vivino_reviews >= 50  THEN '50+'
  WHEN vivino_reviews >= 25  THEN '25+'
  ELSE '<25'
END AS bucket, COUNT(*) FROM wines WHERE vivino_reviews IS NOT NULL GROUP BY 1 ORDER BY 1;

-- V5: Dados brutos intactos
SELECT COUNT(*) FROM wines WHERE vivino_reviews > 500;
```

### 11.2. Script `scripts/validate_note_v2.py`

- Carrega 100 vinhos de cada cenario.
- Aplica `resolve_note_v2` a cada um.
- Aplica `_resolve_note_legacy` ao mesmo vinho (comparacao lado a lado).
- Mede:
  - Distribuicao por `display_note_type` (v2 vs legacy).
  - Distribuicao por `display_note_source`.
  - Casos com maior variacao de nota vs logica antiga.
  - Integridade do dado bruto.
- Gera relatorio.

**Criterio de saida:** relatorio read-only satisfatorio antes do deploy.

---

## FASE 12: Rollout e rollback

### 12.1. Ordem de deploy

A ordem resolve 2 restricoes:
- O frontend antigo NAO pode consumir backend novo (contextual vira estimated, null pode crashear).
- O score persistido so deve mudar DEPOIS de validar que o runtime esta correto (ver 12.2).

O frontend novo e retrocompativel: aceita `verified`, `estimated` (do backend antigo) E `contextual`, `null` (do backend novo). Portanto ele pode ser deployado PRIMEIRO sem risco.

Ordem:
1. Aplicar migration(s)
2. Popular buckets via `rebuild_context_buckets.py`
3. **Deploy frontend PRIMEIRO** (tipos + ScoreBadge + page — retrocompativel com backend antigo)
4. Validar que o frontend novo funciona com backend antigo (verified/estimated continuam renderizando)
5. **Deploy backend** (note_v2 + display + consumers + WCF hygiene)
6. Validar amostras reais pos-deploy (runtime correto, notas sensiveis)
7. **So entao rodar recalculo do score** (batch) — esta e a ultima etapa, deliberadamente
8. Validar scores pos-recalculo

O recalculo de score fica por ULTIMO porque e a unica operacao que persiste dados derivados no banco. Se algo der errado antes do passo 7, os scores estao intactos em semantica legacy e nenhum rollback de dados e necessario.

### 12.2. Estrategia de rollback

**Rollback e COORDENADO e depende de QUANDO o problema for detectado.**

Existem 3 pontos de rollback possiveis, cada um com escopo diferente:

**Ponto A: problema detectado ANTES do recalculo de score (passos 1-6).**
- Scores no banco ainda estao em semantica legacy (intactos).
- Rollback: reverter backend para legacy (`_resolve_note_legacy`). Se o frontend novo ja foi deployado, nao precisa reverter (e retrocompativel). Se quiser, pode reverter tambem.
- Resultado: sistema volta ao estado identico ao pre-deploy. Zero inconsistencia.
- Este e o cenario mais limpo e o motivo pelo qual o recalculo de score fica por ultimo.

**Ponto B: problema detectado DEPOIS do recalculo de score (passo 7+).**
- Scores no banco foram recalculados com nota v2 (winegod_score e winegod_score_type persistidos).
- Rollback de runtime: reverter backend para legacy.
- Mas agora existe inconsistencia: display mostra nota legacy, score no banco reflete nota v2.
- Para rollback completo: PRECISA re-rodar calc_score.py com a logica legacy para restaurar os scores antigos.
- Para viabilizar isso: antes de rodar o recalculo v2 no passo 7, fazer snapshot dos scores:
```sql
CREATE TABLE scores_backup_pre_v2 AS
SELECT id, winegod_score, winegod_score_type, winegod_score_components
FROM wines
WHERE winegod_score IS NOT NULL;
```
- Rollback de score: restaurar a partir do snapshot:
```sql
UPDATE wines w
SET winegod_score = b.winegod_score,
    winegod_score_type = b.winegod_score_type,
    winegod_score_components = b.winegod_score_components
FROM scores_backup_pre_v2 b
WHERE w.id = b.id;
```
- Alternativa ao snapshot: re-rodar calc_score.py com logica legacy (mais lento, mas nao precisa de tabela extra).

**Ponto C: rollback parcial — manter v2 runtime, reverter apenas score.**
- Se o problema for especificamente no recalculo de score (valores absurdos), mas o runtime de nota estiver correto.
- Restaurar scores do snapshot e re-rodar o recalculo com correcoes.

**Em todos os casos:**
- Dados brutos nunca sao tocados.
- A tabela `wine_context_buckets` pode ser ignorada (inerte se nao consultada).
- Frontend novo e retrocompativel com backend antigo — nao precisa de rollback obrigatorio.
- Mas se o backend voltar para legacy, o frontend novo mostrara `verified`/`estimated` normalmente (sem contextual, porque o backend legacy nunca emite contextual).

### 12.3. Validacao pos-deploy

- 5 vinhos verified no chat
- 3 vinhos estimated
- 2 vinhos contextual
- 1 vinho sem nota
- Comparar top-100 scores antes/depois (variacao aceitavel)

**Criterio de saida:** rollback factivel sem perda de dados, deploy validado em amostras reais.

---

## Criterios de aceite

1. Existe UMA unica fonte de verdade para nota (`note_v2.py`).
2. Nenhum consumer calcula regra propria paralela.
3. `verified` / `estimated` / `contextual` / `None` tem semantica consistente do banco ate a UI.
4. Display, share, busca, compare, resolver e score consomem a mesma base.
5. Nenhum dado bruto de rating/review foi truncado, apagado ou sobrescrito.
6. Os 309k vinhos passam a comportar-se como fallback publico ancorado, nao contextual.
7. Frontend nao mostra `~0.00` para vinhos sem nota.
8. Frontend trata `contextual` sem crash nem coercao errada.
9. Os scripts WCF/upload nao reintroduzem classificacao derivada antiga.
10. Testes cobrem regras centrais e regressoes de integracao.
11. Existe caminho de rollback coordenado sem perda de dados.

---

## Tabela de arquivos

| Arquivo | Acao | Fase |
|---|---|---|
| `backend/services/note_v2.py` | CRIAR | 4 |
| `backend/services/display.py` | MODIFICAR | 5 |
| `backend/tools/search.py` | MODIFICAR (SELECT) | 5 |
| `backend/db/models_share.py` | MODIFICAR (SELECT) | 5 |
| `backend/tools/compare.py` | MODIFICAR (SELECT) | 5 |
| `backend/tools/resolver.py` | MODIFICAR (bucket) | 5 |
| `scripts/calc_score.py` | MODIFICAR | 6 |
| `scripts/calc_score_incremental.py` | MODIFICAR | 6 |
| `scripts/calc_wcf_fast.py` | MODIFICAR (remover score_type) | 7 |
| `scripts/calc_wcf.py` | MODIFICAR (remover score_type) | 7 |
| `scripts/upload_wcf_render.py` | MODIFICAR (remover score_type) | 7 |
| `scripts/upload_wcf_remaining.py` | MODIFICAR (remover score_type) | 7 |
| `scripts/upload_wcf_batched_remaining.py` | MODIFICAR (remover score_type) | 7 |
| `scripts/calc_wcf_batched.py` | MODIFICAR (remover score_type) | 7 |
| `scripts/calc_wcf_step5.py` | MODIFICAR (remover score_type) | 7 |
| `backend/prompts/baco_system.py` | MODIFICAR | 8 |
| `frontend/lib/types.ts` | MODIFICAR | 9 |
| `frontend/components/wine/ScoreBadge.tsx` | MODIFICAR | 9 |
| `frontend/app/c/[id]/page.tsx` | MODIFICAR | 9 |
| `scripts/rebuild_context_buckets.py` | CRIAR | 3 |
| `scripts/validate_note_v2.py` | CRIAR | 11 |
| `backend/tests/test_note_v2.py` | CRIAR | 10 |
| `database/migrations/NNN_context_buckets.sql` | CRIAR | 2 |
| `reports/2026-04-16_nota_wcf_v2_delivery.md` | CRIAR | 12 |

**Arquivos que NAO mudam:**
- `backend/tools/details.py` (usa SELECT *, ja traz tudo)
- `backend/routes/chat.py` (nao toca na nota diretamente)

---

## Grafo de dependencias

```
FASE 1:  Gate 0 (vivino_reviews)               [decisao, sem codigo]
   |
FASE 2:  Migrations                             [DDL aditivo]
   |
FASE 3:  Materializacao Cascata B               [script rebuild com staging+swap]
   |
FASE 4:  note_v2.py                             [engine canonica, funcoes puras]
   |
   +-- FASE 5:  Consumers backend               [display, search, share, compare, resolver]
   |
   +-- FASE 6:  Score batch + incremental        [fail-fast no cache]
   |
   +-- FASE 7:  Higiene scripts WCF              [remover winegod_score_type]
   |
   +-- FASE 8:  Baco                             [prompt contextual + bucket]
   |
   +-- FASE 9:  Frontend                         [types, ScoreBadge, page.tsx]
   |
FASE 10: Testes                                  [unit + integracao + higiene]
   |
FASE 11: Validacao operacional                   [read-only, comparacao v2 vs legacy]
   |
FASE 12: Rollout + rollback                      [deploy coordenado]
```

Fases 5-9 podem ser feitas em paralelo apos Fase 4.
Fase 10 pode comecar junto com Fase 4 (TDD).

---

## Riscos e mitigacoes

| Risco | Mitigacao |
|---|---|
| `vivino_reviews` nao serve como contador publico | Gate 0 verifica antes de tudo. Se reprovar: cruzar com vivino_vinhos.total_ratings. Se nenhuma fonte confiavel: selo publico inoperante, resto da v2 prossegue. Nunca copiar fonte nao confiavel. |
| Consumers recebem payload incompleto | Fase 5 ajusta SELECTs. Matriz de campos garante cobertura. |
| Scripts WCF recontaminam `winegod_score_type` | Fase 7 remove escrita derivada de todos os 7 scripts. |
| Cache nao carrega em batch | Fail-fast via `ensure_loaded()`. Script aborta com erro claro. |
| Cache nao carrega em web runtime | Graceful degradation: nota funciona sem contexto, nao crasheia. |
| Rebuild de buckets falha no meio | Staging + swap atomico: tabela original intacta ate o swap completar. |
| Buckets vazios para vinhos sem `pais` | Esperado. Cai pro degrau 4 ou sem nota contextual. |
| Shrinkage altera nota de vinhos existentes | Intencional. Clamp impede mudancas exageradas. |
| Frontend crasheia com null | Fase 9 corrige ANTES do deploy. |
| `contextual` nao entendido pelo Baco | Fase 8 atualiza prompt. |
| Deploy backend quebra frontend antigo | Frontend deploya PRIMEIRO (retrocompativel). Janela de incompatibilidade eliminada. |
| Score persistido inconsistente apos rollback | Recalculo de score e ultimo passo. Antes dele, rollback nao toca em dados persistidos. Depois dele, snapshot permite restauracao. |
| Schema docs desatualizados | Fase 2 atualiza. Usar migrations e queries como fonte primaria. |

---

## O que NAO esta neste plano (escopo futuro)

- Completar scraping massivo (repo `winegod`)
- Enrichment de `pais` (maior alavanca de cobertura, mas e pipeline)
- Clamp progressivo (descartado nesta versao)
- `uvas` como refinador da cascata (aprovado conceitualmente, adiado)
- Endpoint admin de reload de cache (desnecessario — startup + TTL interno basta)
- Delta contextual em tabela separada (mesma granularidade, fica como coluna)
- WhatsApp WABA / MCP Server
- Redesign visual amplo da UI
