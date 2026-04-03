"""Deep audit of wines_clean — extended checks"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import psycopg2
import re

conn = psycopg2.connect("postgresql://postgres:postgres123@localhost:5432/winegod_db")
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM wines_clean")
total_clean = cur.fetchone()[0]

print("=" * 70)
print("  AUDITORIA PROFUNDA — wines_clean")
print(f"  Total: {total_clean:,} registros")
print("=" * 70)

# ── 1. ITENS NAO-VINHO ──
print("\n" + "=" * 70)
print("  1. ITENS NAO-VINHO")
print("=" * 70)

categorias = {
    "whisky/whiskey/bourbon/scotch": [
        "whisky", "whiskey", "bourbon", "scotch", "single malt",
    ],
    "beer/cerveja": [
        "beer", "cerveja", "lager", "pale ale", "ipa ", " ipa",
        "stout", "pilsner", "craft beer",
    ],
    "gin": [
        " gin ", "gin %", "% gin",
        "london dry gin", "dry gin",
    ],
    "vodka": [
        "vodka",
    ],
    "rum/cachaça": [
        " rum ", "rum %", "% rum",
        "cachaca", "cachaça",
    ],
    "tequila/mezcal": [
        "tequila", "mezcal", "mescal",
    ],
    "licor/liqueur": [
        "licor ", "liqueur", "limoncello", "amaretto", "baileys",
        "kahlua", "cointreau", "triple sec", "absinth",
    ],
    "queijo/cheese": [
        "queijo", "cheese", "fromage", "queso", "formaggio",
        "parmigian", "cheddar", "brie ", "camembert", "gouda",
        "roquefort", "gruyere", "manchego",
    ],
    "chocolate/doce": [
        "chocolate", "bonbon", "truffle candy", "praline",
    ],
    "nao-bebida (misc)": [
        "bear ", "teddy", "pelucia", "pelúcia", "keeleco",
        "candle", "vela ", "soap", "sabonete",
        "t-shirt", "camiseta", "gift card", "voucher", "gutschein",
        "glass set", "corkscrew", "saca-rolha", "decanter",
        "body spray", "perfume",
    ],
    "refrigerante/juice": [
        "coca-cola", "pepsi", "fanta", "sprite",
        "red bull", "monster energy", "suco ", "juice box",
    ],
}

total_nao_vinho = 0
detalhes_nao_vinho = {}

for cat, termos in categorias.items():
    likes = " OR ".join([f"LOWER(nome_limpo) LIKE '%{t.strip()}%'" for t in termos])
    query = f"SELECT COUNT(*) FROM wines_clean WHERE {likes}"
    cur.execute(query)
    cnt = cur.fetchone()[0]
    if cnt > 0:
        detalhes_nao_vinho[cat] = cnt
        total_nao_vinho += cnt
        # Pegar exemplos
        query_ex = f"SELECT nome_limpo FROM wines_clean WHERE {likes} ORDER BY RANDOM() LIMIT 5"
        cur.execute(query_ex)
        exemplos = [r[0] for r in cur.fetchall()]
        print(f"\n  {cat}: {cnt:,}")
        for ex in exemplos:
            print(f"    - {ex[:90]}")

print(f"\n  TOTAL ITENS SUSPEITOS: {total_nao_vinho:,} ({total_nao_vinho/total_clean*100:.2f}%)")

# ── 2. HTML ENTITIES ──
print("\n" + "=" * 70)
print("  2. HTML ENTITIES no banco inteiro")
print("=" * 70)

entities = {
    "&#8211; (en-dash)":  "&#8211;",
    "&#8212; (em-dash)":  "&#8212;",
    "&#8216; (left sq)":  "&#8216;",
    "&#8217; (right sq)": "&#8217;",
    "&#8220; (left dq)":  "&#8220;",
    "&#8221; (right dq)": "&#8221;",
    "&#39; (apostrophe)": "&#39;",
    "&amp; (ampersand)":  "&amp;",
    "&eacute;":           "&eacute;",
    "&egrave;":           "&egrave;",
    "&oacute;":           "&oacute;",
    "&uuml;":             "&uuml;",
    "&ouml;":             "&ouml;",
    "&auml;":             "&auml;",
    "&ntilde;":           "&ntilde;",
    "&nbsp;":             "&nbsp;",
    "&#NNN; (generico)":  "&#",
    "&XXXX; (generico)":  "&",
}

total_html = 0
for label, entity in entities.items():
    if label == "&#NNN; (generico)":
        cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~ '&#[0-9]+;'")
    elif label == "&XXXX; (generico)":
        cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~ '&[a-zA-Z]+;'")
    else:
        cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE %s", (f"%{entity}%",))
    cnt = cur.fetchone()[0]
    if cnt > 0:
        print(f"  {label}: {cnt:,}")
        if label not in ("&#NNN; (generico)", "&XXXX; (generico)"):
            total_html += cnt

# Total unico (vinhos com QUALQUER entity)
cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~ '&#[0-9]+;' OR nome_limpo ~ '&[a-zA-Z]+;'")
total_com_entity = cur.fetchone()[0]
print(f"\n  TOTAL vinhos com alguma HTML entity: {total_com_entity:,} ({total_com_entity/total_clean*100:.2f}%)")

# ── 3. TOP 50 PRODUTORES ──
print("\n" + "=" * 70)
print("  3. TOP 50 PRODUTORES MAIS FREQUENTES")
print("=" * 70)

cur.execute("""
    SELECT produtor_extraido, COUNT(*) as cnt
    FROM wines_clean
    WHERE produtor_extraido IS NOT NULL AND produtor_extraido != ''
    GROUP BY produtor_extraido
    ORDER BY cnt DESC
    LIMIT 50
