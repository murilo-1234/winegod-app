# Handoff — Como salvar respostas do Codex na base de dados

## Contexto

O Codex (OpenAI) classifica vinhos e salva as respostas em arquivos TXT na pasta `C:\winegod-app\lotes_codex\`. Cada arquivo `resposta_*.txt` tem 1000 linhas com classificacoes (W|..., X, S, =N). Esses arquivos precisam ser inseridos na tabela `y2_results` do banco PostgreSQL local.

## O script que faz tudo

```bash
cd C:\winegod-app
python scripts/salvar_respostas_codex.py
```

Esse comando:
1. Detecta TODOS os arquivos `resposta_*.txt` na pasta `lotes_codex/`
2. Para cada resposta, encontra o arquivo de IDs correspondente (`lote_*_ids.txt`)
3. Parseia cada linha (W|prod|vinho|..., X, S, =N)
4. Faz INSERT na `y2_results` com `fonte_llm = 'codex_gpt54mini'`
5. ON CONFLICT DO NOTHING (se o clean_id ja existe, pula sem erro)
6. Registra no `y2_lotes_log`

## Modo especifico (salvar lotes especificos)

```bash
python scripts/salvar_respostas_codex.py 700 701 702
```

Salva apenas os lotes indicados. Util quando voce sabe quais acabaram de terminar.

## Como verificar antes de salvar

```python
# Ver quantas respostas estao prontas e nao salvas
cd C:\winegod-app
python -c "
import os, re
respostas = [f for f in os.listdir('lotes_codex') if f.startswith('resposta_') and f.endswith('.txt')]
print(f'Respostas na pasta: {len(respostas)}')
for f in sorted(respostas)[-10:]:
    lines = len(open(f'lotes_codex/{f}', encoding='utf-8').readlines())
    print(f'  {f}: {lines} linhas')
"
```

## Como verificar depois de salvar

```python
cd C:\winegod-app
python -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='winegod_db', user='postgres', password='postgres123')
cur = conn.cursor()
cur.execute(\"SELECT COUNT(*) FROM y2_results WHERE fonte_llm = 'codex_gpt54mini'\")
print(f'Total Codex na base: {cur.fetchone()[0]}')
cur.execute(\"SELECT classificacao, COUNT(*) FROM y2_results WHERE fonte_llm = 'codex_gpt54mini' GROUP BY classificacao ORDER BY COUNT(*) DESC\")
for r in cur.fetchall():
    print(f'  {r[0] or \"NULL\"}: {r[1]}')
conn.close()
"
```

## Como verificar qualidade dos campos

```python
cd C:\winegod-app
python -c "
import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='winegod_db', user='postgres', password='postgres123')
cur = conn.cursor()
cur.execute('''
    SELECT COUNT(*) as total,
        SUM(CASE WHEN prod_banco IS NOT NULL AND prod_banco != '' THEN 1 ELSE 0 END) as prod,
        SUM(CASE WHEN vinho_banco IS NOT NULL AND vinho_banco != '' THEN 1 ELSE 0 END) as vinho,
        SUM(CASE WHEN safra IS NOT NULL AND safra != '' THEN 1 ELSE 0 END) as safra,
        SUM(CASE WHEN cor IS NOT NULL AND cor != '' THEN 1 ELSE 0 END) as cor,
        SUM(CASE WHEN corpo IS NOT NULL AND corpo != '' THEN 1 ELSE 0 END) as corpo
    FROM y2_results WHERE fonte_llm = 'codex_gpt54mini' AND classificacao = 'W'
''')
r = cur.fetchone()
t = r[0]
print(f'Vinhos (W): {t}')
for campo, val in zip(['produtor','vinho','safra','cor','corpo'], r[1:]):
    print(f'  {campo}: {val}/{t} ({val/t*100:.0f}%)')
conn.close()
"
```

## Detalhes tecnicos do parser

O script `salvar_respostas_codex.py` aceita 2 formatos de linha:
- Com numero: `1. W|produtor|vinho|pais|cor|...` (remove o "1. " antes de parsear)
- Sem numero: `W|produtor|vinho|pais|cor|...`

Mapeamento dos campos:
```
W|[1]produtor|[2]vinho|[3]pais|[4]cor|[5]uva|[6]regiao|[7]subregiao|[8]safra|[9]abv|[10]classificacao|[11]corpo|[12]harmonizacao|[13]docura
```

Duplicatas (`=N`): o N referencia o item N do lote. O script converte pra `clean_id` do item referenciado e salva como `status=duplicate`.

## Banco de dados

```
Host: localhost
Port: 5432
DB: winegod_db
User: postgres
Pass: postgres123
```

Tabela: `y2_results`
Log: `y2_lotes_log`

## Fluxo resumido

1. O Codex termina abas e gera `resposta_*.txt`
2. Rodar `python scripts/salvar_respostas_codex.py`
3. Verificar total na base
4. Pronto — os itens salvos nao serao reprocessados por ninguem (LEFT JOIN exclui)
