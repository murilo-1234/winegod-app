INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Rode TODOS os checks abaixo e reporte o resultado.

# CHAT AUDIT — Auditoria Profunda da Fase 1 (wines_clean)

## CREDENCIAIS

```
WINEGOD_LOCAL_URL=postgresql://postgres:XXXXXXXXX@localhost:5432/winegod_db
```

## EXECUTE TODOS OS 15 CHECKS ABAIXO

Conectar ao banco e rodar cada check. Reportar resultado de TODOS.

### CHECK 1 — Contagem total
```sql
SELECT COUNT(*) FROM wines_clean;
-- Comparar com soma das 50 tabelas originais:
SELECT SUM(n_live_tup) FROM pg_stat_user_tables WHERE relname LIKE 'vinhos_%' AND relname NOT LIKE '%_fontes';
-- Diferenca aceitavel: < 3% (itens nao-vinho foram filtrados)
```

### CHECK 2 — Todos os 50 paises presentes
```sql
SELECT pais_tabela, COUNT(*) FROM wines_clean GROUP BY pais_tabela ORDER BY COUNT(*) DESC;
-- Verificar: nenhum pais pode faltar. Contar quantos paises distintos.
-- Comparar cada pais com a tabela original (diferenca > 10% = ALERTA)
```

### CHECK 3 — Campos obrigatorios NULL
```sql
SELECT 'nome_limpo' as campo, COUNT(*) FROM wines_clean WHERE nome_limpo IS NULL OR nome_limpo = ''
UNION ALL SELECT 'nome_normalizado', COUNT(*) FROM wines_clean WHERE nome_normalizado IS NULL OR nome_normalizado = ''
UNION ALL SELECT 'pais_tabela', COUNT(*) FROM wines_clean WHERE pais_tabela IS NULL OR pais_tabela = ''
UNION ALL SELECT 'id_original', COUNT(*) FROM wines_clean WHERE id_original IS NULL;
-- ZERO e o unico resultado aceitavel
```

### CHECK 4 — Encoding quebrado restante
```sql
SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%�%';
SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%\ufffd%';
-- Aceitavel: 0
```

### CHECK 5 — HTML entities restantes (CRITICO — falhou na auditoria anterior)
```sql
SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&#%';
SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&amp;%';
SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%&nbsp;%';
-- Aceitavel: 0. Se > 0, a limpeza falhou.
```

### CHECK 6 — Volume no nome (CRITICO — falhou na auditoria anterior)
```sql
SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d+\s*ml\b';
SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d+\s*cl\b';
SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~* '\d[\.,]\d+\s*[lL]\b';
-- Aceitavel: < 0.5% do total. Se > 1%, a limpeza falhou.
```

### CHECK 7 — Preco no nome (CRITICO — falhou na auditoria anterior)
```sql
SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~ '[\$€£¥]' OR nome_limpo LIKE '%R$%';
-- Aceitavel: < 0.1%
```

### CHECK 8 — Itens nao-vinho restantes
```sql
-- Buscar com palavras INTEIRAS (evitar falsos positivos)
SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(whisky|whiskey|vodka|tequila|cognac)\y';
SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(queijo|cheese|fromage|chocolate)\y';
SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(red bull|coca.cola|gift card|gutschein)\y';
-- Aceitavel: < 500 total
```

### CHECK 9 — Produtores que sao dominios de loja
```sql
SELECT produtor_extraido, COUNT(*) FROM wines_clean
WHERE produtor_extraido ~ '\.(com|net|cl|br|co|org|shop)'
GROUP BY produtor_extraido ORDER BY COUNT(*) DESC LIMIT 20;
-- Aceitavel: 0
```

### CHECK 10 — Top 30 produtores mais frequentes (verificar se fazem sentido)
```sql
SELECT produtor_extraido, COUNT(*) as cnt FROM wines_clean
WHERE produtor_extraido IS NOT NULL
GROUP BY produtor_extraido ORDER BY cnt DESC LIMIT 30;
-- Verificar manualmente: todos devem ser nomes reais de vinicolas/produtores
-- ALERTAR se aparecer: "Vinho", "Wine", "Tinto", "Chianti", "Bordeaux", artigos soltos
```

### CHECK 11 — Safras absurdas
```sql
SELECT COUNT(*) FROM wines_clean WHERE safra IS NOT NULL AND (safra < 1900 OR safra > 2026);
SELECT safra, COUNT(*) FROM wines_clean WHERE safra IS NOT NULL AND (safra < 1900 OR safra > 2026) GROUP BY safra ORDER BY COUNT(*) DESC LIMIT 10;
-- Aceitavel: < 500
```

