INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar.

# CHAT Y8 — Match Vivino (Grupo 8/8: mx, fr, nz, se, uy, lu, no)

Voce e 1 de 8 abas rodando em paralelo. Seu grupo: **8** (mx, fr, nz, se, uy, lu, no, ~344K vinhos).

## O QUE FAZER

Rodar no terminal:

```bash
cd C:\winegod-app && python scripts/match_vivino.py 8
```

O script:
1. Le vinhos de wines_unique WHERE pais_tabela IN ('mx', 'fr', 'nz', 'se', 'uy', 'lu', 'no')
2. Busca match contra vivino_match (1.7M vinhos Vivino importados localmente)
3. Salva resultado em match_results_y8

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