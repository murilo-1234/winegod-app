# HANDOFF — Recalcular WCF local e subir pro Render

**Data**: 2026-04-12
**Objetivo**: Recalcular `nota_wcf` pra todos os vinhos com reviews no `vivino_db` local e subir os resultados pro banco `winegod` no Render, corrigindo um bug critico onde `nota_wcf_sample_size` esta NULL pra todos os vinhos.
**Prioridade**: Alta. Sem o `nota_wcf_sample_size`, o produto ignora o WCF e usa `vivino_rating` puro.

---

## INSTRUCAO PRINCIPAL

**ANTES de executar qualquer coisa, elabore um plano de execucao detalhado com cada query/comando que pretende rodar, e espere a aprovacao do usuario.** Nao rode nada no banco do Render sem aprovacao explicita. O usuario nao e programador — explique de forma simples.

---

## 1. CONTEXTO — DOIS BANCOS ENVOLVIDOS

### PC local — `vivino_db` (`postgresql://postgres:postgres123@localhost:5432/vivino_db`)

Onde ficam os reviews brutos scrapeados do Vivino. Tabelas relevantes:

| Tabela | Rows | O que tem |
|---|---|---|
| `vivino_reviews` | ~35M (com rating > 0) | Reviews individuais: `vinho_id` (int), `rating` (real, 1.0-5.0), `usuario_id` (int) |
| `vivino_reviewers` | ~4.8M | Perfis de reviewers: `usuario_id` (int PK), `total_ratings` (int — quantas avaliacoes o reviewer fez no Vivino) |
| `vivino_vinhos` | 1.738.585 | Catalogo Vivino: `id` (int PK = vivino_id), `rating_medio`, `total_ratings`, `nota_estimada` (campo legado local; fora da decisao atual do produto), `reviews_coletados`, `total_reviews_db` |
| `wcf_calculado` | 1.289.183 (DESATUALIZADO) | Resultado do ultimo calculo WCF. Colunas: `vinho_id`, `nota_wcf`, `total_reviews_wcf`. **Este calculo foi feito ANTES de ~72.873 vinhos ganharem reviews novos.** |

**Joins corretos (nomes reais dos campos):**
- `vivino_reviews.vinho_id` → `vivino_vinhos.id`
- `vivino_reviews.usuario_id` → `vivino_reviewers.usuario_id`

### Render — `winegod` (connection string em `C:\winegod-app\backend\.env` como `DATABASE_URL`)

Banco de producao do produto WineGod.ai. Tabela `wines` (2.506.441 vinhos).

**Campos relevantes na tabela `wines`:**

| Campo | Tipo | Estado atual | O que deveria ter |
|---|---|---|---|
| `vivino_id` | bigint | 1.727.058 populados | Chave de ligacao com `vivino_vinhos.id` |
| `vivino_rating` | numeric | 1.727.058 populados | Nota publica oficial do Vivino (OK, nao mexer) |
| `vivino_reviews` | integer | 1.559.186 populados | Contagem publica do Vivino (OK, nao mexer) |
| `nota_wcf` | decimal(3,2) | 1.727.054 populados | Nota WCF — **DESATUALIZADA** (calculada antes dos ultimos 72K vinhos com reviews) |
| `nota_wcf_sample_size` | integer | **NULL PRA TODOS** | **BUG CRITICO** — deveria ter o numero de reviews usadas no calculo WCF |
| `confianca_nota` | decimal(3,2) | 1.727.054 populados | Confianca 0.2-1.0 baseada em sample_size |
| `winegod_score_type` | varchar | 1.727.054 populados | "verified" ou "estimated" |

### Por que `nota_wcf_sample_size = NULL` e um BUG CRITICO

O arquivo `C:\winegod-app\backend\services\display.py` resolve a nota que o Baco (IA sommelier) mostra ao usuario em runtime:

```python
# Rule 1: sample >= 100 + vivino exists -> clamp(wcf, vivino +/- 0.30) -> "verified"
# Rule 2: sample >= 25  + vivino exists -> clamp(wcf, vivino +/- 0.30) -> "estimated"
# Rule 3: vivino exists                 -> vivino direto               -> "estimated"
# Rule 4: nada                          -> null
```

