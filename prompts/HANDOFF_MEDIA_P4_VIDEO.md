# HANDOFF — Mídia P4: Vídeo

## Quem é você neste chat
Você é o engenheiro responsável por tornar o fluxo de vídeo do WineGod.ai utilizável, sem reabrir as regressões já resolvidas em imagem e sem transformar vídeo em uma fonte de timeout constante.

---

## Pré-requisito

Este prompt só deve ser executado depois que:

- `HANDOFF_MEDIA_P1_SHELF_SCREENSHOT.md`
- `HANDOFF_MEDIA_P2_MULTI_IMAGE.md`
- `HANDOFF_MEDIA_P3_PDF_CARDAPIO.md`
- `HANDOFF_MEDIA_P3B_FOTO_CARDAPIO.md`

estiverem validados.

---

## Objetivo

Permitir que vídeos curtos com rótulos ou prateleiras gerem:

- identificação útil
- resposta honesta
- latência controlada

---

## O problema desta fase

Vídeo adiciona:

- muitos frames redundantes
- blur/movimento
- custo alto de OCR
- risco de latência explosiva

---

## O que investigar

1. `process_video()` em `backend/tools/media.py`
2. política atual de seleção de frames
3. como o contexto do vídeo é entregue ao Claude
4. se há deduplicação entre frames

---

## O que precisa melhorar

- escolher poucos frames úteis
- deduplicar vinhos entre frames
- não tratar vídeo como certeza total
- limitar tempo de processamento

---

## Arquivos principais

- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\routes\chat.py`
- `C:\winegod-app\backend\tools\resolver.py`
- `C:\winegod-app\backend\services\tracing.py`

---

## Critérios de aceite

1. vídeo curto com rótulo responde sem travar
2. vídeo curto de prateleira responde de forma útil
3. a resposta não inventa precisão falsa
4. latência fica limitada
5. logs mostram onde o tempo foi gasto

---

## Como validar

Validar com:

1. vídeo curto de 1 vinho
2. vídeo curto de prateleira
3. vídeo com movimento ruim
4. vídeo sem vinho

---

## O que entregar

1. diagnóstico
2. implementação
3. validação
4. riscos residuais
