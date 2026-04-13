# HANDOFF — Mídia P2: Múltiplas Fotos

## Quem é você neste chat
Você é o engenheiro responsável por fazer o WineGod.ai lidar bem com **múltiplas imagens no mesmo request**, sem regressão do fluxo de rótulo simples e sem contaminar a resposta quando uma das imagens falha.

---

## Pré-requisito

Este prompt só deve ser executado depois que `HANDOFF_MEDIA_P1_SHELF_SCREENSHOT.md` estiver validado.

---

## O problema desta fase

O backend já aceita listas de imagens, mas a cobertura real de produção para esse caso ainda não foi validada em profundidade.

Problemas esperados:

- uma foto boa + uma foto ruim derrubando o conjunto inteiro
- o mesmo vinho aparecendo duplicado em várias imagens
- imagens com naturezas diferentes no mesmo request
- resposta confusa demais para o usuário
- payload/contexto grande demais

---

## Objetivo

Permitir que o usuário envie várias fotos de uma vez e receba:

- resposta consolidada
- sem duplicação desnecessária
- com falhas parciais tratadas honestamente
- sem travar

---

## Casos que esta fase deve cobrir

- 2 a 5 fotos de rótulos
- mistura de rótulo + prateleira
- mistura de rótulo + screenshot
- algumas imagens válidas e outras inválidas
- imagens repetindo o mesmo vinho

---

## O que investigar primeiro

1. `backend/routes/chat.py` no fluxo batch
2. `process_images_batch()` em `backend/tools/media.py`
3. deduplicação de vinhos resolvidos
4. construção do contexto final no batch

---

## O que precisa funcionar bem

### 1. Deduplicação
- se o mesmo vinho aparece em 2 imagens, ele não deve ser listado 2 vezes como se fossem achados independentes

### 2. Erro parcial
- se 1 imagem falhar e 2 funcionarem, a resposta precisa preservar as 2 boas

### 3. Consolidação clara
- o usuário deve entender o conjunto do que foi encontrado
- não pode virar uma parede confusa de dados

### 4. Fallback honesto
- se nada foi resolvido, dizer isso claramente
- se parte foi resolvida, dizer isso claramente

---

## Arquivos principais

- `C:\winegod-app\backend\routes\chat.py`
- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\tools\resolver.py`
- `C:\winegod-app\backend\prompts\baco_system.py`

---

## Critérios de aceite

1. múltiplas imagens válidas geram resposta consolidada
2. imagens duplicadas não geram vinho duplicado
3. falha parcial não derruba o request inteiro
4. batch sem vinho válido responde honestamente
5. a resposta continua útil e legível

---

## Como validar

Validar com:

1. 2 fotos do mesmo vinho
2. 2 fotos de vinhos diferentes
3. 1 foto válida + 1 sem vinho
4. 1 rótulo + 1 prateleira

---

## O que entregar

1. diagnóstico
2. mudanças implementadas
3. arquivos alterados
4. resultados dos testes
5. riscos residuais

