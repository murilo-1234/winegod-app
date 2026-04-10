# Prompt: Recriar Wine Sources Faltantes no Render

## INSTRUCAO PRINCIPAL

Voce vai criar e executar um script Python que recria os `wine_sources` faltantes para ~76,812 vinhos novos no banco de producao (Render). Esses vinhos existem no Render mas nao tem nenhum link de loja associado, apesar de os links existirem no banco local.

Siga este documento PASSO A PASSO. Nao mude o caminho logico nem reintroduza `check_exists_in_render`, mas pode reforcar robustez, observabilidade e seguranca operacional.

---

## 1. O QUE ACONTECEU (contexto)

O WineGod.ai tem ~2.5M vinhos no banco Render (PostgreSQL). Desses, ~779K sao vinhos "novos" (vindos de scraping de lojas de vinho, sem vivino_id). Cada vinho novo veio de uma loja real e tem pelo menos uma URL de produto.

O script `import_render_z.py` importou esses vinhos para o Render, mas ~76,812 deles ficaram sem `wine_sources` (a tabela que liga vinho ↔ loja ↔ URL ↔ preco).

### Por que os links se perderam

Duas causas atuaram em conjunto:

1. **check_exists_in_render (causa dominante)**: A funcao que verifica se um vinho ja existe no Render usava matching por produtor + overlap de nome. Para produtores genericos (espumante, langhe, barbera, il, barolo, etc.), ela matchava ao vinho ERRADO, redirecionando os links para outro wine_id. Evidencia: 84,654 fontes excedentes em 17,314 wines receptores — ratio quase 1:1 com os 76,812 sem link.

2. **Rollback de batch inteiro (causa secundaria)**: Quando um erro ocorria em qualquer vinho do batch (encoding, varchar overflow), o rollback revertia os wine_sources de TODOS os vinhos do batch. Combinado com DELETE de sources entre rodadas e reexecucao, isso deixou vinhos existentes sem sources.

### Distribuicao dos 76,812 vinhos sem link (referencia operacional — auditoria de 2026-04-06)

| Categoria | Qtd | % | Significado |
|-----------|-----|---|-------------|
| A — BUG | 74,520 | 97.0% | Fonte + loja existem no local, link nao foi criado |
| B — Loja faltante | 9 | 0.0% | Dominio sem store no Render |
| C — Sem fonte local | 2,084 | 2.7% | Fontes nao existem em vinhos_XX_fontes |
| D — Hash nao encontrado | 199 | 0.3% | hash_dedup nao existe no wines_clean |

### O que este script resolve

Apenas a Categoria A: recriar wine_sources para vinhos que tem fonte local e loja no Render.

### O que este script NAO resolve

- Links errados (wine_sources ligados ao vinho errado) — requer auditoria separada
- Vinhos sem fonte local (Cat C) — nao ha URL para criar
- Vinhos sem hash no local (Cat D) — nao ha como rastrear

---

## 2. O QUE JA ESTA FEITO E NAO PODE SER TOCADO

- **NAO altere** o script `C:\winegod-app\scripts\import_render_z.py`
- **NAO delete** nenhum dado do Render (nem wines, nem wine_sources, nem stores)
- **NAO altere** nenhuma tabela do banco local
- **NAO use** `check_exists_in_render` — essa funcao e a causa do bug
- **NAO use** `wines_clean.fontes` — esta vazio em 96% dos registros
- **NAO use** workers/threads — complexidade desnecessaria que causou problemas
- **NAO use** `hash_to_fontes` — o dict do script original que sobrescrevia fontes

---

## 3. CONEXOES DOS BANCOS

### Banco LOCAL (fonte de verdade dos links)

```python
LOCAL_DB = dict(
    host="localhost",
    port=5432,
    dbname="winegod_db",
    user="postgres",
    password="postgres123"
)
```

### Banco RENDER (producao — onde inserir os wine_sources)

```python
RENDER_DB = "<DATABASE_URL_FROM_ENV>"
```

Conexao Render OBRIGATORIA com keepalive e timeout:

```python
import psycopg2

def conectar_render():
    return psycopg2.connect(
        RENDER_DB,
        options='-c statement_timeout=120000',
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
```

---

## 4. ESTRUTURA DAS TABELAS (o que voce precisa saber)

### Banco LOCAL

