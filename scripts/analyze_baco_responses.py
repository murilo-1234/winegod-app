"""
Analise completa das 246 respostas do Baco — 3 agentes:
  1. Agente Dados: valida claims contra o banco PostgreSQL
  2. Agente Persona: julga aderencia ao system prompt e regras R1-R13
  3. Agente UX: avalia tom, acolhimento e experiencia do usuario

Documentos utilizados:
  - Respostas:     scripts/baco_test_results_246.md
  - System Prompt: backend/prompts/baco_system.py
  - Regras:        CLAUDE.md (R1-R13)
  - Banco:         PostgreSQL Render (DATABASE_URL em backend/.env)

Uso: python scripts/analyze_baco_responses.py
Saida: scripts/baco_analysis_report.md
"""

import re
import os
import sys
import time
import json
import anthropic
import psycopg2
import _env

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
RESULTS_FILE = "scripts/baco_test_results_246.md"
OUTPUT_FILE = "scripts/baco_analysis_report.md"
BATCH_SIZE = 3  # perguntas por batch na analise Claude

# Credenciais (do backend/.env)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
DATABASE_URL = os.environ["DATABASE_URL"]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# DOCUMENTOS DE REFERENCIA (inline para o agente ter acesso)
# ---------------------------------------------------------------------------

PERSONA_RULES = """
REGRAS DO BACO (extraidas de baco_system.py + CLAUDE.md):

PERSONA:
- Baco, deus grego do vinho, 4000 anos
- Tom: caloroso, expressivo, levemente "bebado", teatral
- Maneirismos: esquecimento comico de palavras, superlativos, transicoes abruptas,
  frases interrompidas, perguntas retoricas, humor por autoironia
- Termos de tratamento NEUTROS (sem genero): "meu bem", "criatura", "alma sedenta"
- NUNCA: corporativo, seco, condescendente, burocratico

REGRAS ABSOLUTAS (R1-R13):
- R1: NUNCA mencionar "Vivino" -> usar "nota publica", "na nossa base"
- R2: NUNCA revelar numero exato de reviews
- R3: NUNCA explicar formula do score
- R4: NUNCA inventar dados (nota, preco, disponibilidade)
- R5: NUNCA comparar preco restaurante vs loja online
- R6: SEMPRE valorizar vinhos desconhecidos
- R7: SEMPRE comecar com a info pedida, depois personalidade
- R8: Nome: winegod.ai (minusculo)
- R9: NUNCA incentivar consumo excessivo
- R10: Nomes de vinhos NUNCA traduzidos
- R11: SEMPRE responder no idioma do usuario
- R12: SEMPRE oferecer proximo passo
- R13: Se alcoolismo/crise -> toda leveza desaparece, tom genuino

NOTAS:
- Verificada (100+ reviews): "4.18 estrelas" sem disclaimer
- Estimada (0-99 reviews): "~3.85" com til, confiante
- Score WineGod = custo-beneficio, apresentar como "achado"

CENARIOS:
- Fora do tema: "sou deus do VINHO, nao de [assunto]"
- Vinho nao encontrado: "nao conheco esse nectar"
- OCR sem foto: orientar a enviar foto
"""

