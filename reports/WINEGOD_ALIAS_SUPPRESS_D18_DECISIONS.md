# WINEGOD_ALIAS_SUPPRESS_D18_DECISIONS

**Data:** 2026-04-20
**Founder:** Murilo
**Status:** travadas e aprovadas
**Projeto:** D18 alias suppress
**Documento mestre:** `C:\winegod-app\reports\WINEGOD_ALIAS_SUPPRESS_D18_HANDOFF_OFICIAL.md`

Este documento trava a interpretacao final do D18. Mudancas nestas decisoes exigem nova aprovacao explicita do founder.

---

## Decisoes travadas

**1. O objetivo oficial do D18**
- Decisao: **soft-suppress de source wines duplicados para limpeza de busca/discovery**
- Implicacao: o sucesso do D18 e medido por tirar duplicatas aprovadas dos fluxos que usam `suppressed_at IS NULL`.

**2. O significado do gate de 3,30%**
- Decisao: **tratar como excecao formal aceita**
- Implicacao: os `130` casos errados da amostra QA ficam excluidos do lote aprovado, mas NAO bloqueiam o fechamento operacional do D18.

**3. Tratamento dos 130 casos do QA**
- Decisao: **nao suprimir**
- Implicacao: esses casos nao sao "nao-vinho"; sao aliases errados entre vinhos reais. Suprimir esses itens poderia esconder vinhos validos.

**4. Necessidade de nova execucao de banco**
- Decisao: **nao ha nova execucao obrigatoria**
- Implicacao: o D18 ja fechou o que precisava fechar em `wines`. Os `250` residuos vistos apos a rodada `231915` ja foram resolvidos em `234936`.

**5. Estado final aceito para `wine_aliases`**
- Decisao: **aceitar cleanup posterior**
- Implicacao: o estado final oficial aceita `72.415` aliases D17 removidos de `wine_aliases`, mantendo apenas `43` aliases manuais aprovados. Isso NAO invalida o suppress em `wines`.

**6. O que continua fora do escopo deste fechamento**
- Decisao: **hardening do D17 vira follow-up separado**
- Implicacao: se quisermos baixar a taxa de erro abaixo de `3%`, isso vira um trabalho novo de heuristica/materializacao/QA, e nao reabre o D18.

**7. Status final do projeto D18**
- Decisao: **FECHADO COM EXCECAO FORMAL**
- Implicacao: operacionalmente concluido, com excecao estatistica registrada e aceita.

---

## Assinatura logica

```
Founder: Murilo
Data: 2026-04-20
Decisoes travadas: 7
```

## Proximo passo

- Se quiser formalizacao em historico git, fazer commit posterior ao `3c9bf2a4` incluindo:
  - `C:\winegod-app\reports\WINEGOD_ALIAS_SUPPRESS_D18_HANDOFF_OFICIAL.md`
  - `C:\winegod-app\reports\WINEGOD_ALIAS_SUPPRESS_D18_DECISIONS.md`
  - summaries finais de D18 e artefatos de closeout ja criados no repo
