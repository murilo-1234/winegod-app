"""
clean_wines.py — Limpa e normaliza 4.17M vinhos de 50 tabelas vinhos_{pais}
Cria tabela wines_clean no banco local com dados corrigidos.
"""

import gc
import html
import json
import os
import re
import sys
import time
import unicodedata

import psycopg2
from psycopg2.extras import execute_values

LOCAL_URL = os.environ.get(
    "WINEGOD_LOCAL_URL",
    "postgresql://postgres:postgres123@localhost:5432/winegod_db",
)

BATCH_SIZE = 5000

# Mapeamento de encoding quebrado -> correto
ENCODING_FIXES = {
    "Vi\ufffd": "Viñ",
    "Vi�a": "Viña",
    "M\ufffdlinand": "Mélinand",
    "M�linand": "Mélinand",
    "Ch\ufffdteau": "Château",
    "Ch�teau": "Château",
    "Ros\ufffd": "Rosé",
    "Ros�": "Rosé",
    "Cr\ufffdmant": "Crémant",
    "Cr�mant": "Crémant",
    "Cuv\ufffde": "Cuvée",
    "Cuv�e": "Cuvée",
    "S\ufffdo": "São",
    "S�o": "São",
    "Fran\ufffdois": "François",
    "Fran�ois": "François",
    "\ufffd": "",
    "�": "",
}

# Sufixos a remover do final do nome
SUFFIX_PATTERN = re.compile(
    r'\s*[-–—]?\s*'
    r'(?:750\s*ml|1\.5\s*L|1500\s*ml|375\s*ml|3\s*L|3000\s*ml|'
    r'500\s*ml|187\s*ml|6000\s*ml|'
    r'Meia\s+gfa\.?|Magnum|Jeroboam|Double\s+Magnum|Half\s+Bottle)'
    r'\s*$',
    re.IGNORECASE,
)

# Volume em QUALQUER posicao do nome (nao so no final)
VOLUME_ANYWHERE = re.compile(
    r'\b(?:\d+(?:\.\d+)?\s*(?:ml|cl|lt?|litr[eo]s?)\b)'
    r'|\b\d+\s*x\s*\d+(?:\.\d+)?\s*(?:ml|cl|lt?)\b',
    re.IGNORECASE,
)

# Precos no nome — usar Unicode escape para cifrão para evitar ambiguidade
PRICE_PATTERN = re.compile(
    r'(?:R\u0024|USD?|\u0024|€|£|¥|₩)\s*\d+[\.,]?\d*'
    r'|\d+[\.,]\d{2}\s*(?:R\u0024|USD?|\u0024|€|£)'
    r'|\b\d+[\.,]?\d*\s*(?:€|£|¥)',
    re.IGNORECASE,
)

# Itens que NAO sao vinho (para filtrar ou marcar)
NOT_WINE_WORDS = {
    'whisky', 'whiskey', 'scotch', 'bourbon', 'vodka', 'tequila',
    'mezcal', 'cognac', 'brandy', 'grappa', 'cachaça', 'cachaca',
    'rum ', 'gin ', 'sake', 'soju', 'baijiu',
    'cerveja', 'beer', 'lager', 'pilsner', 'stout', 'pale ale', 'ipa ',
    'queijo', 'cheese', 'fromage', 'queso',
    'chocolate', 'azeite', 'olive oil', 'aceite de oliva',
    'gift card', 'gutschein', 'voucher', 'vale presente',
    'red bull', 'coca-cola', 'pepsi', 'refrigerante',
    'ray ban', 'pelucia', 'teddy bear', 'caneca', 'decanter set',
    'captain morgan', 'jose cuervo', 'jack daniels', 'johnnie walker',
    'absolut vodka', 'smirnoff', 'bacardi rum', 'tanqueray',
    'hendricks gin', "hendrick's gin", 'bombay sapphire',
    'sardinha', 'sardine', 'leite', 'milk', 'pao de hamburguer',
    'salada', 'salad', 'cha ', 'tea ', "victoria's secret",
    'wicker hamper', 'hamper', 'candle', 'incense',
    'decanter', 'saca-rolha', 'sacarolha', 'corkscrew', 'wine glass',
    'abridor', 'aerador', 'cooler', 'stopper', 'opener', 'wine rack',
    'termometro', 'taca de', 'copa de', 'balde de gelo',
}

