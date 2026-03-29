#!/usr/bin/env python3
"""
fix_wines_clean_final.py -- Fix cirurgico nos 5 problemas da auditoria.
NAO recria a tabela. Faz UPDATE/DELETE direto na wines_clean.

Problemas:
  CHECK 5:  2 HTML entities
  CHECK 7:  1,995 precos no nome
  CHECK 12: 351 nomes >200 chars
  CHECK 16: 233 safras duplicadas
  CHECK 22: 113 acessorios (nao sao vinho)

Uso:
  python scripts/fix_wines_clean_final.py
  python scripts/fix_wines_clean_final.py --dry-run   # mostra sem alterar
"""

import html
import os
import re
import sys
import unicodedata

import psycopg2

LOCAL_URL = os.environ.get(
    "WINEGOD_LOCAL_URL",
    "postgresql://postgres:postgres123@localhost:5432/winegod_db",
)

DRY_RUN = "--dry-run" in sys.argv


def normalizar(texto):
    """Normaliza texto: lowercase, sem acentos, sem especiais."""
    if not texto:
        return ""
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('ASCII')
    texto = texto.lower().strip()
    texto = re.sub(r'[^a-z0-9\s]', '', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto


def clean_trailing(text):
    """Remove espacos extras e tracos soltos no final."""
    text = re.sub(r'\s*[-\u2013\u2014]+\s*$', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def main():
    conn = psycopg2.connect(LOCAL_URL)
    cur = conn.cursor()

    mode = "DRY-RUN (nenhuma alteracao)" if DRY_RUN else "EXECUTANDO alteracoes"
    print("=" * 60)
    print(f"FIX CIRURGICO -- wines_clean [{mode}]")
    print("=" * 60)

    # ────────────────────────────────────────────────────────────
    # FIX 1: CHECK 5 -- HTML entities (2 registros)
    # ────────────────────────────────────────────────────────────
    print("\n--- FIX 1: HTML entities (CHECK 5) ---")
    cur.execute("""
        SELECT id, nome_limpo FROM wines_clean
        WHERE nome_limpo LIKE '%%&#%%'
           OR nome_limpo LIKE '%%&amp;%%'
           OR nome_limpo LIKE '%%&nbsp;%%'
           OR nome_limpo LIKE '%%&lt;%%'
           OR nome_limpo LIKE '%%&gt;%%'
           OR nome_limpo LIKE '%%&quot;%%'
    """)
    rows = cur.fetchall()
    print(f"  Encontrados: {len(rows)}")
    fix1_count = 0
    for row_id, nome in rows:
        nome_fixed = html.unescape(nome)
        if nome_fixed != nome:
            nome_norm = normalizar(nome_fixed)
            print(f"  [{row_id}] {nome[:80]}")
            print(f"    ->{nome_fixed[:80]}")
            if not DRY_RUN:
                cur.execute(
                    "UPDATE wines_clean SET nome_limpo = %s, nome_normalizado = %s WHERE id = %s",
                    (nome_fixed, nome_norm, row_id),
                )
            fix1_count += 1
    if not DRY_RUN:
        conn.commit()
    print(f"  Corrigidos: {fix1_count}")

    # ────────────────────────────────────────────────────────────
    # FIX 2: CHECK 7 -- Precos no nome (1,995 registros)
    # ────────────────────────────────────────────────────────────
    print("\n--- FIX 2: Precos no nome (CHECK 7) ---")
    cur.execute("""
        SELECT id, nome_limpo FROM wines_clean
        WHERE nome_limpo ~ '[$€£¥₩]'
           OR nome_limpo LIKE '%%R$%%'
    """)
    rows = cur.fetchall()
    print(f"  Encontrados: {len(rows)}")

    # Patterns ordenados do mais especifico ao mais generico
    price_patterns = [
        # R$123,45 ou R$ 123.45 (com ou sem numero)
        re.compile(r'R\$\s*\d*[\.,]?\d*'),
        # USD 123 ou US$123
        re.compile(r'US[D$]\s*\d*[\.,]?\d*'),
        # Numero ANTES do simbolo: 15€, 35$, 18£, 1200¥ (crucial -- faltava antes)
        re.compile(r'\d+[\.,]?\d*\s*[$€£¥₩]'),
        # Simbolo ANTES do numero: $123.45, €15, £12.50
        re.compile(r'[$€£¥₩]\s*\d+[\.,]?\d*'),
        # Numero + codigo moeda: 123 EUR, 45.00 USD
        re.compile(r'\d+[\.,]?\d*\s*(?:USD|EUR|GBP|BRL|KRW|JPY|AUD|CAD|CHF|SEK|NOK|DKK|CZK|PLN|HUF|RON|TRY|ZAR|MXN|CLP|COP|ARS|PEN)\b', re.IGNORECASE),
        # Simbolo de moeda solto (sem numero) -- ultimo recurso
        re.compile(r'[$€£¥₩]'),
    ]

    fix2_count = 0
    fix2_samples = []
    for row_id, nome in rows:
        nome_fixed = nome
        for pat in price_patterns:
            nome_fixed = pat.sub('', nome_fixed)
        nome_fixed = clean_trailing(nome_fixed)

        # Se ficou vazio ou muito curto, manter original (melhor que nada)
        if len(nome_fixed) < 3:
            continue

        if nome_fixed != nome:
            nome_norm = normalizar(nome_fixed)
            if fix2_count < 10:
                fix2_samples.append((nome[:60], nome_fixed[:60]))
            if not DRY_RUN:
                cur.execute(
                    "UPDATE wines_clean SET nome_limpo = %s, nome_normalizado = %s WHERE id = %s",
                    (nome_fixed, nome_norm, row_id),
                )
            fix2_count += 1
    if not DRY_RUN:
        conn.commit()
    for orig, fixed in fix2_samples:
        print(f"  {orig}")
        print(f"  ->{fixed}")
    print(f"  Corrigidos: {fix2_count}")

    # ────────────────────────────────────────────────────────────
    # FIX 3: CHECK 12 -- Nomes longos >200 chars (351 registros)
    # ────────────────────────────────────────────────────────────
    print("\n--- FIX 3: Nomes longos >200 chars (CHECK 12) ---")
    cur.execute("SELECT id, nome_limpo FROM wines_clean WHERE LENGTH(nome_limpo) > 200")
    rows = cur.fetchall()
    print(f"  Encontrados: {len(rows)}")

    fix3_count = 0
    for row_id, nome in rows:
        truncated = nome[:200]
        # Cortar na ultima palavra completa
        last_space = truncated.rfind(' ')
        if last_space > 150:
            truncated = truncated[:last_space]
        nome_norm = normalizar(truncated)
        if fix3_count < 5:
            print(f"  [{row_id}] {len(nome)} chars -> {len(truncated)} chars")
            print(f"    {truncated[:80]}...")
        if not DRY_RUN:
            cur.execute(
                "UPDATE wines_clean SET nome_limpo = %s, nome_normalizado = %s WHERE id = %s",
                (truncated, nome_norm, row_id),
            )
        fix3_count += 1
    if not DRY_RUN:
        conn.commit()
    print(f"  Truncados: {fix3_count}")

    # ────────────────────────────────────────────────────────────
    # FIX 4: CHECK 16 -- Safra duplicada no nome (233 registros)
    # ────────────────────────────────────────────────────────────
    print("\n--- FIX 4: Safra duplicada (CHECK 16) ---")
    cur.execute(r"""
        SELECT id, nome_limpo, safra FROM wines_clean
        WHERE safra IS NOT NULL
          AND nome_limpo ~ (safra::text || '\s+' || safra::text)
    """)
    rows = cur.fetchall()
    print(f"  Encontrados: {len(rows)}")

    fix4_count = 0
    for row_id, nome, safra in rows:
        safra_str = str(safra)
        # Quantificador + para pegar 2, 3, ou mais repeticoes consecutivas
        pattern = re.compile(
            r'(\b' + re.escape(safra_str) + r')(?:\s+' + re.escape(safra_str) + r')+\b'
        )
        nome_fixed = pattern.sub(r'\1', nome)
        if nome_fixed != nome:
            nome_fixed = clean_trailing(nome_fixed)
            nome_norm = normalizar(nome_fixed)
            if fix4_count < 10:
                print(f"  {nome[:60]}")
                print(f"  ->{nome_fixed[:60]}")
            if not DRY_RUN:
                cur.execute(
                    "UPDATE wines_clean SET nome_limpo = %s, nome_normalizado = %s WHERE id = %s",
                    (nome_fixed, nome_norm, row_id),
                )
            fix4_count += 1
    if not DRY_RUN:
        conn.commit()
    print(f"  Corrigidos: {fix4_count}")

    # ────────────────────────────────────────────────────────────
    # FIX 5: CHECK 22 -- Acessorios (113 registros)
    # ────────────────────────────────────────────────────────────
    print("\n--- FIX 5: Acessorios (CHECK 22) ---")
    # Usar EXATAMENTE a mesma regex do auditor (CHECK 22)
    AUDIT_REGEX_22 = r"\y(decanter|saca.?rolha|corkscrew|wine glass|taca|copa|abridor|aerador|balde|cooler|stopper|opener)\y"

    cur.execute(f"SELECT id, nome_limpo FROM wines_clean WHERE LOWER(nome_limpo) ~ '{AUDIT_REGEX_22}' LIMIT 15")
    examples = cur.fetchall()
    for eid, ename in examples[:10]:
        print(f"  [{eid}] {ename[:80]}")

    cur.execute(f"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '{AUDIT_REGEX_22}'")
    count = cur.fetchone()[0]
    print(f"  Total a deletar: {count}")

    if not DRY_RUN:
        cur.execute(f"DELETE FROM wines_clean WHERE LOWER(nome_limpo) ~ '{AUDIT_REGEX_22}'")
        conn.commit()
    print(f"  Deletados: {count}")

    # ────────────────────────────────────────────────────────────
    # VERIFICACAO POS-FIX -- re-roda as mesmas queries do auditor
    # ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("VERIFICACAO POS-FIX")
    print("=" * 60)

    checks = [
        ("CHECK 5  HTML entities",
         "SELECT COUNT(*) FROM wines_clean WHERE nome_limpo LIKE '%%&#%%' OR nome_limpo LIKE '%%&amp;%%' OR nome_limpo LIKE '%%&nbsp;%%'",
         "= 0"),
        ("CHECK 7  Preco no nome",
         "SELECT COUNT(*) FROM wines_clean WHERE nome_limpo ~ '[$€£¥₩]' OR nome_limpo LIKE '%%R$%%'",
         "= 0"),
        ("CHECK 12 Nomes longos",
         "SELECT COUNT(*) FROM wines_clean WHERE LENGTH(nome_limpo) > 200",
         "< 100"),
        ("CHECK 16 Safra duplicada",
         r"SELECT COUNT(*) FROM wines_clean WHERE safra IS NOT NULL AND nome_limpo ~ (safra::text || '\s+' || safra::text)",
         "= 0"),
        ("CHECK 22 Acessorios",
         r"SELECT COUNT(*) FROM wines_clean WHERE LOWER(nome_limpo) ~ '\y(decanter|saca.?rolha|corkscrew|wine glass|taca|copa|abridor|aerador|balde|cooler|stopper|opener)\y'",
         "= 0"),
    ]

    all_pass = True
    for label, query, threshold in checks:
        cur.execute(query)
        val = cur.fetchone()[0]
        status = "OK" if val == 0 else ("OK" if "< 100" in threshold and val < 100 else "FALHA")
        if status == "FALHA":
            all_pass = False
        print(f"  {label}: {val} (criterio: {threshold}) [{status}]")

    cur.execute("SELECT COUNT(*) FROM wines_clean")
    total = cur.fetchone()[0]
    print(f"\n  Total final: {total:,} vinhos")

    print("\n" + "=" * 60)
    if DRY_RUN:
        print("DRY-RUN concluido. Rode sem --dry-run para aplicar.")
    elif all_pass:
        print("TODOS OS 5 CHECKS PASSARAM. Rode o auditor completo para confirmar.")
    else:
        print("AINDA HA FALHAS. Verifique os resultados acima.")
    print("=" * 60)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
