# Handoff - Auditoria Completa da Linhagem de Links de Loja ate o Render

## Missao

Voce vai reconstruir a linhagem completa dos vinhos de scraping do WineGod, desde a origem nas tabelas `vinhos_XX` e `vinhos_XX_fontes` no banco LOCAL ate os registros finais em `wines`, `stores` e `wine_sources` no Render.

O objetivo nao e apenas explicar o bug dos vinhos novos sem link no Render. A estimativa inicial usada na investigacao era `~88K`, mas a auditoria empirica mais recente registrada em `prompts/JULGAMENTO_HANDOFF_CODEX.md` aponta `76,812` casos. O objetivo maior e:

1. Provar exatamente quais URLs pertencem a quais vinhos no Render
2. Descobrir em que etapa cada link se perdeu ou foi associado ao vinho errado
3. Gerar artefatos confiaveis para correcoes posteriores
4. Deixar uma trilha de auditoria que qualquer outra IA ou engenheiro possa continuar

Este documento foi escrito para ser executado por outra IA como se fosse uma continuacao direta da investigacao humana atual.

---

## Regra Absoluta

- Nao executar `DELETE`, `INSERT`, `UPDATE`, `ALTER`, `TRUNCATE` nem qualquer correcao persistente
- Nao alterar o script `scripts/import_render_z.py`
- Nao confiar em intuicao onde uma query ou reproducao fiel do algoritmo puder responder
- Tratar o banco LOCAL como fonte de verdade dos links
- Tratar o Render como estado observado a ser auditado
- Se precisar de tabelas auxiliares, prefira arquivos locais `csv/json/md`
- Se a politica permitir `TEMP TABLE`, pode usar apenas `TEMP TABLE` de sessao; caso contrario, usar CTEs e arquivos locais

---

## O Que Voce Deve Entregar

Ao final da auditoria, entregar tudo abaixo.

1. Um diagnostico executivo em Markdown
2. Uma tabela com a contagem exata das categorias `A/B/C/D` para os vinhos novos sem link, usando como referencia atual `76,812` casos segundo `prompts/JULGAMENTO_HANDOFF_CODEX.md`
3. Um CSV ou JSON com a linhagem canonicamente reconstruida por vinho e por URL
4. Um CSV com todos os `wine_sources` esperados mas ausentes no Render
5. Um CSV completo, potencialmente grande, com todos os `wine_sources` existentes no Render mas associados ao vinho errado
6. Um CSV com casos ambiguos ou irresoluveis
7. Uma explicacao da causa raiz dominante
8. Uma proposta de correcao detalhada para outro chat executar depois

---

## Contexto Atual Ja Conhecido

Data de referencia: `2026-04-06`

Estado atual do Render, conforme investigacao em andamento:

```text
wines total:        2,506,441
wines vivino:       1,727,058
wines novos:          779,383
stores:                19,881
wine_sources:       3,659,501
wines com link:     1,008,941
wines sem link:     1,497,500
```

Breakdown relevante:

- `~1.422M` vinhos Vivino puros sem link: esperado
- estimativa inicial `~88K` vinhos novos de scraping sem link: bug
- contagem empirica mais recente: `76,812` vinhos novos de scraping sem link, segundo `prompts/JULGAMENTO_HANDOFF_CODEX.md`
- `matched`: cobertura muito alta, faltas residuais

Historico operacional relevante:

- Rodada 1 teve mapeamento de fontes errado
- No dia `2026-04-05`, a auditoria empirica mais recente identifica duas rodadas relevantes de Fase 2, uma menor por volta de `14h` e outra principal por volta de `18h`
- A mesma auditoria reporta crescimento da taxa de erro ao longo das rodadas principais, de aproximadamente `5.7%` para `13.3%` e depois `8.7%`, o que reforca a suspeita de deterioracao do ramo `check_exists_in_render` conforme o estado acumulado do Render cresce
- Rodada 2 teve reexecucao com sanitizacao
- Entre rodadas houve `DELETE` de `wine_sources` errados, o que e um contexto causal importante para explicar wines existentes sem sources
- Rodada 3 teve:
  - delete dos `wine_sources` errados
  - import de lojas faltantes
  - Fase 1 com `sem_loja=0`
  - Fase 2 concluida com erros de `encoding` e `varchar`