### CHECK 12 — Nomes muito curtos ou muito longos
```sql
SELECT COUNT(*) FROM wines_clean WHERE LENGTH(nome_limpo) < 3;
SELECT COUNT(*) FROM wines_clean WHERE LENGTH(nome_limpo) > 200;
SELECT nome_limpo FROM wines_clean WHERE LENGTH(nome_limpo) < 5 LIMIT 10;
-- Curtos < 3: aceitavel < 50. Longos > 200: aceitavel < 100.
```

### CHECK 13 — Duplicatas (pais_tabela + id_original)
```sql
SELECT COUNT(*) FROM (
    SELECT pais_tabela, id_original FROM wines_clean
    GROUP BY pais_tabela, id_original HAVING COUNT(*) > 1
) sub;
-- DEVE ser ZERO
```

### CHECK 14 — Nomes mais repetidos (possiveis lixo)
```sql
SELECT nome_normalizado, COUNT(*) FROM wines_clean
GROUP BY nome_normalizado ORDER BY COUNT(*) DESC LIMIT 20;
-- Se top nomes sao so uvas ("chardonnay", "merlot") sem produtor, e um problema
```

### CHECK 15 — Amostragem visual de 50 vinhos aleatorios
```python
# Para cada vinho, mostrar:
# - nome_original vs nome_limpo (mudou?)
# - produtor_extraido (faz sentido?)
# - volume removido? HTML removido? preco removido?
cur.execute("""
    SELECT wc.pais_tabela, wc.id_original, wc.nome_original, wc.nome_limpo,
           wc.produtor_extraido, wc.safra, wc.nome_normalizado
    FROM wines_clean wc
    ORDER BY RANDOM() LIMIT 50
""")
for row in cur.fetchall():
    pais, id_orig, nome_orig, nome_limpo, produtor, safra, nome_norm = row
    changed = "MUDOU" if nome_orig != nome_limpo else "igual"
    print(f"[{pais}] {changed}")
    print(f"  ORIG:  {(nome_orig or '')[:100]}")
    print(f"  LIMPO: {(nome_limpo or '')[:100]}")
    print(f"  PROD:  {produtor or 'NULL'} | SAFRA: {safra}")
    print()
```

### CHECK 16 — Safra duplicada no nome
```sql
SELECT COUNT(*) FROM wines_clean
WHERE safra IS NOT NULL
  AND nome_limpo ~ (safra::text || '\s+' || safra::text);
-- Ex: "Reserva 2018 2018" — deve ser 0
```

### CHECK 17 — Nomes que sao APENAS uva (sem produtor, regiao, nada)
```sql
SELECT nome_limpo, COUNT(*) FROM wines_clean
WHERE LOWER(nome_limpo) IN ('chardonnay','merlot','cabernet sauvignon','pinot noir','malbec','syrah','shiraz','sauvignon blanc','riesling','tempranillo','sangiovese','grenache','carmenere','tannat','prosecco','rose','brut','reserva','crianza','tinto','blanco','red','white')
GROUP BY nome_limpo ORDER BY COUNT(*) DESC;
-- Vinhos com nome = so a uva sao inuteis pra busca. Reportar quantidade.
```

### CHECK 18 — Distribuicao de tamanho do nome
```sql
SELECT
    CASE
        WHEN LENGTH(nome_limpo) < 5 THEN '<5'
        WHEN LENGTH(nome_limpo) < 10 THEN '5-9'
        WHEN LENGTH(nome_limpo) < 20 THEN '10-19'
        WHEN LENGTH(nome_limpo) < 40 THEN '20-39'
        WHEN LENGTH(nome_limpo) < 80 THEN '40-79'
        ELSE '80+'
    END as faixa,
    COUNT(*) as qtd
FROM wines_clean GROUP BY 1 ORDER BY 1;
-- Faixa normal: 10-79 chars. Muitos <5 ou >80 = problema.
```

### CHECK 19 — Consistencia nome_limpo vs nome_normalizado
```sql
-- nome_normalizado deve ser lowercase sem acentos do nome_limpo
-- Se nome_normalizado tem caracteres especiais, falhou
SELECT COUNT(*) FROM wines_clean WHERE nome_normalizado ~ '[^a-z0-9 ]';
-- Deve ser 0
```

