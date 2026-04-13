# HANDOFF — Mídia P1: Shelf e Screenshot

## Quem é você neste chat
Você é o engenheiro responsável por transformar o fluxo de `shelf` e `screenshot` do WineGod.ai em um caminho funcional, confiável e validável no request path real.

Você não está começando do zero. O fluxo de foto única de rótulo já foi estabilizado em produção. O seu trabalho agora é expandir essa qualidade para imagens com **múltiplos vinhos**.

---

## O que já funciona

O backend já consegue:

- receber imagem
- rodar OCR via Gemini
- distinguir `label`, `shelf`, `screenshot` e `not_wine`
- usar pre-resolve no backend antes do Claude para o fluxo principal de rótulo
- responder corretamente a uma foto sem vinho
- fazer streaming com status

O que **não** foi validado com a mesma profundidade:

- prateleiras com múltiplos vinhos
- screenshots de apps/sites/listas
- ranking e desambiguação de vários vinhos na mesma imagem
- resposta do Baco sem exagerar o que “viu”

---

## O problema desta fase

Hoje o WineGod.ai já tem código parcial para `shelf` e `screenshot`, mas essa cobertura ainda não tem a mesma robustez do fluxo de `label`.

Problemas típicos esperados:

- OCR listando vinhos errados ou incompletos
- nomes truncados ou com typo
- `total_visible` inflado
- o Baco falando como se tivesse certeza sobre garrafas ao fundo
- o sistema citando vinhos não lidos
- resposta confusa quando existem 2-5 vinhos relevantes na mesma cena

---

## Objetivo desta fase

Fazer com que imagens do tipo:

- prateleira
- display com várias garrafas
- screenshot de app/site/carta visual com vários vinhos

gerem uma resposta útil, honesta e estável.

---

## Casos que esta fase deve cobrir

### Shelf
- 2 a 10 rótulos visíveis
- alguns repetidos
- alguns parcialmente legíveis

### Screenshot
- print de ecommerce
- print de app de vinho
- print de lista com nome e preço

### Casos mistos
- imagem com 1 vinho dominante e vários ao fundo
- imagem com 2-3 vinhos legíveis e outros irrelevantes

---

## Casos que esta fase NÃO precisa resolver

- várias fotos no mesmo request
- PDF
- vídeo
- upload de texto

Se você precisar mexer em algo compartilhado com esses fluxos, faça o mínimo necessário, mas não desvie o foco.

---

## O que investigar primeiro

1. Como `backend/tools/media.py` produz `shelf` e `screenshot`
2. Como `backend/routes/chat.py` transforma isso em contexto
3. Como `backend/tools/resolver.py` resolve múltiplos vinhos
4. Como o Baco usa o contexto com vários vinhos
5. Se o fluxo atual está integrado no request path ou só existe parcialmente

---

## O que precisa melhorar

### 1. Resolução de múltiplos vinhos
- priorizar os vinhos explicitamente lidos
- evitar citar vinho não listado
- deduplicar resultados por `id`

### 2. Honestidade de resposta
- se a imagem mostra mais coisas ao fundo, o sistema não deve inventar
- se o OCR só leu 3 vinhos, o Baco deve falar desses 3
- se houver incerteza, ela deve aparecer de forma natural

### 3. Preço visível
- quando houver preço claro na screenshot/prateleira, isso deve ser âncora principal da cena
- preços da base entram como complemento, não substituição automática

### 4. Resposta útil do Baco
- organizar os vinhos encontrados
- permitir comparação
- permitir recomendação dentro do que foi realmente lido

---

## Arquivos principais

- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\routes\chat.py`
- `C:\winegod-app\backend\tools\resolver.py`
- `C:\winegod-app\backend\tools\search.py`
- `C:\winegod-app\backend\prompts\baco_system.py`
- `C:\winegod-app\backend\services\baco.py`

---

## Direção técnica recomendada

### 1. Manter o máximo possível do fluxo de pre-resolve no backend
Não voltar para um modelo onde o Claude precisa “descobrir” tudo sozinho via tool calls.

### 2. Tratar screenshot e shelf como listas imperfeitas, não como visão total da cena
O sistema deve responder sobre o que o OCR conseguiu ler, não sobre a imagem inteira como se tivesse certeza perfeita.

### 3. Melhorar o contexto entregue ao Claude
O contexto de múltiplos vinhos precisa ser:

- compacto
- explícito
- honesto
- ancorado nos vinhos realmente resolvidos

### 4. Não deixar o Baco exagerar
Se o OCR não leu, o Baco não viu.

---

## Critérios de aceite

Esta fase só está pronta quando estes casos passarem:

1. Uma prateleira com 2-5 vinhos legíveis gera resposta útil
2. Um screenshot com vinhos e preços gera resposta útil
3. O Baco fala apenas dos vinhos realmente listados no contexto
4. O sistema não inventa quantidade de garrafas ao fundo
5. A resposta não trava
6. Em caso de OCR parcial, a resposta continua honesta

---

## Como validar

Valide com:

1. uma foto de prateleira pequena
2. uma foto de prateleira média
3. um screenshot de ecommerce/app
4. um caso com preço visível
5. um caso onde parte da imagem é legível e parte não

Se possível, use logs reais do Render para confirmar:

- OCR
- pre_resolve
- resultado consolidado
- resposta final

---

## O que entregar

1. diagnóstico do fluxo atual
2. mudanças implementadas
3. arquivos alterados
4. validação dos casos principais
5. riscos residuais
6. se ficou pronto para produção ou se precisa de mais uma rodada

---

## Regras

- não reabrir infra base já resolvida sem motivo forte
- não misturar esta fase com múltiplas fotos, PDF ou vídeo
- não declarar entregue sem validar o request path real
- manter persona do Baco
- priorizar honestidade sobre exuberância