# Palavras de lote/leilão (inuteis para busca de vinho)
LOTE_PATTERN = re.compile(r'^lote\s+\d', re.IGNORECASE)

# Palavras que NAO sao produtores (genericas demais)
NOT_PRODUCER_WORDS = {
    'vinho', 'vino', 'wine', 'wein', 'vin',
    'tinto', 'branco', 'blanco', 'rosado', 'red', 'white',
    'the', 'le', 'la', 'el', 'il', 'los', 'les', 'das', 'del', 'di', 'de', 'do',
    'and', 'und', 'et', 'e', 'y',
    'pack', 'box', 'kit', 'set', 'combo', 'mix',
    'organic', 'organico', 'natural', 'bio',
    'chianti', 'barolo', 'brunello', 'barbaresco', 'amarone',
    'bordeaux', 'bourgogne', 'burgundy', 'champagne', 'rioja',
    'douro', 'dao', 'alentejo', 'vinho verde',
    'espumante', 'rosso', 'bianco', 'langhe', 'alto adige',
    'franciacorta', 'toscana', 'cotes du rhone', 'alsace',
    'sancerre', 'valpolicella', 'finca', 'caja', 'terre',
    'lote', 'lot', 'cru', 'igp', 'igt', 'doc', 'docg', 'aoc', 'aop',
    'reserva', 'reserve', 'gran', 'premium', 'classic',
}

# Pattern para safra (4 digitos entre 1900-2030)
YEAR_PATTERN = re.compile(r'\b(19\d{2}|20[0-3]\d)\b')


def fix_encoding(text):
    """Corrige encoding quebrado (latin1/utf8 mistura)."""
    if not text:
        return text

    # Tentar decodificar latin1 -> utf8 para replacement characters
    try:
        if '\ufffd' in text or '�' in text:
            attempt = text.encode('latin1', errors='ignore').decode('utf-8', errors='ignore')
            if attempt and len(attempt) >= len(text) * 0.5:
                text = attempt
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass

    # Substituicoes conhecidas
    for k, v in ENCODING_FIXES.items():
        if k in text:
            text = text.replace(k, v)

    return text.strip()


def decode_html_entities(text):
    """Decodifica HTML entities (&#8211; -> –, &amp; -> &, etc.)."""
    if not text:
        return text
    if '&' in text:
        text = html.unescape(text)
    return text


def remove_suffixes(name):
    """Remove sufixos de volume, precos e formato do nome."""
    if not name:
        return name
    # 1. Remover volume no final
    cleaned = SUFFIX_PATTERN.sub('', name)
    # 2. Remover volume em qualquer posicao
    cleaned = VOLUME_ANYWHERE.sub('', cleaned)
    # 3. Remover precos
    cleaned = PRICE_PATTERN.sub('', cleaned)
    # 4. Remover trailing dashes e espacos
    cleaned = re.sub(r'\s*[-–—]+\s*$', '', cleaned)
    # 5. Limpar espacos multiplos
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def is_not_wine(name):
    """Verifica se o item NAO e vinho (whisky, cerveja, queijo, etc.)."""
    if not name:
        return False
    lower = name.lower()
    # Lotes de leilão
    if LOTE_PATTERN.match(lower):
        return True
    for word in NOT_WINE_WORDS:
        if word.endswith(' '):
            if word in lower:
                return True
        elif f' {word} ' in f' {lower} ' or lower.startswith(word) or lower.endswith(word):
            return True
    return False


def remove_duplicate_vintage(name, safra):
    """Remove safra duplicada no nome (ex: 'Reserva 2018 2018' -> 'Reserva 2018')."""
    if not name or not safra:
        return name
    safra_str = str(safra)
    # Procura padrao: safra aparecendo 2+ vezes consecutivas no final
    pattern = re.compile(r'(\b' + re.escape(safra_str) + r')\s+' + re.escape(safra_str) + r'\b')
    return pattern.sub(r'\1', name)


