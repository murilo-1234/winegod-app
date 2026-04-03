INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar.

# EXECUTAR — Pipeline completo em 3.96M vinhos (8 grupos paralelos)

## CONTEXTO

O pipeline de classificacao e match foi desenvolvido e testado em 2000 vinhos com resultado:
- A (match Vivino): 52.4%
- B (vinho novo): 7.4%
- C2 (incerto): 13.3%
- D+E (eliminado): 26.8%

Agora precisa rodar em escala na base completa de 3,962,334 vinhos.

## O QUE FAZER

### Passo 1: Verificar pre-requisitos

```python
import psycopg2
conn = psycopg2.connect('postgresql://postgres:postgres123@localhost:5432/winegod_db')
cur = conn.cursor()
cur.execute('SELECT count(*) FROM wines_clean')
print(f'wines_clean: {cur.fetchone()[0]:,}')  # deve ser 3,962,334
cur.execute('SELECT count(*) FROM vivino_match')
print(f'vivino_match: {cur.fetchone()[0]:,}')  # deve ser 1,727,058
cur.execute("SELECT extname FROM pg_extension WHERE extname='pg_trgm'")
print(f'pg_trgm: {cur.fetchone()}')  # deve existir
conn.close()
```

### Passo 2: Atualizar match_vivino.py

O script `C:\winegod-app\scripts\match_vivino.py` esta DESATUALIZADO. Precisa ser atualizado com as melhorias do `analise_letra.py`. As mudancas necessarias:

1. Copiar do `analise_letra.py` as seguintes secoes COMPLETAS:
   - `PALAVRAS_PROIBIDAS` (expandida com cerveja, licor, whisky regions)
   - `PADROES_NAO_VINHO`
   - `DESTILADOS`
   - `UVAS` (expandida com 150 uvas de 50 paises)
   - `UVAS_ABREV` (expandida com 35 multi-palavra)
   - `TERMOS_VINHO` (expandida com 170+ termos em 8 linguas)
   - `GARANTIA_VINHO` (26 palavras que forcam wl=3)
   - `TIPO_MAP`, `GENERIC_WORDS`
   - Funcoes: `chars_uteis`, `has_forbidden_word`, `has_nonwine_pattern`, `is_spirit`, `wine_likeness`, `classify_prewine`
   - Funcoes: `nome_overlap_score`, `tipo_bate`, `safra_bate`, `produtor_parcial`
   - Funcao `classify_match` atualizada (com regra nome overlap, sem C1)
   - Funcoes de match: `score_candidate`, `search_producer`, `search_keyword`, `search_trgm_nome`, `search_trgm_combined`, `find_best_match`

2. Atualizar os GROUPS pra refletir os 3.96M:

```python
GROUPS = {
    1: ['us'],
    2: ['br', 'es', 'be', 'in', 'il', 'tw'],
    3: ['au', 'nz', 'ie', 'ro', 'hu', 'bg', 'hr'],
    4: ['gb', 'fr', 'pe', 'gr', 'fi', 'jp', 'tr', 'th'],
    5: ['it', 'pt', 'at', 'za', 'md', 'ge', 'cn'],
    6: ['de', 'mx', 'ca', 'pl', 'se', 'cz', 'ae'],
    7: ['nl', 'hk', 'ph', 'ch', 'co', 'lu', 'no'],
    8: ['dk', 'ar', 'sg', 'uy', 'cl', 'ru', 'kr'],
}
```

3. Mudar a query pra ler de `wines_clean` (NAO `wines_unique`):

```python
cur.execute(f"""
    SELECT id, nome_normalizado, produtor_normalizado, safra, tipo, pais_tabela, regiao
    FROM wines_clean
    WHERE pais_tabela IN ({placeholders})
    ORDER BY id
""", countries)
```

4. A tabela de output deve incluir o destino:

```sql
CREATE TABLE match_results_y{GROUP_NUM} (
    id SERIAL PRIMARY KEY,
    clean_id INTEGER NOT NULL,      -- ID na wines_clean
    vivino_id INTEGER,              -- ID na vivino_match (NULL se B/C2/D/E)
    match_score REAL,
    match_strategy VARCHAR(20),
    destino VARCHAR(5),             -- A, B, C2, D, E
    wine_likeness INTEGER,
    loja_nome TEXT,
    vivino_nome TEXT
)
```

