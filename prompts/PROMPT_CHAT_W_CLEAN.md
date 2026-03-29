INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# CHAT W — Fase 1: Limpar e Normalizar 4.17M Vinhos de Lojas

## CONTEXTO

WineGod.ai tem 4,175,376 vinhos scraped de lojas online em 50 tabelas `vinhos_{pais}` no banco local. Esses dados tem problemas:
1. Encoding quebrado (Vi�a → Viña, M�linand → Mélinand)
2. Safra duplicada no nome ("Reserva 2018 2018")
3. Campo `vinicola_nome` contem o DOMINIO DA LOJA (ex: "demaisoneast"), NAO o produtor real
4. Sufixos inuteis no nome ("750ml", "- Meia gfa.", "1.5L")
5. Nomes nao normalizados (acentos, maiusculas inconsistentes)
6. 72% dos vinhos NAO tem hash_dedup

## SUA TAREFA

Criar um script que:
1. Le todos os vinhos das 50 tabelas `vinhos_{pais}`
2. Limpa e normaliza os dados
3. Salva numa tabela unificada `wines_clean` no banco local

## CREDENCIAIS

```
# Banco local
WINEGOD_LOCAL_URL=postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db
```

## TABELA DE ORIGEM

50 tabelas `vinhos_{pais}` (vinhos_br, vinhos_us, etc.) com colunas relevantes:
- `id` — ID unico na tabela do pais
- `nome` — nome do vinho (pode ter encoding quebrado, safra duplicada, sufixos)
- `vinicola_nome` — CUIDADO: e o dominio da loja, NAO o produtor
- `safra` — ano (int ou string)
- `tipo_nome` — tipo do vinho (Red, White, Rose, Sparkling, etc.)
- `pais_nome` — pais de origem do vinho
- `pais_codigo` — codigo do pais (BR, US, etc.)
- `regiao_nome` — regiao
- `sub_regiao` — sub-regiao
- `rating_medio` — nota media (float)
- `total_ratings` — quantidade de ratings
- `preco` — preco (pode ser NULL)
- `moeda` — moeda do preco
- `uvas` — uvas/castas
- `url_imagem` — URL da imagem
- `url_vivino` — URL do Vivino (se existir)
- `hash_dedup` — hash de deduplicacao (pode ser NULL)
- `nome_normalizado` — nome normalizado (pode ser NULL)
- `produtor_normalizado` — produtor normalizado (pode ser NULL)
- `preco_min`, `preco_max` — precos agregados
- `fontes` — JSON com fontes/lojas
- `total_fontes` — quantidade de lojas
- `ean_gtin` — codigo de barras (se existir)

## TABELA DE DESTINO

Criar tabela `wines_clean` no banco local:

```sql
CREATE TABLE IF NOT EXISTS wines_clean (
    id SERIAL PRIMARY KEY,
    pais_tabela VARCHAR(5) NOT NULL,        -- codigo do pais da tabela original (br, us, etc.)
    id_original INTEGER NOT NULL,            -- id na tabela vinhos_{pais}
    nome_original TEXT,                      -- nome como veio
    nome_limpo TEXT NOT NULL,                -- nome corrigido (encoding, sufixos removidos)
    nome_normalizado TEXT NOT NULL,           -- lowercase, sem acentos, sem especiais
    produtor_extraido TEXT,                  -- produtor EXTRAIDO do nome (nao da vinicola_nome)
    produtor_normalizado TEXT,               -- produtor lowercase, sem acentos
    safra INTEGER,                           -- ano
    tipo TEXT,                               -- Red, White, Rose, Sparkling, etc.
    pais TEXT,                               -- pais de origem do vinho
    regiao TEXT,
    sub_regiao TEXT,
    uvas TEXT,
    rating REAL,
    total_ratings INTEGER,
    preco REAL,
    moeda VARCHAR(10),
    preco_min REAL,
    preco_max REAL,
    url_imagem TEXT,
    hash_dedup VARCHAR(64),
    ean_gtin VARCHAR(50),
    fontes TEXT,                              -- JSON com lojas
    total_fontes INTEGER,
    UNIQUE(pais_tabela, id_original)
);

CREATE INDEX idx_wc_nome_norm ON wines_clean (nome_normalizado);
CREATE INDEX idx_wc_produtor_norm ON wines_clean (produtor_normalizado);
CREATE INDEX idx_wc_hash ON wines_clean (hash_dedup) WHERE hash_dedup IS NOT NULL;
CREATE INDEX idx_wc_pais_tipo ON wines_clean (pais, tipo);
CREATE INDEX idx_wc_safra ON wines_clean (safra) WHERE safra IS NOT NULL;
CREATE INDEX idx_wc_ean ON wines_clean (ean_gtin) WHERE ean_gtin IS NOT NULL;
```

