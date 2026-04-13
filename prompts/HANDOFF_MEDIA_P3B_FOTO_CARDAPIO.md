# HANDOFF - Midia P3B: Foto de Cardapio / Lista

## Quem e voce neste chat
Voce e o engenheiro responsavel por fazer o WineGod.ai lidar bem com **foto de cardapio, foto de carta e foto de lista/catalogo**, sem confundir esse caso com PDF e sem reabrir regressao em rotulo, shelf ou screenshot.

---

## Pre-requisito

Este prompt so deve ser executado depois que:

- `HANDOFF_MEDIA_P1_SHELF_SCREENSHOT.md` estiver validado
- `HANDOFF_MEDIA_P2_MULTI_IMAGE.md` estiver validado

---

## Objetivo

Permitir que o usuario tire:

- foto de um cardapio
- foto de uma carta de vinhos
- foto de uma lista/catalogo impressa

e receba uma resposta util sobre os vinhos realmente lidos.

---

## O problema desta fase

Foto de cardapio/lista nao e igual a:

- PDF
- shelf
- screenshot
- foto de rotulo

Ela adiciona:

- muito texto compacto na mesma imagem
- secoes e titulos
- colunas
- precos muito proximos de varios itens
- risco alto de OCR puxar ruido visual e associar preco errado

---

## O que investigar

1. `process_image()` em `C:\winegod-app\backend\tools\media.py`
2. se faz sentido criar um tipo explicito como `menu` / `cardapio` / `list`
3. como o contexto da imagem chega em `C:\winegod-app\backend\routes\chat.py`
4. se o fluxo atual esta empurrando foto de cardapio para `shelf` ou `screenshot`
5. como preservar ancora de preco sem fingir confirmacao forte

---

## O que precisa melhorar

- distinguir foto de cardapio/lista de shelf e de screenshot quando fizer sentido
- separar vinho de texto decorativo
- tratar precos como ancora visual da cena
- nao transformar layout em vinho
- manter resposta util sem fingir certeza total

---

## Arquivos principais

- `C:\winegod-app\backend\tools\media.py`
- `C:\winegod-app\backend\routes\chat.py`
- `C:\winegod-app\backend\tools\resolver.py`
- `C:\winegod-app\backend\prompts\baco_system.py`

---

## Criterios de aceite

1. uma foto de cardapio gera resposta util
2. uma foto de lista/catalogo gera resposta util
3. precos da foto sao tratados como ancora visual
4. o sistema nao inventa itens nao lidos
5. nao ha travamento excessivo

---

## Como validar

Validar com:

1. foto simples de cardapio
2. foto com varios precos
3. foto com secoes/titulos
4. foto ruim ou inclinada

---

## O que entregar

1. diagnostico
2. implementacao
3. arquivos alterados
4. validacao
5. riscos residuais
