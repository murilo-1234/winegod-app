"""Validacao manual do fluxo de PDF com fixtures reais.

Gera PDFs de teste com fpdf2, roda process_pdf() e mostra evidencia.
Carrega GEMINI_API_KEY de backend/.env automaticamente.

Uso: cd backend && python -m tests.validate_pdf_real
"""

import sys
import os
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carregar .env do backend de forma explicita
from dotenv import load_dotenv

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_path = os.path.join(_backend_dir, ".env")
load_dotenv(_env_path)

from fpdf import FPDF


# --- Geradores de fixtures ---

def _make_native_wine_pdf():
    """PDF nativo com texto: carta de vinhos simples."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Carta de Vinhos", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Tintos", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)

    wines = [
        ("Alamos Malbec 2021 - Mendoza, Argentina", "R$ 89,00"),
        ("Casillero del Diablo Cabernet Sauvignon 2020 - Chile", "R$ 65,00"),
        ("Marques de Casa Concha Carmenere 2019 - Chile", "R$ 120,00"),
        ("Catena Zapata Malbec Argentino 2018 - Mendoza", "R$ 195,00"),
        ("Luigi Bosca Malbec Reserva 2020 - Lujan de Cuyo", "R$ 145,00"),
    ]
    for name, price in wines:
        pdf.cell(0, 7, f"  {name}  ....  {price}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Brancos", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)

    whites = [
        ("Cloudy Bay Sauvignon Blanc 2022 - Marlborough, NZ", "R$ 180,00"),
        ("Santa Rita 120 Chardonnay 2021 - Chile", "R$ 55,00"),
    ]
    for name, price in whites:
        pdf.cell(0, 7, f"  {name}  ....  {price}", new_x="LMARGIN", new_y="NEXT")

    return pdf.output()


def _make_non_wine_pdf():
    """PDF nativo com texto que NAO e sobre vinho."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Contrato de Prestacao de Servicos", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 10)

    paragraphs = [
        "Clausula 1: Das partes contratantes.",
        "A empresa XYZ Ltda, inscrita no CNPJ 12.345.678/0001-00, "
        "doravante denominada CONTRATANTE, e a empresa ABC S.A., "
        "inscrita no CNPJ 98.765.432/0001-00, doravante denominada "
        "CONTRATADA, firmam o presente contrato.",
        "Clausula 2: Do objeto.",
        "O presente contrato tem por objeto a prestacao de servicos "
        "de consultoria em tecnologia da informacao, incluindo "
        "desenvolvimento de software, manutencao e suporte tecnico.",
        "Clausula 3: Do valor e pagamento.",
        "O valor total dos servicos e de R$ 50.000,00 (cinquenta mil reais), "
        "a ser pago em 10 parcelas mensais de R$ 5.000,00.",
        "Clausula 4: Do prazo.",
        "O presente contrato vigora por 12 meses a partir da data "
        "de assinatura, podendo ser renovado mediante acordo.",
    ]
    for p in paragraphs:
        pdf.multi_cell(0, 6, p)
        pdf.ln(3)

    return pdf.output()


def _make_scanned_wine_pdf():
    """PDF 'escaneado' — imagem de carta de vinhos, sem texto selecionavel.

    Renderiza texto como imagem JPEG e embute no PDF.
    pdfplumber NAO vai extrair texto. O fallback visual (pypdfium2 + Gemini) sim.
    """
    from PIL import Image, ImageDraw, ImageFont
    import tempfile

    img = Image.new("RGB", (900, 700), (255, 252, 245))
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("arial.ttf", 36)
        font_section = ImageFont.truetype("arial.ttf", 24)
        font_item = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font_title = ImageFont.load_default(size=36)
        font_section = ImageFont.load_default(size=24)
        font_item = ImageFont.load_default(size=20)

    y = 40
    draw.text((300, y), "Carta de Vinhos", fill="black", font=font_title)
    y += 70

    draw.text((60, y), "Tintos", fill=(120, 30, 30), font=font_section)
    y += 45

    wines = [
        ("1. Trapiche Malbec 2020", "R$ 75,00"),
        ("2. Norton Reserva Cabernet Sauvignon 2019", "R$ 110,00"),
        ("3. Susana Balbo Signature Malbec 2018", "R$ 160,00"),
    ]
    for name, price in wines:
        draw.text((80, y), name, fill="black", font=font_item)
        draw.text((700, y), price, fill="black", font=font_item)
        y += 40

    y += 20
    draw.text((60, y), "Brancos", fill=(30, 80, 30), font=font_section)
    y += 45

    whites = [
        ("4. Terrazas Reserva Chardonnay 2021", "R$ 95,00"),
        ("5. Caro Amancaya Malbec Blend 2020", "R$ 200,00"),
    ]
    for name, price in whites:
        draw.text((80, y), name, fill="black", font=font_item)
        draw.text((700, y), price, fill="black", font=font_item)
        y += 40

    # Salvar imagem como JPEG temporario e embutir no PDF
    tmp_path = os.path.join(tempfile.gettempdir(), "winegod_scan_fixture.jpg")
    img.save(tmp_path, "JPEG", quality=92)

    pdf = FPDF()
    pdf.add_page()
    pdf.image(tmp_path, x=5, y=5, w=200)
    pdf_bytes = pdf.output()

    os.unlink(tmp_path)
    return pdf_bytes


# --- Validacao ---

