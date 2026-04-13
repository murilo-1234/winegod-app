# Pesquisa 5: Cálculo da `nota_base`, penalidade contextual e fallback sem degrau

Quero que você atue como pesquisador estatístico da regra central da `nota_wcf v2`.

Esta aba deve estudar três pontos que hoje são críticos:
- como calcular a `nota_base` dentro do balde
- como tratar a penalidade contextual
- o que fazer com vinhos que têm `n > 0`, mas não se encaixam na cascata

Importante:
- não implemente nada
- não altere banco ou código
- faça estudo, comparação e proposta

## Contexto do problema

A lógica geral aprovada até agora é:

```text
nota_final = (n / (n + 20)) * nota_wcf_bruta
           + (20 / (n + 20)) * nota_base
```

Onde:
- `nota_wcf_bruta` = nota das reviews com pesos do WCF antigo
- `nota_base` = nota contextual do balde da cascata
- `n` = número de reviews válidas

Mas ainda existem três lacunas sérias:

1. Como a `nota_base` é agregada dentro do balde?
- média simples?
- média ponderada?
- média ponderada com teto?

2. A penalidade contextual atual é heurística:
- `0,00`
- `-0,03`
- `-0,05`
- `-0,08`
- `-0,10`
- `-0,12`
- `-0,15`

3. Já foi medido que há vinhos com `n > 0` sem encaixe estrutural na cascata:
- total com `n > 0` = `410.290`
- sem encaixe estrutural = `44.186`
- entre eles:
  - `43.395` sem `tipo`
  - `791` com `tipo`, mas sem produtor, sub_região, região e país

## O que já está decidido

Não reabra estes pontos:
- a fórmula de shrinkage continua sendo o eixo do modelo
- `k = 20` continua sendo o valor fechado por enquanto
- sem fallback global universal
- sem `tipo global`

## O que você precisa responder

1. Como a `nota_base` deveria ser calculada?

Quero comparação honesta entre:
- média simples
- média ponderada por `n`
- média ponderada com teto, por exemplo `min(n, 50)`
- qualquer outra opção realmente melhor

Para cada opção, explique:
- risco de outlier
- risco de fama histórica dominar
- aderência à tese do fundador
- robustez estatística

2. Penalidade contextual ainda faz sentido?
- ela deve existir sempre?
- só quando `n = 0`?
- deve ser fixa por degrau?
- deve usar variância real do balde?

3. Qual é a melhor regra para vinho com `n > 0` e sem degrau?

Compare opções como:
- deixar sem nota
- usar `nota_wcf_bruta` direta
- usar algum fallback contextual especial
- usar regra condicional por presença de `tipo`

4. Como ser justo com vinhos novos?
- sem delirar
- sem premiar fama antiga demais
- sem perder lastro

## O que você deve investigar

No banco:
- exemplos de baldes com dispersão alta e baixa
- sensibilidade de agregadores diferentes
- impacto provável de outliers
- perfil dos `44.186` vinhos com `n > 0` sem encaixe estrutural

## O que eu quero como resposta

1. Resumo executivo
2. Melhor forma de calcular a `nota_base`
3. Crítica às alternativas
4. Melhor tratamento para penalidade contextual
5. Melhor fallback para `n > 0` sem degrau
6. Casos reais ou exemplos numéricos
7. Recomendação final
8. O que ainda não foi provado

## Regras de rigor

- não use só discurso; traga exemplos
- se defender média ponderada, diga por quê e com qual limite
- se defender penalidade, diga onde ela entra e onde não entra
- se defender fallback para `n > 0`, diga exatamente em quais casos