Isso reduz drasticamente a probabilidade de `store` faltante ser a causa dominante do problema atual.

---

## Verdades Nao Negociaveis

1. Todo vinho de scraping nasceu de uma URL de loja
2. A fonte da verdade do link e `vinhos_XX_fontes`, nao `wines_clean.fontes`
3. `wines_clean.id` nao e `vinhos_XX.id`
4. A ponte correta e sempre `wines_clean.pais_tabela + wines_clean.id_original`
5. Para `matched`, `y2_results.vivino_id` aponta para `wines.id` do Render
6. Para `new`, o render owner pode surgir por dois caminhos:
   - insercao por `hash_dedup`
   - absorcao por `check_exists_in_render`
7. Um mesmo vinho no Render pode consolidar varias linhas locais
8. Um mesmo `hash_dedup` pode consolidar varios `clean_id` em teoria, mas a auditoria empirica mais recente nao confirmou isso como fenomeno relevante nos dados atuais
9. O script atual da Fase 2 e batch com workers, nao a versao antiga de insert individual
10. O Render atual nao e a fonte da verdade dos links; ele e o estado auditado

---

## Mapa de Entidades e IDs

### Banco LOCAL

#### 1. `lojas_scraping`
- Fonte de descoberta das lojas
- Chave pratica para auditoria: dominio/url da loja

#### 2. `vinhos_XX`
- Vinhos brutos por pais
- Exemplo: `vinhos_br`, `vinhos_us`
- Chave local bruta: `vinhos_XX.id`

#### 3. `vinhos_XX_fontes`
- URLs reais dos produtos e preco por loja
- Chave pratica da fonte bruta: `(pais, vinho_id, url_original)`
- `vinho_id` aponta para `vinhos_XX.id`

#### 4. `wines_clean`
- Vinhos deduplicados
- Chave local limpa: `wines_clean.id`
- Ponte para origem bruta:
  - `pais_tabela`
  - `id_original`

#### 5. `y2_results`
- Classificacao da IA
- Campo critico:
  - `status`
  - `clean_id`
  - `vivino_id` para `matched`
  - `prod_banco`, `vinho_banco`, `safra`

### Banco RENDER

#### 6. `wines`
- Chave primaria final: `wines.id`
- Campo critico para auditoria:
  - `hash_dedup`
  - `vivino_id`
  - `nome_normalizado`
  - `produtor_normalizado`
  - `safra`

#### 7. `stores`
- Chave final de loja: `stores.id`
- Chave pratica de match:
  - `dominio`

#### 8. `wine_sources`
- Tabela final de links vinho-loja-url
- Chave semantica:
  - `(wine_id, store_id, url)`

---

## Linhagem Canonica Correta

### Caminho bruto -> limpo

```text
vinhos_XX.id
  -> wines_clean.id_original
  + wines_clean.pais_tabela
  -> vinhos_XX_fontes.vinho_id
```

### Caminho limpo -> classificacao

```text
wines_clean.id
  -> y2_results.clean_id
```

### Caminho classificacao -> Render para `matched`

```text
y2_results.status = 'matched'
  -> y2_results.vivino_id
  -> Render wines.id
```

### Caminho classificacao -> Render para `new`

Existem dois caminhos validos.

#### Caminho N1 - absorvido por vinho existente

```text
y2_results.status = 'new'
  -> check_exists_in_render(prod_banco, vinho_banco)
  -> render wine_id existente
```

ATENCAO:

- segundo a auditoria empirica registrada em `prompts/JULGAMENTO_HANDOFF_CODEX.md`, este caminho N1 e o principal suspeito de redirecionar fontes para o vinho errado
- produtores curtos ou genericos, como `espumante`, `langhe`, `barbera`, `il`, `barolo`, tendem a gerar falsos positivos no `check_exists_in_render`
- o handoff principal deve tratar esse ramo como causa raiz prioritaria a ser provada ou refutada