def _validate_text_extraction(pdf_bytes, label):
    """Testa so a extracao de texto e heuristica (sem Gemini)."""
    import pdfplumber
    import io
    from tools.media import _text_looks_wine_related

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text_pages = []
        for page in pdf.pages[:20]:
            text_pages.append(page.extract_text() or "")
        full_text = "\n\n".join(text_pages).strip()

    wine_related = _text_looks_wine_related(full_text) if len(full_text) > 100 else "N/A (texto curto)"

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Texto extraido por pdfplumber: {len(full_text)} chars")
    if full_text:
        print(f"  Primeiros 200 chars: {full_text[:200]!r}")
    else:
        print(f"  (nenhum texto selecionavel)")
    print(f"  Heuristica wine_related: {wine_related}")

    return full_text, wine_related


def _validate_full_flow(pdf_bytes, label):
    """Roda process_pdf() completo (requer Gemini)."""
    from tools.media import process_pdf

    print(f"\n  --- {label}: process_pdf() ---")

    b64 = base64.b64encode(pdf_bytes).decode()
    result = process_pdf(b64)

    print(f"  status:            {result.get('status')}")
    print(f"  extraction_method: {result.get('extraction_method', 'N/A')}")
    print(f"  wine_count:        {result.get('wine_count', 0)}")
    print(f"  was_truncated:     {result.get('was_truncated', 'N/A')}")
    print(f"  pages_processed:   {result.get('pages_processed', 'N/A')}")

    if result.get("wines"):
        print(f"  Vinhos encontrados:")
        for i, w in enumerate(result["wines"], 1):
            name = w.get("name", "?")
            price = w.get("price", "N/A")
            producer = w.get("producer", "N/A")
            print(f"    {i}. {name} | produtor: {producer} | preco: {price}")
    elif result.get("message"):
        print(f"  Mensagem: {result['message']}")

    return result


if __name__ == "__main__":
    has_key = bool(os.getenv("GEMINI_API_KEY"))
    print(f"GEMINI_API_KEY: {'disponivel' if has_key else 'NAO disponivel'}")
    print(f".env carregado de: {_env_path}")
    print(f".env existe: {os.path.isfile(_env_path)}")

    if not has_key:
        print("\nERRO: GEMINI_API_KEY nao encontrada. Validacao completa impossivel.")
        print(f"Verifique se {_env_path} contem GEMINI_API_KEY=...")
        sys.exit(1)

    # --- Gerar fixtures ---
    pdf_native = _make_native_wine_pdf()
    pdf_contract = _make_non_wine_pdf()
    pdf_scanned = _make_scanned_wine_pdf()

    # --- Validacao de texto + heuristica (pre-Gemini) ---
    text1, wine1 = _validate_text_extraction(pdf_native, "CASO 1: PDF nativo - carta de vinhos")
    assert wine1 is True, f"FALHA: wine_related deveria ser True, got {wine1}"
    print(f"  PASS: heuristica correta")

    text2, wine2 = _validate_text_extraction(pdf_contract, "CASO 2: PDF nativo - contrato")
    assert wine2 is False, f"FALHA: wine_related deveria ser False, got {wine2}"
    print(f"  PASS: heuristica correta")

    text3, wine3 = _validate_text_extraction(pdf_scanned, "CASO 3: PDF escaneado - carta de vinhos")
    assert wine3 == "N/A (texto curto)", \
        f"FALHA: PDF escaneado nao deveria ter texto extraivel, got wine_related={wine3}"
    print(f"  PASS: sem texto selecionavel, fallback visual sera ativado")

    # --- Fluxo completo com Gemini ---
    print(f"\n{'='*60}")
    print("  FLUXO COMPLETO COM GEMINI")
    print(f"{'='*60}")

    # Caso 1: PDF nativo com vinhos
    r1 = _validate_full_flow(pdf_native, "CASO 1: PDF nativo - carta de vinhos")
    assert r1["status"] == "success", f"FALHA: esperava success, got {r1['status']}"
    assert r1.get("extraction_method") == "native_text", \
        f"FALHA: esperava native_text, got {r1.get('extraction_method')}"
    assert r1.get("wine_count", 0) >= 3, \
        f"FALHA: esperava >= 3 vinhos, got {r1.get('wine_count', 0)}"
    print(f"  PASS: {r1['wine_count']} vinhos via native_text\n")

    # Caso 2: contrato (caso negativo)
    r2 = _validate_full_flow(pdf_contract, "CASO 2: PDF nativo - contrato (sem vinho)")
    assert r2["status"] == "no_wines_found", \
        f"FALHA: esperava no_wines_found, got {r2['status']}"
    assert r2.get("extraction_method") == "native_text_no_wine", \
        f"FALHA: esperava native_text_no_wine, got {r2.get('extraction_method')}"
    assert "foto" not in r2.get("message", ""), "FALHA: mensagem menciona 'foto'"
    print(f"  PASS: contrato rejeitado, sem fallback visual, mensagem correta\n")

    # Caso 3: PDF escaneado com carta de vinhos como imagem
    r3 = _validate_full_flow(pdf_scanned, "CASO 3: PDF escaneado - carta de vinhos")
    assert r3["status"] == "success", f"FALHA: esperava success, got {r3['status']}"
    assert r3.get("extraction_method") == "visual_fallback", \
        f"FALHA: esperava visual_fallback, got {r3.get('extraction_method')}"
    assert r3.get("wine_count", 0) >= 2, \
        f"FALHA: esperava >= 2 vinhos no scan, got {r3.get('wine_count', 0)}"
    print(f"  PASS: {r3['wine_count']} vinhos via visual_fallback\n")

    # --- Resultado final ---
    print(f"{'='*60}")
    print(f"  VALIDACAO COMPLETA: 3/3 CASOS PASSARAM")
    print(f"  - PDF nativo:    {r1['wine_count']} vinhos, method={r1['extraction_method']}")
    print(f"  - Contrato:      rejeitado, method={r2['extraction_method']}")
    print(f"  - Escaneado:     {r3['wine_count']} vinhos, method={r3['extraction_method']}")
    print(f"{'='*60}")
