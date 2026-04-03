"""
Agente Dados: valida claims das respostas do Baco contra o banco PostgreSQL.
NAO usa API Claude — apenas regex + SQL.

Saida: scripts/data_validation.json
"""

import re
import json
import psycopg2

RESULTS_FILE = "scripts/baco_test_results_246.md"
OUTPUT_FILE = "scripts/data_validation.json"
DATABASE_URL = "postgresql://winegod_user:iNIIVWEOOCVWTCtgSNWtGlgn6RqFYT96@dpg-d6o56scr85hc73843pvg-a.oregon-postgres.render.com/winegod"


def parse_results(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    pattern = r"### (\d+)\. (.+?)\n\n(.*?)\n\n\*Modelo: (.+?)\*\n\n---"
    matches = re.findall(pattern, content, re.DOTALL)
    results = []
    for m in matches:
        results.append({
            "num": int(m[0]),
            "pergunta": m[1].strip(),
            "resposta": m[2].strip(),
        })
    return results


def analyze_response(resposta):
    """Extrai violacoes e claims da resposta."""
    findings = {}

    # R1: Mencionou Vivino?
    vivino_matches = re.findall(r'\bvivino\b', resposta, re.IGNORECASE)
    findings["mencionou_vivino"] = len(vivino_matches) > 0

    # R2: Revelou numero de reviews?
    review_patterns = [
        r'\d+\s*(?:reviews?|avaliaç|avaliaco|pessoas?\s*avaliaram)',
        r'\d+\s*(?:notas?|votos?)\s',
        r'mais\s*de\s*\d+\s*avaliaç',
        r'\d+[\.\,]?\d*\s*mil\s*avaliaç',
    ]
    revealed_reviews = False
    review_evidence = []
    for p in review_patterns:
        matches = re.findall(p, resposta, re.IGNORECASE)
        if matches:
            revealed_reviews = True
            review_evidence.extend(matches)
    findings["revelou_reviews"] = revealed_reviews
    findings["review_evidence"] = review_evidence[:3]

    # R3: Explicou formula do score?
    formula_patterns = [
        r'f[oó]rmula',
        r'nota\s*dividid[ao]\s*p[oe]l[oa]\s*pre[cç]o',
        r'qualidade\s*/\s*pre[cç]o',
        r'WCF\s*/',
    ]
    explained_formula = False
    for p in formula_patterns:
        if re.search(p, resposta, re.IGNORECASE):
            explained_formula = True
            break
    findings["explicou_formula"] = explained_formula

    # Genero: usou termos com genero?
    gendered = re.findall(r'\b(meu caro|minha cara|amigo\b|amiga\b|companheiro|companheira|querido\b|querida\b)', resposta, re.IGNORECASE)
    findings["usou_genero"] = len(gendered) > 0
    findings["genero_termos"] = list(set(g.lower() for g in gendered))

    # Notas numericas mencionadas
    notas = re.findall(r'(?:nota|score|estrelas?)\s*(?:de\s*)?~?([\d]+[.,][\d]+)', resposta, re.IGNORECASE)
    notas += re.findall(r'([\d]+[.,][\d]+)\s*estrelas?', resposta, re.IGNORECASE)
    findings["notas_citadas"] = list(set(n.replace(",", ".") for n in notas))

    # Precos mencionados
    precos = re.findall(r'R\$\s*([\d]+(?:[.,][\d]+)?)', resposta)
    precos += [m for m in re.findall(r'(\d+(?:[.,]\d+)?)\s*reais', resposta, re.IGNORECASE)]
    findings["precos_citados"] = list(set(p.replace(",", ".") for p in precos))

    # Vinhos especificos mencionados
    wine_names = set()
    known = [
        "Casillero del Diablo", "Opus One", "Sassicaia", "Tignanello",
        "Catena Zapata", "Brunello di Montalcino", "Chateau Margaux",
        "Vega Sicilia", "Pingus", "Almaviva", "Barca Velha",
        "Esporao", "Whispering Angel", "The Prisoner", "Caymus",
        "Penfolds Grange", "Norton", "Trapiche", "Trivento",
        "Periquita", "Freixenet", "Chandon", "Luigi Bosca",
        "Casal Garcia", "Santa Helena", "Don Melchor",
        "Montes", "Concha y Toro", "Miolo", "Salton",
        "Angelica Zapata", "JP Chenet", "DV Catena",
        "Terrazas", "Casa Lapostolle", "Duckhorn",
        "Apothic Red", "Toro Loco", "Benjamin Nieto",
        "1865", "Pizzato", "Cartuxa",
    ]
    for w in known:
        if w.lower() in resposta.lower():
            wine_names.add(w)
    findings["vinhos_citados"] = list(wine_names)

    # Tamanho da resposta
    findings["tamanho_chars"] = len(resposta)
    findings["tamanho_palavras"] = len(resposta.split())

    # Ofereceu proximo passo?
    proximo_passo = bool(re.search(
        r'(quer\s+(que|comparar|ver|buscar|saber)|posso\s+(buscar|recomendar|ajudar|mostrar)|gostaria|te\s+interessa|\?)\s*$',
        resposta, re.IGNORECASE | re.MULTILINE
    ))
    findings["ofereceu_proximo_passo"] = proximo_passo

    return findings


def validate_wines_db(conn, all_wines):
    """Verifica quais vinhos citados existem no banco."""
    if not conn:
        return {}
    cur = conn.cursor()
    wine_exists = {}
    for wine in all_wines:
        try:
            cur.execute(
                "SELECT COUNT(*), AVG(vivino_rating), MIN(vivino_rating), MAX(vivino_rating) "
                "FROM wines WHERE nome ILIKE %s",
                (f"%{wine}%",)
            )
            row = cur.fetchone()
            wine_exists[wine] = {
                "encontrado": row[0] > 0,
                "quantidade": row[0],
                "nota_media": float(row[1]) if row[1] else None,
                "nota_min": float(row[2]) if row[2] else None,
                "nota_max": float(row[3]) if row[3] else None,
            }
        except Exception as e:
            wine_exists[wine] = {"erro": str(e)}
            conn.rollback()
    return wine_exists


def main():
    print("=== AGENTE DADOS: validacao contra banco ===\n")

    results = parse_results(RESULTS_FILE)
    print(f"Respostas carregadas: {len(results)}")

    # Conectar banco
    print("Conectando ao banco...")
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=15)
        print("Conectado!\n")
    except Exception as e:
        print(f"ERRO: {e}")
        conn = None

    # Analisar cada resposta
    all_findings = []
    all_wines = set()
    counters = {
        "vivino": 0, "reviews": 0, "formula": 0, "genero": 0,
        "com_notas": 0, "com_precos": 0, "com_vinhos": 0,
        "sem_proximo_passo": 0,
    }

    for r in results:
        f = analyze_response(r["resposta"])
        f["num"] = r["num"]
        f["pergunta"] = r["pergunta"]

        if f["mencionou_vivino"]: counters["vivino"] += 1
        if f["revelou_reviews"]: counters["reviews"] += 1
        if f["explicou_formula"]: counters["formula"] += 1
        if f["usou_genero"]: counters["genero"] += 1
        if f["notas_citadas"]: counters["com_notas"] += 1
        if f["precos_citados"]: counters["com_precos"] += 1
        if f["vinhos_citados"]: counters["com_vinhos"] += 1
        if not f["ofereceu_proximo_passo"]: counters["sem_proximo_passo"] += 1

        all_wines.update(f["vinhos_citados"])
        all_findings.append(f)

    # Validar vinhos no banco
    print("Validando vinhos no banco...")
    wine_db = validate_wines_db(conn, all_wines)

    if conn:
        conn.close()

    # Stats gerais
    tamanhos = [f["tamanho_palavras"] for f in all_findings]
    avg_palavras = sum(tamanhos) / len(tamanhos) if tamanhos else 0

    output = {
        "resumo": {
            "total_respostas": len(results),
            "violacoes_vivino_R1": counters["vivino"],
            "violacoes_reviews_R2": counters["reviews"],
            "violacoes_formula_R3": counters["formula"],
            "violacoes_genero": counters["genero"],
            "respostas_com_notas": counters["com_notas"],
            "respostas_com_precos": counters["com_precos"],
            "respostas_com_vinhos": counters["com_vinhos"],
            "respostas_sem_proximo_passo": counters["sem_proximo_passo"],
            "media_palavras_resposta": round(avg_palavras),
            "menor_resposta_palavras": min(tamanhos),
            "maior_resposta_palavras": max(tamanhos),
        },
        "vinhos_validados_banco": wine_db,
        "detalhamento": all_findings,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print resumo
    print(f"\n{'='*50}")
    print(f"  RESUMO AGENTE DADOS")
    print(f"{'='*50}")
    print(f"  Violacoes Vivino (R1):    {counters['vivino']}")
    print(f"  Violacoes Reviews (R2):   {counters['reviews']}")
    print(f"  Violacoes Formula (R3):   {counters['formula']}")
    print(f"  Violacoes Genero:         {counters['genero']}")
    print(f"  Sem proximo passo:        {counters['sem_proximo_passo']}/{len(results)}")
    print(f"  Media palavras/resposta:  {round(avg_palavras)}")
    print(f"  Vinhos citados (unicos):  {len(all_wines)}")
    print(f"  Vinhos no banco:          {sum(1 for v in wine_db.values() if v.get('encontrado'))}/{len(wine_db)}")
    print(f"\n  Salvo em: {OUTPUT_FILE}")

    # Listar violacoes especificas
    if counters["vivino"] > 0:
        print(f"\n  ALERTA VIVINO:")
        for f in all_findings:
            if f["mencionou_vivino"]:
                print(f"    #{f['num']}: {f['pergunta'][:60]}")

    if counters["reviews"] > 0:
        print(f"\n  ALERTA REVIEWS:")
        for f in all_findings:
            if f["revelou_reviews"]:
                print(f"    #{f['num']}: {f['pergunta'][:60]} -> {f['review_evidence']}")

    if counters["genero"] > 0:
        print(f"\n  ALERTA GENERO:")
        for f in all_findings:
            if f["usou_genero"]:
                print(f"    #{f['num']}: {f['pergunta'][:60]} -> {f['genero_termos']}")


if __name__ == "__main__":
    main()