#### Caminho N2 - inserido por hash

```text
y2_results.status = 'new'
  -> hash_final
  -> Render wines.hash_dedup
  -> Render wines.id
```

### Caminho final para o link

```text
owner render wine_id
  + dominio derivado de url_original
  -> stores.id
  -> wine_sources(wine_id, store_id, url)
```

---

## O Que Significa "Ligar Todas as Fases"

Ha duas leituras possiveis. As duas sao validas, mas voce precisa saber qual esta executando.

### A. Reconstrucao Canonica

Pergunta:

> Dado o estado atual correto dos dados, quais URLs deveriam estar associadas a quais `wines.id` no Render?

Esse e o modo recomendado para auditoria e correcao.

### B. Replay Historico do Script

Pergunta:

> Dado o algoritmo do `import_render_z.py` e a ordem real dos lotes, qual `wines.id` o script provavelmente escolheu em cada momento?

Esse modo e util para explicar por que um bug aconteceu, mas nao e o caminho principal para corrigir a base.

Regra pratica:

- Para produzir plano de correcao, use a reconstrucao canonica
- Para provar causa raiz, complemente com replay parcial do algoritmo

---

## Fonte de Verdade por Camada

Use esta ordem de confianca.

### Para existencia de URL de produto
1. `vinhos_XX_fontes.url_original`
2. Nunca usar `wines_clean.fontes` como fonte principal
3. Nunca usar `wines.fontes` do Render como prova primaria

### Para dono do link `matched`
1. `y2_results.vivino_id`
2. Nunca usar `wines.vivino_id`

### Para dono do link `new`
1. `hash_final` reproduzido exatamente como o script
2. Se nao resolver, replay de `check_exists_in_render`
3. Se ainda nao resolver, classificar como ambiguo

### Para loja
1. `stores.dominio`
2. Dominio normalizado exatamente como no script:
   - `urlparse(url).netloc`
   - remover prefixo `www.`

---

## Pontos de Falha Ja Suspeitos ou Confirmados

### 1. Branch `check_exists_in_render`

Se um `new` e absorvido por vinho ja existente:

- ele nao depende do insert do vinho
- ele depende do algoritmo de matching por produtor e overlap de nome
- ele ainda depende de `fontes_map.get(clean_id)`
- ele ainda depende de o batch sobreviver ate o insert dos `wine_sources`

Segundo a auditoria empirica registrada em `prompts/JULGAMENTO_HANDOFF_CODEX.md`, este e o ponto de falha dominante a ser investigado primeiro:

- produtores genericos parecem redirecionar fontes para o `wine_id` errado
- a auditoria reporta `84,654` fontes excedentes em `17,314` wines receptores
- a auditoria tambem reporta que os mesmos produtores aparecem nos vinhos sem link e nos receptores errados

Regra deste handoff:

- tratar `check_exists_in_render` como suspeita principal
- provar ou refutar isso com comparacao entre links faltantes e links errados

### 2. Rollback do batch inteiro na Fase 2

No worker da Fase 2:

- qualquer `Exception` faz `rollback()` do lote inteiro
- depois o worker marca erro no batch e segue

Trecho critico do script:

```python
except Exception as e:
    print(f"\\n  [W{worker_id}] ERRO batch: {e}")
    r_conn.rollback()
    result["erros"] = len(wines_to_insert) if wines_to_insert else 0
    break
```

Implicacao:

- uma linha ruim pode perder os `wine_sources` de muitas linhas boas
- o contador de erro ainda subconta perdas, porque ele olha so `wines_to_insert`
- `existing_sources` tambem podem ser perdidos e nao entram no contador

ATENCAO:

- rollback sozinho nao explica `wine` existente sem `wine_source` se o insert do wine e do source estava na mesma transacao
- ele passa a explicar o estado atual principalmente quando combinado com:
  - vinho inserido em rodada anterior
  - `DELETE` de `wine_sources` errados entre rodadas
  - falha posterior ao recriar os `wine_sources`