Com `nota_wcf_sample_size = NULL`, as regras 1 e 2 **NUNCA disparam**. O produto SEMPRE cai na regra 3 (usa `vivino_rating` puro). Ou seja, **toda a nota WCF calculada para 1,7M vinhos esta sendo ignorada pelo produto.**

---

## 2. A FORMULA WCF (fonte da verdade)

Documentada em `C:\winegod-app\prompts\PROMPT_CHAT_H_WCF.md` linhas 73-98.

**Query com nomes de campos REAIS do banco:**

```sql
SELECT
    r.vinho_id,
    ROUND(
        SUM(r.rating * CASE
            WHEN COALESCE(rv.total_ratings, 0) <= 10 THEN 1.0
            WHEN rv.total_ratings <= 50 THEN 1.5
            WHEN rv.total_ratings <= 200 THEN 2.0
            WHEN rv.total_ratings <= 500 THEN 3.0
            ELSE 4.0
        END) /
        NULLIF(SUM(CASE
            WHEN COALESCE(rv.total_ratings, 0) <= 10 THEN 1.0
            WHEN rv.total_ratings <= 50 THEN 1.5
            WHEN rv.total_ratings <= 200 THEN 2.0
            WHEN rv.total_ratings <= 500 THEN 3.0
            ELSE 4.0
        END), 0)
    , 2) AS nota_wcf,
    COUNT(*) AS total_reviews_wcf
FROM vivino_reviews r
LEFT JOIN vivino_reviewers rv ON rv.usuario_id = r.usuario_id
WHERE r.rating IS NOT NULL AND r.rating > 0
GROUP BY r.vinho_id;
```

**Intuicao:** media ponderada das notas de cada review, onde reviewers mais experientes contam mais:

| Experiencia do reviewer | total_ratings | Peso |
|---|---|---|
| Novato | 0-10 | 1.0x |
| Casual | 11-50 | 1.5x |
| Regular | 51-200 | 2.0x |
| Ativo | 201-500 | 3.0x |
| Expert | 500+ | 4.0x |

**Resultado esperado:** ~1.361.814 vinhos com nota_wcf (todos que tem pelo menos 1 review com rating > 0 no vivino_db). Isso e ~72K a mais que o wcf_calculado atual (1.289.183).

**AVISO:** A query roda em 35M reviews x 4.8M reviewers. Pode levar 5-30 minutos no PC local. Indice recomendado: `CREATE INDEX IF NOT EXISTS idx_reviews_vinho ON vivino_reviews(vinho_id);` (ja deve existir).

---

## 3. CAMPOS DERIVADOS (calculados a partir do resultado WCF)

Apos ter `nota_wcf` e `total_reviews_wcf` por vinho, calcular:

### confianca_nota (0.2 - 1.0)
```python
def confianca(total_reviews_wcf):
    if total_reviews_wcf >= 100: return 1.0
    if total_reviews_wcf >= 50:  return 0.8
    if total_reviews_wcf >= 25:  return 0.6
    if total_reviews_wcf >= 10:  return 0.4
    return 0.2
```

### winegod_score_type ("verified" / "estimated")
```python
def score_type(total_reviews_wcf):
    if total_reviews_wcf >= 100: return "verified"
    if total_reviews_wcf >= 1:   return "estimated"
    return "none"
```

### nota_wcf_sample_size (= total_reviews_wcf direto)

---

## 4. PIPELINE DE UPLOAD PRO RENDER

### Scripts existentes (em `C:\winegod-app\scripts\`):

| Script | O que faz | Atualiza sample_size? |
|---|---|---|
| `calc_wcf.py` | Le `wcf_results.csv`, UPDATE em lotes de 1000 | **SIM** (atualiza nota_wcf, confianca_nota, winegod_score_type, nota_wcf_sample_size) |
| `calc_wcf_fast.py` | Le `wcf_results.csv`, COPY + single UPDATE | **NAO** (so atualiza nota_wcf, confianca_nota, winegod_score_type — **BUG: esquece sample_size**) |
| `calc_wcf_batched.py` | Le de staging table `_wcf_bulk` no Render | **NAO** |

