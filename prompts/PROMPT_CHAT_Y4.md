INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar.

# CHAT Y4 — Match Vivino (Grupo 4/8: it, es, pe, cl, fi, ru, tr)

Voce e 1 de 8 abas rodando em paralelo. Seu grupo: **4** (it, es, pe, cl, fi, ru, tr, ~341K vinhos).

## O QUE FAZER

Rodar no terminal:

```bash
cd C:\winegod-app && python scripts/match_vivino.py 4
```

O script:
1. Le vinhos de wines_unique WHERE pais_tabela IN ('it', 'es', 'pe', 'cl', 'fi', 'ru', 'tr')
2. Busca match contra vivino_match (1.7M vinhos Vivino importados localmente)
3. Salva resultado em match_results_y4

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