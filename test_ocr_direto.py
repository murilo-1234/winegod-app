"""
Teste direto da OCR (Gemini) + busca no banco, sem passar pelo Baco.
Muito mais rapido que o pipeline completo (~5-15s vs ~90s por foto).
"""
import base64, json, os, sys, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

from tools.media import process_image
import psycopg2

FOTOS_DIR = r"C:\winegod\fotos-vinhos-testes"
DB_URL = os.environ.get("DATABASE_URL", "")

# Todas as 24 fotos com ground truth
FOTOS = [
    ("1.jpeg", "Prateleira grande supermercado, vinhos variados"),
    ("2.jpeg", "Pena Vermelha Reserva close-up, R$89.99"),
    ("3.jpeg", "Contada 1926 Chianti + Primitivo, R$59"),
    ("4.jpeg", "Contada 1926 Chianti close-up"),
    ("5.jpeg", "D'Eugenio Crianza La Mancha, R$54"),
    ("6.jpeg", "D'Eugenio Tinto La Mancha, R$41"),
    ("7.jpeg", "Prateleira mista com Contada 1926 e outros"),
    ("8.jpeg", "Prateleira com Syrah, Graffigna, Contada 1926"),
    ("9.jpeg", "She Noir Pinot Noir R$189.99 + Freixenet 0.0 R$129"),
    ("10.jpeg", "Finca Las Moras CS 2024 + Trivento Malbec de Fuego"),
    ("11.jpeg", "Prateleira vinhos variados (Moscatel etc)"),
    ("12.jpeg", "Prateleira grande com muitos vinhos"),
    ("13.jpeg", "Dona Dominga dois tipos com precos"),
    ("14.jpeg", "Amaral (chileno) em oferta + outros"),
    ("15.jpeg", "Perez Cruz Limited Ed. R$144.99 + Dona Dominga R$63.99"),
    ("16.jpeg", "Perez Cruz Piedra Seca R$159.99 + Grenache R$183.99"),
    ("17.jpeg", "Prateleira vinhos brancos"),
    ("18.jpeg", "Prateleira vinhos variados"),
    ("19.jpeg", "Prateleira Toro + brancos"),
    ("20.jpeg", "Prateleira roses"),
    ("21.jpeg", "Prateleira premium: Dom Perignon, Krug"),
    ("22.jpeg", "Espumantes variados"),
    ("23.jpeg", "Chandon + espumantes"),
    ("24.jpeg", "Freixenet + Corvezzo Prosecco"),
]

def search_wine_db(conn, wine_name):
    """Busca vinho no banco e retorna ratings."""
    cur = conn.cursor()
    # Tentar busca exata primeiro, depois fuzzy
    for pattern in [f"%{wine_name}%"]:
        cur.execute("""
            SELECT id, nome, vivino_rating, winegod_score, nota_wcf, winegod_score_type
            FROM wines
            WHERE nome ILIKE %s
            ORDER BY vivino_rating DESC NULLS LAST
            LIMIT 3
        """, (pattern,))
        rows = cur.fetchall()
        if rows:
            return [{"id": r[0], "nome": r[1], "vivino": float(r[2]) if r[2] else None,
                      "wg_score": float(r[3]) if r[3] else None, "wcf": float(r[4]) if r[4] else None,
                      "type": r[5]} for r in rows]
    return []

