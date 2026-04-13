# HANDOFF — Problema P5: Deduplicação de Vinhos (Vivino vs Lojas)

## Quem é você neste chat
Você é um engenheiro de dados sênior investigando um problema crítico de deduplicação no WineGod.ai. Sua missão é **estudar o problema, diagnosticar a causa raiz e propor soluções**. NÃO implemente nada ainda — só entregue o diagnóstico e a proposta.

---

## O que é o WineGod.ai

WineGod.ai é uma IA sommelier. O usuário manda fotos de vinhos no chat (chat.winegod.ai) e o sistema identifica o vinho, dá nota, compara preços.

### Stack
- **Frontend**: Next.js + TypeScript (Vercel)
- **Backend**: Python 3.11, Flask (`C:\winegod-app\backend\`)
- **Banco**: PostgreSQL 16 no Render (`winegod`)
- **IA Chat**: Claude Haiku 4.5 (Anthropic API)
- **IA OCR**: Gemini 2.5 Flash (fotos → identificação de vinhos)
- **Cache**: Upstash Redis

### Repositórios
- `winegod-app` (ESTE) — produto: chat frontend + backend API + system prompt
- `winegod` (SEPARADO, em `C:\winegod\`) — pipeline de dados: scraping Vivino, scraping lojas, enrichment, dedup

### Banco de dados — tabela `wines`
~1.72M vinhos. Campos relevantes:
- `id` — PK
- `nome` — nome do vinho (texto livre, vem de fontes diferentes)
- `nome_normalizado` — versão normalizada para busca
- `produtor`, `safra`, `tipo`, `pais_nome`, `regiao`
- `vivino_id` — ID do vinho no Vivino (NULL se veio de loja)
- `vivino_rating` — nota Vivino original (NULL se veio de loja)
- `vivino_reviews` — número de reviews no Vivino
- `nota_wcf` — nota calculada por Weighted Collaborative Filtering
- `winegod_score` — score custo-benefício (nota ajustada / preço normalizado)
- `winegod_score_type` — "verified" (100+ reviews), "estimated", "none"
- `preco_min`, `preco_max`, `moeda` — preço (pode vir do Vivino ou de lojas)

### Outras tabelas relevantes
- `wine_sources` — vinho × loja × preço (relação N:N)
- `stores` — lojas de vinho (~57K)

---

## O PROBLEMA

Testamos 24 fotos de vinhos reais de prateleiras de supermercado brasileiro. A OCR do Gemini identificou ~40 vinhos. Buscamos no banco:

- **10 (25%)** têm vivino_rating
- **19 (48%)** existem no banco mas SEM rating
- **11 (28%)** não encontrados

Investigando mais fundo, descobrimos que a maioria dos vinhos "sem rating" **existem no banco DUAS VEZES**:

### Versão 1: Vinda do scraping do Vivino
- Tem `vivino_id`, `vivino_rating`, `nota_wcf`, `winegod_score`
- Nome no formato do Vivino (ex: "Las Moras Cabernet Sauvignon")

### Versão 2: Vinda do scraping de lojas brasileiras
- Sem `vivino_id` (NULL), sem `vivino_rating` (NULL), sem `nota_wcf` (NULL)
- Nome no formato da loja (ex: "FINCA LAS MORAS CABERNET SAUVIGNON")

**Quando o usuário busca, o sistema encontra a versão da LOJA (sem dados) em vez da versão do VIVINO (com dados).**

---

## EXEMPLOS CONCRETOS DO BANCO

### Exemplo 1: Finca Las Moras Cabernet Sauvignon
```
VERSÃO VIVINO:
  ID=40743 | nome="Las Moras Cabernet Sauvignon" | vivino_id=1133655 | vivino_rating=3.40 | wcf=3.46

VERSÃO LOJA (sem dados):
  ID=1803853 | nome="FINCA LAS MORAS CABERNET SAUVIGNON" | vivino_id=NULL | vivino_rating=NULL
  ID=1806948 | nome="VINO FINCA LAS MORAS CABERNET SAUVIGNON 750CC" | vivino_id=NULL
```

### Exemplo 2: Perez Cruz Piedra Seca
```
VERSÃO VIVINO:
  ID=1537829 | nome="Piedra Seca Cabernet Sauvignon" | vivino_id=11452537 | vivino_rating=4.10

VERSÃO LOJA:
  Não encontrado por "Perez Cruz Piedra Seca" — nome diferente demais!
```

### Exemplo 3: Chaski / Petit Verdot
```
VERSÃO VIVINO:
  ID=94874 | nome="Petit Verdot Chaski" | vivino_id=1231597 | vivino_rating=4.10 | wg_score=5.00

VERSÃO LOJA:
  ID=1796520 | nome="Chaski Petit Verdot 2019" | vivino_id=NULL | tudo NULL
```

### Exemplo 4: Dom Perignon (GRAVE — nenhuma versão com rating!)
```
VERSÃO VIVINO COM RATING: NÃO EXISTE NO BANCO (!)
  (O Vivino tem Dom Perignon com rating 4.6, mas nosso scraping não trouxe com vivino_id)

VERSÃO LOJA (sem dados):
  ID=1756999 | nome="DOM PERIGNON LOUMINOUS LABEL" | vivino_id=NULL
  ID=1748294 | nome="2012 Dom Perignon Brut" | vivino_id=NULL
  ID=1740942 | nome="1995 Dom Perignon, P2" | vivino_id=NULL
```

### Exemplo 5: Luigi Bosca (match ERRADO!)
```
VERSÃO "VIVINO" COM RATING: VINHO ITALIANO DIFERENTE!
  ID=251059 | nome="'Luigi Bosca' Moscato d'Asti" | vivino_rating=4.30 | pais=Itália
  (Este é um produtor ITALIANO, não o argentino!)

VERSÃO LOJA (argentino correto, sem dados):
  ID=1757396 | nome="Luigi Bosca De Sangre Malbec DOC" | vivino_id=NULL
```

### Vinhos genuinamente AUSENTES (nem versão Vivino nem loja):
- **Contada 1926** (Chianti/Primitivo) — marca existe no Vivino (url: vivino.com/pt-PT/contada-1926-chianti/w/13174009) mas não foi scrapeada
- **She's Always Pinot Noir RED** — só temos Rosé e Spumante, falta o tinto (url: vivino.com/en/enoitalia-she-s-always-pinot-noir/w/12788727)
- **Corvezzo Prosecco DOC Treviso** — url: vivino.com/US/en/corvezzo-prosecco-treviso/w/2260165, rating 3.9
- **Perez Cruz Grenache** — url: vivino.com/US/en/perez-cruz-grenache/w/10001666, rating 4.0
- **MontGras Aura Reserva CS** — url: vivino.com/NL/en/montgras-aura-reserva-cabernet-sauvignon/w/7379406

---

## NÚMEROS DO BANCO

```sql
-- Total de vinhos
SELECT COUNT(*) FROM wines;  -- ~1.72M

-- Vinhos com vivino_id (vieram do Vivino)
SELECT COUNT(*) FROM wines WHERE vivino_id IS NOT NULL;  -- verificar

-- Vinhos sem vivino_id (vieram de lojas)
SELECT COUNT(*) FROM wines WHERE vivino_id IS NULL;  -- verificar

-- Vinhos com rating
SELECT COUNT(*) FROM wines WHERE vivino_rating IS NOT NULL;  -- verificar

-- Vinhos de lojas sem rating
SELECT COUNT(*) FROM wines WHERE vivino_id IS NULL AND vivino_rating IS NULL;  -- verificar
```

---

## ARQUIVOS QUE VOCÊ PRECISA LER

### Neste repo (winegod-app):
- `C:\winegod-app\backend\tools\search.py` — função search_wine (como Baco busca vinhos)
- `C:\winegod-app\backend\tools\details.py` — get_wine_details
- `C:\winegod-app\backend\db\connection.py` — conexão com banco
- `C:\winegod-app\scripts\calc_score.py` — cálculo do winegod_score
- `C:\winegod-app\scripts\calc_wcf.py` — importação do nota_wcf
- `C:\winegod-app\database\` — migrações SQL, schema

### No repo separado (winegod):
- `C:\winegod\` — pipeline de dados (scraping, enrichment, dedup)
- Procurar scripts de dedup, merge, ou linking entre Vivino e lojas
- Procurar como os vinhos de lojas são inseridos no banco
- Procurar o vivino scraper e entender por que vinhos como Dom Perignon não foram scrapeados com rating

---

## O QUE VOCÊ DEVE INVESTIGAR

1. **Quantos vinhos duplicados existem?** — Vinhos que estão no banco 2+ vezes (versão Vivino + versão loja) sem link entre si
2. **Por que a dedup não funciona?** — Existe algum processo de dedup? Se sim, por que falha? Se não, nunca foi feito?
3. **Por que Dom Perignon não tem vivino_id?** — É um dos vinhos mais famosos do mundo, deveria estar no scraping do Vivino
4. **Como os vinhos de lojas entram no banco?** — Qual script insere? Por que não faz match com o Vivino na hora da inserção?
5. **Qual a melhor estratégia de dedup?** — fuzzy match por nome? match por vivino_url? combinação de produtor+nome+país?

---

## O QUE VOCÊ DEVE ENTREGAR

1. **Diagnóstico completo** — causa raiz do problema, números exatos de duplicatas
2. **Mapa do pipeline** — como os dados fluem desde o scraping até a tabela wines
3. **Proposta de solução** — com prós e contras de cada abordagem:
   - Opção A: Dedup retroativa (merge de registros existentes)
   - Opção B: Link na hora da busca (search_wine prioriza versão com rating)
   - Opção C: Dedup na inserção (prevenir futuras duplicatas)
   - Ou combinação
4. **Riscos** — o que pode dar errado em cada abordagem
5. **Estimativa de esforço** — simples/médio/complexo para cada opção

---

## REGRAS

- NÃO implemente nada. Só diagnóstico e proposta.
- NÃO faça commit ou push.
- NÃO delete dados do banco.
- NÃO altere colunas existentes.
- Pode rodar queries SELECT no banco para investigar.
- Use caminhos completos ao mencionar arquivos.
- Respostas em português, simples e diretas.
- O usuário NÃO é programador — explique de forma acessível.
