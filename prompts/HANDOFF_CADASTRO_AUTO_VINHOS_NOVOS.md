# HANDOFF — Cadastro Automatico de Vinhos Novos (Pre-Aprovacao + Enriquecimento)

**Data**: 2026-04-12
**Contexto**: Feature nova. Nenhum codigo existe ainda pra isso.
**Prioridade**: Alta — impacta diretamente a experiencia do usuario no chat.

---

## 1. O Problema

Quando um usuario manda foto, PDF, video, print ou texto com vinhos, o sistema faz OCR (Gemini/Qwen) e tenta casar com o banco (`wines`, 1.72M vinhos). Hoje:

- **Se acha no banco** → mostra nota, score, preco. Otimo.
- **Se NAO acha** → marca como `visual_only` e responde "nao temos esse vinho na base". **Experiencia ruim.**

Queremos que vinhos NAO encontrados sejam **cadastrados automaticamente** numa tabela de pre-aprovacao, **enriquecidos com dados de IAs**, e idealmente **tenham nota_wcf calculada ainda durante a sessao do usuario**.

---

## 2. O que Ja Existe (Reusar)

### 2.1 Pipeline de enriquecimento (Y2)
O projeto `winegod-app` ja tem um pipeline de enriquecimento que classifica e extrai dados de vinhos usando IAs. Documentacao completa em `prompts/PROMPT_CTO_WINEGOD_V2.md` (secao "Chat Y v2 — Enrichment Pipeline").

**Scripts existentes** (em `wine_classifier/`):
- `run_edge.py` — roda Claude Opus em abas do browser
- `run_mistral.py` — roda Mistral em abas do browser
- Scripts de browser em `scripts/lotes_llm/` — Gemini, Grok, Qwen, ChatGPT, Claude, GLM

**Via API** (mais rapido, ideal pra tempo real):
- ChatGPT 5.4 mini high — ja validado como eficiente pra enriquecimento
- Pode usar via API OpenAI (endpoint padrao)

### 2.2 Calculo de nota_wcf
Scripts em `scripts/calc_wcf*.py`. A nota_wcf e calculada com base em:
- Reviews individuais (se disponiveis)
- Media ponderada por `usuario_total_ratings`
- Fallback por media regional (mesmo pais + nota proxima)
- Detalhes em `prompts/PROMPT_CTO_WINEGOD_V2.md` secao "L+N (Score)" e "P7/P8"

### 2.3 Match Vivino
Script `scripts/trgm_fast.py` — carrega 1.7M produtores do Vivino em memoria e faz match por produtor exato + overlap de nome. 2000x mais rapido que pg_trgm puro.

### 2.4 OCR atual (onde os vinhos NAO encontrados aparecem)
Arquivo `backend/tools/media.py` — funcao `process_image()` retorna vinhos identificados.
Arquivo `backend/tools/resolver.py` — funcao `resolve_wines_from_ocr()` tenta casar com o banco. Quando NAO acha, classifica como `visual_only` em `format_resolved_context()` (backend/routes/chat.py).

### 2.5 Banco de dados
Banco `winegod` no Render (PostgreSQL 16). Tabelas relevantes:
- `wines` (~1.72M) — vinhos unicos deduplicados
- `wine_sources` — vinho x loja x preco
- `wine_scores` — scores de enrichment
- Schema completo em `database/` e `prompts/PROMPT_CTO_WINEGOD_V2.md`

---

## 3. Feature Desejada

### 3.1 Fluxo completo

```
Usuario manda foto/PDF/video/print/texto
  ↓
OCR extrai nomes de vinhos (Qwen flash / turbo — ja implementado)
  ↓
Resolver tenta casar com banco (search_wine — ja implementado)
  ↓
VINHO ENCONTRADO → fluxo normal (nota, score, preco)
  ↓
VINHO NAO ENCONTRADO → ** NOVO FLUXO **
  ↓
1. Inserir na tabela `wines_pending` (pre-aprovacao)
     - nome original do OCR
     - fonte (foto/pdf/video/print)
     - session_id do usuario
     - timestamp
     - dados brutos do OCR (producer, vintage, region, grape, price)
  ↓
2. Disparar enriquecimento async (nao bloquear o chat)
     - Chamar ChatGPT 5.4 mini high via API com prompt de enriquecimento:
       "Dado este vinho: [nome]. Retorne JSON com: nome_completo, produtor,
        pais, regiao, uva, safra, tipo (tinto/branco/rose/espumante),
        classificacao, descricao_curta, faixa_de_preco_usd, nota_estimada_0_5"
     - Opcionalmente chamar 2a IA (Mistral/Grok/Gemini) pra cross-validar
     - Salvar resultado do enriquecimento na wines_pending
  ↓
3. Verificar se existe no Vivino
     - Rodar match por produtor + nome (estilo trgm_fast.py)
     - Se achar match Vivino: puxar vivino_rating, vivino_reviews_count
     - Se NAO achar: marcar como "sem_vivino" (nao e erro — vinhos artesanais/novos)
  ↓
4. Calcular nota_wcf provisoria
     - Se tem Vivino match com reviews: usar formula WCF padrao
     - Se NAO tem Vivino: usar nota_estimada da IA + flag "estimated/ai"
     - Salvar nota_wcf + nota_wcf_type na wines_pending
  ↓
5. Responder ao usuario (ainda na mesma sessao se possivel)
     - Se enriquecimento terminou a tempo (~5-10s):
       "Encontrei esse vinho! Ele nao estava na nossa base mas ja cadastrei.
        [dados enriquecidos + nota provisoria]"
     - Se demorou demais:
       "Esse vinho ainda nao esta na nossa base. Estou analisando —
        na proxima vez que voce perguntar, ja vou ter os dados!"
  ↓
6. Aprovacao posterior (admin)
     - Painel ou script que lista wines_pending
     - Admin aprova → move pra tabela wines (producao)
     - Admin rejeita → marca como rejeitado (nao deleta, pra nao reprocessar)
```