**ATENCAO:** O upload anterior usou `calc_wcf_fast.py` que NAO atualiza `nota_wcf_sample_size`. Por isso o campo esta NULL no Render. A solucao e:
- Usar `calc_wcf.py` (que ja atualiza sample_size), OU
- Corrigir `calc_wcf_fast.py` adicionando `nota_wcf_sample_size` na staging table e no UPDATE

### Formato do CSV (`wcf_results.csv`):
```csv
vinho_id,nota_wcf,total_reviews_wcf
1163903,4.13,100
66284,4.54,100
...
```

---

## 5. O QUE PRECISA SER FEITO (plano sugerido — ESPERAR APROVACAO)

### Etapa 1 — Recalcular WCF no vivino_db local (zero risco ao Render)
1. Verificar que o indice `idx_reviews_vinho` existe em `vivino_reviews(vinho_id)`
2. Rodar a query WCF (secao 2 acima) no vivino_db
3. Salvar resultado em `wcf_calculado` (DROP + recreate) ou exportar direto pra CSV
4. Validar: contar linhas, verificar range de nota_wcf (deve ser 1.0-5.0), media (~3.70)
5. Comparar com o wcf_calculado anterior: quantos novos, quantos mudaram

### Etapa 2 — Exportar pra CSV
```sql
COPY (SELECT vinho_id, nota_wcf, total_reviews_wcf FROM wcf_calculado) 
TO 'C:/winegod-app/scripts/wcf_results.csv' WITH CSV HEADER;
```

### Etapa 3 — Dry-run no Render (LIMIT 1000, com ROLLBACK)
1. Fazer backup do estado atual:
```sql
COPY (SELECT vivino_id, nota_wcf, confianca_nota, winegod_score_type, nota_wcf_sample_size 
      FROM wines WHERE nota_wcf IS NOT NULL LIMIT 10) 
TO STDOUT WITH CSV HEADER;
```
2. Rodar o upload pra 1000 vinhos com ROLLBACK no final
3. Verificar que os 4 campos foram atualizados (especialmente `nota_wcf_sample_size` NAO NULL)

### Etapa 4 — Upload completo pro Render
1. Usar `calc_wcf.py` (que atualiza os 4 campos incluindo sample_size) OU corrigir `calc_wcf_fast.py`
2. Rodar o upload completo (~1.36M vinhos)
3. Tempo estimado: 5-15 minutos

### Etapa 5 — Validacao pos-upload
```sql
-- Verificar cobertura
SELECT 
    COUNT(*) AS total,
    COUNT(nota_wcf) AS com_wcf,
    COUNT(nota_wcf_sample_size) AS com_sample,
    COUNT(*) FILTER (WHERE nota_wcf_sample_size >= 100) AS verified,
    COUNT(*) FILTER (WHERE nota_wcf_sample_size BETWEEN 25 AND 99) AS estimated,
    COUNT(*) FILTER (WHERE nota_wcf_sample_size BETWEEN 1 AND 24) AS low_sample
FROM wines;

-- Verificar que display.py agora usa WCF (testar regra 1)
SELECT vivino_id, nota_wcf, vivino_rating, nota_wcf_sample_size,
       CASE 
         WHEN nota_wcf_sample_size >= 100 AND vivino_rating > 0 THEN 'rule1_verified'
         WHEN nota_wcf_sample_size >= 25 AND vivino_rating > 0 THEN 'rule2_estimated'
         WHEN vivino_rating > 0 THEN 'rule3_vivino'
         ELSE 'rule4_null'
       END AS display_rule
FROM wines
WHERE nota_wcf IS NOT NULL
ORDER BY nota_wcf_sample_size DESC NULLS LAST
LIMIT 20;
```

