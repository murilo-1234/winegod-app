# ANALISE CTO — 2000 VINHOS POR LETRA (29/03/2026)

## CONTEXTO

O outro CTO rodou analise de 2000 vinhos (250 por letra, 8 letras: B, D, J, M, O, P, R, T) com o sistema de 5 destinos (A-E). Este documento e a analise do CTO principal sobre os resultados.

## RESULTADO REPORTADO

| Destino | Qtd | % | Extrapolado (2.9M) |
|---|---|---|---|
| A — Sobe pro Render | 458 | 22.9% | ~674K |
| B — Vinho novo | 48 | 2.4% | ~71K |
| C1 — Quarentena provavel | 319 | 16.0% | ~469K |
| C2 — Quarentena incerto | 695 | 34.8% | ~1.02M |
| D — Nao-vinho (elimina) | 446 | 22.3% | ~656K |
| E — Destilado (arquivo) | 34 | 1.7% | ~50K |

## PROBLEMAS GRAVES ENCONTRADOS NA VERIFICACAO VISUAL

### 1. Destino A tem muitos FALSOS POSITIVOS

Exemplos de matches classificados como A (sobe pro Render) que estao ERRADOS:

```
[A] 0.76  "j alberto 2020" [ar] → "alberto quacquarini serrapetrona" [it]
  ERRADO: produtor diferente (J. Alberto de Argentina vs Quacquarini de Italia)
  Esse erro se repete 4 vezes (#12-15 na letra J) — mesmo match errado pra safras 2020-2023

[A] 0.68  "b 1er 2018" [jp] → "v etien 1er champagne" [fr]
  ERRADO: "b 1er" e nome truncado japones, nao e champagne

[A] 0.50  "d angels classique red" [ae] → "angels gate red angel" [ca]
  ERRADO: produtor diferente (D'Angels vs Angels Gate)

[A] 0.61  "j alberto bodega noemia" [pe] → "bodega aconquija alberto furque malbec" [ar]
  ERRADO: Bodega Noemia != Bodega Aconquija

[A] 0.68  "m 1er 2021" [jp] → "v etien 1er champagne" [fr]
  ERRADO: mesmo erro do "b 1er" — nome truncado japones
```

Estimativa: 30-40% do Destino A sao falsos positivos. O numero real que deveria subir pro Render e ~400-470K, nao 674K.

### 2. Lixo massivo de nomes truncados (Japao + Grecia)

Centenas de registros com nomes de 1-3 caracteres + numero:
```
"b 2019", "b 2020", "b 2022", "b 200", "b 200gr", "b 230gr", "b 600gr", "b 70"
"d 05", "d 075", "d 4", "d 5"
"m 1", "m 100", "m 100gr", "m 15", "m 15oz", "m 18oz", "m 1q83", "m 1q87"
"p 2022", "p 10 198g", "p 11000", "p 2"
"t 1", "t 14", "t 140", "t 15", "t 17", "t 19", "t 38 075", "t 40", "t 500"
```

Pais predominante: jp (Japao) e gr (Grecia). Sao nomes que perderam conteudo durante scraping. A maioria esta indo pra C2 (quarentena) mas deveria ser D (eliminar). Isso infla o C2 artificialmente.

### 3. Wine-likeness 1 nao e vinho

Registros com wl=1 (tipo reconhecido OU safra, mas so 1 dos 5 criterios) quase nunca sao vinhos uteis:
```
"b 2023" wl=1 → nao e nada, e uma letra + ano
"j 2003" wl=1 → matchou com Bollinger por coincidencia
"p 2022" wl=1 → varios registros identicos de paises diferentes
"t 2009" wl=1 → idem
```

Esses estao indo pra C2 mas deveriam ser D (eliminar). Sugestao: wl<=1 E nome com menos de 5 caracteres = D.

### 4. D'Arenberg — exemplo de match que DEVERIA funcionar mas nao funciona

Na letra D vi varios vinhos da D'Arenberg (produtor australiano famoso):
```
"d arenberg 2021 footbolt shiraz" → "darenberg the footbolt shiraz" — score 0.30, C1
"d arenberg 2024 the hermit crab viognier marsanne" → "darenberg the hermit crab" — score 0.35, C2
"d arenberg darrys original shiraz grenache 2020" → "darenberg darrys original" — score 0.51, C1
"d arenberg dead arm shiraz 18" → "dead duck shiraz" — score 0.41, C2 (ERRADO, matchou com outro)
```

