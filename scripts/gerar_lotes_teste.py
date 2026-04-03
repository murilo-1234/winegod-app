"""Gera 2 lotes da wines_clean que NAO foram processados pelo Gemini.
Ordem alfabetica. Dados crus, sem filtro.
Lote 1: 1000 | Lote 2: 2000 (sequenciais, sem overlap)
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432, dbname="winegod_db",
    user="postgres", password="postgres123",
    options="-c client_encoding=UTF8"
)
cur = conn.cursor()

# Pegar os primeiros 3000 nao processados, em ordem alfabetica
print("Puxando 3000 itens nao processados pelo Gemini, ordem alfabetica...")
cur.execute("""
    SELECT wc.nome_original
    FROM wines_clean wc
    LEFT JOIN y2_results y ON y.clean_id = wc.id
    WHERE y.id IS NULL
      AND wc.nome_original IS NOT NULL
      AND LENGTH(TRIM(wc.nome_original)) > 3
    ORDER BY LOWER(wc.nome_original) ASC
    LIMIT 3000
""")
rows = cur.fetchall()
print(f"  Puxados: {len(rows)}")

lote1 = [r[0].strip().lower() for r in rows[:1000]]
lote2 = [r[0].strip().lower() for r in rows[1000:3000]]

print(f"  Lote 1: {len(lote1)} (de '{lote1[0][:40]}' ate '{lote1[-1][:40]}')")
print(f"  Lote 2: {len(lote2)} (de '{lote2[0][:40]}' ate '{lote2[-1][:40]}')")

# Ler header do prompt B final
with open("C:/winegod-app/scripts/lotes_llm/prompt_B_final.txt", encoding="utf-8") as f:
    full = f.read()
header_end = full.find("1. lowenbrau sng")
header = full[:header_end] if header_end > 0 else full

# Salvar lotes com prompt
for nome_arq, lote in [("lote_1000.txt", lote1), ("lote_2000.txt", lote2)]:
    with open(f"C:/winegod-app/scripts/lotes_llm/{nome_arq}", "w", encoding="utf-8") as f:
        f.write(header)
        for i, nome in enumerate(lote, 1):
            f.write(f"{i}. {nome}\n")
    print(f"  Salvo: {nome_arq}")

# Nomes pra referencia futura
for nome_arq, lote in [("lote_1000_nomes.txt", lote1), ("lote_2000_nomes.txt", lote2)]:
    with open(f"C:/winegod-app/scripts/lotes_llm/{nome_arq}", "w", encoding="utf-8") as f:
        for nome in lote:
            f.write(f"{nome}\n")

print(f"\nLote 1 — primeiros 10:")
for i, x in enumerate(lote1[:10], 1): print(f"  {i}. {x}")
print(f"\nLote 1 — ultimos 5:")
for i, x in enumerate(lote1[-5:], 996): print(f"  {i}. {x}")

print(f"\nLote 2 — primeiros 10:")
for i, x in enumerate(lote2[:10], 1): print(f"  {i}. {x}")
print(f"\nLote 2 — ultimos 5:")
for i, x in enumerate(lote2[-5:], 1996): print(f"  {i}. {x}")

conn.close()
print("\nDone!")
