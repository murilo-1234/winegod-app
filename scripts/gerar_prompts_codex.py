"""
Gera prompts individuais para cada janela do Codex.
Cada janela processa 5 lotes sequenciais.

Uso:
  python scripts/gerar_prompts_codex.py [num_janelas]
  python scripts/gerar_prompts_codex.py 4       # 4 janelas, lotes 1-5, 6-10, 11-15, 16-20

Gera:
  prompts/PROMPT_CODEX_JANELA_1.md  (lotes z_001 a z_005)
  prompts/PROMPT_CODEX_JANELA_2.md  (lotes z_006 a z_010)
  ...
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

NUM_JANELAS = int(sys.argv[1]) if len(sys.argv) > 1 else 4
LOTES_POR_JANELA = 5

PROMPT_DIR = r"C:\winegod-app\prompts"
LOTE_DIR = r"C:\winegod-app\lotes_codex"
TEMPLATE_FILE = os.path.join(PROMPT_DIR, "PROMPT_CODEX_WINE_CLASSIFIER.md")

# Verificar quantos lotes existem
lotes_existentes = sorted([f for f in os.listdir(LOTE_DIR) if f.startswith("lote_z_") and f.endswith(".txt") and "_ids" not in f])
total_lotes = len(lotes_existentes)
print(f"Lotes existentes: {total_lotes}")

if total_lotes == 0:
    print("ERRO: Nenhum lote encontrado. Rode gerar_lotes_codex.py primeiro.")
    sys.exit(1)

max_janelas = (total_lotes + LOTES_POR_JANELA - 1) // LOTES_POR_JANELA
if NUM_JANELAS > max_janelas:
    print(f"Ajustando: so da pra {max_janelas} janelas (nao {NUM_JANELAS})")
    NUM_JANELAS = max_janelas

# Ler template
with open(TEMPLATE_FILE, encoding="utf-8") as f:
    template = f.read()

for janela in range(1, NUM_JANELAS + 1):
    start_lote = (janela - 1) * LOTES_POR_JANELA + 1
    end_lote = min(start_lote + LOTES_POR_JANELA - 1, total_lotes)
    lotes_lista = list(range(start_lote, end_lote + 1))
    lotes_str = ", ".join([str(l) for l in lotes_lista])
    lotes_desc = f"lote_z_{start_lote:03d} ate lote_z_{end_lote:03d}"

    # Substituir placeholders
    prompt = template.replace("LOTES_AQUI", f"{len(lotes_lista)} lotes")
    prompt = template.replace("LOTES_AQUI", f"{len(lotes_lista)} lotes")
    prompt = prompt.replace("LOTES_LISTA", lotes_str)
    prompt = prompt.replace("NUMERO_DO_LOTE", str(lotes_lista[0]))  # primeiro lote como exemplo

    # Adicionar instrucao clara de quais lotes processar
    header = f"""# JANELA {janela} — Processar {lotes_desc}

Voce deve processar estes lotes em sequencia: **{lotes_str}**

Para cada lote, trocar LOTE_NUM no script pelo numero correto ({', '.join([str(l) for l in lotes_lista])}).

Ordem: comecar pelo lote {lotes_lista[0]}, depois {', '.join([str(l) for l in lotes_lista[1:]])}.

---

"""
    final_prompt = header + prompt

    # Salvar
    out_file = os.path.join(PROMPT_DIR, f"PROMPT_CODEX_JANELA_{janela}.md")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(final_prompt)
    print(f"  Janela {janela}: lotes {lotes_str} -> {out_file}")

# Gerar comandos prontos pra copiar e colar
print(f"\n{'='*60}")
print("COMANDOS PARA O TERMINAL (copiar e colar):")
print(f"{'='*60}\n")

for janela in range(1, NUM_JANELAS + 1):
    start_lote = (janela - 1) * LOTES_POR_JANELA + 1
    end_lote = min(start_lote + LOTES_POR_JANELA - 1, total_lotes)
    print(f"**Janela {janela} (lotes {start_lote}-{end_lote}):**")
    print(f'cd C:\\winegod-app && codex -p "$(cat prompts/PROMPT_CODEX_JANELA_{janela}.md)"')
    print()

print(f"Total: {NUM_JANELAS} janelas x {LOTES_POR_JANELA} lotes = {NUM_JANELAS * LOTES_POR_JANELA} lotes = {NUM_JANELAS * LOTES_POR_JANELA * 1000} itens")