| Tabela | O que contem | Registros |
|--------|-------------|-----------|
| `wines_clean` | Vinhos deduplicados | 3,962,334 |
| `vinhos_XX_fontes` (50 tabelas, ex: vinhos_br_fontes) | URLs + preco por loja | ~5.6M total |

Campos criticos de `wines_clean`:
- `id` — ID proprio (NAO e o mesmo que vinhos_XX.id)
- `hash_dedup` — hash MD5 unico do vinho
- `pais_tabela` — codigo do pais (br, us, fr, etc.)
- `id_original` — ID na tabela vinhos_XX de origem

Campos de `vinhos_XX_fontes`:
- `vinho_id` — aponta para vinhos_XX.id = wines_clean.id_original
- `url_original` — URL da pagina do produto na loja
- `preco` — preco do produto
- `moeda` — moeda (BRL, USD, EUR, etc.)

### Banco RENDER

| Tabela | O que contem | Registros |
|--------|-------------|-----------|
| `wines` | Todos os vinhos | 2,506,441 |
| `stores` | Lojas | 19,881 |
| `wine_sources` | Links vinho ↔ loja | 3,659,501 |

Campos criticos de `wines`:
- `id` — chave primaria
- `hash_dedup` — hash MD5 (unico, indexado)
- `vivino_id` — NULL para vinhos de scraping

Campos de `stores`:
- `id` — chave primaria
- `dominio` — dominio da loja (ex: evino.com.br)

Campos de `wine_sources`:
- `wine_id` — FK para wines.id
- `store_id` — FK para stores.id
- `url` — URL do produto
- `preco` — preco
- `moeda` — moeda
- `disponivel` — boolean
- `descoberto_em` — timestamp
- `atualizado_em` — timestamp
- Indice UNIQUE parcial: `(wine_id, store_id, url) WHERE url IS NOT NULL`

---

## 5. O CAMINHO CORRETO (linhagem dos links)

```
Render wines.hash_dedup
    ↓ (match por hash no banco local)
wines_clean.hash_dedup → pega pais_tabela + id_original
    ↓ (ponte para tabela de origem)
vinhos_{pais_tabela}_fontes WHERE vinho_id = id_original
    ↓ (URLs reais)
url_original → extrair dominio → stores.dominio → store_id
    ↓ (criar link)
INSERT wine_sources (wine_id, store_id, url, preco, moeda)
```

### Normalizacao de dominio (EXATAMENTE como no script original)

```python
from urllib.parse import urlparse

def get_domain(url):
    try:
        d = urlparse(url).netloc
        return d.replace('www.', '') if d else None
    except:
        return None
```

NAO adicione nenhuma outra normalizacao (sem lowercase extra, sem remover subdominio, sem nada).

---

## 6. PASSO A PASSO DO SCRIPT

### Arquivo a criar

```
C:\winegod-app\scripts\recriar_wine_sources_faltantes.py
```

### Passo 0 — Validacao pre-execucao

Antes de qualquer INSERT, o script DEVE verificar e imprimir:

```python
# No Render: quantos wines novos sem source?
SELECT COUNT(*) FROM wines w
WHERE w.vivino_id IS NULL
AND NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id);
# Esperado: ~76,812

# No Render: quantos stores existem?
SELECT COUNT(*) FROM stores WHERE dominio IS NOT NULL;
# Esperado: ~19,881

# No Local: quantos wines_clean existem?
SELECT COUNT(*) FROM wines_clean;
# Esperado: ~3,962,334
```

Se os numeros divergirem MUITO (>20%), PARE e avise o usuario.

Alem disso, no piloto (500 wines), validar que os ratios fazem sentido:
- hash_resolvidos / processados >= 0.90 (esperado: ~99.7%)
- sem_fonte_local / processados <= 0.10 (esperado: ~2.7%)
- erros_batch = 0
Se algum ratio estiver fora, PARE e investigue antes de rodar completo.

### Passo 1 — Carregar domain_to_store do Render

```python
render_cur.execute("SELECT dominio, id FROM stores WHERE dominio IS NOT NULL")
domain_to_store = {row[0]: row[1] for row in render_cur.fetchall()}
print(f"Stores carregadas: {len(domain_to_store):,}")
```

### Passo 2 — Buscar todos os wines novos sem source do Render

```python
render_cur.execute("""
    SELECT w.id, w.hash_dedup
    FROM wines w
    WHERE w.vivino_id IS NULL
    AND w.hash_dedup IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)
    ORDER BY w.id
""")
wines_sem_source = render_cur.fetchall()
print(f"Wines novos sem source: {len(wines_sem_source):,}")
```