def normalizar(texto):
    """Normaliza texto: lowercase, sem acentos, sem caracteres especiais."""
    if not texto:
        return ""
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')
    texto = texto.lower().strip()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto


def extrair_produtor(nome_limpo):
    """Extrai produtor do nome do vinho usando heurísticas."""
    if not nome_limpo:
        return None

    name = nome_limpo.strip()

    # Remover safra do nome para analise
    name_no_year = YEAR_PATTERN.sub('', name).strip()
    name_no_year = re.sub(r'\s+', ' ', name_no_year)

    # Se nome tem poucas palavras, dificil extrair produtor
    words = name_no_year.split()
    if len(words) < 2:
        return None

    # Palavras que indicam inicio do nome do vinho (nao do produtor)
    wine_keywords = {
        'reserva', 'reserve', 'gran', 'grand', 'grande', 'cru',
        'premier', 'cuvee', 'cuvée', 'brut', 'extra', 'blanc',
        'rouge', 'noir', 'rosé', 'rose', 'tinto', 'blanco',
        'crianza', 'roble', 'seleccion', 'selection', 'limited',
        'edition', 'special', 'premium', 'classic', 'classico',
        'superiore', 'riserva', 'single', 'vineyard', 'estate',
        'old', 'vines', 'vintage', 'barrel', 'aged', 'select',
        'family', 'private', 'bin', 'block', 'lot',
    }

    # Tipos de vinho que nao sao produtor
    wine_types = {
        'cabernet', 'sauvignon', 'merlot', 'pinot', 'chardonnay',
        'syrah', 'shiraz', 'malbec', 'tempranillo', 'sangiovese',
        'nebbiolo', 'riesling', 'gewurztraminer', 'viognier',
        'grenache', 'mourvedre', 'carmenere', 'tannat',
        'prosecco', 'champagne', 'cava', 'lambrusco',
        'zinfandel', 'primitivo', 'barbera', 'dolcetto',
        'garnacha', 'monastrell', 'albarino', 'verdejo',
        'torrontes', 'bonarda', 'touriga', 'nacional',
    }

    # Padroes comuns: "Chateau X ...", "Domaine X ...", "Bodega X ..."
    estate_prefixes = [
        'chateau', 'château', 'domaine', 'bodega', 'bodegas',
        'casa', 'cantina', 'tenuta', 'fattoria', 'podere',
        'weingut', 'quinta', 'herdade', 'cave', 'caves',
        'maison', 'clos', 'baron', 'conte', 'marchesi',
        'viña', 'vina', 'vinícola', 'vinicola',
    ]

    lower_words = [w.lower() for w in words]

    # Caso 1: Comeca com prefixo de propriedade
    for prefix in estate_prefixes:
        if lower_words[0] == prefix and len(words) >= 2:
            # Produtor = prefixo + proxima(s) palavra(s) ate encontrar keyword
            producer_parts = [words[0]]
            for i, w in enumerate(words[1:], 1):
                wl = w.lower()
                if wl in wine_keywords or wl in wine_types:
                    break
                producer_parts.append(w)
                if i >= 3:  # maximo 4 palavras no produtor
                    break
            if len(producer_parts) >= 2:
                return ' '.join(producer_parts)

    # Caso 1b: Comeca com artigo + nome proprio (ex: "Le Petit Mouton", "La Crema")
    articles = {'le', 'la', 'les', 'il', 'el', 'los', 'das', 'the'}
    if lower_words[0] in articles and len(words) >= 3:
        producer_parts = [words[0], words[1]]
        for i, w in enumerate(words[2:], 2):
            wl = w.lower()
            if wl in wine_keywords or wl in wine_types:
                break
            if YEAR_PATTERN.match(w):
                break
            producer_parts.append(w)
            if i >= 3:
                break
        if len(producer_parts) >= 2:
            return ' '.join(producer_parts)

    # Caso 2: Primeira palavra nao e keyword/tipo/generica -> provavelmente produtor
    if (lower_words[0] not in wine_keywords
            and lower_words[0] not in wine_types
            and lower_words[0] not in NOT_PRODUCER_WORDS
            and len(lower_words[0]) > 1):
        producer_parts = [words[0]]
        for i, w in enumerate(words[1:], 1):
            wl = w.lower()
            if wl in wine_keywords or wl in wine_types or wl in NOT_PRODUCER_WORDS:
                break
            # Se encontrar ano, parar antes
            if YEAR_PATTERN.match(w):
                break
            producer_parts.append(w)
            if i >= 2:  # maximo 3 palavras sem prefixo
                break
        if producer_parts:
            result = ' '.join(producer_parts)
            # Rejeitar se parece dominio de loja
            if '.' in result and any(tld in result.lower() for tld in ['.com', '.net', '.cl', '.br', '.co']):
                return None
            return result

    return None