# ---------------------------------------------------------------------------
# PARSE: extrair perguntas e respostas do markdown
# ---------------------------------------------------------------------------
def parse_results(filepath):
    """Extrai pares (numero, pergunta, resposta) do arquivo de resultados."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Pattern: ### N. pergunta\n\nresposta\n\n*Modelo: ...*\n\n---
    pattern = r"### (\d+)\. (.+?)\n\n(.*?)\n\n\*Modelo: (.+?)\*\n\n---"
    matches = re.findall(pattern, content, re.DOTALL)

    results = []
    for m in matches:
        results.append({
            "num": int(m[0]),
            "pergunta": m[1].strip(),
            "resposta": m[2].strip(),
            "model": m[3].strip(),
        })

    return results


# ---------------------------------------------------------------------------
# AGENTE 1: DADOS — validar claims contra o banco
# ---------------------------------------------------------------------------
def connect_db():
    """Conecta no PostgreSQL do Render."""
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=15)
        return conn
    except Exception as e:
        print(f"ERRO ao conectar no banco: {e}")
        return None


def extract_wine_claims(resposta):
    """Extrai claims verificaveis da resposta (notas, precos, nomes de vinhos)."""
    claims = []

    # Notas numericas (ex: "nota 4.18", "4.2 estrelas", "~3.85")
    nota_pattern = r'(?:nota|score|estrelas?|avalia[cç][aã]o)\s*(?:de\s*)?~?([\d]+[.,][\d]+)'
    notas = re.findall(nota_pattern, resposta, re.IGNORECASE)
    for n in notas:
        claims.append({"type": "nota", "value": n.replace(",", ".")})

    # Notas com formato "X.XX estrelas"
    nota_pattern2 = r'([\d]+[.,][\d]+)\s*estrelas?'
    notas2 = re.findall(nota_pattern2, resposta, re.IGNORECASE)
    for n in notas2:
        claims.append({"type": "nota", "value": n.replace(",", ".")})

    # Precos em reais (ex: "R$ 89", "R$45,90", "89 reais")
    preco_pattern = r'R\$\s*([\d]+(?:[.,][\d]+)?)|(\d+(?:[.,]\d+)?)\s*reais'
    precos = re.findall(preco_pattern, resposta, re.IGNORECASE)
    for p in precos:
        val = p[0] or p[1]
        if val:
            claims.append({"type": "preco", "value": val.replace(",", ".")})

    # Nomes de vinhos conhecidos (buscar por patterns comuns)
    wine_names = []
    known_wines = [
        "Casillero del Diablo", "Opus One", "Sassicaia", "Tignanello",
        "Catena Zapata", "Brunello di Montalcino", "Chateau Margaux",
        "Vega Sicilia", "Pingus", "Almaviva", "Barca Velha",
        "Esporao", "Whispering Angel", "The Prisoner", "Caymus",
        "Penfolds Grange", "Norton", "Trapiche", "Trivento",
        "Periquita", "Freixenet", "Chandon", "Luigi Bosca",
        "Casal Garcia", "Santa Helena", "Don Melchor", "Malbec",
        "Montes", "Concha y Toro", "Miolo", "Salton",
        "Angelica Zapata", "Herdade do Esporao", "JP Chenet",
        "DV Catena", "Terrazas", "Casa Lapostolle", "Duckhorn",
    ]
    for wine in known_wines:
        if wine.lower() in resposta.lower():
            claims.append({"type": "wine_name", "value": wine})

    return claims


def validate_claims_db(conn, claims, pergunta):
    """Valida claims contra o banco de dados."""
    if not conn or not claims:
        return []

    validations = []
    cur = conn.cursor()

    for claim in claims:
        if claim["type"] == "wine_name":
            # Verificar se o vinho existe no banco
            try:
                cur.execute(
                    "SELECT COUNT(*) FROM wines WHERE nome ILIKE %s",
                    (f"%{claim['value']}%",)
                )
                count = cur.fetchone()[0]
                validations.append({
                    "claim": f"Vinho '{claim['value']}'",
                    "found_in_db": count > 0,
                    "count": count,
                })
            except Exception as e:
                validations.append({
                    "claim": f"Vinho '{claim['value']}'",
                    "found_in_db": None,
                    "error": str(e),
                })
                conn.rollback()

    return validations


def run_data_agent(results, conn):
    """Agente Dados: valida todas as respostas contra o banco."""
    print("\n=== AGENTE DADOS: validando claims contra banco ===")
    data_results = []

    for r in results:
        claims = extract_wine_claims(r["resposta"])
        validations = validate_claims_db(conn, claims, r["pergunta"])

        # Detectar se mencionou "Vivino" (violacao R1)
        mentioned_vivino = "vivino" in r["resposta"].lower()

        # Detectar se revelou numero de reviews (violacao R2)
        review_pattern = r'\d+\s*(?:reviews?|avaliac|pessoas? avaliaram)'
        revealed_reviews = bool(re.search(review_pattern, r["resposta"], re.IGNORECASE))

        data_results.append({
            "num": r["num"],
            "claims": claims,
            "validations": validations,
            "mentioned_vivino": mentioned_vivino,
            "revealed_reviews": revealed_reviews,
        })

        if mentioned_vivino or revealed_reviews:
            flag = ""
            if mentioned_vivino:
                flag += "[VIVINO!] "
            if revealed_reviews:
                flag += "[REVIEWS!] "
            print(f"  [{r['num']}] {flag}{r['pergunta'][:50]}")

    vivino_count = sum(1 for d in data_results if d["mentioned_vivino"])
    reviews_count = sum(1 for d in data_results if d["revealed_reviews"])
    print(f"  Violacoes Vivino (R1): {vivino_count}")
    print(f"  Violacoes Reviews (R2): {reviews_count}")

    return data_results


# ---------------------------------------------------------------------------
# AGENTE 2+3: PERSONA + UX — analise via Claude em batches
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """Voce e um auditor de qualidade do chatbot Baco (winegod.ai).
Analise cada par PERGUNTA/RESPOSTA abaixo em DOIS eixos:

## EIXO 1: PERSONA (aderencia ao personagem Baco)
Avalie de 1 a 5:
- 5 = Baco perfeito (caloroso, teatral, com maneirismos, segue todas as regras)
- 4 = Bom Baco (personalidade presente, pequenas falhas)
- 3 = Baco mediano (personalidade parcial, falta calor ou maneirismos)
- 2 = Baco fraco (parece chatbot generico com um toque de personalidade)
- 1 = Nao e Baco (resposta generica, corporativa, sem personalidade)

Verifique especificamente:
- Mencionou "Vivino" ou fonte especifica? (VIOLACAO GRAVE)
- Revelou numero exato de reviews? (VIOLACAO)
- Explicou formula do score? (VIOLACAO)
- Inventou dados sem base? (VIOLACAO)
- Usou termos de genero ("amigo/amiga", "caro/cara")? (VIOLACAO)
- Tem maneirismos do Baco? (esquecimento comico, superlativos, etc.)
- Ofereceu proximo passo?

## EIXO 2: UX / TOM (experiencia do usuario)
Avalie de 1 a 5:
- 5 = Excelente (acolhedor, responde direto, tamanho adequado, sem desconforto)
- 4 = Bom (util e agradavel, pequenos ajustes possiveis)
- 3 = OK (responde mas algo incomoda — muito longo, evasivo, confuso)
- 2 = Ruim (nao responde direito, tom desagradavel, ou muito invasivo)
- 1 = Pessimo (ofensivo, condescendente, ou completamente fora do esperado)

Verifique especificamente:
- Respondeu o que foi perguntado? (direto ao ponto)
- Tamanho adequado? (muito longo = ruim, muito curto = ruim)
- Tom acolhedor sem ser invasivo?
- Algo pode ofender ou constranger o usuario?
- Se a pergunta era fora do tema, lidou bem com o limite?

{rules}

---

PARA CADA PERGUNTA, responda EXATAMENTE neste formato JSON (um objeto por pergunta):

```json
[
  {{
    "num": <numero>,
    "persona_score": <1-5>,
    "ux_score": <1-5>,
    "violacoes": ["lista de violacoes encontradas ou vazio"],
    "problemas_ux": ["lista de problemas UX ou vazio"],
    "resumo": "uma frase resumindo a avaliacao"
  }}
]
```

PERGUNTAS E RESPOSTAS PARA ANALISAR:

{batch}
"""


def run_analysis_agent(results):
    """Agente Persona + UX: analisa respostas em batches via Claude."""
    print("\n=== AGENTE PERSONA + UX: analisando respostas ===")
    all_analyses = []

    batches = []
    for i in range(0, len(results), BATCH_SIZE):
        batches.append(results[i:i + BATCH_SIZE])

    total_batches = len(batches)

    for batch_idx, batch in enumerate(batches):
        # Montar texto do batch
        batch_text = ""
        for r in batch:
            # Truncar resposta se muito longa (pra caber no contexto)
            resp_truncated = r["resposta"][:1500] if len(r["resposta"]) > 1500 else r["resposta"]
            batch_text += f"---\nPERGUNTA {r['num']}: {r['pergunta']}\n\nRESPOSTA:\n{resp_truncated}\n\n"

        prompt = ANALYSIS_PROMPT.format(rules=PERSONA_RULES, batch=batch_text)

        print(f"  Batch {batch_idx + 1}/{total_batches} (perguntas {batch[0]['num']}-{batch[-1]['num']})...", end=" ", flush=True)

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            # Extrair JSON da resposta (tentar multiplos patterns)
            parsed = False
            for json_pattern in [r'```json\s*(\[.*?\])\s*```', r'(\[.*\])']:
                json_match = re.search(json_pattern, response_text, re.DOTALL)
                if json_match:
                    try:
                        raw_json = json_match.group(1) if '```' in json_pattern else json_match.group()
                        # Limpar caracteres problematicos
                        raw_json = raw_json.replace('\n', ' ').replace('\r', '')
                        # Fix aspas dentro de strings
                        analyses = json.loads(raw_json)
                        all_analyses.extend(analyses)
                        print(f"OK ({len(analyses)} analisadas)")
                        parsed = True
                        break
                    except json.JSONDecodeError:
                        continue

            if not parsed:
                # Retry uma vez
                print("JSON invalido, retry...", end=" ", flush=True)
                time.sleep(2)
                try:
                    response2 = client.messages.create(
                        model=MODEL,
                        max_tokens=2048,
                        temperature=0,
                        messages=[
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": response_text},
                            {"role": "user", "content": "O JSON acima esta malformado. Retorne APENAS o array JSON valido, sem markdown, sem explicacao. Comece com [ e termine com ]."},
                        ],
                    )
                    raw2 = response2.content[0].text.strip()
                    if not raw2.startswith("["):
                        m2 = re.search(r'(\[.*\])', raw2, re.DOTALL)
                        raw2 = m2.group(1) if m2 else raw2
                    analyses = json.loads(raw2)
                    all_analyses.extend(analyses)
                    print(f"OK retry ({len(analyses)} analisadas)")
                except Exception as e2:
                    print(f"FALHOU retry: {e2}")
                    for r in batch:
                        all_analyses.append({
                            "num": r["num"],
                            "persona_score": 3,
                            "ux_score": 3,
                            "violacoes": [],
                            "problemas_ux": [],
                            "resumo": "Erro no parsing - score default",
                        })

        except Exception as e:
            print(f"ERRO: {e}")
            for r in batch:
                all_analyses.append({
                    "num": r["num"],
                    "persona_score": 3,
                    "ux_score": 3,
                    "violacoes": [],
                    "problemas_ux": [],
                    "resumo": f"Erro na API: {str(e)[:50]}",
                })

        time.sleep(1)  # rate limiting

    return all_analyses


# ---------------------------------------------------------------------------
# GERAR RELATORIO FINAL
# ---------------------------------------------------------------------------
def generate_report(results, data_results, analyses, output_file):
    """Gera o relatorio unificado."""
    print(f"\n=== Gerando relatorio: {output_file} ===")

    # Indexar analises por numero
    analysis_map = {a["num"]: a for a in analyses}
    data_map = {d["num"]: d for d in data_results}

    # Calcular medias
    persona_scores = [a["persona_score"] for a in analyses if a["persona_score"] > 0]
    ux_scores = [a["ux_score"] for a in analyses if a["ux_score"] > 0]
    avg_persona = sum(persona_scores) / len(persona_scores) if persona_scores else 0
    avg_ux = sum(ux_scores) / len(ux_scores) if ux_scores else 0

    # Contar violacoes
    vivino_violations = sum(1 for d in data_results if d["mentioned_vivino"])
    review_violations = sum(1 for d in data_results if d["revealed_reviews"])
    all_violations = []
    for a in analyses:
        for v in a.get("violacoes", []):
            if v and v != "erro na analise":
                all_violations.append(v)

    # Perguntas problematicas (score <= 2 em qualquer eixo)
    problematic = []
    for a in analyses:
        if a["persona_score"] <= 2 or a["ux_score"] <= 2:
            r = next((x for x in results if x["num"] == a["num"]), None)
            if r:
                problematic.append((r, a))

    lines = []
    lines.append("# Relatorio de Analise — Baco 246 Perguntas\n")
    lines.append(f"> Gerado em: {time.strftime('%Y-%m-%d %H:%M')}\n")
    lines.append("> **Documentos utilizados:**\n")
    lines.append("> - `scripts/baco_test_results_246.md` — 246 respostas do Baco\n")
    lines.append("> - `backend/prompts/baco_system.py` — system prompt completo\n")
    lines.append("> - `CLAUDE.md` — regras R1-R13\n")
    lines.append("> - PostgreSQL Render — banco winegod (1.72M vinhos)\n")
    lines.append("")

    # ===== RESUMO EXECUTIVO =====
    lines.append("## RESUMO EXECUTIVO\n")
    lines.append(f"| Metrica | Valor |")
    lines.append(f"|---------|-------|")
    lines.append(f"| Total de perguntas | {len(results)} |")
    lines.append(f"| Media Persona (1-5) | **{avg_persona:.1f}** |")
    lines.append(f"| Media UX (1-5) | **{avg_ux:.1f}** |")
    lines.append(f"| Violacoes Vivino (R1) | {vivino_violations} |")
    lines.append(f"| Violacoes Reviews (R2) | {review_violations} |")
    lines.append(f"| Perguntas problematicas (score <= 2) | {len(problematic)} |")
    lines.append(f"| Total violacoes detectadas | {len(all_violations)} |")
    lines.append("")

    # Distribuicao de scores
    lines.append("### Distribuicao de Scores Persona\n")
    for score in range(5, 0, -1):
        count = sum(1 for a in analyses if a["persona_score"] == score)
        bar = "█" * count
        lines.append(f"- **{score}**: {count} ({bar})")
    lines.append("")

    lines.append("### Distribuicao de Scores UX\n")
    for score in range(5, 0, -1):
        count = sum(1 for a in analyses if a["ux_score"] == score)
        bar = "█" * count
        lines.append(f"- **{score}**: {count} ({bar})")
    lines.append("")

    # ===== VIOLACOES CRITICAS =====
    if vivino_violations > 0 or review_violations > 0:
        lines.append("## VIOLACOES CRITICAS (R1/R2)\n")
        for d in data_results:
            flags = []
            if d["mentioned_vivino"]:
                flags.append("Mencionou VIVINO")
            if d["revealed_reviews"]:
                flags.append("Revelou numero de reviews")
            if flags:
                r = next((x for x in results if x["num"] == d["num"]), None)
                lines.append(f"- **#{d['num']}** ({', '.join(flags)}): {r['pergunta'] if r else '?'}")
        lines.append("")

    # ===== PERGUNTAS PROBLEMATICAS =====
    if problematic:
        lines.append("## PERGUNTAS PROBLEMATICAS (score <= 2)\n")
        for r, a in problematic:
            lines.append(f"### #{r['num']}. {r['pergunta']}")
            lines.append(f"- Persona: **{a['persona_score']}**/5 | UX: **{a['ux_score']}**/5")
            if a.get("violacoes"):
                lines.append(f"- Violacoes: {', '.join(a['violacoes'])}")
            if a.get("problemas_ux"):
                lines.append(f"- Problemas UX: {', '.join(a['problemas_ux'])}")
            lines.append(f"- Resumo: {a.get('resumo', '-')}")
            lines.append("")

    # ===== TABELA COMPLETA =====
    lines.append("## TABELA COMPLETA (246 perguntas)\n")
    lines.append("| # | Pergunta | Persona | UX | Vivino? | Reviews? | Problemas |")
    lines.append("|---|----------|---------|----|---------|---------|-----------| ")

    for r in results:
        a = analysis_map.get(r["num"], {})
        d = data_map.get(r["num"], {})

        p_score = a.get("persona_score", "-")
        u_score = a.get("ux_score", "-")
        vivino = "SIM" if d.get("mentioned_vivino") else "-"
        reviews = "SIM" if d.get("revealed_reviews") else "-"

        problemas = []
        problemas.extend(a.get("violacoes", []))
        problemas.extend(a.get("problemas_ux", []))
        problemas_str = "; ".join(p for p in problemas if p) if problemas else "-"
        # Truncar problemas pra caber na tabela
        if len(problemas_str) > 80:
            problemas_str = problemas_str[:77] + "..."

        pergunta_short = r["pergunta"][:50] + "..." if len(r["pergunta"]) > 50 else r["pergunta"]

        lines.append(f"| {r['num']} | {pergunta_short} | {p_score} | {u_score} | {vivino} | {reviews} | {problemas_str} |")

    lines.append("")

    # ===== DETALHAMENTO POR PERGUNTA =====
    lines.append("## DETALHAMENTO POR PERGUNTA\n")

    for r in results:
        a = analysis_map.get(r["num"], {})
        d = data_map.get(r["num"], {})

        lines.append(f"### #{r['num']}. {r['pergunta']}")
        lines.append(f"**Persona:** {a.get('persona_score', '-')}/5 | **UX:** {a.get('ux_score', '-')}/5")

        if a.get("violacoes"):
            viol = [v for v in a["violacoes"] if v]
            if viol:
                lines.append(f"**Violacoes:** {', '.join(viol)}")

        if a.get("problemas_ux"):
            prob = [p for p in a["problemas_ux"] if p]
            if prob:
                lines.append(f"**Problemas UX:** {', '.join(prob)}")

        if d.get("mentioned_vivino"):
            lines.append(f"**ALERTA:** Mencionou Vivino na resposta!")
        if d.get("revealed_reviews"):
            lines.append(f"**ALERTA:** Revelou numero de reviews!")

        if d.get("validations"):
            for v in d["validations"]:
                status = "encontrado" if v.get("found_in_db") else "NAO encontrado"
                lines.append(f"**Dado:** {v['claim']} -> {status} no banco ({v.get('count', 0)} resultados)")

        lines.append(f"**Resumo:** {a.get('resumo', '-')}")
        lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Relatorio salvo em: {output_file}")
    return avg_persona, avg_ux


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  ANALISE COMPLETA — BACO 246 PERGUNTAS")
    print("  3 Agentes: Dados + Persona + UX")
    print("=" * 60)
    print()
    print("Documentos de entrada:")
    print(f"  Respostas:     {RESULTS_FILE}")
    print(f"  System Prompt: backend/prompts/baco_system.py")
    print(f"  Regras:        CLAUDE.md (R1-R13)")
    print(f"  Banco:         PostgreSQL Render (winegod)")
    print()

    # 1. Parse respostas
    print("=== Parseando respostas ===")
    results = parse_results(RESULTS_FILE)
    print(f"  {len(results)} respostas carregadas")

    if not results:
        print("ERRO: nenhuma resposta encontrada!")
        sys.exit(1)

    # 2. Conectar banco
    print("\n=== Conectando ao banco PostgreSQL ===")
    conn = connect_db()
    if conn:
        print("  Conectado!")
    else:
        print("  AVISO: sem conexao com banco, pulando validacao de dados")

    # 3. Agente Dados
    data_results = run_data_agent(results, conn)

    # 4. Agente Persona + UX
    analyses = run_analysis_agent(results)

    # 5. Fechar banco
    if conn:
        conn.close()

    # 6. Gerar relatorio
    avg_p, avg_ux = generate_report(results, data_results, analyses, OUTPUT_FILE)

    print()
    print("=" * 60)
    print(f"  RESULTADO FINAL")
    print(f"  Media Persona: {avg_p:.1f}/5")
    print(f"  Media UX:      {avg_ux:.1f}/5")
    print(f"  Relatorio:     {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