### 3. Falta de observabilidade na Fase 2

A Fase 1 mede `sem_fontes` e `sem_loja`.

A Fase 2 nao mede:

- quantos `new` ficaram sem fontes
- quantos `new` tinham fonte mas sem loja
- quantos `new` perderam source por excecao de batch
- quantos casos entraram no ramo `check_exists_in_render`
- quantos matches desse ramo eram produtores genericos

### 4. Overwrite em `hash_to_fontes`

Na Fase 2:

```python
if fontes:
    hash_to_fontes[hash_final] = fontes
```

Implicacao:

- se varios `clean_id` compartilham o mesmo `hash_final` dentro do mesmo batch
- so a ultima lista de fontes sobrevive no dict
- isso pode causar perda parcial ou total de links esperados

Nota de prioridade:

- manter esse ponto como risco estrutural secundario
- a auditoria empirica mais recente nao o identificou como causa dominante do conjunto atual

---

## Reproducao Fiel de Regras do Script

### 1. Normalizacao de dominio

Reproduzir exatamente:

```python
def get_domain(url):
    d = urlparse(url).netloc
    return d.replace('www.', '') if d else None
```

Nao aplicar heuristicas extras de dominio sem registrar isso como desvio.

### 2. Fallback de hash para `new`

Reproduzir exatamente:

```python
hash_final = wc.hash_dedup if wc.hash_dedup else md5(
    f"{prod_banco or ''}|{wc.nome_normalizado or ''}|{safra or ''}"
)
```

Critico:

- usar `prod_banco`, nao `produtor_extraido`
- usar `wc.nome_normalizado`
- usar `y.safra`

### 3. Algoritmo de `check_exists_in_render`

Reproduzir exatamente:

- lookup por `produtor_normalizado` exato
- gerar `word_set` removendo palavras curtas e stopwords
- score = `overlap / max(len(nome_words), len(wnome_words))`
- match so se `score >= 0.5`

Stopwords do script:

```text
de, du, la, le, les, des, del, di, the, and, et
```

Regra:

- nao inventar fuzzy match diferente sem registrar desvio
- se fizer abordagem canonica com heuristica adicional, entregar isso separadamente

---

## Estrategia Recomendada de Execucao

Nao tente resolver tudo manualmente com queries isoladas. Isso escala mal.

O caminho certo e produzir uma auditoria em duas camadas:

1. Camada de inventario
2. Camada de comparacao

ATENCAO:

- esta e a estrategia para auditoria completa, incluindo deteccao de links faltantes e links errados
- para correcao tatica dos wines sem `wine_source`, existe um modo reduzido descrito em `prompts/HANDOFF_CORRECAO_RAPIDA_LINKS_FALTANTES_RENDER.md`
- nao confundir simplificacao operacional para correcao com rebaixamento do escopo de auditoria

### Camada 1 - Inventario Local Canonico

Construir um inventario canonico de todas as fontes locais relevantes.

Cada linha do inventario deve conter no minimo:

```text
source_pais
source_vinho_id
clean_id
status_y2
render_join_mode
render_join_key
url_original
dominio_normalizado
preco
moeda
```

### Camada 2 - Inventario Render Observado

Construir um inventario do estado atual do Render com:

```text
render_wine_id
hash_dedup
vivino_id
nome
nome_normalizado
produtor_normalizado
safra
```

e um inventario separado de:

```text
render_wine_id
store_id
url
```

### Camada 3 - Tabela de Expectativa

Para cada URL local valida, gerar a associacao esperada:

```text
expected_render_wine_id
expected_store_id
url
expected_reason
provenance_type
clean_id
```

### Camada 4 - Comparacao

Comparar expectativa com observado:

- esperado e existe: correto
- esperado e nao existe: faltando
- existe e nao e esperado: inesperado
- existe para outro wine_id: link errado

---

## Ordem Recomendada de Trabalho

### Passo 0 - Ler antes de agir

Ler:

1. `prompts/PROMPT_INVESTIGAR_LINKS_FALTANTES.md`
2. `scripts/import_render_z.py`
3. este handoff

### Passo 1 - Validar conexoes e estado

Confirmar que as duas conexoes abrem e que os totais batem aproximadamente com o contexto atual.

Conexoes:

```text
LOCAL:
host=localhost port=5432 dbname=winegod_db user=postgres password=postgres123

RENDER:
<DATABASE_URL_FROM_ENV>
```

### Passo 2 - Extrair universo relevante do LOCAL

Extrair duas tabelas logicas:

#### 2A. Universo `matched`

Campos minimos:

```sql
SELECT
    y.id AS y2_id,
    y.clean_id,
    y.vivino_id AS render_wine_id,
    y.status,
    wc.hash_dedup,
    wc.nome_normalizado,
    wc.pais_tabela,
    wc.id_original
FROM y2_results y
JOIN wines_clean wc ON wc.id = y.clean_id
WHERE y.status = 'matched'
  AND y.vivino_id IS NOT NULL;
```

#### 2B. Universo `new`

Campos minimos:

```sql
SELECT
    y.id AS y2_id,
    y.clean_id,
    y.prod_banco,
    y.vinho_banco,
    y.safra,
    y.status,
    wc.hash_dedup,
    wc.nome_normalizado,
    wc.produtor_extraido,
    wc.pais_tabela,
    wc.id_original
FROM y2_results y
JOIN wines_clean wc ON wc.id = y.clean_id
WHERE y.status = 'new';
```

Para `new`, calcular localmente:

- `hash_final`
- `render_join_mode = 'hash'` como principal
- `render_join_mode = 'check_exists'` como fallback ou replay historico

### Passo 3 - Extrair universo relevante do Render

Modo recomendado:

- em auditoria completa, carregar o universo necessario para comparar esperado vs observado
- se o ambiente estiver limitado, priorizar:
  - wines novos sem source
  - wines envolvidos em `wrong_wine_association`
  - stores
  - wine_sources apenas para as URLs relevantes

#### 3A. Wines

```sql
SELECT
    id,
    hash_dedup,
    vivino_id,
    nome,
    nome_normalizado,
    produtor_normalizado,
    safra
FROM wines;
```

#### 3B. Stores

```sql
SELECT id, dominio
FROM stores
WHERE dominio IS NOT NULL;
```

#### 3C. Wine sources

```sql
SELECT wine_id, store_id, url
FROM wine_sources;
```

### Passo 4 - Resolver donos de render para cada linha local

#### 4A. `matched`

Regra:

- owner final = `y2_results.vivino_id`

Nao usar nenhuma heuristica adicional.

#### 4B. `new` por hash

Regra:

- buscar `wines.id` por `hash_final`

Se encontrou 1 vinho:

- owner final = `wines.id`
- `provenance_type = new_hash`

Se nao encontrou:

- marcar para fallback ou categoria `D`

Se encontrou mais de 1:

- isso indica problema de unicidade; classificar como ambiguo

#### 4C. `new` por `check_exists_in_render`

Aplicar em dois cenarios:

1. para replay historico do script
2. para casos `new` sem hash resolvido no modo canonico

Regra de uso:

- manter este ramo para diagnostico e prova de causa raiz
- nao reutilizar automaticamente este ramo numa correcao tatica de links faltantes

Regra:

- buscar candidatos no mapa `render_by_prod`
- aplicar mesmo algoritmo do script
- se encontrar 1 owner com score >= 0.5:
  - owner final = esse `wines.id`
  - `provenance_type = new_existing`
- senao:
  - marcar como nao resolvido

### Passo 5 - Construir mapa `(pais, id_original) -> clean_id`

Isto e obrigatorio e nao pode ser trocado por `clean_id == vinho_id`.

Query base:

```sql
SELECT id, pais_tabela, id_original
FROM wines_clean
WHERE id_original IS NOT NULL;
```

Criar em memoria:

```text
orig_to_clean[(pais_tabela, id_original)] = clean_id
```

