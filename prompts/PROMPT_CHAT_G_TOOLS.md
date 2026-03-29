# CHAT G — 14 Tools do Claude + Busca Fuzzy (WineGod)

## CONTEXTO
WineGod.ai e uma IA sommelier. O backend Flask ja existe em `C:\winegod-app\backend\`. O chat com Baco funciona, mas ele NAO consegue buscar vinhos no banco — so responde com conhecimento geral. Voce vai criar as 14 tools que permitem ao Baco consultar o banco de 1.72M vinhos.

## COMO TOOLS FUNCIONAM NO CLAUDE
A Claude API tem uma feature chamada "tool use". Voce define ferramentas como JSON schema, o Claude decide quando usar cada uma, e o backend executa a funcao correspondente e retorna o resultado pro Claude.

## CONEXAO COM O BANCO
Criar arquivo `C:\winegod-app\backend\.env` (se nao existir):
```
ANTHROPIC_API_KEY=sk-ant-api03-XXXXXXXXX (ver .env)
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod
FLASK_ENV=development
FLASK_PORT=5000
```

## SUA TAREFA

1. Criar as 14 tools como funcoes Python em `backend/tools/`
2. Definir os JSON schemas pra Claude API em `backend/tools/schemas.py`
3. Modificar `backend/services/baco.py` pra enviar tools na chamada da API
4. Modificar `backend/routes/chat.py` pra processar tool_use responses

## ESTRUTURA A CRIAR

```
C:\winegod-app\backend\tools\
  __init__.py
  schemas.py          <- JSON schemas das 14 tools
  search.py           <- search_wine, get_similar_wines
  details.py          <- get_wine_details, get_wine_history
  prices.py           <- get_prices, get_store_wines
  compare.py          <- compare_wines, get_recommendations
  media.py            <- process_image, process_video, process_pdf, process_voice (stubs)
  location.py         <- get_nearby_stores
  share.py            <- share_results
  executor.py         <- recebe tool_name + args, executa a funcao certa
```

## AS 14 TOOLS

### 1. search_wine(query, limit=5)
Busca vinhos por nome usando pg_trgm (fuzzy match).
```sql
SELECT id, nome, produtor, safra, tipo, pais_nome, regiao,
       vivino_rating, vivino_reviews, preco_min, preco_max, moeda,
       winegod_score, winegod_score_type, nota_wcf,
       similarity(nome_normalizado, %s) as sim
FROM wines
WHERE nome_normalizado % %s
ORDER BY sim DESC, vivino_reviews DESC NULLS LAST
LIMIT %s
```

### 2. get_wine_details(wine_id)
Retorna TODOS os dados de um vinho especifico.
```sql
SELECT * FROM wines WHERE id = %s
```

### 3. get_prices(wine_id, country=None)
Retorna precos de um vinho nas lojas. (wine_sources pode estar vazio ainda — retornar preco_min/preco_max da tabela wines como fallback)
```sql
SELECT ws.preco, ws.moeda, ws.url, ws.disponivel, s.nome as loja, s.pais
FROM wine_sources ws JOIN stores s ON ws.store_id = s.id
WHERE ws.wine_id = %s AND ws.disponivel = TRUE
ORDER BY ws.preco ASC
```

### 4. compare_wines(wine_ids[])
Compara 2-5 vinhos lado a lado.
```sql
SELECT id, nome, produtor, safra, tipo, pais_nome, regiao, uvas,
       vivino_rating, vivino_reviews, preco_min, preco_max, moeda,
       winegod_score, winegod_score_type, nota_wcf
FROM wines WHERE id = ANY(%s)
```

### 5. get_recommendations(filters)
Retorna top N vinhos por score/rating com filtros.
Filtros possiveis: tipo (tinto/branco/rose/espumante), pais, regiao, uva, preco_max, preco_min, limit.
```sql
SELECT id, nome, produtor, safra, tipo, pais_nome, regiao,
       vivino_rating, preco_min, moeda, winegod_score, nota_wcf