### Passo 3 — Carregar mapa hash_dedup → origens do LOCAL (filtrado)

Carregar APENAS os hashes que precisamos (76K), nao os 3.96M do wines_clean inteiro:

```python
# Extrair os hashes que precisamos
hashes_necessarios = [h for _, h in wines_sem_source]
print(f"Hashes a resolver: {len(hashes_necessarios):,}")

# Consultar wines_clean em chunks de 5000
hash_to_origins = {}  # hash -> [(pais, id_original), ...]
for i in range(0, len(hashes_necessarios), 5000):
    chunk = hashes_necessarios[i:i+5000]
    local_cur.execute("""
        SELECT hash_dedup, pais_tabela, id_original
        FROM wines_clean
        WHERE hash_dedup = ANY(%s) AND id_original IS NOT NULL
    """, (chunk,))
    for hdp, pais, id_orig in local_cur.fetchall():
        if hdp not in hash_to_origins:
            hash_to_origins[hdp] = []
        hash_to_origins[hdp].append((pais, id_orig))

print(f"Hashes resolvidos: {len(hash_to_origins):,}")
```

Nota: na pratica cada hash mapeia para 1 clean_id (verificado empiricamente: 0 duplicatas). Mas guardar lista e defensivo para o caso da base mudar.

### Passo 4 — Processar em batches

```python
import re
from datetime import datetime, timezone
from psycopg2.extras import execute_values

BATCH_SIZE = args.batch_size  # default 500
ts = datetime.now(timezone.utc)

# Contadores
total = len(wines_sem_source)
processados = 0
hash_resolvidos = 0
sem_hash_local = 0
sem_fonte_local = 0
tabela_inexistente = 0
sem_store = 0
links_tentados = 0
links_inseridos_aprox = 0  # rowcount: aproximado com ON CONFLICT
erros_batch = 0
erros_linha = 0

for batch_start in range(0, total, BATCH_SIZE):
    batch = wines_sem_source[batch_start:batch_start + BATCH_SIZE]
    ws_values = []  # valores para INSERT

    for render_wine_id, hash_dedup in batch:
        processados += 1

        # 4a. Resolver hash no local (pode ter multiplas origens)
        origins = hash_to_origins.get(hash_dedup)
        if origins is None:
            sem_hash_local += 1
            continue
        hash_resolvidos += 1

        # 4b. Para cada origem, buscar fontes
        wine_tem_fonte = False
        for pais_tabela, id_original in origins:
            # Validar pais_tabela antes de interpolar em SQL (whitelist: 2 letras minusculas)
            if not pais_tabela or not re.match(r'^[a-z]{2}$', pais_tabela):
                tabela_inexistente += 1
                continue
            tabela_fontes = f"vinhos_{pais_tabela}_fontes"
            try:
                local_cur.execute(
                    f"SELECT url_original, preco, moeda FROM {tabela_fontes} WHERE vinho_id = %s AND url_original IS NOT NULL",
                    (id_original,)
                )
                fontes = local_cur.fetchall()
            except Exception as e:
                local_conn.rollback()
                tabela_inexistente += 1
                continue

            if not fontes:
                continue
            wine_tem_fonte = True

            # 4c. Para cada fonte, resolver store e montar valor
            for url, preco, moeda in fontes:
                if not url:
                    continue
                dominio = get_domain(url)
                if not dominio:
                    continue
                store_id = domain_to_store.get(dominio)
                if not store_id:
                    sem_store += 1
                    continue

                ws_values.append((
                    render_wine_id, store_id, url, preco, moeda,
                    True, ts, ts
                ))
                links_tentados += 1

        if not wine_tem_fonte:
            sem_fonte_local += 1

    # 4d. INSERT batch com SAVEPOINT e fallback granular
    if ws_values and not args.dry_run:
        try:
            render_cur.execute("SAVEPOINT batch_sp")
            execute_values(render_cur, """
                INSERT INTO wine_sources
                    (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
                VALUES %s
                ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING
            """, ws_values)
            links_inseridos_aprox += render_cur.rowcount
            render_cur.execute("RELEASE SAVEPOINT batch_sp")
            render_conn.commit()
        except Exception as e:
            print(f"  ERRO batch {batch_start}: {e}")
            render_cur.execute("ROLLBACK TO SAVEPOINT batch_sp")
            render_conn.commit()
            erros_batch += 1

            # Fallback: inserir linha a linha para isolar o erro
            print(f"  Fallback: inserindo {len(ws_values)} linhas individualmente...")
            for row in ws_values:
                try:
                    render_cur.execute("SAVEPOINT row_sp")
                    render_cur.execute("""
                        INSERT INTO wine_sources
                            (wine_id, store_id, url, preco, moeda, disponivel, descoberto_em, atualizado_em)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (wine_id, store_id, url) WHERE url IS NOT NULL DO NOTHING
                    """, row)
                    links_inseridos_aprox += render_cur.rowcount
                    render_cur.execute("RELEASE SAVEPOINT row_sp")
                except Exception as e2:
                    render_cur.execute("ROLLBACK TO SAVEPOINT row_sp")
                    erros_linha += 1
            render_conn.commit()

    # Log de progresso
    if processados % 5000 == 0 or processados == total:
        dry_tag = " [DRY RUN]" if args.dry_run else ""
        print(f"  {processados:,}/{total:,} | hash_ok={hash_resolvidos:,} | sem_hash={sem_hash_local:,} | sem_fonte={sem_fonte_local:,} | sem_store={sem_store:,} | inseridos~={links_inseridos_aprox:,} | erros_batch={erros_batch:,} | erros_linha={erros_linha:,}{dry_tag}")
```

