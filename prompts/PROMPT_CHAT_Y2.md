INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar.

# CHAT Y2 — Match Vivino (Grupo 2/8: br, pl, ch, za, jp, ae)

Voce e 1 de 8 abas rodando em paralelo. Seu grupo: **2** (br, pl, ch, za, jp, ae, ~342K vinhos).

## O QUE FAZER

Rodar no terminal:

```bash
cd C:\winegod-app && python scripts/match_vivino.py 2
```

O script:
1. Le vinhos de wines_unique WHERE pais_tabela IN ('br', 'pl', 'ch', 'za', 'jp', 'ae')
2. Busca match contra vivino_match (1.7M vinhos Vivino importados localmente)
3. Salva resultado em match_results_y2

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