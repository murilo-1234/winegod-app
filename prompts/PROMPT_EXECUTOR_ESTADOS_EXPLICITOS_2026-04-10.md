# Executor - Sprint de Estados Explicitos

Voce vai executar a proxima sprint de produto do WineGod: estados explicitos de confirmacao.

## Objetivo desta aba

Esta aba e a EXECUTORA.

Voce NAO vai rediscutir produto amplo.
Voce NAO vai abrir novas frentes.
Voce vai pegar um escopo curto e entregar codigo + validacao.

## Projeto

- app: `https://chat.winegod.ai/`
- backend: `https://winegod-app.onrender.com/healthz`
- repo local: `C:\winegod-app`

## Contexto resumido do estado aprovado

O sistema vinha sofrendo com:
- recall baixo
- candidate generation insuficiente
- alguns bugs de matching
- cobertura desigual de base
- latencia alta
- fragilidade de infra no Render Basic

Nos ultimos ciclos, o matching foi endurecido e estabilizado.

Estado aprovado hoje:
- OCR melhorou bastante
- o Baco ficou mais honesto
- a separacao entre visual e confirmado melhorou
- falsos positivos graves cairam muito
- `Cuatro Vientos Tinto` agora fica `unresolved`
- `D. Eugenio` teve melhora real de latencia
- batch agora preserva preco OCR por item no contexto

## Regressoes historicas que NAO podem voltar

1. `MontGras Aura` colapsando para:
- `Day One`
- `De.Vine`

2. `Casa Silva Family Wines` colapsando para:
- `Los Lingues Single Block`

3. `Toro Centenario Chardonnay` colapsando para:
- `Centenario Rose`

## Testes / confianca atual

- suite principal reportada: `88/88`
- matching esta mais seguro
- o foco desta sprint NAO e mexer em matching

## Escopo exato desta sprint

Formalizar os 3 estados por item:
- `visual_only`
- `confirmed_no_note`
- `confirmed_with_note`

Hoje o sistema ja age como se esses estados existissem, mas isso ainda esta implicito em texto/contexto.

Seu trabalho e transformar isso em estrutura explicita no backend.

## Arquivos-alvo

- `C:\winegod-app\backend\tools\resolver.py`
- `C:\winegod-app\backend\routes\chat.py`
- `C:\winegod-app\backend\services\display.py`
- opcionalmente 1 teste novo focado em estados/contexto

## Arquivos que voce pode ler para contexto

- `C:\winegod-app\backend\tools\resolver.py`
- `C:\winegod-app\backend\routes\chat.py`
- `C:\winegod-app\backend\services\display.py`
- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\prompts\baco_system.py`
- `C:\winegod-app\backend\tests\test_resolver_line_matching.py`

## Arquivos que voce NAO deve tocar

- `C:\winegod-app\backend\tools\search.py`
- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\prompts\baco_system.py`
- frontend
- deploy
- infra externa
- qualquer refatoracao ampla fora do escopo

## Regras de negocio que devem virar estrutura

### `visual_only`

Use quando:
- o item foi lido via OCR
- mas nao foi confirmado com seguranca na base

Pode carregar:
- nome visual
- preco visual
- outros sinais visuais uteis

Nao pode carregar:
- nota confirmada
- score
- ranking
- texto que pareca confirmacao de banco

### `confirmed_no_note`

Use quando:
- o item foi confirmado na base
- mas nao ha `display_note` utilizavel

Pode carregar:
- dados do banco
- produtor, linha, safra, preco de banco se houver

Nao pode:
- parecer que existe nota quando nao existe
- inventar score
- ser misturado com ranking de vinhos avaliados

### `confirmed_with_note`

Use quando:
- o item foi confirmado na base
- e existe `display_note`

Pode:
- participar de comparacao
- participar de ranking
- aparecer como confirmado com nota

## Resultado de produto esperado

Depois desta sprint:
- cada item precisa ter um estado explicito
- o pipeline interno precisa saber em qual estado o item esta
- o contexto textual para o Baco precisa refletir esse estado
- batch e single precisam ficar coerentes

## O que voce deve fazer

1. Identificar onde o item resolvido nasce em `C:\winegod-app\backend\tools\resolver.py`
2. Definir o estado explicito ali, ou no ponto mais proximo e seguro
3. Propagar esse estado ate `C:\winegod-app\backend\routes\chat.py`
4. Se necessario, usar `C:\winegod-app\backend\services\display.py` para derivar `confirmed_no_note` vs `confirmed_with_note`
5. Ajustar o contexto textual para nao confundir:
   - visual com confirmado
   - confirmado sem nota com confirmado com nota

## Restricoes

- Nao mexer em matching
- Nao mexer em latencia
- Nao mexer em prompt/persona
- Nao afrouxar protecoes historicas
- Nao assumir deploy automatico
- Nao abrir nova frente de enrichment
- Nao fazer redesign de arquitetura

## Criterios de sucesso

- Cada item resolvido tem estado explicito
- `visual_only` nunca parece confirmado
- `confirmed_no_note` nunca parece ter nota
- `confirmed_with_note` continua apto para ranking/comparacao
- contexto de batch e single ficam alinhados
- nenhum fluxo aprovado anteriormente sofre regressao

## O que eu NAO aceito como entrega

- so explicacao sem estrutura explicita
- mudanca que dependa de mexer em prompt para compensar ambiguidade
- reabertura de `resolver.py` para mudar matching
- alteracao de `search.py`
- alteracao de `media.py`
- "funciona em tese", sem evidencia de codigo e validacao

## Sugestoes de validacao

Sem ampliar demais a suite, valide pelo menos:
- um item `visual_only`
- um item `confirmed_no_note`
- um item `confirmed_with_note`
- consistencia entre single image e batch
- ausencia de regressao nos caminhos ja aprovados

Se criar teste novo, mantenha escopo pequeno e diretamente ligado aos estados.

## Formato obrigatorio do relatorio final

Entregue em 5 blocos:

1. `Onde os estados passaram a ser definidos`
- ponto exato do pipeline
- campos adicionados ou alterados

2. `Como eles percorrem o pipeline`
- de `resolver.py` ate `chat.py`
- onde `display.py` entra, se entrar

3. `O que mudou no contexto enviado ao Baco`
- single
- batch
- como `visual_only`, `confirmed_no_note` e `confirmed_with_note` aparecem ou deixam de aparecer

4. `Testes e validacoes executados`
- comandos
- resultados
- o que foi validado manualmente, se houver

5. `Riscos restantes`
- qualquer ambiguidade residual
- qualquer dependencia manual
- qualquer ponto que precise de sprint seguinte

## Importante

- Nao diga que foi deployado.
- Se nao rodar algum teste, diga isso explicitamente.
- Melhor mudanca pequena e correta do que mudanca grande e instavel.
- Melhor unresolved do que confirmacao errada.
