INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# CHAT Q — Deduplicacao Cross-Reference (Vivino x Lojas)

## CONTEXTO

WineGod.ai tem 2 fontes de dados de vinhos:
1. **wines** (Render): 1.72M vinhos importados do Vivino com ratings e notas WCF
2. **wine_sources** (Render): 66,216 registros ligando vinhos a lojas, importados de um banco local que tem 3.78M vinhos de lojas

O problema: a importacao de lojas (Chat I) usou `hash_dedup` para fazer match entre vinhos de lojas e vinhos Vivino. Apenas 11,783 vinhos tiveram match — os outros 4.5M nao bateram porque o hash e fragil (diferenca minima no nome invalida o match).

Precisamos de um matching mais inteligente para conectar mais vinhos de lojas aos vinhos Vivino.

## SUA TAREFA

Criar um script que faz deduplicacao fuzzy para aumentar o numero de matches entre vinhos de lojas (banco local) e vinhos Vivino (Render).

## CREDENCIAIS

```
# Banco WineGod no Render (wines, stores, wine_sources)
DATABASE_URL=postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod

# Banco local com vinhos de lojas
WINEGOD_LOCAL_URL=postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db
```

## ESTRATEGIA DE MATCHING

O banco local tem 50 tabelas `vinhos_{pais}` (vinhos_BR, vinhos_US, vinhos_AR, etc.) com ~3.78M vinhos. Cada vinho tem:
- `nome` — nome do vinho na loja
- `produtor` — produtor/vinicola
- `safra` — ano
- `pais` — pais

O banco Render tem `wines` com:
- `nome` — nome do vinho Vivino
- `produtor` — produtor Vivino
- `safra` — vintage
- `pais_nome` — pais
- `nome_normalizado` — nome sem acentos, lowercase (com indice pg_trgm)

### Algoritmo de matching (3 niveis):

**Nivel 1 — Match exato normalizado (rapido)**
- Normalizar nome do vinho local (lowercase, sem acentos, sem caracteres especiais)
- Comparar com `nome_normalizado` no Render (WHERE =)
- Se match unico no mesmo pais: MATCH

**Nivel 2 — Match fuzzy com pg_trgm (medio)**
- Usar `similarity(nome_normalizado, %s) > 0.6` no Render
- Filtrar mesmo pais
- Se melhor match tem similarity > 0.8 e e unico: MATCH
- Se melhor match tem similarity 0.6-0.8: validar com produtor

**Nivel 3 — Match por produtor + safra (fallback)**
- Normalizar produtor local
- Buscar no Render: mesmo produtor (ILIKE) + mesma safra + mesmo pais
- Se resultado unico: MATCH

### Para cada match encontrado:
1. Inserir em `wine_sources` (wine_id, store_id, preco, url, etc.)
2. Atualizar `preco_min`/`preco_max` no `wines` se for menor/maior

## ARQUIVOS A CRIAR

### 1. scripts/dedup_crossref.py (NOVO)

Script principal. Estrutura:

```python
#!/usr/bin/env python3
"""Deduplicacao cross-reference: vinhos de lojas (local) x vinhos Vivino (Render)."""

import psycopg2
import os
import time
import unicodedata
import re

RENDER_URL = os.getenv("DATABASE_URL", "postgresql://winegod_user:XXXXXXXXX@dpg-XXXXXXXXX.oregon-postgres.render.com/winegod")
LOCAL_URL = os.getenv("WINEGOD_LOCAL_URL", "postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db")

# Lista de paises com tabelas no banco local
PAISES = ["BR", "US", "AR", "CL", "PT", "ES", "FR", "IT", "DE", "GB",
          "AU", "NZ", "ZA", "AT", "BE", "CA", "CH", "CN", "CO", "CZ",
          "DK", "FI", "GR", "HK", "HU", "IE", "IL", "IN", "JP", "KR",
          "LU", "MD", "MX", "NL", "NO", "PE", "PH", "PL", "RO", "RU",
          "SE", "SG", "TH", "TR", "TW", "UY", "AE", "BG", "GE", "HR"]

def normalizar(texto):
    """Remove acentos, lowercase, remove caracteres especiais."""
    if not texto:
        return ""
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')
    texto = texto.lower().strip()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto

def processar_pais(pais_code, conn_local, conn_render):
    """Processa todos os vinhos de um pais."""
    # 1. Buscar vinhos locais da tabela vinhos_{pais}
    # 2. Para cada vinho, tentar match nivel 1, 2, 3
    # 3. Inserir matches em wine_sources do Render
    # 4. Atualizar precos se necessario
    pass

def main():
    conn_local = psycopg2.connect(LOCAL_URL)
    conn_render = psycopg2.connect(RENDER_URL)

    total_matches = 0
    for pais in PAISES:
        matches = processar_pais(pais, conn_local, conn_render)
        total_matches += matches
        print(f"[{pais}] {matches} novos matches")

    print(f"\nTotal: {total_matches} novos matches")
    conn_local.close()
    conn_render.close()

if __name__ == "__main__":
    main()
```

**IMPORTANTE sobre performance:**
- Processar por pais (50 tabelas, uma de cada vez)
- Usar batch INSERT (executemany) a cada 500 matches
- Nao fazer SELECT individual por vinho — buscar em lotes
- Pular vinhos que ja tem wine_source (verificar antes)
- Imprimir progresso: `[BR] 5000/45000 processados, 823 matches (16%)`
- Tempo estimado: pode levar 30-60 min pra 3.78M vinhos

### 2. scripts/dedup_report.py (NOVO — opcional)

Script curto que mostra estatisticas:
- Total wines no Render
- Total wine_sources antes/depois
- Top 10 paises com mais matches
- Distribuicao por nivel de match (exato, fuzzy, produtor)

## O QUE NAO FAZER

- **NAO modificar app.py** — e um script standalone
- **NAO modificar nenhum arquivo do backend ou frontend**
- **NAO modificar tabelas existentes** (wines, stores, wine_sources) — apenas INSERT/UPDATE
- **NAO deletar dados existentes** — so adicionar novos matches
- **NAO fazer git commit/push** — avisar quando terminar
- **NAO rodar contra o banco Render com queries pesadas sem LIMIT** — sempre testar com 1 pais primeiro

## COMO TESTAR

1. Testar com 1 pais (BR):
```bash
cd scripts
python -c "
from dedup_crossref import processar_pais, RENDER_URL, LOCAL_URL
import psycopg2
conn_l = psycopg2.connect(LOCAL_URL)
conn_r = psycopg2.connect(RENDER_URL)
matches = processar_pais('BR', conn_l, conn_r)
print(f'BR: {matches} matches')
conn_l.close()
conn_r.close()
"
```

2. Verificar no banco:
```sql
SELECT COUNT(*) FROM wine_sources;  -- deve ter aumentado
```

3. Rodar completo:
```bash
cd scripts && python dedup_crossref.py
```

## ENTREGAVEL

- `scripts/dedup_crossref.py` — script de deduplicacao (pronto pra rodar)
- `scripts/dedup_report.py` — relatorio de estatisticas (opcional)
- Relatorio no terminal: quantos matches novos por pais

## REGRA DE COMMIT

Commitar APENAS os arquivos que VOCE criou/modificou nesta sessao. NUNCA incluir arquivos de outros chats. Fazer `git pull` antes de `git push` para nao conflitar com outros chats que rodam em paralelo.