### Passo 5 — Resumo final

```python
modo = "DRY RUN — nenhum insert realizado" if args.dry_run else "EXECUCAO REAL"
print(f"""
=== RESULTADO FINAL ({modo}) ===
Processados:          {processados:,}
Hash resolvidos:      {hash_resolvidos:,}
Sem hash local:       {sem_hash_local:,}
Sem fonte local:      {sem_fonte_local:,}
Tabela inexistente:   {tabela_inexistente:,}
Sem store:            {sem_store:,}
Links tentados:       {links_tentados:,}
Links inseridos (~):  {links_inseridos_aprox:,}  (rowcount aproximado — usar query pos-execucao para delta real)
Erros de batch:       {erros_batch:,}
Erros de linha:       {erros_linha:,}
""")
```

### Passo 6 — Validacao pos-execucao (medida real)

Estas queries sao a MEDIDA REAL de sucesso, nao o rowcount:

```python
if not args.dry_run:
    # Quantos wines novos AINDA sem source?
    render_cur.execute("""
        SELECT COUNT(*) FROM wines w
        WHERE w.vivino_id IS NULL
        AND NOT EXISTS (SELECT 1 FROM wine_sources ws WHERE ws.wine_id = w.id)
    """)
    sem_source_depois = render_cur.fetchone()[0]
    print(f"Wines novos sem source ANTES:  {total:,}")
    print(f"Wines novos sem source DEPOIS: {sem_source_depois:,}")
    print(f"Delta (corrigidos):            {total - sem_source_depois:,}")
    # Esperado: DEPOIS ~2,292 (Cat B + C + D)

    # Total de wine_sources para wines novos
    render_cur.execute("""
        SELECT COUNT(*) FROM wine_sources ws
        JOIN wines w ON w.id = ws.wine_id
        WHERE w.vivino_id IS NULL
    """)
    print(f"Wine sources de novos DEPOIS:  {render_cur.fetchone()[0]:,}")
else:
    print("DRY RUN: validacao pos-execucao pulada (nenhum insert foi realizado)")
```

---

## 7. ESTRATEGIA DE EXECUCAO

### Piloto primeiro

Antes de rodar para todos os 76K wines:

1. Rode o script com `--piloto` (limita automaticamente a 500 wines)
2. Verifique os numeros (hash_resolvidos, links_inseridos, erros)
3. Se tudo estiver correto (>90% de hash_resolvidos, 0 erros), rode sem `--piloto`

O `--piloto` deve adicionar `LIMIT 500` programaticamente na query do Passo 2 — NAO editar SQL manualmente.

### Tempo estimado

- Piloto (500 wines): ~1-2 minutos
- Completo (76K wines): extrapolar do piloto. Estimativa: 15-30 minutos

---

## 8. ARMADILHAS CONHECIDAS (NAO REPITA ESTES ERROS)

