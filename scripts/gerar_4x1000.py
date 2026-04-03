"""Regera os 4 lotes que falharam como 2000, agora divididos em 4x1000.
Usa os mesmos itens dos lote_2000_1 a lote_2000_4 (8000 itens no total).
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Ler os nomes dos 4 lotes originais de 2000
all_items = []
for i in range(1, 5):
    fname = f"C:/winegod-app/scripts/lotes_llm/lote_2000_{i}_nomes.txt"
    with open(fname, encoding="utf-8") as f:
        items = [l.strip() for l in f if l.strip()]
        all_items.extend(items)
        print(f"Lote 2000_{i}: {len(items)} itens")

print(f"Total: {len(all_items)} itens")

# Dividir em 8 lotes de 1000
lotes = []
for i in range(8):
    start = i * 1000
    end = start + 1000
    lote = all_items[start:end]
    lotes.append(lote)

# Ler header do prompt B v2
with open("C:/winegod-app/scripts/lotes_llm/prompt_B_v2.txt", encoding="utf-8") as f:
    header = f.read()

# Salvar os 8 lotes
for i, lote in enumerate(lotes, 1):
    fname = f"lote_1000_{i}.txt"
    with open(f"C:/winegod-app/scripts/lotes_llm/{fname}", "w", encoding="utf-8") as f:
        f.write(header)
        for j, nome in enumerate(lote, 1):
            f.write(f"{j}. {nome}\n")

    nfname = f"lote_1000_{i}_nomes.txt"
    with open(f"C:/winegod-app/scripts/lotes_llm/{nfname}", "w", encoding="utf-8") as f:
        for nome in lote:
            f.write(f"{nome}\n")

    print(f"\nLote {i} ({len(lote)} itens):")
    print(f"  Primeiro: {lote[0][:60]}")
    print(f"  Ultimo:   {lote[-1][:60]}")
    print(f"  Arquivo:  C:\\winegod-app\\scripts\\lotes_llm\\{fname}")

print(f"\n=== {len(lotes)} lotes de 1000 criados ===")
print("Done!")
