"""
Teste de classificacao de vinhos com Gemini Flash.
Roda 5000 itens em 2 formatos e compara resultados.

Uso: python scripts/teste_llm_classificacao.py SUA_GEMINI_API_KEY
"""

import csv
import json
import sys
import time
import os
import google.generativeai as genai

# === CONFIG ===
CSV_PATH = os.path.join(os.path.dirname(__file__), "teste_5000.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "teste_llm_resultados")
BATCH_SIZE = 150
MODEL_NAME = "gemini-2.5-flash-lite"

# === PROMPTS ===

PROMPT_FORMATO_A = """TAREFA: Classifique cada item e extraia dados de vinho.

REGRAS:
- X = nao e vinho (comida, objeto, cosmetico, cerveja, etc)
- S = destilado ou spirit (whisky, gin, rum, vodka, cognac, etc)
- W = vinho. Formato: W|Produtor|Nome do Vinho|Pais (2 letras)|Cor (r/w/p/s/f/d)
  - Produtor = nome EXATO da vinicola/bodega/chateau/weingut
  - Nome do Vinho = nome do vinho SEM o produtor
  - Cor: r=tinto, w=branco, p=rose, s=espumante, f=fortificado, d=sobremesa
  - Se nao sabe o pais, use ??
- Se o item e DUPLICATA de outro no lote (mesmo vinho, safra ou formato diferente): adicione =N (N = numero do primeiro do grupo)
- NAO invente dados. Se nao consegue identificar o produtor, use ?? como produtor.

ITEMS:
"""

PROMPT_FORMATO_B = """TAREFA: Classifique cada item e extraia dados de vinho COM verificacao Vivino.

REGRAS:
- X = nao e vinho (comida, objeto, cosmetico, cerveja, etc)
- S = destilado ou spirit (whisky, gin, rum, vodka, cognac, etc)
- W = vinho. Formato: W|Produtor|Nome do Vinho|Pais (2 letras)|Cor|V ou N|Regiao
  - Produtor = nome EXATO da vinicola/bodega/chateau/weingut
  - Nome do Vinho = nome do vinho SEM o produtor
  - Cor: r=tinto, w=branco, p=rose, s=espumante, f=fortificado, d=sobremesa
  - V = voce tem CERTEZA que este vinho existe no Vivino. Informe a REGIAO EXATA como aparece no Vivino (ex: Champagne, Barossa Valley, Ribera del Duero, Napa Valley)
  - N = NAO esta no Vivino, ou voce NAO tem certeza. Nao informe regiao.
  - Se nao sabe a regiao exata do Vivino, responda N — NAO invente
  - Se nao sabe o pais, use ??
- Se o item e DUPLICATA de outro no lote (mesmo vinho, safra ou formato diferente): adicione =N (N = numero do primeiro do grupo)
- NAO invente dados. Se nao consegue identificar o produtor, use ?? como produtor.

ITEMS:
"""


def load_items(csv_path):
    """Carrega itens do CSV."""
    items = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append(row)
    return items


def make_batches(items, batch_size):
    """Divide itens em lotes."""
    batches = []
    for i in range(0, len(items), batch_size):
        batches.append(items[i : i + batch_size])
    return batches


def format_batch(batch, start_num=1):
    """Formata um lote de itens numerados."""
    lines = []
    for i, item in enumerate(batch):
        lines.append(f"{start_num + i}. {item['loja_nome']}")
    return "\n".join(lines)


def call_gemini(model, prompt, items_text, batch_num, formato):
    """Chama o Gemini e retorna a resposta."""
    full_prompt = prompt + items_text
    try:
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=8192,
            ),
        )
        return response.text
    except Exception as e:
        print(f"  ERRO lote {batch_num} formato {formato}: {e}")
        return f"ERRO: {e}"


def parse_response(response_text, batch, start_num):
    """Parseia resposta do LLM e associa aos itens originais."""
    results = []
    lines = response_text.strip().split("\n")
    line_map = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Extrair numero do inicio
        parts = line.split(".", 1)
        if len(parts) == 2 and parts[0].strip().isdigit():
            num = int(parts[0].strip())
            content = parts[1].strip()
            line_map[num] = content

    for i, item in enumerate(batch):
        num = start_num + i
        llm_response = line_map.get(num, "MISSING")
        results.append(
            {
                "num": num,
                "clean_id": item["clean_id"],
                "loja_nome": item["loja_nome"],
                "destino_atual": item["destino"],
                "score_atual": item["score"],
                "wl": item["wine_likeness"],
                "vivino_id_atual": item["vid"],
                "vivino_nome_atual": item["vnome"],
                "llm": llm_response,
            }
        )
    return results