1. **wines_clean.id ≠ vinhos_XX.id** — SEMPRE usar `id_original` + `pais_tabela` para chegar em vinhos_XX_fontes
2. **wines_clean.fontes esta vazio** — em 96% dos registros. NUNCA usar esse campo. Usar `vinhos_XX_fontes`
3. **IDs de paises diferentes se sobrepoe** — vinhos_br.id=1 ≠ vinhos_us.id=1 ≠ wines_clean.id=1
4. **Conexao Render cai com operacoes longas** — usar keepalives (ja incluido na funcao `conectar_render`)
5. **execute_values rowcount nao e confiavel com ON CONFLICT DO NOTHING** — usar como contador aproximado (`links_inseridos_aprox`), confiar na query pos-execucao como medida real
6. **NOW() como string** — `execute_values` insere como texto literal. Usar `datetime.now(timezone.utc)` (ja incluido)
7. **Render tem NOT NULL em hash_dedup** — o filtro `hash_dedup IS NOT NULL` na query do Passo 2 ja trata isso
8. **NAO usar LEFT JOIN + GROUP BY + HAVING COUNT = 0** — e lento. Usar `NOT EXISTS` (ja incluido)
9. **NAO usar check_exists_in_render** — essa funcao e a CAUSA do bug. Usar apenas hash_dedup
10. **NAO usar batch grande** — batches de 1000+ podem causar timeout. Usar 500

---

## 9. VALIDACAO DE SANIDADE (DURANTE A EXECUCAO)

Se durante a execucao voce observar qualquer um destes sinais, PARE:

- `sem_hash_local` > 1,000 (esperado: ~199)
- `sem_fonte_local` > 5,000 (esperado: ~2,084)
- `tabela_inexistente` > 0 (esperado: 0 — todas as 50 tabelas existem)
- `erros_batch` > 10
- `erros_linha` > 100
- `links_inseridos_aprox` = 0 apos 5,000 processados
- A conexao Render cai repetidamente

---

## 10. O QUE FAZER DEPOIS

Depois que o script rodar com sucesso:

1. **Confirmar os numeros**: wines sem source deve cair de ~76,812 para ~2,292
2. **Relatar**: informar ao usuario os numeros finais
3. **NAO tentar corrigir** os links errados (84K fontes em wines errados) — isso requer auditoria separada
4. **NAO deletar** nenhum dado
5. **NAO rerodar** sem revisar o resultado da primeira execucao. O script e idempotente (ON CONFLICT protege contra duplicatas), mas rerun so deve ocorrer conscientemente apos analisar os numeros

---

## 11. ESTRUTURA COMPLETA DO SCRIPT

O script deve ficar em `C:\winegod-app\scripts\recriar_wine_sources_faltantes.py` e ter esta estrutura:

```
1. Imports (psycopg2, psycopg2.extras, urlparse, datetime, argparse)
2. Constantes (LOCAL_DB, RENDER_DB)
3. Funcao get_domain(url)
4. Funcao conectar_render()
5. Funcao conectar_local()
6. Funcao main(args):
   a. Conectar LOCAL e RENDER
   b. Passo 0: Validacao pre-execucao (parar se divergir >20%)
   c. Passo 1: Carregar domain_to_store do Render
   d. Passo 2: Buscar wines sem source (com LIMIT 500 se --piloto)
   e. Passo 3: Carregar hash_to_origins filtrado (chunks de 5000)
   f. Passo 4: Processar em batches com fallback granular
   g. Passo 5: Resumo final (com tag DRY RUN se aplicavel)
   h. Passo 6: Validacao pos-execucao (queries reais de delta)
   i. Fechar conexoes
7. if __name__ == "__main__": parse args e chamar main(args)
```

Argparse com:
- `--piloto` — roda apenas para 500 wines, adiciona LIMIT na query automaticamente (default: False)
- `--dry-run` — simula sem INSERT, imprime o que faria (default: False)
- `--batch-size N` — tamanho do batch (default: 500)

---

## 12. CHECKLIST ANTES DE RODAR

Antes de executar o script, confirme:

- [ ] O script esta em `C:\winegod-app\scripts\recriar_wine_sources_faltantes.py`
- [ ] O banco local esta acessivel (PostgreSQL rodando em localhost:5432)
- [ ] O banco Render esta acessivel (testar conexao)
- [ ] O script foi rodado primeiro com `--piloto` e os numeros fazem sentido
- [ ] O usuario autorizou a execucao completa

---

## RESUMO EM UMA FRASE

Pegar cada wine do Render sem source → buscar hash_dedup no local → pegar pais + id_original → buscar URLs em vinhos_XX_fontes → resolver store por dominio → INSERT wine_sources.
