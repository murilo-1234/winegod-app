INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar.

# CHAT Y5 — Match Vivino (Grupo 5/8: ar, nl, sg, md, ro, cn, cz)

Voce e 1 de 8 abas rodando em paralelo. Seu grupo: **5** (ar, nl, sg, md, ro, cn, cz, ~344K vinhos).

## O QUE FAZER

Rodar no terminal:

```bash
cd C:\winegod-app && python scripts/match_vivino.py 5
```

O script:
1. Le vinhos de wines_unique WHERE pais_tabela IN ('ar', 'nl', 'sg', 'md', 'ro', 'cn', 'cz')
2. Busca match contra vivino_match (1.7M vinhos Vivino importados localmente)
3. Salva resultado em match_results_y5

## CREDENCIAL

```
Banco local: postgresql://postgres:postgres123@localhost:5432/winegod_db
```

## SE DER ERRO

- O script faz DROP TABLE no inicio, entao pode rodar de novo sem problema
- Se travar, reportar a posicao (o script imprime progresso a cada 1000 vinhos)
- NAO alterar o script — apenas rodar e reportar

## ENTREGAVEL

Ao terminar, imprimir o resumo que o script gera (taxa de match, distribuicao, exemplos).

NAO fazer commit/push.