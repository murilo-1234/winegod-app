INSTRUCAO: Execute tudo diretamente. NAO pergunte se pode comecar. NAO peca confirmacao. Leia este prompt e implemente imediatamente.

# TAREFA: Classificar vinhos de lojas e salvar no banco PostgreSQL

## REGRA CRITICA — NUNCA USE API

**VOCE MESMO classifica os itens usando seu proprio conhecimento.**
- NUNCA importe openai, anthropic, google.generativeai, ou qualquer SDK de IA
- NUNCA chame APIs de LLM (openai.chat.completions, etc)
- NUNCA use requests/httpx para chamar endpoints de IA
- VOCE esta rodando no plano Plus do usuario. VOCE e a IA. VOCE classifica.
- Se voce tentar chamar qualquer API de IA, o usuario vai cancelar a tarefa.

## O QUE VOCE VAI FAZER

Voce vai processar LOTES_AQUI (1000 itens cada) de vinhos de lojas online. Para cada lote:

1. Ler o arquivo do lote (prompt + 1000 itens numerados)
2. Ler o arquivo de IDs correspondente
3. Classificar VOCE MESMO cada item (W=vinho, X=nao-vinho, S=destilado)
4. Para cada vinho (W), extrair 14 campos
5. Salvar os resultados no banco PostgreSQL local
6. Registrar o lote no log

## BANCO DE DADOS

```python
import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432, dbname="winegod_db",
    user="postgres", password="postgres123",
    options="-c client_encoding=UTF8"
)
```

## COMO CLASSIFICAR CADA ITEM

O arquivo do lote tem um prompt de classificacao no cabecalho seguido de itens numerados:
```
1. chateau montrose 2016
2. jack daniels tennessee whiskey
3. led neon sign wine
```

Para cada item, responder com UMA das opcoes:

**X** = NAO e vinho (cerveja, seltzer, cooler, sidra, agua, acessorio, caixa, gift basket, neon sign, comida, roupa, desconto, UI de site)

**S** = Destilado (whisky, gin, rum, vodka, tequila, grappa, cachaca, brandy, calvados, pisco, soju, baijiu, shochu)

**W** = Vinho (inclui espumante, champagne, cava, prosecco, cremant, pet-nat, fortificado como sherry/porto/madeira/marsala, sobremesa, icewine, sake, yakju)

Para W, extrair 14 campos:
```
W|Produtor|Vinho|Pais|Cor|Uva|Regiao|SubRegiao|Safra|ABV|Classificacao|Corpo|Harmonizacao|Docura
```

### Regras dos campos:
- **Produtor** = vinicola/bodega/domaine/chateau, minusculo, sem acento. Quem FAZ o vinho.
  - gaja (nao "gaia & rey"), michele chiarlo (nao "nivole"), felton road (nao "block 3")
- **Vinho** = nome do vinho SEM o produtor, minusculo, sem acento. NUNCA deixe ?? se o nome e derivavel do input.
  - "chateau montrose" → produtor: chateau montrose, vinho: montrose
  - "larentis malbec" → produtor: larentis, vinho: malbec
- **Pais** = 2 letras (fr, it, ar, us, au, br, ca, es, cl, pt, de, za, nz, at, hu, gr, hr, gb, jp). ?? se nao sabe
- **Cor**: r=tinto, w=branco, p=rose, s=espumante, f=fortificado, d=sobremesa
- **Uva** = uva(s) principal(is). Para blends: 2-3 principais. ?? se nao sabe
- **Regiao** = regiao vinicola (bordeaux, mendoza, etc). ?? se nao sabe
- **SubRegiao** = sub-regiao (pauillac, saint-estephe, etc). ?? se nao sabe
- **Safra** = ano. NV se sem safra. ?? se nao sabe
- **ABV** = teor alcoolico estimado (champagne ~12, bordeaux ~13.5, amarone ~15, porto ~20). ?? so se impossivel estimar
- **Classificacao** = DOC, DOCG, AOC, DO, DOCa, IGT, IGP, AVA, Grand Cru, Reserva, etc. ?? se nao tem
- **Corpo** = leve, medio, encorpado. ?? se nao sabe
- **Harmonizacao** = 1-3 pratos (carne vermelha, queijo, frutos do mar). ?? se nao sabe
- **Docura** = seco, demi-sec, doce, brut, extra brut, brut nature. ?? se nao sabe
- NAO invente dados. Se nao sabe, use ??.

### FORTIFICADOS — ATENCAO:
Sherry, porto, madeira, marsala, manzanilla = W (cor f). NAO sao destilados.
Calvados, brandy, grappa = S (destilado).

### DUPLICATAS:
Se 2 itens sao o MESMO vinho (nome escrito diferente, ou com "future arrival", "12 pack"):
- Classificar normalmente o primeiro
- No segundo, colocar =N onde N e o numero do primeiro
Mesmo produtor com uvas diferentes NAO e duplicata.