**ALTERNATIVA MAIS SIMPLES:** Em vez de atualizar o match_vivino.py manualmente, copiar o `analise_letra.py` inteiro e modificar:
- Trocar a logica do main() pra processar por grupo de paises em vez de por letra
- Trocar a query pra `wines_clean WHERE pais_tabela IN (...)`
- Adicionar batch insert e progresso a cada 1000
- Salvar em tabela em vez de TXT

### Passo 3: Rodar 8 grupos em paralelo

```bash
cd C:\winegod-app
python scripts/match_vivino.py 1 &
python scripts/match_vivino.py 2 &
python scripts/match_vivino.py 3 &
python scripts/match_vivino.py 4 &
python scripts/match_vivino.py 5 &
python scripts/match_vivino.py 6 &
python scripts/match_vivino.py 7 &
python scripts/match_vivino.py 8 &
```

Rodar TODOS em background. Cada um leva estimado 2-6 horas dependendo do tamanho do grupo.
- Grupo 1 (US, 785K) e o mais pesado — pode levar 6h+
- Grupos 2-8 (~450K cada) — 3-4h cada

### Passo 4: Monitorar

Cada script imprime progresso a cada 1000 vinhos. Verificar periodicamente.

### Passo 5: Merge dos resultados

Quando TODOS terminarem:

```sql
DROP TABLE IF EXISTS match_results_final;
CREATE TABLE match_results_final AS
SELECT clean_id, vivino_id, match_score, match_strategy, destino, wine_likeness, loja_nome, vivino_nome
FROM match_results_y1
UNION ALL SELECT clean_id, vivino_id, match_score, match_strategy, destino, wine_likeness, loja_nome, vivino_nome FROM match_results_y2
UNION ALL SELECT clean_id, vivino_id, match_score, match_strategy, destino, wine_likeness, loja_nome, vivino_nome FROM match_results_y3
UNION ALL SELECT clean_id, vivino_id, match_score, match_strategy, destino, wine_likeness, loja_nome, vivino_nome FROM match_results_y4
UNION ALL SELECT clean_id, vivino_id, match_score, match_strategy, destino, wine_likeness, loja_nome, vivino_nome FROM match_results_y5
UNION ALL SELECT clean_id, vivino_id, match_score, match_strategy, destino, wine_likeness, loja_nome, vivino_nome FROM match_results_y6
UNION ALL SELECT clean_id, vivino_id, match_score, match_strategy, destino, wine_likeness, loja_nome, vivino_nome FROM match_results_y7
UNION ALL SELECT clean_id, vivino_id, match_score, match_strategy, destino, wine_likeness, loja_nome, vivino_nome FROM match_results_y8;

CREATE INDEX idx_mrf_clean ON match_results_final (clean_id);
CREATE INDEX idx_mrf_vivino ON match_results_final (vivino_id);
CREATE INDEX idx_mrf_dest ON match_results_final (destino);
```

### Passo 6: Relatorio final

```sql
SELECT destino, count(*), round(100.0 * count(*) / sum(count(*)) OVER(), 1) as pct
FROM match_results_final GROUP BY destino ORDER BY count(*) DESC;
```

Resultado esperado (baseado na amostra):
- A: ~2.08M (52%)
- B: ~293K (7%)
- C2: ~527K (13%)
- D: ~995K (25%)
- E: ~67K (2%)

## CREDENCIAIS

```
Banco local: postgresql://postgres:postgres123@localhost:5432/winegod_db
```

## DOCUMENTACAO DE REFERENCIA

- Metodologia completa: `C:\winegod-app\prompts\DOC_MATCH_VIVINO_METODOLOGIA.md`
- Script de referencia (com todas as melhorias): `C:\winegod-app\scripts\analise_letra.py`
- CTO doc: `C:\winegod-app\prompts\PROMPT_CTO_WINEGOD_V2.md`

## IMPORTANTE

- Ler de `wines_clean` (3,962,334) — NAO de `wines_unique`
- Tabela `vivino_match` ja existe com 1,727,058 vinhos e indexes trgm
- NAO alterar wines_clean nem vivino_match
- NAO fazer commit/push
- Script base com todas as melhorias: `C:\winegod-app\scripts\analise_letra.py`
- Se der erro, verificar que pg_trgm esta habilitado e que vivino_match tem indexes