### Passo 6 - Carregar fontes reais somente para o universo relevante

Nao carregue `5.6M` linhas sem filtro se puder evitar.

Estrutura recomendada:

1. construir `relevant_orig_keys = {(pais, id_original)}` apenas para `matched` e `new` relevantes
2. enumerar `vinhos_%_fontes`
3. para cada tabela:
   - derivar `pais`
   - stream de `SELECT vinho_id, url_original, preco, moeda FROM tabela WHERE url_original IS NOT NULL`
   - manter somente linhas cujo `(pais, vinho_id)` esteja em `relevant_orig_keys`

Cada linha valida deve virar:

```text
clean_id
url_original
dominio_normalizado
preco
moeda
```

### Passo 7 - Gerar o inventario de links esperados

Para cada linha local com owner render resolvido:

1. derivar `expected_render_wine_id`
2. derivar `dominio_normalizado`
3. buscar `expected_store_id` em `stores`
4. registrar a expectativa

Cada expectativa deve guardar o maximo de contexto:

```text
expected_render_wine_id
expected_store_id
url
dominio
preco
moeda
clean_id
y2_id
status_y2
provenance_type
hash_final
source_pais
source_vinho_id
```

### Passo 8 - Gerar o inventario observado no Render

Modo recomendado:

- em auditoria completa, gerar inventario suficiente para detectar `wrong_wine_association`
- em ambiente com restricao de volume, filtrar primeiro para os `wines` novos sem source e para as URLs suspeitas

Para cada linha de `wine_sources`, guardar:

```text
actual_render_wine_id
actual_store_id
url
```

E tambem um indice reverso:

```text
url -> {wine_id(s)}
```

Isso sera necessario para detectar links associados ao vinho errado.

### Passo 9 - Comparar esperado vs observado

#### 9A. Comparacao exata por tripla

Chave exata:

```text
(wine_id, store_id, url)
```

Se a tripla existe:

- `status = correct_present`

Se a tripla nao existe:

- `status = expected_missing`

#### 9B. Comparacao reversa por URL

Para cada `expected_missing`, verificar:

- a URL ja existe em `wine_sources` mas com outro `wine_id`?

Se sim:

- `status = wrong_wine_association`
- guardar `actual_wine_id`

Se nao:

- `status = fully_missing`

### Passo 10 - Classificar os vinhos novos sem link em `A/B/C/D`

A classificacao deve ser por `render_wine_id` novo sem nenhum `wine_source`.

Referencia:

- estimativa inicial: `~88K`
- contagem empirica mais recente registrada em `prompts/JULGAMENTO_HANDOFF_CODEX.md`: `76,812`
- a metodologia abaixo deve continuar sendo executavel mesmo se os numeros mudarem

Regra:

#### Categoria A - bug de script

Se para o `render_wine_id`:

- existe dono local resolvido
- existe ao menos uma URL local
- existe ao menos um `store_id` no Render para essas URLs
- e mesmo assim nao existe `wine_source`

Entao:

- categoria `A`

#### Categoria B - loja faltante

Se:

- existe ao menos uma URL local
- nenhuma URL valida encontra `store_id` no Render

Entao:

- categoria `B`

#### Categoria C - sem fonte local

Se:

- o `render_wine_id` mapeia para linha(s) locais
- mas nenhuma `vinhos_XX_fontes` aparece para os `id_original`

Entao:

- categoria `C`

#### Categoria D - sem linhagem local resolvida

Se:

- o `render_wine_id` nao consegue ser ligado a `wines_clean`/`y2_results`
- nem por `hash_final`
- nem por replay controlado de `check_exists_in_render`

Entao:

- categoria `D`

### Passo 11 - Detectar links errados ja presentes

Isso e tao importante quanto os links faltantes.

Um `wine_source` e errado se:

- a URL existe no Render
- mas a reconstrucao canonica mostra que ela pertence a outro `wine_id`

Casos a auditar:

1. URL ligada a vinho errado
2. Mesma URL ligada a mais de um `wine_id`
3. URL presente no Render sem qualquer linhagem local valida