### CHECK 20 — Amostragem DIRECIONADA de vinhos problematicos (100 vinhos)
```python
# Pegar 20 de cada categoria problematica:
# a) 20 com nome_original contendo '&#' (HTML entities)
# b) 20 com nome_original contendo 'ml' ou 'ML' (volume)
# c) 20 com nome_original contendo '$' ou '€' (preco)
# d) 20 com produtor_extraido IS NOT NULL e LENGTH < 3 (produtor suspeito)
# e) 20 com nome_limpo = nome_original (nao mudou — verificar se devia)

for cat, query in [
    ("HTML", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original LIKE '%&#%' ORDER BY RANDOM() LIMIT 20"),
    ("VOLUME", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original ~* '\\d+\\s*ml' ORDER BY RANDOM() LIMIT 20"),
    ("PRECO", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original ~ '[$€£]' ORDER BY RANDOM() LIMIT 20"),
    ("PROD_CURTO", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE produtor_extraido IS NOT NULL AND LENGTH(produtor_extraido) < 3 ORDER BY RANDOM() LIMIT 20"),
    ("NAO_MUDOU", "SELECT nome_original, nome_limpo, produtor_extraido FROM wines_clean WHERE nome_original = nome_limpo AND nome_original LIKE '%ml%' ORDER BY RANDOM() LIMIT 20"),
]:
    print(f"\n=== {cat} ===")
    cur.execute(query)
    for row in cur.fetchall():
        orig, limpo, prod = row
        changed = "LIMPO" if orig != limpo else "IGUAL"
        print(f"  [{changed}] ORIG: {(orig or '')[:80]}")
        print(f"         LIMPO: {(limpo or '')[:80]}")
        print(f"         PROD:  {prod or 'NULL'}")
        print()
```

### CHECK 21 — Grappa e destilados que passaram pelo filtro
```sql
SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(grappa|aguardente|brandy|eau.de.vie|marc)\y';
-- Grappa e destilado de uva, pode ser aceitavel manter. Reportar quantidade.
```

### CHECK 22 — Acessorios e nao-produtos
```sql
SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(decanter|saca.?rolha|corkscrew|wine glass|taca|copa|abridor|aerador|balde|cooler|stopper|opener)\y';
-- Deve ser 0
```

## RESULTADO FINAL

Apos TODOS os 22 checks, imprima:

```
=== RESUMO DA AUDITORIA PROFUNDA ===
CHECK 1  Total:              [X vinhos | diff Y% vs original]
CHECK 2  Paises:             [N paises | faltando: lista]
CHECK 3  NULLs:              [N campos com NULL]
CHECK 4  Encoding quebrado:  [N]
CHECK 5  HTML entities:      [N] ← CRITICO
CHECK 6  Volume no nome:     [N (X%)] ← CRITICO
CHECK 7  Preco no nome:      [N (X%)] ← CRITICO
CHECK 8  Itens nao-vinho:    [N]
CHECK 9  Produtores-dominio: [N]
CHECK 10 Top produtores:     [OK/PROBLEMAS — listar]
CHECK 11 Safras absurdas:    [N]
CHECK 12 Nomes curtos/longos:[curtos N, longos N]
CHECK 13 Duplicatas:         [N]
CHECK 14 Nomes repetidos:    [OK/PROBLEMAS — listar top 5]
CHECK 15 Amostragem 50:      [N mudaram / N iguais / problemas]
CHECK 16 Safra duplicada:    [N]
CHECK 17 Nome = so uva:      [N]
CHECK 18 Distribuicao tamanho:[faixas]
CHECK 19 nome_norm limpo:    [N com chars especiais]
CHECK 20 Amostragem direcio: [HTML: N ok/N falha | VOL: N ok/N falha | PRECO: N ok/N falha]
CHECK 21 Grappa/destilados:  [N]
CHECK 22 Acessorios:         [N]

VEREDICTO: [APROVADO / REPROVADO — motivos]

Criterios de aprovacao:
- CHECK 3, 4, 13, 19: DEVE ser 0
- CHECK 5, 7, 22: DEVE ser 0
- CHECK 6: < 0.5%
- CHECK 8: < 500
- CHECK 9: 0
- CHECK 11: < 500
- CHECK 12: curtos < 50, longos < 100
- CHECK 16: 0
- CHECK 20: maioria dos problematicos deve ter sido LIMPO (nao IGUAL)
```

## O QUE NAO FAZER

- **NAO modificar nenhuma tabela** — so ler
- **NAO fazer git commit/push**
- **NAO corrigir problemas** — so reportar