### Etapa 6 — Testar no produto
Fazer 3-5 perguntas ao Baco sobre vinhos que agora tem `nota_wcf_sample_size >= 100` e verificar se a nota mostrada e diferente de `vivino_rating` (sinal de que `display.py` esta usando WCF).

---

## 6. REGRAS ABSOLUTAS

1. **NAO deletar dados existentes no Render.** Apenas UPDATE.
2. **NAO alterar colunas existentes.** Apenas popular campos que estao NULL ou atualizar valores existentes.
3. **Testar com LIMIT / dry-run antes de rodar em tudo.**
4. **SEMPRE perguntar antes de commit/push.**
5. **O CSV `wcf_results.csv` NAO deve ser commitado no git** (dados pesados).
6. **`nota_wcf` bruta NUNCA e sobrescrita por regra de display** — o display e resolvido em runtime por `display.py`.
7. **Nao mexer em `vivino_rating` nem `vivino_reviews`** — esses campos vem de import separado e estao corretos.

---

## 7. NUMEROS DE REFERENCIA (pra validacao)

| Metrica | Valor esperado |
|---|---|
| Reviews com rating > 0 no vivino_db | ~35.044.788 |
| Vinhos distintos com review rating > 0 | ~1.361.814 |
| wcf_calculado anterior (desatualizado) | 1.289.183 rows |
| Vinhos NOVOS que ganharam reviews e nao tem WCF | ~72.873 |
| nota_wcf range esperado | 1.00 - 5.00 |
| nota_wcf media esperada | ~3.70 |
| nota_wcf_sample_size no Render ANTES | NULL (todos) |
| nota_wcf_sample_size no Render DEPOIS | 1 ate ~17.500 (maioria 1-100) |

---

## 8. CREDENCIAIS E CAMINHOS

- `.env` do projeto: `C:\winegod-app\backend\.env` (contem `DATABASE_URL` do Render)
- `vivino_db` local: `postgresql://postgres:postgres123@localhost:5432/vivino_db`
- psql: `"C:\Program Files\PostgreSQL\16\bin\psql.exe"`
- Scripts existentes: `C:\winegod-app\scripts\calc_wcf.py`, `calc_wcf_fast.py`, `calc_wcf_batched.py`
- Formula WCF documentada: `C:\winegod-app\prompts\PROMPT_CHAT_H_WCF.md`
- Display layer: `C:\winegod-app\backend\services\display.py`
- Baco system prompt: `C:\winegod-app\backend\prompts\baco_system.py`

---

## 9. COMPORTAMENTO ESPERADO

- Respostas curtas, sem jargao. Usuario nao e programador.
- Sempre caminho completo `C:\...` ao citar arquivo.
- Perguntar antes de QUALQUER commit/push.
- Mostrar queries antes de rodar (especialmente UPDATE no Render).
- Dry-run + LIMIT sempre que possivel.
- Duvida sobre produto → parar e perguntar.

---

## 10. RESUMO EXECUTIVO

**Problema:** O produto WineGod.ai calcula nota WCF pra 1.7M vinhos mas NUNCA a usa porque `nota_wcf_sample_size` esta NULL no Render. O produto sempre mostra `vivino_rating` puro.

**Solucao:** Recalcular WCF no vivino_db local (que agora tem ~72K vinhos a mais com reviews) e subir pro Render com os 4 campos corretos: `nota_wcf`, `confianca_nota`, `winegod_score_type`, **`nota_wcf_sample_size`**.

**Impacto esperado:** ~1.36M vinhos passam a ter nota WCF real no produto (em vez de vivino_rating puro). Desses, ~1.2M terao sample_size >= 100 ("verified") e o Baco passara a mostrar notas WCF clampeadas (vivino +/- 0.30) em vez de vivino puro.

**IMPORTANTE:** Ha um re-scrape de 147K vinhos capados rodando em background (worker no Render, ~60 dias). Esse recalculo WCF NAO precisa esperar o re-scrape terminar — usa os dados que JA existem na base. Quando o re-scrape terminar, rodar este mesmo processo de novo pra incluir as reviews novas.