## REGRAS DE LIMPEZA

### 1. Corrigir encoding
```python
def fix_encoding(text):
    if not text:
        return text
    # Tentar decodificar latin1 -> utf8 para caracteres quebrados
    try:
        if '�' in text or '\ufffd' in text:
            # Tentar recuperar
            text = text.encode('latin1', errors='ignore').decode('utf-8', errors='ignore')
    except:
        pass
    # Substituicoes comuns
    replacements = {
        'Vi�a': 'Viña', 'M�linand': 'Mélinand',
        'Ch�teau': 'Château', 'Ros�': 'Rosé',
        'Cr�mant': 'Crémant', 'Cuv�e': 'Cuvée',
        'S�o': 'São', 'Fran�ois': 'François',
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.strip()
```

### 2. Remover sufixos do nome
Remover do final: "750ml", "1.5L", "375ml", "3L", "- Meia gfa.", "Magnum", "Jeroboam", "- ", trailing dashes.

### 3. Remover safra duplicada
Se nome termina com a safra repetida ("Reserva 2018 2018"), remover a segunda.

### 4. Extrair produtor do nome
O campo `vinicola_nome` e a LOJA (dominio), nao o produtor. Extrair produtor do nome:
- Se nome tem formato "Produtor NomeVinho Safra", o primeiro token geralmente e o produtor
- Se nome tem formato "NomeVinho Produtor", mais dificil
- Usar heuristica: primeira palavra/grupo antes do primeiro espaco que parece nome de vinho
- Se impossivel extrair, deixar NULL
- **NAO usar vinicola_nome como produtor** — e o dominio da loja

### 5. Normalizar
```python
import unicodedata, re
def normalizar(texto):
    if not texto: return ""
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')
    texto = texto.lower().strip()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto
```

## PERFORMANCE

- Processar por pais (50 tabelas, uma de cada vez)
- INSERT em batches de 5000 (executemany)
- Imprimir progresso: `[BR] 50000/228973 processados (21.8%)`
- gc.collect() a cada pais
- Tempo estimado: 1-2h para 4.17M vinhos

## ARQUIVO A CRIAR

### scripts/clean_wines.py (NOVO)

Script completo que:
1. Cria tabela `wines_clean` (DROP IF EXISTS primeiro)
2. Para cada tabela `vinhos_{pais}`:
   - SELECT todos os vinhos
   - Limpa encoding, remove sufixos, extrai produtor, normaliza
   - INSERT em `wines_clean` em batches
3. Imprime estatisticas finais:
   - Total de vinhos processados
   - Quantos com produtor extraido
   - Quantos com encoding corrigido
   - Quantos com hash_dedup

## O QUE NAO FAZER

- **NAO modificar as tabelas originais** (vinhos_{pais}) — so ler
- **NAO conectar ao banco Render** — tudo local
- **NAO fazer git commit/push** — avisar quando terminar
- **NAO usar vinicola_nome como produtor** — e o dominio da loja

## COMO TESTAR

```bash
cd scripts && python clean_wines.py
# Verificar resultado:
psql -h localhost -U postgres -d winegod_db -c "SELECT COUNT(*) FROM wines_clean;"
psql -h localhost -U postgres -d winegod_db -c "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean LIMIT 10;"
```

## ENTREGAVEL

- `scripts/clean_wines.py` — script de limpeza
- Tabela `wines_clean` populada no banco local (~4.17M rows)

## REGRA DE COMMIT

Commitar APENAS os arquivos que VOCE criou/modificou nesta sessao. NUNCA incluir arquivos de outros chats. Fazer `git pull` antes de `git push`.