## COMO PROCESSAR CADA LOTE

Para cada lote, executar este script Python (adaptar o numero do lote):

```python
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import psycopg2
import time

DB = dict(host="localhost", port=5432, dbname="winegod_db",
          user="postgres", password="postgres123",
          options="-c client_encoding=UTF8")

def get_db():
    return psycopg2.connect(**DB)

def norm(s):
    if not s: return ""
    s = s.lower().strip()
    for o, n in [("á","a"),("à","a"),("â","a"),("ã","a"),("ä","a"),
                 ("é","e"),("è","e"),("ê","e"),("ë","e"),
                 ("í","i"),("ì","i"),("î","i"),("ï","i"),
                 ("ó","o"),("ò","o"),("ô","o"),("õ","o"),("ö","o"),
                 ("ú","u"),("ù","u"),("û","u"),("ü","u"),
                 ("ñ","n"),("ç","c")]:
        s = s.replace(o, n)
    return s.strip()

def qq(val):
    if not val or val.strip() in ("??", "?", ""):
        return None
    return val.strip()

LOTE_DIR = r"C:\winegod-app\lotes_codex"
LOTE_NUM = NUMERO_DO_LOTE  # trocar por 1, 2, 3...
IA_NAME = "codex_gpt54mini"

# 1. Ler IDs
ids_file = f"{LOTE_DIR}/lote_z_{LOTE_NUM:03d}_ids.txt"
with open(ids_file, encoding="utf-8") as f:
    clean_ids = [int(line.strip()) for line in f if line.strip()]

# 2. Ler itens do lote (pular header do prompt)
lote_file = f"{LOTE_DIR}/lote_z_{LOTE_NUM:03d}.txt"
with open(lote_file, encoding="utf-8") as f:
    content = f.read()

# Extrair so os itens numerados (ignorar prompt header)
import re
items = []
for line in content.split("\n"):
    m = re.match(r'^(\d+)\.\s+(.+)', line)
    if m:
        items.append({"num": int(m.group(1)), "nome": m.group(2).strip()})

print(f"Lote {LOTE_NUM}: {len(items)} itens, {len(clean_ids)} IDs")

# 3. AQUI O CODEX CLASSIFICA
# Classificar os itens como uma lista de strings no formato:
# "W|produtor|vinho|pais|cor|uva|regiao|subregiao|safra|abv|classif|corpo|harmon|docura"
# ou "X" ou "S" ou "=N"
#
# IMPORTANTE: VOCE MESMO faz isso. Leia cada item e classifique com seu conhecimento.
# Salve numa lista chamada `classificacoes` com 1000 strings.

classificacoes = []
# <<<< CODEX: CLASSIFIQUE TODOS OS ITENS AQUI >>>>
# Para cada item em `items`, adicionar a classificacao na lista.
# Exemplo:
#   classificacoes.append("W|chateau montrose|montrose|fr|r|cabernet sauvignon, merlot|bordeaux|saint-estephe|2016|13.5|2eme Grand Cru Classe|encorpado|carne vermelha|seco")
#   classificacoes.append("X")
#   classificacoes.append("S")
#   classificacoes.append("=3")  # duplicata do item 3

# 4. Parsear e salvar
results = []
for i, classif in enumerate(classificacoes):
    if i >= len(clean_ids):
        break
    clean_id = clean_ids[i]
    loja_nome = items[i]["nome"] if i < len(items) else ""
    
    r = {
        "clean_id": clean_id, "loja_nome": loja_nome,
        "classificacao": None, "prod_banco": None, "vinho_banco": None,
        "pais": None, "cor": None, "uva": None, "regiao": None,
        "subregiao": None, "safra": None, "abv": None, "denominacao": None,
        "corpo": None, "harmonizacao": None, "docura": None,
        "duplicata_de": None, "status": "error", "fonte_llm": IA_NAME,
    }
    
    classif = classif.strip()
    if not classif:
        continue
    
    if classif.upper() == "X":
        r["classificacao"] = "X"
        r["status"] = "not_wine"
    elif classif.upper() == "S" or classif.upper().startswith("S|"):
        r["classificacao"] = "S"
        r["status"] = "spirit"
        parts = classif.split("|")
        if len(parts) >= 3:
            r["prod_banco"] = qq(norm(parts[1]))
            r["vinho_banco"] = qq(norm(parts[2]))
        if len(parts) >= 4:
            r["pais"] = qq(parts[3].strip()[:5])
    elif classif.startswith("="):
        try:
            ref_num = int(classif[1:])
            if 1 <= ref_num <= len(clean_ids):
                r["classificacao"] = "W"
                r["duplicata_de"] = clean_ids[ref_num - 1]
                r["status"] = "duplicate"
        except ValueError:
            pass
    elif classif.upper().startswith("W|"):
        parts = classif.split("|")
        # Checar se ultimo campo e =N (duplicata)
        is_dup = False
        dup_ref = None
        if parts[-1].strip().startswith("="):
            try:
                ref_num = int(parts[-1].strip()[1:])
                if 1 <= ref_num <= len(clean_ids):
                    dup_ref = clean_ids[ref_num - 1]
                    is_dup = True
            except ValueError:
                pass
            parts = parts[:-1]
        
        r["classificacao"] = "W"
        r["prod_banco"] = qq(norm(parts[1])) if len(parts) > 1 else None
        r["vinho_banco"] = qq(norm(parts[2])) if len(parts) > 2 else None
        r["pais"] = qq(parts[3].strip()[:5]) if len(parts) > 3 else None
        r["cor"] = qq(parts[4].strip()[:1]) if len(parts) > 4 else None
        r["uva"] = qq(parts[5]) if len(parts) > 5 else None
        r["regiao"] = qq(parts[6]) if len(parts) > 6 else None
        r["subregiao"] = qq(parts[7]) if len(parts) > 7 else None
        r["safra"] = qq(parts[8]) if len(parts) > 8 else None
        r["abv"] = qq(parts[9]) if len(parts) > 9 else None
        r["denominacao"] = qq(parts[10]) if len(parts) > 10 else None
        r["corpo"] = qq(parts[11]) if len(parts) > 11 else None
        r["harmonizacao"] = qq(parts[12]) if len(parts) > 12 else None
        r["docura"] = qq(parts[13]) if len(parts) > 13 else None
        r["duplicata_de"] = dup_ref
        r["status"] = "duplicate" if is_dup else "pending_match"
    
    results.append(r)

# 5. INSERT no banco
conn = get_db()
cur = conn.cursor()
inserted = 0
for r in results:
    try:
        cur.execute("""
            INSERT INTO y2_results (
                clean_id, loja_nome, classificacao, prod_banco, vinho_banco,
                pais, cor, uva, regiao, subregiao, safra, abv, denominacao,
                corpo, harmonizacao, docura, duplicata_de, status, fonte_llm
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            ) ON CONFLICT DO NOTHING
        """, (
            r["clean_id"], r["loja_nome"], r["classificacao"],
            r["prod_banco"], r["vinho_banco"],
            r["pais"], r["cor"], r["uva"], r["regiao"], r["subregiao"],
            r["safra"], r["abv"], r["denominacao"],
            r["corpo"], r["harmonizacao"], r["docura"],
            r["duplicata_de"], r["status"], r["fonte_llm"],
        ))
        inserted += 1
    except Exception as e:
        print(f"  ERRO insert clean_id={r['clean_id']}: {e}")
        conn.rollback()
conn.commit()

# 6. Log no y2_lotes_log
cur.execute("""
    INSERT INTO y2_lotes_log (lote, ia, enviados, recebidos, faltantes, processado_em, duracao_seg, observacao)
    VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s)
""", (LOTE_NUM, IA_NAME, len(items), inserted, len(items) - inserted, 0, f"codex lote_z_{LOTE_NUM:03d}"))
conn.commit()
conn.close()

print(f"LOTE {LOTE_NUM} SALVO: {inserted}/{len(items)} itens inseridos")
```

