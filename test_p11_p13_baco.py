"""Teste P11/P13: chamar Baco real com contextos corretos. Arquivo temporario."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

import anthropic
from prompts.baco_system import BACO_SYSTEM_PROMPT
from tools.schemas import TOOLS
from tools.executor import execute_tool
from config import Config

client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
MAX_TOOL_ROUNDS = 5


def call_baco(user_message):
    """Chama Baco com tool loop, retorna resposta final."""
    messages = [{"role": "user", "content": user_message}]
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, temperature=0.7,
            system=BACO_SYSTEM_PROMPT, messages=messages, tools=TOOLS,
        )
        if response.stop_reason == "end_turn":
            return "".join(b.text for b in response.content if hasattr(b, 'text'))
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [tool] {block.name}({str(block.input)[:80]}...)")
                    result = execute_tool(block.name, block.input)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
            messages.append({"role": "user", "content": tool_results})
        else:
            return "".join(b.text for b in response.content if hasattr(b, 'text'))
    return "".join(b.text for b in response.content if hasattr(b, 'text'))


# ====== CASO 1: Label foto 2 ======
print("=" * 70)
print("CASO 1 - Baco: label foto 2 (Pena Vermelha R$89,99)")
print("=" * 70)
ctx1 = (
    "[O usuario enviou foto de um rotulo. OCR identificou: Pena Vermelha Reserva Santos & Seixo Wine 2021 Tejo. "
    "Preco visivel na foto: R$ 89,99. Use search_wine para buscar este vinho e responda sobre ele.]"
    "\n\nO que voce acha desse vinho?"
)
resp1 = call_baco(ctx1)
print(f"\nRESPOSTA BACO:\n{resp1}")
print(f"\n  Mencionou 89,99: {'SIM' if '89' in resp1 else 'NAO'}")
print(f"  Trocou por preco estrangeiro sem avisar: ", end="")
# Check if mentions EUR/USD/CAD without qualification
import re
foreign = re.findall(r'(?:EUR|USD|CAD|\$\d|€)', resp1)
if foreign:
    has_disclaimer = any(w in resp1.lower() for w in ['outro mercado', 'outra moeda', 'diverge', 'referencia', 'diferente'])
    print(f"{'COM AVISO (OK)' if has_disclaimer else 'SEM AVISO (FALHA)'} ({foreign})")
else:
    print("NAO (OK)")
print(f"  Disse 'garrafas'/'~N': {'FALHA' if 'garrafas' in resp1.lower() or re.search(r'~\d', resp1) else 'OK'}")

# ====== CASO 2: Shelf foto 11 ======
print("\n" + "=" * 70)
print("CASO 2 - Baco: shelf foto 11 (MontGras, total_visible=6)")
print("=" * 70)
ctx2 = (
    "[O usuario enviou foto de prateleira. "
    "Vinhos identificados: MontGras Aura Reserva Cabernet Sauvignon (preco: R$ 69,99); "
    "MontGras Aura Reserva Merlot (preco: R$ 69,99); "
    "MontGras Aura Reserva Carmenere (preco: R$ 54,99); "
    "MontGras Aura Reserva Pinot Noir (preco: R$ 54,99); "
    "Casa Silva Reserva. "
    "Use search_wine para buscar os vinhos legiveis e responda sobre eles.]"
    "\n\nMe fala desses vinhos"
)
resp2 = call_baco(ctx2)
print(f"\nRESPOSTA BACO:\n{resp2}")
has_exaggeration = bool(re.search(r'(~?\d+\s*(outras?\s*)?garrafa|vi\s+\d+|mais\s+\d+\s+garrafa|\d+\s+outras)', resp2.lower()))
print(f"\n  Exagerou contagem: {'FALHA' if has_exaggeration else 'OK'}")
print(f"  Mencionou precos da foto: {'SIM' if '69' in resp2 or '54' in resp2 else 'NAO'}")

# ====== CASO 3: Shelf foto 12 (grande) ======
print("\n" + "=" * 70)
print("CASO 3 - Baco: shelf foto 12 (prateleira grande, total_visible=10)")
print("=" * 70)
ctx3 = (
    "[O usuario enviou foto de prateleira. "
    "Vinhos identificados: BALDUZZI Grand Reserva (preco: R$ 169,99); "
    "MONTGRAS (preco: R$ 109,99); AMARAL (preco: R$ 99,99); "
    "CASTILLO de MOLINA (preco: R$ 89,99); "
    "BALDUZZI Varietal (preco: R$ 29,99); MONTGRAS Aura (preco: R$ 89,99). "
    "Use search_wine para buscar os vinhos legiveis e responda sobre eles.]"
    "\n\nO que tem de bom ai?"
)
resp3 = call_baco(ctx3)
print(f"\nRESPOSTA BACO:\n{resp3}")
has_exaggeration3 = bool(re.search(r'(~?\d+\s*(outras?\s*)?garrafa|vi\s+\d+|mais\s+\d+\s+garrafa|\d+\s+outras)', resp3.lower()))
print(f"\n  Exagerou contagem: {'FALHA' if has_exaggeration3 else 'OK'}")
print(f"  Inventou vinhos nao listados: ", end="")
# Simple heuristic - check for wine names NOT in context
known = ['balduzzi', 'montgras', 'amaral', 'castillo', 'molina']
mentioned_wines = [w for w in re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', resp3) if len(w) > 5]
print("verificar manualmente")

# ====== CASO 4: Shelf foto 15 com preco ======
print("\n" + "=" * 70)
print("CASO 4 - Baco: shelf foto 15 (Perez Cruz R$144 + Dominga R$69)")
print("=" * 70)
ctx4 = (
    "[O usuario enviou foto de prateleira. "
    "Vinhos identificados: Perez Cruz Limited Edition Cabernet Franc (preco: R$ 144,99); "
    "Dona Dominga Reserva (preco: R$ 69,99). "
    "Use search_wine para buscar os vinhos legiveis e responda sobre eles.]"
    "\n\nQual desses vale mais a pena?"
)
resp4 = call_baco(ctx4)
print(f"\nRESPOSTA BACO:\n{resp4}")
print(f"\n  Mencionou R$144: {'SIM' if '144' in resp4 else 'NAO'}")
print(f"  Mencionou R$69: {'SIM' if '69' in resp4 else 'NAO'}")
foreign4 = re.findall(r'(?:EUR|USD|CAD|\$\d|€)', resp4)
if foreign4:
    has_disclaimer4 = any(w in resp4.lower() for w in ['outro mercado', 'outra moeda', 'diverge', 'referencia', 'diferente', 'foto'])
    print(f"  Preco estrangeiro: {'COM AVISO (OK)' if has_disclaimer4 else 'SEM AVISO (FALHA)'}")
else:
    print(f"  Preco estrangeiro: NAO APARECEU (OK)")

print("\n" + "=" * 70)
print("FIM DOS TESTES BACO")
print("=" * 70)
