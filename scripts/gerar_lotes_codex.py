"""
Gera lotes de 1000 itens da wines_clean em ordem Z->A (reversa).
Exclui itens ja processados (presentes na y2_results).
Cada lote gera 2 arquivos:
  - lote_z_NNN.txt       (prompt B v2 + 1000 itens numerados)
  - lote_z_NNN_ids.txt   (1000 clean_ids na mesma ordem)

Uso:
  python scripts/gerar_lotes_codex.py [total_lotes]
  python scripts/gerar_lotes_codex.py 50       # gera 50 lotes (50K itens)
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import psycopg2

TOTAL_LOTES = int(sys.argv[1]) if len(sys.argv) > 1 else 20
BATCH_SIZE = 1000

DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "winegod_db"
DB_USER = "postgres"
DB_PASS = "postgres123"

PROMPT_FILE = r"C:\winegod-app\scripts\lotes_llm\prompt_B_v2.txt"
OUTPUT_DIR = r"C:\winegod-app\lotes_codex"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Ler prompt header
with open(PROMPT_FILE, encoding="utf-8") as f:
    prompt_header = f.read().strip() + "\n\n"

# Conectar ao banco
conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
    user=DB_USER, password=DB_PASS,
    options="-c client_encoding=UTF8"
)
cur = conn.cursor()

total_needed = TOTAL_LOTES * BATCH_SIZE
print(f"Buscando {total_needed} itens nao processados, ordem Z->A...")

cur.execute("""
    SELECT wc.id, wc.nome_normalizado
    FROM wines_clean wc
    LEFT JOIN y2_results yr ON yr.clean_id = wc.id
    WHERE yr.id IS NULL
      AND wc.nome_normalizado IS NOT NULL
      AND LENGTH(TRIM(wc.nome_normalizado)) > 3
      AND LOWER(LEFT(wc.nome_normalizado, 1)) != 'c'
    ORDER BY LOWER(wc.nome_normalizado) DESC
    LIMIT %s
""", (total_needed,))
rows = cur.fetchall()
conn.close()

print(f"  Encontrados: {len(rows)}")
if len(rows) == 0:
    print("Nenhum item pendente!")
    sys.exit(0)

actual_lotes = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
if actual_lotes < TOTAL_LOTES:
    print(f"  Ajustando: so da pra gerar {actual_lotes} lotes (nao {TOTAL_LOTES})")
    TOTAL_LOTES = actual_lotes

for lote_idx in range(TOTAL_LOTES):
    start = lote_idx * BATCH_SIZE
    end = min(start + BATCH_SIZE, len(rows))
    batch = rows[start:end]

    lote_num = lote_idx + 1
    lote_name = f"lote_z_{lote_num:03d}"

    # Arquivo com prompt + itens numerados
    prompt_path = os.path.join(OUTPUT_DIR, f"{lote_name}.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt_header)
        for i, (clean_id, nome) in enumerate(batch, 1):
            nome_limpo = (nome or "").strip().lower()
            f.write(f"{i}. {nome_limpo}\n")

    # Arquivo com clean_ids (mesma ordem)
    ids_path = os.path.join(OUTPUT_DIR, f"{lote_name}_ids.txt")
    with open(ids_path, "w", encoding="utf-8") as f:
        for clean_id, nome in batch:
            f.write(f"{clean_id}\n")

    first = (batch[0][1] or "")[:50]
    last = (batch[-1][1] or "")[:50]
    print(f"  {lote_name}: {len(batch)} itens | '{first}' -> '{last}'")

print(f"\nTotal: {TOTAL_LOTES} lotes gerados em {OUTPUT_DIR}")
print(f"Itens: {min(TOTAL_LOTES * BATCH_SIZE, len(rows))}")