### 3.2 Tabela `wines_pending` (sugestao de schema)

```sql
CREATE TABLE wines_pending (
    id SERIAL PRIMARY KEY,
    -- Dados do OCR (fonte original)
    ocr_name TEXT NOT NULL,
    ocr_producer TEXT,
    ocr_price TEXT,
    ocr_source VARCHAR(20), -- 'photo', 'pdf', 'video', 'screenshot', 'text'
    session_id UUID,
    
    -- Dados enriquecidos por IA
    enriched_name TEXT,
    enriched_producer TEXT,
    enriched_country VARCHAR(100),
    enriched_region VARCHAR(200),
    enriched_grape VARCHAR(200),
    enriched_type VARCHAR(20), -- tinto, branco, rose, espumante
    enriched_classification VARCHAR(100),
    enriched_description TEXT,
    enriched_price_range VARCHAR(50),
    enrichment_model VARCHAR(50), -- 'chatgpt-5.4-mini-high', 'mistral', etc.
    enrichment_raw JSONB, -- resposta completa da IA
    
    -- Match Vivino
    vivino_wine_id BIGINT,
    vivino_name TEXT,
    vivino_rating DECIMAL(3,2),
    vivino_reviews_count INTEGER,
    vivino_match_score DECIMAL(3,2),
    
    -- Nota calculada
    nota_wcf DECIMAL(3,2),
    nota_wcf_type VARCHAR(20), -- 'verified/wcf', 'estimated/ai', 'estimated/vivino'
    
    -- Status de aprovacao
    status VARCHAR(20) DEFAULT 'pending', -- pending, approved, rejected, duplicate
    approved_wine_id INTEGER REFERENCES wines(wine_id),
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_wines_pending_status ON wines_pending(status);
CREATE INDEX idx_wines_pending_ocr_name ON wines_pending(lower(ocr_name));
```

### 3.3 Onde encaixar no codigo

**Ponto de insercao**: `backend/routes/chat.py` na funcao `_process_media()` ou `format_resolved_context()`. Quando um vinho fica como `visual_only` (nao encontrado no banco), em vez de so informar "nao temos", disparar o cadastro.

**Opcao A — Sincrono (simples, bloqueante)**:
- Chamar enriquecimento inline, esperar ~5s, responder com dados
- Pro: usuario recebe dados na hora
- Contra: adiciona 5-10s de latencia na resposta

**Opcao B — Assincrono (ideal)**:
- Disparar enriquecimento em background (thread/task)
- Responder imediatamente com dados do OCR ("encontrei esse vinho, estou buscando mais info")
- Quando enriquecimento terminar, salvar na wines_pending
- Na proxima interacao do usuario sobre esse vinho, dados ja estarao la
- Pro: zero latencia extra
- Contra: mais complexo

**Recomendacao**: comecar com Opcao A (sincrono) pra validar o fluxo. Migrar pra B depois.

---

## 4. Enriquecimento via API — Prompt Sugerido

```
Voce e um especialista em vinhos. Dado o nome de um vinho (possivelmente incompleto ou com erros de OCR), retorne informacoes completas.

Vinho: "{nome_do_ocr}"
Produtor (se disponivel): "{produtor_do_ocr}"

Retorne SOMENTE JSON valido:
{
  "nome_completo": "nome oficial do vinho com produtor e safra se conhecidos",
  "produtor": "nome da vinicola",
  "pais": "pais de origem",
  "regiao": "regiao/denominacao",
  "uva": "variedade(s) de uva",
  "tipo": "tinto|branco|rose|espumante",
  "classificacao": "Reserva/Gran Reserva/etc ou null",
  "safra": "ano ou null",
  "descricao_curta": "1-2 frases descrevendo o vinho",
  "faixa_preco_usd": "XX-YY (faixa tipica em USD)",
  "nota_estimada": X.X (0.0 a 5.0, sua melhor estimativa de qualidade),
  "confianca": "alta|media|baixa" (quao confiante voce esta na identificacao),
  "vivino_provavel": true|false (voce acha que este vinho esta no Vivino?)
}

Se voce NAO reconhece o vinho, retorne confianca="baixa" e preencha o que puder.
NAO invente dados — use null para campos que nao sabe.
```

