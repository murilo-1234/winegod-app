"""Test PDF pipeline improvements: heuristic, metadata, error messages.

Runs offline (no DB, no Gemini): python -m tests.test_pdf_pipeline
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.media import (
    _text_looks_wine_related,
    _deduplicate_wines,
    _split_text_into_chunks,
)
import tools.media as media


# --- _text_looks_wine_related ---

def test_wine_text_detected():
    """Carta de vinhos em portugues deve ser detectada como wine-related."""
    text = """
    Carta de Vinhos
    Tintos
    1. Alamos Malbec 2020 - R$ 89,00
    2. Casillero del Diablo Cabernet Sauvignon 2019 - R$ 65,00
    3. Marques de Casa Concha Merlot 2018 - R$ 120,00
    """
    assert _text_looks_wine_related(text), "Carta de vinhos deveria ser detectada"


def test_wine_text_english():
    """Wine list in English should be detected."""
    text = """
    Wine List
    Red Wines
    Chateau Margaux 2015 - Cabernet Sauvignon blend
    Domaine Romanee-Conti Pinot Noir 2018
    """
    assert _text_looks_wine_related(text), "English wine list should be detected"


def test_non_wine_text_rejected():
    """Contrato juridico nao deve ser detectado como wine-related."""
    text = """
    CONTRATO DE PRESTACAO DE SERVICOS
    Clausula 1: Das partes contratantes
    A empresa XYZ Ltda, inscrita no CNPJ 12.345.678/0001-00,
    doravante denominada CONTRATANTE, e a empresa ABC S.A.,
    inscrita no CNPJ 98.765.432/0001-00, doravante denominada
    CONTRATADA, firmam o presente contrato de prestacao de servicos.
    Clausula 2: Do objeto
    O presente contrato tem por objeto a prestacao de servicos de
    consultoria em tecnologia da informacao.
    """
    assert not _text_looks_wine_related(text), "Contrato nao deveria ser detectado como vinho"


def test_non_wine_corporate_rejected():
    """Relatorio corporativo nao deve ser detectado."""
    text = """
    Annual Report 2025
    Revenue grew 15% year over year. Operating margins improved
    from 22% to 25%. We expanded to 3 new markets including
    Southeast Asia and Latin America. Our customer satisfaction
    score reached 4.5/5.0.
    """
    assert not _text_looks_wine_related(text), "Relatorio corporativo nao e vinho"


def test_long_preface_with_wines_after():
    """Catalogo com prefacio longo e vinhos so no meio/fim deve ser detectado."""
    preface = (
        "Bem-vindo ao nosso restaurante. Fundado em 1985, temos uma tradicao "
        "de excelencia culinaria. Nossa equipe de cozinheiros premiados prepara "
        "pratos com ingredientes selecionados das melhores fazendas do pais. "
        "Ambiente acolhedor e sofisticado para todas as ocasioes. "
    ) * 30  # ~6000 chars de prefacio sem keywords de vinho
    wine_section = """
    Carta de Vinhos
    Tintos
    1. Alamos Malbec 2020 - R$ 89,00
    2. Casillero del Diablo Cabernet Sauvignon 2019 - R$ 65,00
    """
    text = preface + wine_section
    assert len(preface) > 5000, "Prefacio precisa ser >5000 chars para testar amostragem"
    assert _text_looks_wine_related(text), "Catalogo com prefacio longo deve ser detectado"


def test_edge_case_one_keyword():
    """Texto com apenas 1 keyword nao deve passar (min_matches=2)."""
    text = "O restaurante serve um ótimo vinho com a refeição principal."
    assert not _text_looks_wine_related(text), "1 keyword sozinha nao deve bastar"


def test_edge_case_two_keywords():
    """Texto com 2+ keywords deve passar."""
    text = "Temos vinho tinto e branco disponíveis."
    assert _text_looks_wine_related(text), "2 keywords devem ser suficientes"


# --- _deduplicate_wines (confirmar que nao quebramos) ---

def test_dedup_preserves_unique():
    """Vinhos com nomes diferentes devem permanecer."""
    wines = [
        {"name": "Alamos Malbec", "price": "R$ 89"},
        {"name": "Casillero Cabernet", "price": "R$ 65"},
    ]
    result = _deduplicate_wines(wines)
    assert len(result) == 2


def test_dedup_merges_same_name():
    """Vinhos com mesmo nome (case-insensitive) e produtor ausente em ambos devem ser mergeados."""
    wines = [
        {"name": "Alamos Malbec", "price": "R$ 89", "vintage": None},
        {"name": "alamos malbec", "price": None, "vintage": "2020"},
    ]
    result = _deduplicate_wines(wines)
    assert len(result) == 1
    assert result[0]["price"] == "R$ 89"
    assert result[0]["vintage"] == "2020"


def test_dedup_keeps_different_producers_same_name():
    """Vinhos com mesmo nome mas produtores DIFERENTES NAO devem colapsar.

    Caso real: 'Brut Reserve' aparece em cartas de Champagne para varios
    produtores distintos (Bereche, Billecart-Salmon, Philipponnat). O dedup
    antigo (chave = name) colapsava todos em um, derrubando ~38% da carta
    do Elephante. O fix usa chave (name, producer) e preserva os 3 vinhos.
    """
    wines = [
        {"name": "Brut Reserve", "producer": "Bereche", "price": "170"},
        {"name": "Brut Reserve", "producer": "Billecart-Salmon", "price": "180"},
        {"name": "Brut Reserve", "producer": "Philipponnat", "price": "125"},
    ]
    result = _deduplicate_wines(wines)
    assert len(result) == 3, f"Esperava 3 vinhos distintos, recebi {len(result)}"
    producers = sorted((r.get("producer") or "").lower() for r in result)
    assert producers == ["bereche", "billecart-salmon", "philipponnat"]


def test_dedup_merges_same_name_same_producer():
    """Mesmo nome + mesmo produtor (case-insensitive) AINDA deve colapsar."""
    wines = [
        {"name": "Brut Reserve", "producer": "Bereche", "price": "170", "vintage": None},
        {"name": "brut reserve", "producer": "BERECHE", "price": None, "vintage": "2018"},
    ]
    result = _deduplicate_wines(wines)
    assert len(result) == 1
    assert result[0]["price"] == "170"
    assert result[0]["vintage"] == "2018"


# --- _split_text_into_chunks (P3A.1 chunked recovery) ---

def test_split_chunks_short_text_single():
    """Texto curto cabe em 1 unico chunk."""
    text = "Alamos Malbec R$ 89"
    chunks = _split_text_into_chunks(text, chunk_size=100)
    assert chunks == [text], f"Expected 1 chunk with full text, got {chunks}"


def test_split_chunks_long_text_multiple():
    """Texto longo e dividido em varios chunks, e todos os paragrafos sao preservados."""
    paragraphs = [f"Wine {i}: Producer {i} price R$ {i*10}" for i in range(10)]
    text = "\n\n".join(paragraphs)
    chunks = _split_text_into_chunks(text, chunk_size=80)
    assert len(chunks) >= 2, f"Expected multiple chunks, got {len(chunks)}"
    combined = " ".join(chunks)
    for p in paragraphs:
        assert p in combined, f"Paragrafo perdido: {p!r}"


def test_split_chunks_respects_size_approximately():
    """Chunks devem ficar proximos do chunk_size limite (tolerancia 2x)."""
    text = "\n\n".join([f"Linha curta numero {i}" for i in range(100)])
    chunks = _split_text_into_chunks(text, chunk_size=200)
    for chunk in chunks:
        assert len(chunk) <= 400, f"Chunk excede 2x limite: {len(chunk)} chars"


# --- _extract_wines_native_chunked (com mock de Gemini) ---

def test_extract_chunked_combines_wines_from_chunks():
    """Multiples chunks sucedidos devem ter vinhos combinados (parallel-safe)."""
    original = media._gemini_generate

    def fake_gen(contents):
        # Discriminacao por conteudo do chunk, sem depender de ordem de chamada
        if "primeiro" in contents:
            return '{"wines": [{"name": "Wine A", "price": "10"}]}'
        if "segundo" in contents:
            return '{"wines": [{"name": "Wine B", "price": "20"}]}'
        return '{"wines": []}'

    media._gemini_generate = fake_gen
    try:
        text = "primeiro paragrafo\n\nsegundo paragrafo"
        wines = media._extract_wines_native_chunked(text, chunk_size=25)
        assert len(wines) == 2, f"Expected 2 wines, got {len(wines)}"
        names = {w["name"] for w in wines}
        assert names == {"Wine A", "Wine B"}, f"Wrong names: {names}"
    finally:
        media._gemini_generate = original


def test_extract_chunked_skips_failed_chunks():
    """Chunks que raise devem ser pulados; sucessos continuam (parallel-safe)."""
    original = media._gemini_generate

    def fake_gen(contents):
        # Chunk com 'dois' falha; outros sucedem (sem race em call_count)
        if "dois" in contents:
            raise ValueError("simulated Gemini JSON failure")
        return '{"wines": [{"name": "Wine"}]}'

    media._gemini_generate = fake_gen
    try:
        text = "para um\n\npara dois\n\npara tres"
        wines = media._extract_wines_native_chunked(text, chunk_size=12)
        # 3 chunks esperados, chunk 'dois' falha -> 2 vinhos
        assert len(wines) == 2, f"Expected 2 wines from 2 successful chunks, got {len(wines)}"
    finally:
        media._gemini_generate = original


def test_extract_chunked_all_fail_returns_empty():
    """Se todos os chunks falham, retorna lista vazia sem raise."""
    original = media._gemini_generate

    def fake_gen(contents):
        raise ValueError("always fails")

    media._gemini_generate = fake_gen
    try:
        text = "para um\n\npara dois"
        wines = media._extract_wines_native_chunked(text, chunk_size=12)
        assert wines == [], f"Expected empty list, got {wines}"
    finally:
        media._gemini_generate = original


# --- process_pdf integration (branch selection via mocks) ---

def _make_fake_pdfplumber_open(pages_text):
    """Cria fake de pdfplumber.open() que retorna paginas com os textos dados."""
    class _FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class _FakePdf:
        def __init__(self, pages):
            self.pages = [_FakePage(t) for t in pages]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open(path):
        return _FakePdf(pages_text)

    return fake_open


def _run_process_pdf_with_mocks(pages_text, gemini_fn):
    """Helper: roda process_pdf com pdfplumber e gemini mockados."""
    import base64
    import pdfplumber

    original_open = pdfplumber.open
    original_gemini = media._gemini_generate

    pdfplumber.open = _make_fake_pdfplumber_open(pages_text)
    media._gemini_generate = gemini_fn
    try:
        fake_bytes = b"%PDF-1.4\n%fake"
        return media.process_pdf(base64.b64encode(fake_bytes).decode())
    finally:
        pdfplumber.open = original_open
        media._gemini_generate = original_gemini


def test_process_pdf_chunked_recovery_on_parse_failure():
    """Parse failure em native_text + texto wine-related -> chunked recovery ativa."""
    wine_para = "Carta de Vinhos: Alamos Malbec 2020 Cabernet Sauvignon R$ 89"
    long_wine_text = "\n\n".join([wine_para] * 200)

    call_count = [0]

    def fake_gen(contents):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ValueError("Unterminated string at char 42000")
        return '{"wines": [{"name": "Alamos Malbec", "price": "R$ 89"}]}'

    result = _run_process_pdf_with_mocks([long_wine_text], fake_gen)

    assert result.get("status") == "success", f"Expected success, got {result.get('status')}"
    assert result.get("extraction_method") == "native_text_chunked", (
        f"Expected native_text_chunked, got {result.get('extraction_method')}"
    )
    assert result.get("wine_count", 0) >= 1, "Expected at least 1 wine from chunked recovery"
    assert call_count[0] >= 2, (
        f"Expected Gemini called >=2 times (1 failed + >=1 chunks), got {call_count[0]}"
    )


def test_process_pdf_no_chunked_recovery_for_non_wine_text():
    """Texto longo NAO wine-related NAO deve triggar chunked recovery."""
    contract_para = (
        "Clausula: O presente contrato de prestacao de servicos tem por objeto "
        "a consultoria em tecnologia da informacao, incluindo desenvolvimento "
        "de software, manutencao de sistemas e treinamento tecnico."
    )
    long_contract = "\n\n".join([contract_para] * 50)

    call_count = [0]

    def fake_gen(contents):
        call_count[0] += 1
        return '{"wines": []}'

    result = _run_process_pdf_with_mocks([long_contract], fake_gen)

    assert result.get("status") == "no_wines_found", f"Expected no_wines_found, got {result.get('status')}"
    assert result.get("extraction_method") == "native_text_no_wine", (
        f"Expected native_text_no_wine, got {result.get('extraction_method')}"
    )
    # Apenas 1 call (Branch 1), sem chunked recovery nem visual fallback
    assert call_count[0] == 1, (
        f"Expected exactly 1 Gemini call (native_text only), got {call_count[0]}"
    )


def test_process_pdf_native_text_happy_path_unchanged():
    """Caso aprovado: native_text com JSON valido NAO deve triggar chunked recovery."""
    wine_text = (
        "Carta de Vinhos do Restaurante\nTintos\n"
        "Alamos Malbec 2020 Cabernet Sauvignon Reserva R$ 89,00\n"
        "Casillero del Diablo Merlot 2019 Chile R$ 65,00\n"
        "Marques de Casa Concha Cabernet R$ 120,00\n"
    )

    call_count = [0]

    def fake_gen(contents):
        call_count[0] += 1
        return '{"wines": [{"name": "Alamos Malbec", "price": "R$ 89"}]}'

    result = _run_process_pdf_with_mocks([wine_text], fake_gen)

    assert result.get("status") == "success"
    assert result.get("extraction_method") == "native_text", (
        f"Expected native_text (not chunked), got {result.get('extraction_method')}"
    )
    assert call_count[0] == 1, f"Expected 1 Gemini call (happy path), got {call_count[0]}"


def test_process_pdf_long_text_skips_monolithic_call():
    """P3A.2: texto wine-related muito longo (>15000) deve pular chamada monolitica
    e ir direto para chunked paralelo. Nenhuma chamada deve receber o texto inteiro.
    """
    wine_para = "Vinho tinto Alamos Malbec 2020 Cabernet Sauvignon Argentina R$ 89,00"
    long_text = "\n\n".join([wine_para] * 250)
    assert len(long_text) > 15000, f"Test setup precisa >15000 chars, got {len(long_text)}"

    contents_seen_lengths = []

    def fake_gen(contents):
        contents_seen_lengths.append(len(contents))
        return '{"wines": [{"name": "Alamos Malbec", "price": "R$ 89"}]}'

    result = _run_process_pdf_with_mocks([long_text], fake_gen)

    assert result.get("status") == "success", f"Expected success, got {result.get('status')}"
    assert result.get("extraction_method") == "native_text_chunked", (
        f"Expected native_text_chunked (direct), got {result.get('extraction_method')}"
    )
    # Nenhuma chamada deve carregar o texto inteiro: monolitica esta pulada.
    # Texto inteiro >15000 chars + prompt ~1000 = >16000 chars na chamada.
    # Chunks: prompt ~1000 + chunk_size 8000 = ~9000 chars maximo.
    max_call_len = max(contents_seen_lengths) if contents_seen_lengths else 0
    assert max_call_len < 12000, (
        f"Found a call with {max_call_len} chars (full text), monolithic was NOT skipped"
    )
    assert len(contents_seen_lengths) >= 2, (
        f"Expected >=2 chunked calls, got {len(contents_seen_lengths)}"
    )


def test_process_pdf_scanned_pdf_skips_chunked_recovery():
    """PDF escaneado (sem texto) NAO deve triggar chunked recovery (mantem Branch 2)."""
    import base64
    import pdfplumber

    original_open = pdfplumber.open
    original_chunked = media._extract_wines_native_chunked
    original_gemini = media._gemini_generate

    chunked_called = [False]

    def fake_chunked(*args, **kwargs):
        chunked_called[0] = True
        return []

    def fake_gemini(contents):
        return '{"wines": []}'

    pdfplumber.open = _make_fake_pdfplumber_open([""])  # pagina vazia (scan)
    media._extract_wines_native_chunked = fake_chunked
    media._gemini_generate = fake_gemini
    try:
        fake_bytes = b"%PDF-1.4\n%fake"
        # process_pdf vai tentar visual_fallback e pode retornar error por fake PDF;
        # so importa que chunked recovery NAO tenha sido chamado
        result = media.process_pdf(base64.b64encode(fake_bytes).decode())
        assert not chunked_called[0], (
            "Chunked recovery NAO deve ser chamado para PDF escaneado (Branch 1 nao roda)"
        )
        # E o metodo nao deve ser native_text_chunked
        assert result.get("extraction_method") != "native_text_chunked"
    finally:
        pdfplumber.open = original_open
        media._extract_wines_native_chunked = original_chunked
        media._gemini_generate = original_gemini


# --- Runner ---

if __name__ == "__main__":
    tests = [
        test_wine_text_detected,
        test_wine_text_english,
        test_non_wine_text_rejected,
        test_non_wine_corporate_rejected,
        test_long_preface_with_wines_after,
        test_edge_case_one_keyword,
        test_edge_case_two_keywords,
        test_dedup_preserves_unique,
        test_dedup_merges_same_name,
        test_dedup_keeps_different_producers_same_name,
        test_dedup_merges_same_name_same_producer,
        # P3A.1 chunked recovery
        test_split_chunks_short_text_single,
        test_split_chunks_long_text_multiple,
        test_split_chunks_respects_size_approximately,
        test_extract_chunked_combines_wines_from_chunks,
        test_extract_chunked_skips_failed_chunks,
        test_extract_chunked_all_fail_returns_empty,
        test_process_pdf_chunked_recovery_on_parse_failure,
        test_process_pdf_no_chunked_recovery_for_non_wine_text,
        test_process_pdf_native_text_happy_path_unchanged,
        test_process_pdf_long_text_skips_monolithic_call,
        test_process_pdf_scanned_pdf_skips_chunked_recovery,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