def get_country_tables(conn):
    """Descobre as tabelas vinhos_{pais} existentes."""
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name LIKE 'vinhos_%'
          AND table_name NOT LIKE '%_fontes'
        ORDER BY table_name
    """)
    tables = [row[0] for row in cur.fetchall()]
    cur.close()
    return tables


def create_wines_clean(conn):
    """Cria (ou recria) a tabela wines_clean."""
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS wines_clean CASCADE")
    cur.execute("""
        CREATE TABLE wines_clean (
            id SERIAL PRIMARY KEY,
            pais_tabela VARCHAR(5) NOT NULL,
            id_original INTEGER NOT NULL,
            nome_original TEXT,
            nome_limpo TEXT NOT NULL,
            nome_normalizado TEXT NOT NULL,
            produtor_extraido TEXT,
            produtor_normalizado TEXT,
            safra INTEGER,
            tipo TEXT,
            pais TEXT,
            regiao TEXT,
            sub_regiao TEXT,
            uvas TEXT,
            rating REAL,
            total_ratings INTEGER,
            preco REAL,
            moeda VARCHAR(10),
            preco_min REAL,
            preco_max REAL,
            url_imagem TEXT,
            hash_dedup VARCHAR(64),
            ean_gtin TEXT,
            fontes TEXT,
            total_fontes INTEGER,
            UNIQUE(pais_tabela, id_original)
        )
    """)
    cur.execute("CREATE INDEX idx_wc_nome_norm ON wines_clean (nome_normalizado)")
    cur.execute("CREATE INDEX idx_wc_produtor_norm ON wines_clean (produtor_normalizado)")
    cur.execute("CREATE INDEX idx_wc_hash ON wines_clean (hash_dedup) WHERE hash_dedup IS NOT NULL")
    cur.execute("CREATE INDEX idx_wc_pais_tipo ON wines_clean (pais, tipo)")
    cur.execute("CREATE INDEX idx_wc_safra ON wines_clean (safra) WHERE safra IS NOT NULL")
    cur.execute("CREATE INDEX idx_wc_ean ON wines_clean (ean_gtin) WHERE ean_gtin IS NOT NULL")
    conn.commit()
    cur.close()
    print("Tabela wines_clean criada.")


def create_wines_clean_if_not_exists(conn):
    """Cria a tabela wines_clean se nao existir (para execucao paralela)."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wines_clean (
            id SERIAL PRIMARY KEY,
            pais_tabela VARCHAR(5) NOT NULL,
            id_original INTEGER NOT NULL,
            nome_original TEXT,
            nome_limpo TEXT NOT NULL,
            nome_normalizado TEXT NOT NULL,
            produtor_extraido TEXT,
            produtor_normalizado TEXT,
            safra INTEGER,
            tipo TEXT,
            pais TEXT,
            regiao TEXT,
            sub_regiao TEXT,
            uvas TEXT,
            rating REAL,
            total_ratings INTEGER,
            preco REAL,
            moeda VARCHAR(10),
            preco_min REAL,
            preco_max REAL,
            url_imagem TEXT,
            hash_dedup VARCHAR(64),
            ean_gtin TEXT,
            fontes TEXT,
            total_fontes INTEGER,
            UNIQUE(pais_tabela, id_original)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wc_nome_norm ON wines_clean (nome_normalizado)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wc_produtor_norm ON wines_clean (produtor_normalizado)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wc_hash ON wines_clean (hash_dedup) WHERE hash_dedup IS NOT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wc_pais_tipo ON wines_clean (pais, tipo)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wc_safra ON wines_clean (safra) WHERE safra IS NOT NULL")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wc_ean ON wines_clean (ean_gtin) WHERE ean_gtin IS NOT NULL")
    conn.commit()
    cur.close()
    print("Tabela wines_clean verificada/criada.")