## FLUXO COMPLETO — O QUE VOCE DEVE FAZER

Voce vai processar os lotes: LOTES_LISTA

Para CADA lote, nesta ordem:

### Passo 1: Ler o arquivo do lote
Ler `C:\winegod-app\lotes_codex\lote_z_NNN.txt` e extrair os 1000 itens numerados.

### Passo 2: Classificar TODOS os 1000 itens
Usar SEU PROPRIO conhecimento para classificar cada item. NAO chamar nenhuma API.
Gerar uma lista Python com 1000 classificacoes no formato correto.

DICA: Processar em blocos de 200 itens para nao perder o fio. Classificar itens 1-200, depois 201-400, depois 401-600, depois 601-800, depois 801-1000.

### Passo 3: Salvar no banco
Rodar o script Python acima (adaptado com o numero do lote) para fazer INSERT na y2_results e log na y2_lotes_log.

### Passo 4: Confirmar
Imprimir quantos foram inseridos e passar pro proximo lote.

### Passo 5: Repetir para o proximo lote

## IMPORTANTE — REGRAS FINAIS

1. **NUNCA USE API DE IA** — voce e a IA, voce classifica
2. **Salvar TUDO** — mesmo itens que voce nao tem certeza, classifique como conseguir
3. **Se nao sabe, use ??** — melhor ?? do que inventar
4. **fonte_llm = "codex_gpt54mini"** — sempre usar esse valor
5. **ON CONFLICT DO NOTHING** — se o clean_id ja existe no banco, pula (sem erro)
6. **Nao parar por erro** — se 1 item falhar, continuar com os outros
7. **Processar em blocos de 200** — pra nao perder contexto no meio dos 1000