### Modelos recomendados pra enriquecimento (por ordem de preferencia)
1. **ChatGPT 5.4 mini high** — ja validado pelo fundador como eficiente
2. **Gemini 2.5 Flash** (sem thinking) — bom e barato ($0.002/call)
3. **Mistral Large** — alternativa europeia
4. **Qwen-plus** — se quiser manter no ecossistema DashScope

Custo estimado: ~$0.001-0.005 por vinho enriquecido.

---

## 5. Integracao com Match Vivino

O script `scripts/trgm_fast.py` ja faz match Vivino em memoria. A logica pode ser extraida pra uma funcao reutilizavel:

```python
def match_vivino(producer, wine_name):
    """Tenta casar com Vivino. Retorna (vivino_wine_id, rating, reviews) ou None."""
    # Carregar cache de produtores Vivino (lazy, 1x)
    # Match por produtor exato + token overlap no nome
    # Retornar melhor match com score > threshold
```

**Importante**: o match Vivino pode ser lento na primeira chamada (carrega 1.7M produtores em memoria). Ideal: manter cache em memoria (singleton) ou usar Redis.

---

## 6. Calculo de nota_wcf pra Vinhos Novos

### Se encontrou match Vivino com reviews:
Usar `scripts/calc_wcf.py` padrao — media ponderada dos reviews.

### Se NAO encontrou Vivino (vinho novo/artesanal):
Opcoes:
1. Usar `nota_estimada` da IA de enriquecimento (flag `estimated/ai`)
2. Usar media do pais+regiao como referencia (fallback do calc_wcf)
3. Marcar como `nota_wcf=NULL` e aguardar aprovacao manual

**Recomendacao**: usar opcao 1 com flag claro. O usuario ve "nota estimada por IA" em vez de "nota verificada".

---

## 7. Deduplicacao de wines_pending

Antes de inserir na wines_pending, verificar:
1. Ja existe na wines_pending com mesmo `lower(ocr_name)`? → nao duplicar
2. Ja existe na wines com nome similar? → pode ser falso negativo do resolver (ampliar busca)

---

## 8. Arquivos a Ler Antes de Comecar

Por ordem de prioridade:

1. `backend/tools/resolver.py` — entender onde vinhos NAO sao encontrados (funcao `resolve_wines_from_ocr`, `_resolve_label`, `_resolve_multi`)
2. `backend/routes/chat.py` — entender onde `visual_only` e tratado (funcao `format_resolved_context`)
3. `backend/tools/media.py` — entender o OCR (funcao `process_image`, `process_pdf`)
4. `backend/tools/search.py` — entender `search_wine()` (5 camadas)
5. `scripts/trgm_fast.py` — logica de match Vivino
6. `scripts/calc_wcf.py` ou `scripts/calc_wcf_fast.py` — calculo de nota_wcf
7. `prompts/PROMPT_CTO_WINEGOD_V2.md` — visao geral do sistema
8. `database/` — schema do banco

---

## 9. Restricoes (CLAUDE.md)

- **NAO deletar dados existentes** no banco
- **NAO alterar colunas existentes** (so adicionar novas)
- **Testar queries com LIMIT** antes de rodar em tudo
- **Perguntar antes de commit/push**
- So commitar arquivos alterados na sessao
- Caminhos sempre completos (ex: `C:\winegod-app\backend\...`)
- Usuario NAO e programador — respostas simples e diretas

---

## 10. Entregaveis Esperados

### Fase 1 (MVP — esta sessao)
1. SQL pra criar tabela `wines_pending`
2. Funcao `register_pending_wine(ocr_data, session_id)` em novo arquivo `backend/services/pending_wines.py`
3. Funcao `enrich_wine(name, producer)` que chama ChatGPT 5.4 mini high
4. Integrar no fluxo: quando resolver retorna `visual_only`, chamar `register_pending_wine` + `enrich_wine`
5. Testar com 3-5 vinhos que sabemos que NAO estao no banco

### Fase 2 (posterior)
6. Match Vivino automatico
7. Calculo nota_wcf provisoria
8. Painel admin pra aprovacao
9. Migrar pra async (background task)
10. Cross-validacao com 2a IA

---

## 11. Prompt pra Comecar a Sessao

Cole isso numa nova aba do Claude Code:

> Le `C:\winegod-app\prompts\HANDOFF_CADASTRO_AUTO_VINHOS_NOVOS.md` e comece pela Fase 1 (MVP). Crie a tabela wines_pending, a funcao de enriquecimento via API, e integre no fluxo do resolver. Teste com vinhos que nao estao no banco.