Query util no Render:

```sql
SELECT url, COUNT(DISTINCT wine_id) AS wines
FROM wine_sources
GROUP BY url
HAVING COUNT(DISTINCT wine_id) > 1
ORDER BY wines DESC, url;
```

---

## O Que Provar Com Evidencia

Ao final, a auditoria precisa provar com numeros e exemplos:

1. Quantos `new` sem link sao `A/B/C/D`
2. Quantos `matched` ainda faltam e por qual motivo
3. Quantos links errados ainda restam no Render, se houver
4. Quantos links sao recuperaveis imediatamente
5. Quantos casos precisam de decisao manual

Nao basta dizer "parece bug de script". Precisa provar com:

- contagem agregada
- amostra de casos
- query ou algoritmo reproduzivel

---

## Artefatos Recomendados

Gerar pelo menos estes arquivos locais:

1. `artifacts/render_wines_inventory.csv`
2. `artifacts/render_sources_inventory.csv`
3. `artifacts/local_matched_inventory.csv`
4. `artifacts/local_new_inventory.csv`
5. `artifacts/local_source_inventory.csv`
6. `artifacts/expected_wine_sources.csv`
7. `artifacts/missing_wine_sources.csv`
8. `artifacts/wrong_wine_sources.csv`
9. `artifacts/ambiguous_lineage_cases.csv`
10. `artifacts/audit_summary.md`

Se o volume ficar alto, use `.csv.gz`.

ATENCAO:

- `wrong_wine_sources.csv` e tao critico quanto `missing_wine_sources.csv`
- segundo a auditoria empirica mais recente, esse artefato pode ser grande

Modo reduzido para correcao tatica:

1. `artifacts/missing_wine_sources.csv`
2. `artifacts/quick_fix_summary.md`

---

## Metricas Que Devem Aparecer no Relatorio Final

No minimo:

```text
render_wines_total
render_new_wines_total
render_new_wines_without_sources
matched_expected_sources_total
matched_sources_present
matched_sources_missing
new_expected_sources_total
new_sources_present
new_sources_missing
new_without_sources_A
new_without_sources_B
new_without_sources_C
new_without_sources_D
wrong_wine_sources_total
ambiguous_hash_total
ambiguous_check_exists_total
```

---

## Queries Uteis de Validacao

### 1. Novos no Render sem qualquer source

```sql
SELECT
    w.id,
    w.nome,
    w.hash_dedup
FROM wines w
WHERE w.vivino_id IS NULL
  AND NOT EXISTS (
      SELECT 1
      FROM wine_sources ws
      WHERE ws.wine_id = w.id
  )
ORDER BY w.id;
```

### 2. Links por vinho no Render

```sql
SELECT
    w.id,
    w.nome,
    COUNT(ws.id) AS total_sources
FROM wines w
LEFT JOIN wine_sources ws ON ws.wine_id = w.id
GROUP BY w.id, w.nome
ORDER BY total_sources ASC, w.id
LIMIT 100;
```

### 3. Matched locais para um wine do Render

```sql
SELECT
    y.id AS y2_id,
    y.clean_id,
    y.vivino_id AS render_wine_id,
    wc.pais_tabela,
    wc.id_original
FROM y2_results y
JOIN wines_clean wc ON wc.id = y.clean_id
WHERE y.status = 'matched'
  AND y.vivino_id = %s;
```

### 4. New locais por hash

```sql
SELECT
    y.id AS y2_id,
    y.clean_id,
    y.prod_banco,
    y.safra,
    wc.hash_dedup,
    wc.nome_normalizado,
    wc.pais_tabela,
    wc.id_original
FROM y2_results y
JOIN wines_clean wc ON wc.id = y.clean_id
WHERE y.status = 'new'
  AND wc.hash_dedup = %s;
```

### 5. Fonte local de um `clean_id`

Use a tabela `vinhos_{pais}_fontes` correspondente ao `pais_tabela`.

Exemplo:

```sql
SELECT url_original, preco, moeda
FROM vinhos_br_fontes
WHERE vinho_id = %s
  AND url_original IS NOT NULL;
```

---

## Como Lidar com Ambiguidade

Nem todo caso fecha em 1 passo.

### Ambiguidade de hash

Se varios `clean_id` compartilham o mesmo `hash_final`:

- isso nao e necessariamente erro
- pode ser deduplicacao esperada
- mas as URLs esperadas devem ser a uniao de todas as linhas locais desse hash

Nota:

- a auditoria empirica mais recente nao confirmou esse padrao como relevante no snapshot atual
- ainda assim o algoritmo deve continuar preparado para esse caso

### Ambiguidade de owner no Render

Se mais de um `wines.id` parecer candidato:

- nao escolher arbitrariamente
- classificar como ambiguo
- registrar as evidencias

### Ambiguidade de `check_exists_in_render`

Se varios candidatos tiverem score parecido:

- registrar o score de todos
- nao mascarar isso como match certo

---

## Escopo Recomendado de Implementacao Tecnica

### Recomendacao principal

Implementar um script local de auditoria read-only em Python com `psycopg2`.

Motivos:

1. ha dois bancos distintos
2. a auditoria exige join logico cross-db
3. o volume e grande
4. o processo precisa gerar arquivos de evidencia

### Estrutura sugerida do script

```text
scripts/
  auditar_linhagem_links_render.py
artifacts/
  ...
```

### Funcoes sugeridas

```text
connect_local()
connect_render()
load_render_wines()
load_render_stores()
load_render_sources()
load_local_matched()
load_local_new()
compute_hash_final()
replay_check_exists()
stream_local_sources()
build_expected_sources()
compare_expected_vs_actual()
classify_missing_new_wines()
write_artifacts()
write_summary()
```

### Principios de implementacao

- usar leitura em chunks
- evitar carregar objetos gigantes sem necessidade
- usar sets de tuplas para comparacao rapida
- sempre escrever artefatos intermediarios
- logar progresso a cada tabela e a cada N linhas

---

## Como Saber Que a Auditoria Esta Correta

Voce deve conseguir responder com certeza:

1. Para um `render_wine_id` arbitrario, qual e a sua origem local?
2. Quais URLs locais pertencem a ele?
3. Quais dessas URLs ja estao no Render?
4. Quais faltam?
5. Se uma URL esta ligada a outro vinho, qual e o vinho correto?

Teste de sanidade:

- pegue 20 casos aleatorios de `A`
- 20 de `B`
- 20 de `C`
- 20 de `D`

Para cada um, verifique manualmente a trilha completa e confirme que a classificacao bate.

---

## Sinais de Que Voce Esta Seguindo o Caminho Errado

Pare e corrija a abordagem se voce estiver fazendo qualquer uma destas coisas:

1. usando `wines_clean.id` como se fosse `vinhos_XX.id`
2. usando `wines_clean.fontes`
3. usando `wines.vivino_id` para resolver `matched`
4. confiando em `rowcount` de `execute_values` com `ON CONFLICT`
5. auditando so por amostra sem fechar contagens agregadas
6. assumindo que `new` sempre mapeia 1:1 para `wines` do Render
7. ignorando o branch `check_exists_in_render`
8. ignorando o fallback de `hash_final`
9. ignorando o rollback do batch inteiro
10. ignorando que varios `clean_id` podem colapsar no mesmo hash
11. ignorando que `check_exists_in_render` com produtores genericos pode redirecionar fontes para o vinho errado

---

## Resultado Esperado da Investigacao

Ao terminar, a historia precisa ficar simples e defensavel:

1. Este e o mapeamento correto de linhagem dos links
2. Estes sao os links esperados no Render
3. Estes links faltam
4. Estes links estao errados
5. Estas sao as causas raiz, com peso relativo
6. Este e o procedimento seguro para corrigir depois

Se a sua resposta final nao permitir que outra IA gere os links corretos sem reabrir toda a investigacao, entao a auditoria ainda nao terminou.
