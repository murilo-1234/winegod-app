# Correcao do Prompt do Codex — Produtor Vazio

## O Problema

O Codex classificou ~128K vinhos, mas **94K deles ficaram sem produtor** (campo `prod_banco` vazio ou `??`). Isso impede o match com o Vivino, porque o match funciona assim:

1. Pega o produtor do vinho classificado (ex: "chateau montrose")
2. Busca no Vivino todos os vinhos desse produtor
3. Compara o nome do vinho pra achar o match

**Sem produtor = sem match.** Os 94K ficam travados como `pending_match` pra sempre.

## A Causa

O prompt do Codex dizia apenas:

```
- produtor = quem faz o vinho (vinicola). ?? se nao sabe
- vinho = nome do vinho sem o produtor. ?? se nao sabe
```

O problema: **nenhum exemplo** de como separar produtor de vinho. O Codex nao sabia que:
- "chateau montrose" → produtor: chateau montrose, vinho: montrose
- "norton barrel select malbec" → produtor: norton, vinho: barrel select malbec
- "larentis malbec" → produtor: larentis, vinho: malbec

Sem exemplos, o Codex frequentemente colocava tudo no campo vinho e deixava produtor como `??`.

Comparacao: o prompt das outras IAs (Mistral, Grok, Gemini, GLM, Claude) tem **10 exemplos concretos** de como separar produtor/vinho. Por isso essas IAs quase nunca deixam produtor vazio (apenas 2-3% sem produtor vs 73% do Codex).

## O Que Foi Corrigido

### 1. Exemplos de produtor (PRINCIPAL)

Adicionamos 9 exemplos concretos do nosso banco:

```
- produtor = quem FAZ o vinho (vinicola/bodega/domaine/chateau), NAO o nome do vinho. NUNCA deixe ??.
  Exemplos do nosso banco:
    "chateau levangile" → produtor: chateau levangile, vinho: pomerol
    "campo viejo reserva rioja" → produtor: campo viejo, vinho: reserva rioja
    "penfolds grange shiraz" → produtor: penfolds, vinho: grange shiraz
    "norton barrel select malbec" → produtor: norton, vinho: barrel select malbec
    "larentis malbec" → produtor: larentis, vinho: malbec
  Se produtor e vinho sao o mesmo nome, repita:
    "chateau montrose" → produtor: chateau montrose, vinho: montrose
    "quinta do noval" → produtor: quinta do noval, vinho: noval
    "dom perignon" → produtor: dom perignon, vinho: dom perignon
  O produtor e CRITICO — sem ele nao conseguimos fazer match no banco. Sempre extraia.
```

### 2. NUNCA deixe ??

Antes: `?? se nao sabe` (permissivo demais, o Codex usava ?? em massa)
Agora: `NUNCA deixe ??` + explicacao de por que o produtor e critico

### 3. Fortificados

Faltava no prompt do Codex a instrucao de que sherry, porto, madeira, marsala sao **vinhos** (W, cor f), nao destilados (S). O prompt das outras IAs ja tinha isso.

## Numeros

| IA | Total classificado | Sem produtor | % sem produtor |
|---|---|---|---|
| **Codex (antes)** | **128K** | **94K** | **73%** |
| Mistral | 118K | 2.7K | 2% |
| Grok | 28K | 2.2K | 8% |
| GLM | 14K | 1.2K | 8% |
| Gemini (API antiga) | 754K | 26K | 3% |

## Proximo Passo

Com o prompt corrigido, os novos lotes do Codex vao vir com produtor preenchido. Os 94K antigos sem produtor precisam de uma das opcoes:

1. **Reclassificar** — rodar de novo no Codex com o prompt corrigido (mais preciso)
2. **Match por nome** — usar pg_trgm no nome inteiro em vez de buscar por produtor (mais lento, menos preciso)

## Arquivo Corrigido

`C:\winegod-app\prompts\PROMPT_CODEX_R5_ABA_10.md`
