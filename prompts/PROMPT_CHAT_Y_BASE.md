INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao.

# CHAT Y — Match Vinhos de Loja contra Vivino

## CONTEXTO

WineGod.ai tem 2 bases de vinhos:
- **Vivino:** 1,727,058 vinhos importados localmente na tabela `vivino_match` (banco local)
- **Lojas:** 2,942,304 vinhos unicos na tabela `wines_unique` (banco local)

O desafio: lojas juntam tudo num campo ("barefoot pinot grigio 2022"), Vivino separa produtor ("barefoot") do nome ("pinot grigio"). Comparacao direta de string NAO funciona.

**Solucao validada (96% match em teste com 100 vinhos):**
Script multi-estrategia com scoring:
1. Busca por produtor (rapida, 0.03s) — resolve ~70%
2. Busca por palavra-chave (rapida, 0.05s) — resolve ~20%
3. pg_trgm no nome (media, ~2s) — resolve ~8%
4. pg_trgm combinado (lenta, ~17s) — resolve ~2%

Score 0-1: sobreposicao de tokens (0.45), match de produtor (0.25), safra (0.12), tipo (0.08), reverso (0.10).

## PRE-REQUISITOS (JA FEITOS)

- Tabela `vivino_match` importada localmente (1,727,058 vinhos)
  - Indexes GIN trgm: texto_busca, nome_normalizado, produtor_normalizado
- Tabela `wines_unique` existe (2,942,304 vinhos)
- pg_trgm habilitado no banco local
- Script VALIDADO: `scripts/match_vivino.py` (aceita GROUP_NUM como argumento)

## CREDENCIAIS

```
Banco local: postgresql://postgres:postgres123@localhost:5432/winegod_db
```

## O QUE FAZER

1. Rodar: `cd C:\winegod-app && python scripts/match_vivino.py {GROUP_NUM}`
2. Monitorar o progresso (imprime a cada 1000 vinhos)
3. Se der erro, corrigir e rodar de novo (o script faz DROP TABLE IF EXISTS no inicio)
4. Quando terminar, reportar:
   - Taxa de match (alta + media)
   - Distribuicao por nivel (high/medium/low/no_match)
   - Tempo total
   - 10 exemplos de alta confianca

## GRUPOS

| Grupo | Paises | ~Vinhos |
|---|---|---|
| 1 | us | 545K |
| 2 | br, pl, ch, za, jp, ae | 342K |
| 3 | gb, hk, be, gr, hu, bg, hr | 343K |
| 4 | it, es, pe, cl, fi, ru, tr | 341K |
| 5 | ar, nl, sg, md, ro, cn, cz | 344K |
| 6 | au, pt, at, ca, co, il, kr, th | 340K |
| 7 | de, dk, ph, ie, in, ge, tw | 343K |
| 8 | mx, fr, nz, se, uy, lu, no | 344K |

## TABELA DE RESULTADO

Cada grupo cria: `match_results_y{GROUP_NUM}` com:
- unique_id, vivino_id, match_score, match_strategy, match_level, loja_nome, vivino_nome

## IMPORTANTE

- NAO alterar vivino_match ou wines_unique
- NAO alterar o script match_vivino.py
- Apenas RODAR e REPORTAR
- NAO fazer commit/push
- Se o script travar ou ficar muito lento, reportar a posicao e o erro