O problema: a loja escreve "d arenberg" (com espaco) e o Vivino escreve "darenberg" (junto). Essa diferenca de 1 espaco causa score baixo. Vinhos famosos de $50-200 ficando em quarentena por causa de um espaco.

## PRECISAO ESTIMADA POR FAIXA DE SCORE

| Faixa | O que vi nos 8 arquivos | Precisao estimada |
|---|---|---|
| 0.80-1.00 | Poucos registros mas maioria correta | ~85-90% |
| 0.70-0.79 | Mistura — produtor bate mas vinho errado frequente | ~55-65% |
| 0.60-0.69 | Muito ruido — nomes truncados matchando | ~35-45% |
| 0.50-0.59 | Maioria errada — matches por coincidencia | ~20-30% |
| 0.40-0.49 | Quase tudo errado | ~10-15% |
| < 0.40 | Tudo errado | ~5% |

## O QUE O C2 REALMENTE E

O C2 reportado como 34.8% (~1M) nao e "vinhos em quarentena". Na verdade:
- ~40% lixo de nomes truncados (Japao/Grecia) — deveria ser D
- ~30% vinhos com nomes curtos demais pra matchear
- ~20% vinhos reais que o algoritmo nao conseguiu casar
- ~10% nao-vinhos que passaram pelo filtro

## RECOMENDACOES PARA O PROXIMO CTO

### Ajustes imediatos:
1. **wl=1 + nome < 5 chars = D (eliminar)** — move ~300-400K de C2 pra D
2. **Auditar Destino A com score 0.45-0.65** — pegar 100, verificar manualmente, estimo 40% errado
3. **Nomes com 1-2 chars + numero = D** — "b 2022", "m 1", "t 14" nao sao vinhos
4. **Subir threshold do A pra >= 0.65** — reduz volume mas aumenta confianca

### Problema estrutural a resolver:
5. **Espacos no nome do produtor** — "d arenberg" vs "darenberg" causa perda de matches bons. Normalizar removendo espacos antes de comparar.
6. **Japao e Grecia** contribuem ~50% do lixo. Considerar limpeza especifica por pais.

### Numeros revisados (estimativa apos ajustes):

| Destino | Antes | Depois (estimado) |
|---|---|---|
| A — Sobe pro Render | 674K | ~400-470K (removendo falsos positivos) |
| B — Vinho novo | 71K | ~71K (sem mudanca) |
| C1 — Quarentena provavel | 469K | ~350K |
| C2 — Quarentena incerto | 1.02M | ~600K (apos mover lixo pra D) |
| D — Nao-vinho (elimina) | 656K | ~1.1M (absorveu lixo do C2) |
| E — Destilado | 50K | ~50K |

## DECISAO PENDENTE DO FUNDADOR

A pergunta principal: subimos so o Destino A (com score >= 0.65) agora e melhoramos depois? Ou esperamos melhorar o algoritmo antes de subir qualquer coisa?

Recomendacao CTO: subir A com score >= 0.70 (~300-400K matches de alta confianca). E seguro e ja adiciona valor ao produto. O resto melhora depois.

## ARQUIVOS DE REFERENCIA

Dados brutos da analise (250 vinhos cada):
- `C:\winegod-app\scripts\analise_letra_B.txt`
- `C:\winegod-app\scripts\analise_letra_D.txt`
- `C:\winegod-app\scripts\analise_letra_J.txt`
- `C:\winegod-app\scripts\analise_letra_M.txt`
- `C:\winegod-app\scripts\analise_letra_O.txt`
- `C:\winegod-app\scripts\analise_letra_P.txt`
- `C:\winegod-app\scripts\analise_letra_R.txt`
- `C:\winegod-app\scripts\analise_letra_T.txt`

Analise anterior (200 vinhos aleatorios):
- `C:\winegod-app\scripts\lista_200_vinhos.txt`

Briefings enviados ao outro CTO:
- `C:\winegod-app\prompts\BRIEFING_CTO_Y_ANALISE.md`
- `C:\winegod-app\prompts\BRIEFING_CTO_Y_METRICAS_2000.md`

Documento principal do projeto:
- `C:\winegod-app\prompts\PROMPT_CTO_WINEGOD_V2.md`