""")
produtores = cur.fetchall()
for i, (prod, cnt) in enumerate(produtores, 1):
    print(f"  {i:2d}. {prod[:60]:<60s} {cnt:>7,}")

# ── 4. TOP 20 NOMES MAIS REPETIDOS ──
print("\n" + "=" * 70)
print("  4. TOP 20 NOMES (nome_limpo) MAIS REPETIDOS")
print("=" * 70)

cur.execute("""
    SELECT nome_limpo, COUNT(*) as cnt
    FROM wines_clean
    GROUP BY nome_limpo
    ORDER BY cnt DESC
    LIMIT 20
""")
nomes = cur.fetchall()
for i, (nome, cnt) in enumerate(nomes, 1):
    print(f"  {i:2d}. {nome[:70]:<70s} {cnt:>6,}")

# ── 5. AMOSTRAGEM 1000 VINHOS ──
print("\n" + "=" * 70)
print("  5. AMOSTRAGEM — 1000 vinhos aleatorios")
print("=" * 70)

cur.execute("""
    SELECT pais_tabela, id_original, nome_original, nome_limpo,
           produtor_extraido, safra, nome_normalizado, hash_dedup
    FROM wines_clean
    ORDER BY RANDOM()
    LIMIT 1000
""")
amostras = cur.fetchall()

problemas_amostra = {
    "html_entity": [],
    "nao_vinho": [],
    "nome_igual_original": 0,
    "sem_produtor": 0,
    "sem_safra": 0,
    "sem_normalizado": 0,
    "nome_muito_curto": [],
    "volume_no_nome": [],
    "preco_no_nome": [],
}

nao_vinho_keywords = [
    "whisky", "whiskey", "bourbon", "scotch", "beer", "cerveja",
    "vodka", "gin ", " gin", "tequila", "mezcal", "rum ",
    "queijo", "cheese", "chocolate", "pelucia", "teddy", "candle",
    "coca-cola", "pepsi", "red bull", "body spray", "gutschein",
    "gift card", "voucher", "t-shirt", "corkscrew",
]

for a in amostras:
    pais, id_orig, nome_orig, nome_limpo, produtor, safra, normalizado, hash_d = a
    nl = (nome_limpo or "").lower()

    # HTML entities
    if "&#" in (nome_limpo or "") or re.search(r"&[a-zA-Z]+;", nome_limpo or ""):
        problemas_amostra["html_entity"].append(nome_limpo)

    # Nao-vinho
    for kw in nao_vinho_keywords:
        if kw in nl:
            problemas_amostra["nao_vinho"].append(nome_limpo)
            break

    # Nome igual ao original (sem limpeza)
    if nome_limpo and nome_orig and nome_limpo.strip() == (nome_orig or "").strip():
        problemas_amostra["nome_igual_original"] += 1

    # Sem produtor
    if not produtor:
        problemas_amostra["sem_produtor"] += 1

    # Sem safra
    if safra is None:
        problemas_amostra["sem_safra"] += 1

    # Sem normalizado
    if not normalizado:
        problemas_amostra["sem_normalizado"] += 1

    # Nome muito curto
    if nome_limpo and len(nome_limpo) < 5:
        problemas_amostra["nome_muito_curto"].append(nome_limpo)

    # Volume no nome (750ml, 1.75L etc.)
    if re.search(r"\d+\s*(ml|cl|l\b|liter|litre)", nl):
        problemas_amostra["volume_no_nome"].append(nome_limpo)

    # Preco no nome ($, €, R$)
    if re.search(r"[\$€£]|r\$", nl):
        problemas_amostra["preco_no_nome"].append(nome_limpo)

print(f"  Amostra: 1000 vinhos")
print(f"  Nome igual ao original (sem limpeza aparente): {problemas_amostra['nome_igual_original']}")
print(f"  Sem produtor: {problemas_amostra['sem_produtor']}")
print(f"  Sem safra: {problemas_amostra['sem_safra']}")
print(f"  Sem nome_normalizado: {problemas_amostra['sem_normalizado']}")
print(f"  Com HTML entity: {len(problemas_amostra['html_entity'])}")
print(f"  Suspeita nao-vinho: {len(problemas_amostra['nao_vinho'])}")
print(f"  Nome <5 chars: {len(problemas_amostra['nome_muito_curto'])}")
print(f"  Volume no nome (750ml etc): {len(problemas_amostra['volume_no_nome'])}")
print(f"  Preco no nome ($, €): {len(problemas_amostra['preco_no_nome'])}")

if problemas_amostra["html_entity"]:
    print(f"\n  Exemplos com HTML entity:")
    for ex in problemas_amostra["html_entity"][:10]:
        print(f"    - {(ex or '')[:90]}")

if problemas_amostra["nao_vinho"]:
    print(f"\n  Exemplos nao-vinho:")
    for ex in problemas_amostra["nao_vinho"][:10]:
        print(f"    - {(ex or '')[:90]}")

if problemas_amostra["volume_no_nome"]:
    print(f"\n  Exemplos com volume no nome:")
    for ex in problemas_amostra["volume_no_nome"][:10]:
        print(f"    - {(ex or '')[:90]}")

if problemas_amostra["preco_no_nome"]:
    print(f"\n  Exemplos com preco no nome:")
    for ex in problemas_amostra["preco_no_nome"][:10]:
        print(f"    - {(ex or '')[:90]}")

# ── 6. CONTAGEM EXATA: volume no nome no banco inteiro ──
print("\n" + "=" * 70)
print("  6. CHECKS ADICIONAIS (banco inteiro)")
print("=" * 70)

cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~ '\\d+\\s*(ml|cl|ML|CL)' OR LOWER(nome_limpo) ~ '\\d+(\\.\\d+)?\\s*l\\b'")
vol_total = cur.fetchone()[0]
print(f"  Volume no nome (ml/cl/L): {vol_total:,} ({vol_total/total_clean*100:.2f}%)")

cur.execute("SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~ '[\\$€£]|[Rr]\\$'")
preco_total = cur.fetchone()[0]
print(f"  Preco no nome ($€£R$): {preco_total:,} ({preco_total/total_clean*100:.2f}%)")

# Nomes identicos ao original (inteiro)
cur.execute("SELECT COUNT(*) FROM wines_clean WHERE TRIM(nome_limpo) = TRIM(nome_original)")
igual_total = cur.fetchone()[0]
print(f"  Nome limpo = original (sem limpeza): {igual_total:,} ({igual_total/total_clean*100:.2f}%)")

# ── RESUMO FINAL ──
print("\n" + "=" * 70)
print("  RESUMO DA AUDITORIA PROFUNDA")
print("=" * 70)
print(f"  Total wines_clean:         {total_clean:,}")
print(f"  Itens suspeitos nao-vinho: {total_nao_vinho:,} ({total_nao_vinho/total_clean*100:.2f}%)")
print(f"  HTML entities:             {total_com_entity:,} ({total_com_entity/total_clean*100:.2f}%)")
print(f"  Volume no nome:            {vol_total:,} ({vol_total/total_clean*100:.2f}%)")
print(f"  Preco no nome:             {preco_total:,} ({preco_total/total_clean*100:.2f}%)")
print(f"  Nome sem limpeza:          {igual_total:,} ({igual_total/total_clean*100:.2f}%)")
print()

conn.close()
print("Auditoria profunda concluida.")