def main():
    conn = psycopg2.connect(DB_URL)
    results = []

    print("=" * 80)
    print("TESTE OCR DIRETO (Gemini) + BUSCA DB — WineGod")
    print(f"Total de fotos: {len(FOTOS)}")
    print("=" * 80)

    for i, (filename, ground_truth) in enumerate(FOTOS):
        filepath = os.path.join(FOTOS_DIR, filename)
        if not os.path.exists(filepath):
            print(f"\n[{i+1}] {filename}: ARQUIVO NAO ENCONTRADO")
            continue

        with open(filepath, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(FOTOS)}] {filename}")
        print(f"Ground truth: {ground_truth}")

        # OCR
        start = time.time()
        ocr_result = process_image(img_b64)
        ocr_time = time.time() - start

        image_type = ocr_result.get("image_type", "unknown")
        status = ocr_result.get("status", "unknown")

        print(f"OCR: {ocr_time:.1f}s | type={image_type} | status={status}")

        # Extrair nomes dos vinhos identificados
        wines_found = []
        ocr_raw = {}  # dados estruturados para salvar no JSON

        if image_type == "label":
            wine_name = ocr_result.get("search_text", "")
            if wine_name:
                wines_found.append(wine_name)
            # Preservar campos estruturados do OCR
            raw = ocr_result.get("ocr_result", {})
            if isinstance(raw, dict):
                ocr_raw = {
                    "name": raw.get("name"),
                    "producer": raw.get("producer"),
                    "vintage": raw.get("vintage"),
                    "region": raw.get("region"),
                    "grape": raw.get("grape"),
                    "price": raw.get("price"),
                }
            print(f"  Label: {ocr_result.get('description', '')}")
            if ocr_raw.get("price"):
                print(f"    Preco: {ocr_raw['price']}")
            if ocr_raw.get("grape"):
                print(f"    Uva: {ocr_raw['grape']}")

        elif image_type == "shelf":
            shelf_wines = ocr_result.get("wines", [])
            total_vis = ocr_result.get("total_visible", 0)
            for w in shelf_wines:
                if w.get("name"):
                    wines_found.append(w["name"])
            ocr_raw = {
                "wines": shelf_wines,
                "total_visible": total_vis,
            }
            print(f"  Shelf: {len(wines_found)} vinhos lidos, total_visible={total_vis}")
            for w in shelf_wines:
                price_str = f" | preco: {w['price']}" if w.get("price") else ""
                print(f"    - {w.get('name', '?')}{price_str}")

        elif image_type == "screenshot":
            ss_wines = ocr_result.get("wines", [])
            for w in ss_wines:
                if w.get("name"):
                    wines_found.append(w["name"])
            ocr_raw = {"wines": ss_wines}
            print(f"  Screenshot: {len(wines_found)} vinhos")
            for w in ss_wines:
                parts = [w.get("name", "?")]
                if w.get("price"):
                    parts.append(f"preco: {w['price']}")
                if w.get("rating"):
                    parts.append(f"nota: {w['rating']}")
                print(f"    - {' | '.join(parts)}")

        else:
            print(f"  {image_type}: {ocr_result.get('message', '')[:200]}")

        # Buscar no banco
        db_results = {}
        for wine_name in wines_found[:5]:  # Limitar a 5 buscas
            # Simplificar nome para busca
            search_terms = wine_name.split()[:4]  # Primeiras 4 palavras
            search = " ".join(search_terms)
            db_hits = search_wine_db(conn, search)
            if not db_hits and len(search_terms) > 2:
                # Tentar com menos termos
                db_hits = search_wine_db(conn, " ".join(search_terms[:2]))
            db_results[wine_name] = db_hits
            if db_hits:
                best = db_hits[0]
                print(f"  DB match '{wine_name}': {best['nome'][:50]} | vivino={best['vivino']} | wg={best['wg_score']} | wcf={best['wcf']}")
            else:
                print(f"  DB match '{wine_name}': NAO ENCONTRADO")

        result = {
            "file": filename,
            "ground_truth": ground_truth,
            "ocr_time": ocr_time,
            "image_type": image_type,
            "status": status,
            "wines_found": wines_found,
            "ocr_raw": ocr_raw,
            "db_results": {k: v for k, v in db_results.items()},
        }
        results.append(result)

        time.sleep(1)  # Rate limit Gemini

    conn.close()

    # Salvar resultados
    output_path = os.path.join(os.path.dirname(__file__), "test_ocr_resultados.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    # Resumo final
    print(f"\n\n{'='*80}")
    print("RESUMO OCR")
    print(f"{'='*80}")
    labels = sum(1 for r in results if r["image_type"] == "label")
    shelves = sum(1 for r in results if r["image_type"] == "shelf")
    screenshots = sum(1 for r in results if r["image_type"] == "screenshot")
    not_wine = sum(1 for r in results if r["image_type"] == "not_wine")
    errors = sum(1 for r in results if r["image_type"] in ("error", "unknown"))
    print(f"Labels: {labels} | Shelves: {shelves} | Screenshots: {screenshots} | Not wine: {not_wine} | Errors: {errors}")

    total_wines = sum(len(r["wines_found"]) for r in results)
    wines_in_db = sum(1 for r in results for wn in r["wines_found"] if r["db_results"].get(wn))
    wines_not_in_db = total_wines - wines_in_db
    print(f"Vinhos identificados: {total_wines} | No banco: {wines_in_db} | Fora do banco: {wines_not_in_db}")

    avg_ocr_time = sum(r["ocr_time"] for r in results) / len(results) if results else 0
    print(f"Tempo medio OCR: {avg_ocr_time:.1f}s")

    print(f"\nResultados salvos em: {output_path}")

if __name__ == "__main__":
    main()