def parse_safra(safra_val):
    """Converte safra para inteiro."""
    if safra_val is None:
        return None
    try:
        year = int(float(str(safra_val)))
        if 1900 <= year <= 2030:
            return year
    except (ValueError, TypeError):
        pass
    return None


def process_wine(row, pais_code):
    """Processa um vinho e retorna tupla para INSERT."""
    (
        id_orig, nome, safra, tipo, pais, regiao, sub_regiao,
        uvas, rating, total_ratings, preco, moeda,
        preco_min, preco_max, url_imagem, hash_dedup,
        ean_gtin, fontes, total_fontes
    ) = row

    nome_original = nome
    encoding_fixed = False

    # 1. Decode HTML entities PRIMEIRO
    nome_limpo = decode_html_entities(nome) if nome else ""

    # 2. Fix encoding
    nome_limpo = fix_encoding(nome_limpo) if nome_limpo else ""
    if nome_limpo != nome and nome:
        encoding_fixed = True

    # 3. Parse safra
    safra_int = parse_safra(safra)

    # 4. Remove duplicate vintage
    if safra_int:
        nome_limpo = remove_duplicate_vintage(nome_limpo, safra_int)

    # 5. Remove suffixes (volume, precos, trailing dashes)
    nome_limpo = remove_suffixes(nome_limpo)

    if not nome_limpo:
        nome_limpo = nome_original or ""

    # 5. Extract producer
    produtor = extrair_produtor(nome_limpo)
    produtor_norm = normalizar(produtor) if produtor else None

    # 6. Normalize name
    nome_norm = normalizar(nome_limpo)

    # Fix encoding on other text fields
    pais = fix_encoding(pais) if pais else pais
    regiao = fix_encoding(regiao) if regiao else regiao
    sub_regiao = fix_encoding(sub_regiao) if sub_regiao else sub_regiao
    uvas = fix_encoding(uvas) if uvas else uvas

    return (
        pais_code[:5],
        id_orig,
        nome_original,
        nome_limpo,
        nome_norm,
        produtor,
        produtor_norm,
        safra_int,
        tipo,
        pais,
        regiao,
        sub_regiao,
        uvas,
        float(rating) if rating is not None else None,
        int(total_ratings) if total_ratings is not None else None,
        float(preco) if preco is not None else None,
        moeda[:10] if moeda else moeda,
        float(preco_min) if preco_min is not None else None,
        float(preco_max) if preco_max is not None else None,
        url_imagem,
        hash_dedup[:64] if hash_dedup else hash_dedup,
        ean_gtin,
        json.dumps(fontes) if isinstance(fontes, (dict, list)) else fontes,
        int(total_fontes) if total_fontes is not None else None,
    ), encoding_fixed


