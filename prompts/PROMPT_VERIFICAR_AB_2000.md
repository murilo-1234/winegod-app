INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar.

# VERIFICAR — Amostra de 2000 vinhos da base final (A + B)

## CONTEXTO

O pipeline de classificacao rodou em 3.96M vinhos. Os destinos A (match Vivino, 2.35M) e B (vinho novo, 256K) sao os que vao entrar na base de producao. Precisamos verificar visualmente que:
1. Nao tem lixo (nao-vinho) no A e B
2. Os A estao casando corretamente com o Vivino
3. Os B sao vinhos reais

## CREDENCIAL

```
Banco local: postgresql://postgres:postgres123@localhost:5432/winegod_db
```

## O QUE FAZER

### Passo 1: Gerar amostra de 2000

Pegar 250 vinhos por letra (8 letras: B, D, J, M, O, P, R, T), em ordem alfabetica, somente dos destinos A e B da `match_results_final`.

```python
import psycopg2
import sys
import io
import re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

LOCAL_DB = "postgresql://postgres:postgres123@localhost:5432/winegod_db"
conn = psycopg2.connect(LOCAL_DB)
cur = conn.cursor()

letters = ['B', 'D', 'J', 'M', 'O', 'P', 'R', 'T']
all_entries = []

for letra in letters:
    cur.execute("""
        SELECT loja_nome, vivino_nome, match_score, destino, match_strategy, wine_likeness
        FROM match_results_final
        WHERE destino IN ('A', 'B')
          AND loja_nome LIKE %s
        ORDER BY loja_nome
        LIMIT 250
    """, (f'{letra.lower()}%',))

    for row in cur.fetchall():
        all_entries.append({
            'loja': row[0] or '',
            'vivino': row[1] or '(sem match)',
            'score': row[2] or 0,
            'destino': row[3],
            'strategy': row[4] or '',
            'wl': row[5] or 0,
            'letra': letra,
        })

conn.close()
print(f'Total: {len(all_entries)}')
```

### Passo 2: Gerar arquivo TXT por letra

Para cada letra, gerar `C:\winegod-app\scripts\verificar_AB_{LETRA}.txt` com formato:

```
  1  [A ] 0.85  "nome da loja"
              → "produtor — nome vivino"

  2  [B ] 0.00  "nome da loja"
              → (sem match)
```

### Passo 3: Gerar consolidado ordenado por score

Juntar os 2000 num unico arquivo `C:\winegod-app\scripts\verificar_AB_por_score.md` ordenado do menor score ao maior. Formato igual ao `analise_2000_por_score_v2.md`.

Agrupar por faixas de 0.10 (0.00-0.10, 0.10-0.20, ..., 0.80-0.90).

Para os B (sem match), o score e 0.00 — ficam todos no inicio.

### Passo 4: Resumo

Imprimir:
- Total A e B na amostra
- Distribuicao por letra
- Distribuicao por faixa de score

## ARQUIVOS DE OUTPUT

```
C:\winegod-app\scripts\verificar_AB_B.txt
C:\winegod-app\scripts\verificar_AB_D.txt
C:\winegod-app\scripts\verificar_AB_J.txt
C:\winegod-app\scripts\verificar_AB_M.txt
C:\winegod-app\scripts\verificar_AB_O.txt
C:\winegod-app\scripts\verificar_AB_P.txt
C:\winegod-app\scripts\verificar_AB_R.txt
C:\winegod-app\scripts\verificar_AB_T.txt
C:\winegod-app\scripts\verificar_AB_por_score.md
```

## NAO FAZER

- NAO alterar nenhuma tabela
- NAO rodar o pipeline de novo (so ler match_results_final)
- NAO fazer commit/push
