INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar.

# EXECUTAR — Analise de 2000 vinhos por letra v5 (8 letras)

## O QUE FAZER

Rodar o script `C:\winegod-app\scripts\analise_letra.py` para 8 letras em paralelo. Cada execucao processa 250 vinhos da `wines_clean` que comecam com aquela letra, em ordem alfabetica.

```bash
cd C:\winegod-app
python scripts/analise_letra.py B
python scripts/analise_letra.py D
python scripts/analise_letra.py J
python scripts/analise_letra.py M
python scripts/analise_letra.py O
python scripts/analise_letra.py P
python scripts/analise_letra.py R
python scripts/analise_letra.py T
```

Rode as 8 em PARALELO (background). Cada uma leva ~5-15 minutos.

## CREDENCIAL

```
Banco local: postgresql://postgres:postgres123@localhost:5432/winegod_db
```

## PRE-REQUISITOS (JA FEITOS)

- Tabela `wines_clean` com 3,955,624 vinhos (banco local)
- Tabela `vivino_match` com 1,727,058 vinhos Vivino (banco local, com indexes trgm)
- pg_trgm habilitado
- Script `analise_letra.py` ja atualizado com todas as melhorias (uvas globais, termos multi-lingua, GARANTIA_VINHO, blacklist expandida, regra de comprimento)

## OUTPUT

Cada execucao gera um arquivo TXT:
- `C:\winegod-app\scripts\analise_letra_B.txt`
- `C:\winegod-app\scripts\analise_letra_D.txt`
- `C:\winegod-app\scripts\analise_letra_J.txt`
- `C:\winegod-app\scripts\analise_letra_M.txt`
- `C:\winegod-app\scripts\analise_letra_O.txt`
- `C:\winegod-app\scripts\analise_letra_P.txt`
- `C:\winegod-app\scripts\analise_letra_R.txt`
- `C:\winegod-app\scripts\analise_letra_T.txt`

Os arquivos anteriores serao sobrescritos (e o esperado).

## DEPOIS DE TERMINAR

1. Consolidar os resumos das 8 letras:

```python
import re, os
totals = {'A': 0, 'B': 0, 'C1': 0, 'C2': 0, 'D': 0, 'E': 0}
letters = ['B', 'D', 'J', 'M', 'O', 'P', 'R', 'T']
per_letter = {}

for l in letters:
    path = f'C:/winegod-app/scripts/analise_letra_{l}.txt'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    stats = {}
    for line in content.split('\n'):
        m = re.match(r'\s+(A|B|C1|C2|D|E)\s+\(.+?\):\s*(\d+)', line)
        if m:
            key = m.group(1)
            val = int(m.group(2))
            stats[key] = val
            totals[key] += val
    per_letter[l] = stats

grand = sum(totals.values())
print(f'TOTAL: {grand} vinhos')
for k in ['A', 'B', 'C1', 'C2', 'D', 'E']:
    print(f'  {k}: {totals[k]} ({totals[k]/grand*100:.1f}%)')
```

2. Gerar documento consolidado ordenado por score:

```bash
python -c "
import sys, io, re, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

letters = ['B', 'D', 'J', 'M', 'O', 'P', 'R', 'T']
all_entries = []

for l in letters:
    path = f'C:/winegod-app/scripts/analise_letra_{l}.txt'
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        m = re.match(r'\s*(\d+)\s+\[(\w+\s*)\]\s+([\d.]+|----)\s+(\w+|----)\s+(.*)', line)
        if m:
            dest = m.group(2).strip()
            score_str = m.group(3)
            prod = m.group(4)
            loja = m.group(5).strip()
            score = float(score_str) if score_str != '----' else -1.0
            match_line = ''
            if i + 1 < len(lines):
                match_line = lines[i+1].rstrip().strip()
            all_entries.append({'dest': dest, 'score': score, 'prod': prod, 'loja': loja, 'match': match_line})
        i += 1

all_entries.sort(key=lambda x: x['score'])

md_path = 'C:/winegod-app/scripts/analise_2000_por_score_v2.md'
with open(md_path, 'w', encoding='utf-8') as f:
    f.write('# ANALISE 2000 VINHOS v2 — ORDENADO POR SCORE\n\n')
    from collections import Counter
    dests = Counter(e['dest'] for e in all_entries)
    f.write('## RESUMO\n\n| Destino | Qtd | % |\n|---|---|---|\n')
    for d in ['A', 'B', 'C1', 'C2', 'D', 'E']:
        c = dests.get(d, 0)
        f.write(f'| {d} | {c} | {c/len(all_entries)*100:.1f}% |\n')
    f.write(f'| TOTAL | {len(all_entries)} | |\n\n---\n\n')

    de_entries = [e for e in all_entries if e['score'] < 0]
    f.write(f'## ELIMINADOS (D + E) — {len(de_entries)} registros\n\n')
    for idx, e in enumerate(de_entries, 1):
        f.write(f'{idx}. [{e[\"dest\"]}] {e[\"loja\"]}\n')
        f.write(f'   {e[\"match\"]}\n\n')

    scored = [e for e in all_entries if e['score'] >= 0]
    f.write(f'## COM SCORE — {len(scored)} registros\n\n')
    current_band = None
    for idx, e in enumerate(scored, 1):
        band = int(e['score'] * 10) / 10
        if band != current_band:
            current_band = band
            band_entries = [x for x in scored if int(x['score'] * 10) / 10 == band]
            band_a = sum(1 for x in band_entries if x['dest'] == 'A')
            f.write(f'### Score {band:.2f} - {band+0.10:.2f} ({len(band_entries)} vinhos, {band_a} matches A)\n\n')
        prod_flag = f' PROD={e[\"prod\"]}' if e['prod'] != '----' else ''
        f.write(f'{idx}. [{e[\"dest\"]:>2}] {e[\"score\"]:.2f}{prod_flag}  {e[\"loja\"]}\n')
        f.write(f'   {e[\"match\"]}\n\n')

print(f'Salvo: {md_path}')
"
```

3. Imprimir o resumo consolidado e o caminho dos arquivos.

## SE DER ERRO

- O script usa `wines_clean` (nao `wines_unique`). Se der erro de tabela, verificar que `wines_clean` existe.
- Se `vivino_match` nao existir, rodar primeiro: `python scripts/import_vivino_local.py`
- Se pg_trgm nao estiver habilitado: `CREATE EXTENSION IF NOT EXISTS pg_trgm`

## NAO FAZER

- NAO alterar o script `analise_letra.py`
- NAO alterar tabelas no banco
- NAO fazer commit/push