def process_table(conn, table_name):
    """Processa uma tabela vinhos_{pais}."""
    pais_code = table_name.replace('vinhos_', '')

    cur_read = conn.cursor()
    cur_write = conn.cursor()

    # Contar registros
    cur_read.execute(f'SELECT COUNT(*) FROM "{table_name}"')
    total = cur_read.fetchone()[0]

    if total == 0:
        print(f"  [{pais_code.upper()}] Vazia, pulando.")
        cur_read.close()
        cur_write.close()
        return 0, 0, 0

    print(f"  [{pais_code.upper()}] {total:,} vinhos para processar...")

    # Ler em batches usando cursor server-side
    cur_read.execute(f"""
        SELECT id, nome, safra, tipo_nome, pais_nome, regiao_nome, sub_regiao,
               uvas, rating_medio, total_ratings, preco, moeda,
               preco_min, preco_max, url_imagem, hash_dedup,
               ean_gtin, fontes, total_fontes
        FROM "{table_name}"
    """)

    batch = []
    processed = 0
    encoding_count = 0
    produtor_count = 0
    hash_count = 0

    insert_sql = """
        INSERT INTO wines_clean (
            pais_tabela, id_original, nome_original, nome_limpo, nome_normalizado,
            produtor_extraido, produtor_normalizado, safra, tipo, pais,
            regiao, sub_regiao, uvas, rating, total_ratings,
            preco, moeda, preco_min, preco_max, url_imagem,
            hash_dedup, ean_gtin, fontes, total_fontes
        ) VALUES %s
        ON CONFLICT (pais_tabela, id_original) DO NOTHING
    """

    while True:
        rows = cur_read.fetchmany(BATCH_SIZE)
        if not rows:
            break

        for row in rows:
            # Filtrar itens nao-vinho
            nome_raw = row[1] or ""
            if is_not_wine(nome_raw):
                continue

            result, enc_fixed = process_wine(row, pais_code)

            # Pular se nome_normalizado ficou vazio
            if not result[4]:  # nome_normalizado
                continue

            batch.append(result)
            if enc_fixed:
                encoding_count += 1
            if result[5]:  # produtor_extraido
                produtor_count += 1
            if result[20]:  # hash_dedup
                hash_count += 1

        if len(batch) >= BATCH_SIZE:
            execute_values(cur_write, insert_sql, batch, page_size=BATCH_SIZE)
            conn.commit()
            processed += len(batch)
            batch = []
            pct = (processed / total) * 100
            print(f"  [{pais_code.upper()}] {processed:,}/{total:,} processados ({pct:.1f}%)")

    # Inserir resto
    if batch:
        execute_values(cur_write, insert_sql, batch, page_size=BATCH_SIZE)
        conn.commit()
        processed += len(batch)

    print(f"  [{pais_code.upper()}] {processed:,}/{total:,} processados (100%)")
    print(f"    Encoding corrigido: {encoding_count:,} | Produtor extraido: {produtor_count:,} | Com hash: {hash_count:,}")

    cur_read.close()
    cur_write.close()

    return encoding_count, produtor_count, hash_count


def main():
    print("=" * 60)
    print("CLEAN WINES — Limpar e normalizar vinhos de lojas")
    print("=" * 60)

    conn = psycopg2.connect(LOCAL_URL)
    print(f"Conectado ao banco local.")

    # Aceitar paises como argumento (ex: python clean_wines.py br us ar)
    # Se nenhum argumento, processa TODOS
    filter_countries = [a.lower() for a in sys.argv[1:]] if len(sys.argv) > 1 else []

    # Criar tabela (so faz DROP se processar TODOS, senao CREATE IF NOT EXISTS)
    if filter_countries:
        create_wines_clean_if_not_exists(conn)
    else:
        create_wines_clean(conn)

    # Listar tabelas
    tables = get_country_tables(conn)
    if filter_countries:
        tables = [t for t in tables if t.replace('vinhos_', '') in filter_countries]
    print(f"\n{len(tables)} tabelas a processar: {', '.join(t.replace('vinhos_', '').upper() for t in tables)}")

    total_encoding = 0
    total_produtor = 0
    total_hash = 0
    start = time.time()

    for i, table in enumerate(tables, 1):
        print(f"\n[{i}/{len(tables)}] Processando {table}...")
        enc, prod, hsh = process_table(conn, table)
        total_encoding += enc
        total_produtor += prod
        total_hash += hsh
        gc.collect()

    # Estatisticas finais
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM wines_clean")
    total_rows = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE produtor_extraido IS NOT NULL")
    with_produtor = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM wines_clean WHERE hash_dedup IS NOT NULL")
    with_hash = cur.fetchone()[0]
    cur.close()

    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print("RESULTADO FINAL")
    print("=" * 60)
    print(f"  Total vinhos em wines_clean: {total_rows:,}")
    print(f"  Encoding corrigido:          {total_encoding:,}")
    print(f"  Com produtor extraido:       {with_produtor:,} ({with_produtor/max(total_rows,1)*100:.1f}%)")
    print(f"  Com hash_dedup:              {with_hash:,} ({with_hash/max(total_rows,1)*100:.1f}%)")
    print(f"  Tempo total:                 {elapsed/60:.1f} minutos")
    print("=" * 60)

    conn.close()
    print("Concluido!")


if __name__ == "__main__":
    main()