def run_test(api_key, formato, prompt, items, output_path, max_batches=None):
    """Roda o teste completo pra um formato."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_NAME)

    batches = make_batches(items, BATCH_SIZE)
    if max_batches:
        batches = batches[:max_batches]

    all_results = []
    total_input_tokens = 0
    total_output_tokens = 0
    start_num = 1

    print(f"\n{'='*60}")
    print(f"FORMATO {formato}: {len(batches)} lotes de {BATCH_SIZE}")
    print(f"{'='*60}")

    for i, batch in enumerate(batches):
        items_text = format_batch(batch, start_num)
        full_prompt = prompt + items_text

        # Estimar tokens
        input_tokens = len(full_prompt) // 4
        total_input_tokens += input_tokens

        print(f"  Lote {i+1}/{len(batches)} (itens {start_num}-{start_num+len(batch)-1})...", end=" ", flush=True)

        response_text = call_gemini(model, prompt, items_text, i + 1, formato)
        output_tokens = len(response_text) // 4
        total_output_tokens += output_tokens

        results = parse_response(response_text, batch, start_num)
        all_results.extend(results)

        # Contar classificacoes
        wines = sum(1 for r in results if r["llm"].startswith("W"))
        notwine = sum(1 for r in results if r["llm"].startswith("X"))
        spirits = sum(1 for r in results if r["llm"].startswith("S"))
        missing = sum(1 for r in results if r["llm"] == "MISSING")
        print(f"W={wines} X={notwine} S={spirits} ?={missing}")

        start_num += len(batch)

        # Rate limit - 15 RPM no free tier
        if i < len(batches) - 1:
            time.sleep(4.5)

    # Salvar resultados
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_results[0].keys())
        writer.writeheader()
        writer.writerows(all_results)

    # Resumo
    total = len(all_results)
    wines = sum(1 for r in all_results if r["llm"].startswith("W"))
    notwine = sum(1 for r in all_results if r["llm"].startswith("X"))
    spirits = sum(1 for r in all_results if r["llm"].startswith("S"))
    dupes = sum(1 for r in all_results if "=" in r["llm"])

    print(f"\n--- RESULTADO FORMATO {formato} ---")
    print(f"Total:     {total}")
    print(f"WINE:      {wines} ({wines*100//total}%)")
    print(f"NOT_WINE:  {notwine} ({notwine*100//total}%)")
    print(f"SPIRITS:   {spirits} ({spirits*100//total}%)")
    print(f"Duplicatas: {dupes}")
    print(f"Tokens est: ~{total_input_tokens:,} in + ~{total_output_tokens:,} out")
    print(f"Salvo em:  {output_path}")

    return all_results


def compare_formats(results_a, results_b):
    """Compara os 2 formatos."""
    print(f"\n{'='*60}")
    print("COMPARACAO DOS FORMATOS")
    print(f"{'='*60}")

    # Concordancia na classificacao (W/X/S)
    agree = 0
    disagree = 0
    for a, b in zip(results_a, results_b):
        type_a = a["llm"][0] if a["llm"] and a["llm"][0] in "WXS" else "?"
        type_b = b["llm"][0] if b["llm"] and b["llm"][0] in "WXS" else "?"
        if type_a == type_b:
            agree += 1
        else:
            disagree += 1

    print(f"Concordam (W/X/S): {agree} ({agree*100//(agree+disagree)}%)")
    print(f"Discordam:         {disagree}")

    # Mostrar discordancias
    if disagree > 0:
        print(f"\nPrimeiras 20 discordancias:")
        count = 0
        for a, b in zip(results_a, results_b):
            type_a = a["llm"][0] if a["llm"] and a["llm"][0] in "WXS" else "?"
            type_b = b["llm"][0] if b["llm"] and b["llm"][0] in "WXS" else "?"
            if type_a != type_b:
                print(f"  #{a['num']} \"{a['loja_nome'][:50]}\"")
                print(f"    Formato A: {a['llm'][:80]}")
                print(f"    Formato B: {b['llm'][:80]}")
                count += 1
                if count >= 20:
                    break

    # Comparar com destino atual
    print(f"\n--- VS CLASSIFICACAO ATUAL DO PIPELINE ---")
    for fmt_name, results in [("A", results_a), ("B", results_b)]:
        print(f"\nFormato {fmt_name}:")
        # D que LLM classificou como W (vinhos resgatados)
        rescued = [r for r in results if r["destino_atual"] == "D" and r["llm"].startswith("W")]
        print(f"  D reclassificado como WINE: {len(rescued)} (vinhos resgatados do lixo)")
        # A que LLM classificou como X (falsos positivos no match)
        false_a = [r for r in results if r["destino_atual"] == "A" and r["llm"].startswith("X")]
        print(f"  A reclassificado como NOT_WINE: {len(false_a)} (falsos positivos removidos)")
        # C2 que LLM classificou como W
        c2_wine = [r for r in results if r["destino_atual"] == "C2" and r["llm"].startswith("W")]
        print(f"  C2 confirmado como WINE: {len(c2_wine)} de {sum(1 for r in results if r['destino_atual']=='C2')}")


def main():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if len(sys.argv) >= 2 and not sys.argv[1].startswith("--"):
        api_key = sys.argv[1]

    max_batches = None
    formato_rodar = "AB"
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--max-batches" and i + 1 < len(sys.argv):
            max_batches = int(sys.argv[i + 1])
        if arg == "--formato" and i + 1 < len(sys.argv):
            formato_rodar = sys.argv[i + 1].upper()

    # Carregar itens
    items = load_items(CSV_PATH)
    print(f"Carregados {len(items)} itens de {CSV_PATH}")

    # Criar diretorio de output
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results_a = None
    results_b = None

    if "A" in formato_rodar:
        output_a = os.path.join(OUTPUT_DIR, "formato_A_resultados.csv")
        results_a = run_test(api_key, "A", PROMPT_FORMATO_A, items, output_a, max_batches)

    if "B" in formato_rodar:
        output_b = os.path.join(OUTPUT_DIR, "formato_B_resultados.csv")
        results_b = run_test(api_key, "B", PROMPT_FORMATO_B, items, output_b, max_batches)

    if results_a and results_b:
        compare_formats(results_a, results_b)

    print("\nDone!")


if __name__ == "__main__":
    main()
