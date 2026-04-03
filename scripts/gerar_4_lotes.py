"""Gera 4 lotes de 2000 itens cada, continuando de onde o lote anterior parou.
O lote_2000.txt anterior terminou em "terre de marne" 2023.
Pega os proximos 8000 itens em ordem alfabetica, sem overlap.
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

# Descobrir o ultimo item do lote_2000.txt
# Lendo o arquivo pra pegar o ultimo nome
with open("C:/winegod-app/scripts/lotes_llm/lote_2000_nomes.txt", encoding="utf-8") as f:
    lines = [l.strip() for l in f if l.strip()]
    ultimo = lines[-1]
print(f"Ultimo item do lote anterior: '{ultimo}'")

# Pegar os proximos 8000 itens nao processados pelo Gemini,
# que venham DEPOIS do ultimo item em ordem alfabetica
print(f"\nPuxando 8000 itens apos '{ultimo[:40]}...'")
cur.execute("""
    SELECT wc.nome_original
    FROM wines_clean wc
    LEFT JOIN y2_results y ON y.clean_id = wc.id
    WHERE y.id IS NULL
      AND wc.nome_original IS NOT NULL
      AND LENGTH(TRIM(wc.nome_original)) > 3
      AND LOWER(wc.nome_original) > %s
    ORDER BY LOWER(wc.nome_original) ASC
    LIMIT 8000
""", (ultimo,))
rows = cur.fetchall()
print(f"  Puxados: {len(rows)}")

items = [r[0].strip().lower() for r in rows]

# Dividir em 4 lotes de 2000
lotes = []
for i in range(4):
    start = i * 2000
    end = start + 2000
    lote = items[start:end]
    lotes.append(lote)
    print(f"  Lote {i+1}: {len(lote)} itens ('{lote[0][:40]}' ate '{lote[-1][:40]}')")

# Ler header do prompt B v2
with open("C:/winegod-app/scripts/lotes_llm/prompt_B_v2.txt", encoding="utf-8") as f:
    header = f.read()

# Salvar os 4 lotes
for i, lote in enumerate(lotes, 1):
    fname = f"lote_2000_{i}.txt"
    with open(f"C:/winegod-app/scripts/lotes_llm/{fname}", "w", encoding="utf-8") as f:
        f.write(header)
        for j, nome in enumerate(lote, 1):
            f.write(f"{j}. {nome}\n")
    print(f"  Salvo: {fname}")

    # Nomes pra referencia
    nfname = f"lote_2000_{i}_nomes.txt"
    with open(f"C:/winegod-app/scripts/lotes_llm/{nfname}", "w", encoding="utf-8") as f:
        for nome in lote:
            f.write(f"{nome}\n")

# Resumo
print(f"\n=== RESUMO ===")
print(f"Total: {len(items)} itens em 4 lotes")
for i, lote in enumerate(lotes, 1):
    print(f"\nLote {i} ({len(lote)} itens):")
    print(f"  Primeiro: {lote[0]}")
    print(f"  Ultimo:   {lote[-1]}")
    print(f"  Arquivo:  C:\\winegod-app\\scripts\\lotes_llm\\lote_2000_{i}.txt")

conn.close()
print("\nDone!")