FROM wines
WHERE tipo ILIKE %s AND preco_min <= %s AND preco_min >= %s ...
ORDER BY winegod_score DESC NULLS LAST, vivino_rating DESC NULLS LAST
LIMIT %s
```

### 6. process_image(base64_image)
STUB — retorna mensagem "OCR ainda nao implementado". Sera implementado depois.

### 7. process_video(base64_video)
STUB.

### 8. process_pdf(base64_pdf)
STUB.

### 9. process_voice(audio_text)
STUB — na verdade, voz ja vira texto no frontend (Web Speech API). Entao esta tool simplesmente repassa o texto como busca.

### 10. get_store_wines(store_name, filters={})
Busca vinhos de uma loja especifica. (depende de stores estar populado)
```sql
SELECT w.id, w.nome, w.produtor, ws.preco, ws.moeda
FROM wine_sources ws
JOIN wines w ON ws.wine_id = w.id
JOIN stores s ON ws.store_id = s.id
WHERE s.nome ILIKE %s AND ws.disponivel = TRUE
ORDER BY w.vivino_rating DESC
LIMIT 20
```

### 11. get_similar_wines(wine_id, limit=5)
Encontra vinhos similares por uva + regiao + faixa de preco.
```sql
-- Primeiro pega o vinho base
-- Depois busca similares
SELECT id, nome, produtor, pais_nome, regiao, vivino_rating, preco_min, moeda
FROM wines
WHERE tipo = (tipo do base)
AND pais = (pais do base)
AND regiao = (regiao do base)
AND id != (wine_id)
AND preco_min BETWEEN (preco_base * 0.5) AND (preco_base * 1.5)
ORDER BY vivino_rating DESC NULLS LAST
LIMIT %s
```

### 12. get_wine_history(wine_id)
STUB — historico de preco nao existe ainda. Retornar preco atual.

### 13. get_nearby_stores(latitude, longitude, radius_km=50)
STUB — geolocalizacao das lojas nao existe ainda. Retornar mensagem.

### 14. share_results(wine_ids[])
Gera link compartilhavel. Por enquanto, retorna um ID unico que pode ser usado no futuro.

## SCHEMAS (schemas.py)

Cada tool precisa de um JSON schema pra Claude API. Formato:
```python
TOOLS = [
    {
        "name": "search_wine",
        "description": "Busca vinhos por nome. Use quando o usuario mencionar um vinho especifico ou quiser encontrar vinhos por nome.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nome do vinho, produtor, ou regiao para buscar"},
                "limit": {"type": "integer", "description": "Maximo de resultados (default 5)", "default": 5}
            },
            "required": ["query"]
        }
    },
    # ... mais 13 tools
]
```

IMPORTANTE nas descriptions: seja CLARO sobre QUANDO o Claude deve usar cada tool. Isso guia a decisao do modelo.

## MODIFICAR baco.py

O arquivo `backend/services/baco.py` atual chama Claude sem tools. Voce precisa:

1. Importar TOOLS de tools/schemas.py
2. Adicionar `tools=TOOLS` na chamada da API
3. Processar o response: se o Claude retornar `tool_use`, executar a tool e enviar o resultado de volta
4. Loop: Claude pode chamar multiplas tools antes de dar a resposta final

Fluxo:
```
Usuario pergunta → Claude recebe (com tools disponiveis)
→ Claude decide usar search_wine("malbec mendoza")
→ Backend executa search_wine, retorna resultados
→ Claude recebe resultados, formula resposta como Baco
→ Resposta final vai pro usuario
```

Para streaming: o tool_use acontece ANTES do streaming da resposta. Ou seja:
1. Primeira chamada: Claude retorna tool_use (nao streaming)
2. Executar tool, pegar resultado
3. Segunda chamada: Claude recebe resultado + gera resposta (streaming)

## MODIFICAR chat.py

Atualizar a rota /api/chat/stream pra suportar o loop de tools:
1. Chamar Claude com tools
2. Se response tem tool_use: executar, chamar Claude de novo com resultado
3. Repetir ate Claude dar resposta de texto
4. Fazer streaming da resposta de texto final

## O QUE NAO FAZER
- NAO alterar o BACO_SYSTEM_PROMPT
- NAO alterar o frontend (outra tarefa)
- NAO criar tabelas no banco
- NAO importar dados
- NAO fazer git commit/push
- NAO commitar .env

## COMO TESTAR

```bash
cd C:\winegod-app\backend
pip install -r requirements.txt
python app.py
```

Teste via curl:
```bash
# Busca direta
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Me indica um Malbec argentino bom", "session_id": "test1"}'

# Deve retornar resposta do Baco COM dados reais do banco (nomes, notas, precos)

# Comparacao
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Compara Catena Malbec com Trapiche Malbec", "session_id": "test2"}'

# Recomendacao
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Me recomenda 3 tintos ate 50 dolares", "session_id": "test3"}'
```

Se o Baco responder com nomes especificos de vinhos, notas e precos vindos do banco, as tools estao funcionando.

## ENTREGAVEL
- 14 tools implementadas em `backend/tools/`
- `baco.py` modificado pra usar tools
- `chat.py` modificado pra processar tool_use
- Baco consulta o banco ao responder
