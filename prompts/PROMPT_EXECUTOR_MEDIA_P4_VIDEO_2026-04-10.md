# Executor - Video

Voce vai endurecer o fluxo de video do WineGod sem abrir novas frentes.

## Escopo desta sprint

Inclui:
- video curto de rotulo
- video curto de prateleira
- reducao de redundancia entre frames
- latencia mais controlada
- contexto final mais honesto

Nao inclui:
- PDF
- foto de cardapio/lista
- text upload / texto colado
- reabrir matching
- redesign amplo da midia
- nova UX de gravacao de video no frontend

## Estado atual real

- `C:\winegod-app\backend\tools\media.py` ja tem `process_video()`
- hoje ele:
  - valida `<= 50 MB`
  - valida `<= 30s`
  - extrai frames com `ffmpeg` em `fps=1`
  - limita a `30` frames
  - envia os frames extraidos ao modelo de visao atual
  - deduplica por `(name, producer)` com merge conservador de campos
  - devolve descricao textual para o chat
- `C:\winegod-app\backend\routes\chat.py` usa esse resultado para montar contexto textual ao Baco
- video ainda analisa todos os frames extraidos
- video ainda NAO faz selecao inteligente de poucos frames uteis
- video ainda NAO tem a maturidade de imagem
- objetivo desta sprint NAO e paridade total com imagem

## Objetivo

Melhorar video para ficar UTIL e HONESTO:
- menos chamadas redundantes
- menos risco de latencia explosiva
- melhor consolidacao entre frames
- resposta menos assertiva quando os frames forem ruins ou parciais

## O que fazer

1. Ler:
- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\routes\chat.py`
- opcionalmente `C:\winegod-app\backend\services\tracing.py`
- opcionalmente `C:\winegod-app\prompts\HANDOFF_MEDIA_P4_VIDEO.md`

2. Melhorar `process_video()` com foco em:
- filtro barato de redundancia antes da chamada cara ao modelo
- selecao de poucos frames uteis
- limite claro de trabalho por video
- deduplicacao conservadora entre frames
- sinalizacao de leitura parcial / fraca quando fizer sentido

3. Melhorar o contexto entregue em `chat.py` para:
- deixar claro que a leitura veio de frames amostrados de um video
- deixar claro quando a leitura pode ser parcial
- evitar falsa precisao
- manter o Baco usando `search_wine` sem reabrir matching

4. Adicionar logs minimos por etapa se isso ajudar a enxergar latencia

5. Se fizer sentido, adicionar 1 teste pequeno focado em video/contexto

## Restricoes

- nao mexer em `C:\winegod-app\backend\tools\search.py`
- nao mexer em `C:\winegod-app\backend\prompts\baco_system.py` salvo necessidade minima e bem justificada
- nao mexer em frontend salvo bug claro de validacao/upload
- nao assumir deploy automatico
- nao abrir nova infra de provider se a infra atual ja resolver
- nao tentar dar paridade total com imagem nesta sprint
- nao misturar esta sprint com PDF ou foto de cardapio/lista
- nao vender como "video resolvido por completo"

## Criterios de sucesso

- video curto de 1 vinho responde sem travar
- video curto de prateleira responde de forma util
- video ruim ou sem vinho cai em fallback honesto
- latencia fica limitada
- nao ha regressao em foto/PDF

## O que eu NAO aceito como entrega

- "video agora esta resolvido por completo"
- texto bonito sem codigo
- latencia explosiva escondida por fallback
- reabertura de matching ou OCR de imagem

## Sugestoes de validacao

- um video curto de 1 vinho
- um video curto de prateleira
- um video com movimento ruim
- um video sem vinho

## Formato obrigatorio do relatorio final

1. `Diagnostico do fluxo atual`
2. `O que mudou no pipeline de video`
3. `O que mudou no contexto enviado ao Baco`
4. `Testes e validacoes executados`
5. `Riscos restantes`

## Importante

- Nao diga que foi deployado
- Se nao rodar algum teste, diga isso explicitamente
- Video util e honesto vale mais do que video "completo" e instavel
