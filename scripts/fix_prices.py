#!/usr/bin/env python3
"""
fix_prices.py -- Correcao de precos e moedas nas tabelas vinhos_{pais}_fontes.

3 passes:
  1. Diagnostico (Benford, IQR, distribuicao de moedas)
  2. Correcao de moedas erradas (USD -> moeda local)
  3. Correcao de precos gigantes (IQR method)
  4. Validacao (Benford antes vs depois)
  5. Relatorio final

Uso:
  python fix_prices.py                    # Roda tudo
  python fix_prices.py --pais br          # Apenas Brasil
  python fix_prices.py --pais br --dry-run  # Simula sem alterar
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime

import numpy as np
import psycopg2

# ── Mapeamento pais -> moeda correta ──────────────────────────────────────────

MOEDA_CORRETA = {
    "ae": "AED", "ar": "ARS", "at": "EUR", "au": "AUD", "be": "EUR",
    "bg": "BGN", "br": "BRL", "ca": "CAD", "ch": "CHF", "cl": "CLP",
    "cn": "CNY", "co": "COP", "cz": "CZK", "de": "EUR", "dk": "DKK",
    "es": "EUR", "fi": "EUR", "fr": "EUR", "gb": "GBP", "ge": "GEL",
    "gr": "EUR", "hk": "HKD", "hr": "EUR", "hu": "HUF", "ie": "EUR",
    "il": "ILS", "in": "INR", "it": "EUR", "jp": "JPY", "kr": "KRW",
    "lu": "EUR", "md": "MDL", "mx": "MXN", "nl": "EUR", "no": "NOK",
    "nz": "NZD", "pe": "PEN", "ph": "PHP", "pl": "PLN", "pt": "EUR",
    "ro": "RON", "ru": "RUB", "se": "SEK", "sg": "SGD", "th": "THB",
    "tr": "TRY", "tw": "TWD", "us": "USD", "uy": "UYU", "za": "ZAR",
}

# ── Faixas de preco aceitaveis por moeda ─────────────────────────────────────

FAIXA_PRECO = {
    "USD": (2, 50000), "EUR": (2, 50000), "GBP": (2, 40000),
    "BRL": (10, 100000), "ARS": (500, 5000000), "CLP": (1000, 10000000),
    "MXN": (30, 500000), "COP": (5000, 50000000), "PEN": (10, 50000),
    "UYU": (50, 500000), "AUD": (3, 50000), "NZD": (3, 50000),
    "CAD": (3, 50000), "CHF": (2, 50000), "JPY": (200, 5000000),
    "KRW": (2000, 50000000), "CNY": (10, 500000), "HKD": (10, 500000),
    "SGD": (3, 50000), "TWD": (50, 500000), "THB": (50, 500000),
    "INR": (100, 5000000), "ZAR": (20, 500000), "SEK": (20, 500000),
    "NOK": (20, 500000), "DKK": (20, 500000), "PLN": (5, 100000),
    "CZK": (20, 500000), "HUF": (200, 5000000), "RON": (5, 100000),
    "TRY": (10, 500000), "ILS": (10, 100000), "AED": (5, 200000),
    "BGN": (3, 100000), "GEL": (3, 50000), "MDL": (10, 100000),
    "PHP": (50, 500000), "RUB": (50, 5000000),
}

# ── Benford's Law ────────────────────────────────────────────────────────────

BENFORD_EXPECTED = {
    '1': 0.301, '2': 0.176, '3': 0.125, '4': 0.097,
    '5': 0.079, '6': 0.067, '7': 0.058, '8': 0.051, '9': 0.046,
}


def benford_check(precos):
    """Retorna (desvio_total, passou)."""
    first_digits = [str(int(p))[0] for p in precos if p > 0]
    total = len(first_digits)
    if total < 50:
        return 0.0, True  # amostra pequena demais
    dist = Counter(first_digits)
    desvio_total = 0.0
    for d in '123456789':
        real = dist.get(d, 0) / total
        esperado = BENFORD_EXPECTED[d]
        desvio_total += abs(real - esperado)
    return round(desvio_total, 4), desvio_total < 0.15


# ── Helpers ──────────────────────────────────────────────────────────────────

def tabela_existe(cur, tabela):
    cur.execute(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
        (tabela,),
    )
    return cur.fetchone()[0]


def get_precos(cur, tabela, moeda=None):
    """Retorna lista de (id, preco) com preco > 0."""
    if moeda:
        cur.execute(
            f'SELECT id, preco FROM "{tabela}" WHERE preco > 0 AND moeda = %s',
            (moeda,),
        )
    else:
        cur.execute(f'SELECT id, preco FROM "{tabela}" WHERE preco > 0')
    return cur.fetchall()


def get_all_precos_valores(cur, tabela):
    """Retorna lista de precos (floats) com preco > 0."""
    cur.execute(f'SELECT preco FROM "{tabela}" WHERE preco > 0')
    return [float(r[0]) for r in cur.fetchall()]


def get_moeda_dist(cur, tabela):
    """Retorna distribuicao de moedas."""
    cur.execute(f'SELECT moeda, COUNT(*) FROM "{tabela}" WHERE preco > 0 GROUP BY moeda ORDER BY COUNT(*) DESC')
    return dict(cur.fetchall())


# ── PASSO 1: Diagnostico ────────────────────────────────────────────────────

def diagnostico(cur, paises):
    print("\n" + "=" * 60)
    print("PASSO 1 -- DIAGNOSTICO")
    print("=" * 60)

    diag = {}
    for pais in paises:
        tabela = f"vinhos_{pais}_fontes"
        if not tabela_existe(cur, tabela):
            print(f"  {pais.upper()}: tabela {tabela} nao existe -- pulando")
            continue

        precos = get_all_precos_valores(cur, tabela)
        if not precos:
            print(f"  {pais.upper()}: sem precos > 0 -- pulando")
            continue

        moedas = get_moeda_dist(cur, tabela)
        arr = np.array(precos)
        q1 = float(np.percentile(arr, 25))
        q3 = float(np.percentile(arr, 75))
        iqr = q3 - q1
        p99 = float(np.percentile(arr, 99))
        upper_fence = q3 + 1.5 * iqr
        n_outliers = int(np.sum(arr > upper_fence))
        benford_dev, benford_ok = benford_check(precos)

        info = {
            "total": len(precos),
            "moedas": moedas,
            "mediana": round(float(np.median(arr)), 2),
            "q1": round(q1, 2),
            "q3": round(q3, 2),
            "iqr": round(iqr, 2),
            "min": round(float(arr.min()), 2),
            "max": round(float(arr.max()), 2),
            "p99": round(p99, 2),
            "outliers_1_5iqr": n_outliers,
            "benford_desvio": benford_dev,
            "benford_ok": benford_ok,
        }
        diag[pais] = info

        print(f"  {pais.upper()}: {info['total']:>8,} precos | moedas: {moedas} | "
              f"mediana: {info['mediana']:>10,.2f} | outliers(1.5x): {n_outliers:>6,} | "
              f"benford: {benford_dev:.3f} {'OK' if benford_ok else 'SUSPEITO'}")

    return diag


# ── PASSO 2: Corrigir moedas ────────────────────────────────────────────────

def corrigir_moedas(cur, paises, dry_run=False):
    print("\n" + "=" * 60)
    print("PASSO 2 -- CORRECAO DE MOEDAS")
    print("=" * 60)

    resultado = {}
    for pais in paises:
        tabela = f"vinhos_{pais}_fontes"
        moeda_correta = MOEDA_CORRETA.get(pais)
        if not moeda_correta or not tabela_existe(cur, tabela):
            continue

        # Se a moeda correta ja e USD, nada a fazer
        if moeda_correta == "USD":
            continue

        # Quantos registros estao marcados como USD?
        cur.execute(
            f'SELECT COUNT(*) FROM "{tabela}" WHERE moeda = %s AND preco > 0',
            ("USD",),
        )
        n_usd = cur.fetchone()[0]
        if n_usd == 0:
            continue

        # Mediana dos precos marcados como USD
        cur.execute(
            f'SELECT preco FROM "{tabela}" WHERE moeda = %s AND preco > 0',
            ("USD",),
        )
        precos_usd = [float(r[0]) for r in cur.fetchall()]
        mediana_usd = float(np.median(precos_usd))

        faixa_min, faixa_max = FAIXA_PRECO.get(moeda_correta, (1, 100000))

        # Verificar: o valor SEM conversao faz sentido na moeda local?
        valor_faz_sentido_local = faixa_min <= mediana_usd <= faixa_max

        if not valor_faz_sentido_local:
            print(f"  {pais.upper()}: {n_usd:>8,} registros USD | mediana={mediana_usd:>10,.2f} | "
                  f"faixa {moeda_correta}=({faixa_min}-{faixa_max}) | NAO corrigir (fora da faixa local)")
            continue

        # Moeda errada! Corrigir USD -> moeda local
        print(f"  {pais.upper()}: {n_usd:>8,} registros USD -> {moeda_correta} | "
              f"mediana={mediana_usd:>10,.2f} (faz sentido em {moeda_correta})")

        # Amostra de 20 registros
        cur.execute(
            f'SELECT id, fonte, preco FROM "{tabela}" WHERE moeda = %s AND preco > 0 LIMIT 20',
            ("USD",),
        )
        amostra = cur.fetchall()
        for row in amostra[:5]:
            label = (row[1][:50] if row[1] else 'N/A')
            print(f"    ex: id={row[0]} | {label} | "
                  f"preco={float(row[2]):,.2f} (era USD, sera {moeda_correta})")

        if not dry_run:
            cur.execute(
                f'UPDATE "{tabela}" SET moeda = %s WHERE moeda = %s AND preco > 0',
                (moeda_correta, "USD"),
            )
            print(f"    -> {n_usd:,} registros atualizados")

        resultado[pais] = {"de": "USD", "para": moeda_correta, "registros": n_usd}

    return resultado


# ── PASSO 3: Corrigir precos gigantes ────────────────────────────────────────

def corrigir_precos(cur, paises, dry_run=False):
    print("\n" + "=" * 60)
    print("PASSO 3 -- CORRECAO DE PRECOS GIGANTES (IQR)")
    print("=" * 60)

    resultado = {}
    for pais in paises:
        tabela = f"vinhos_{pais}_fontes"
        moeda_correta = MOEDA_CORRETA.get(pais)
        if not moeda_correta or not tabela_existe(cur, tabela):
            continue

        rows = get_precos(cur, tabela, moeda_correta)
        precos = [float(r[1]) for r in rows]

        if len(precos) < 10:
            continue

        arr = np.array(precos)
        q1 = float(np.percentile(arr, 25))
        q3 = float(np.percentile(arr, 75))
        iqr = q3 - q1
        upper_fence = q3 + 3.0 * iqr  # 3x IQR -- mais permissivo para vinhos de luxo

        faixa_min, faixa_max = FAIXA_PRECO.get(moeda_correta, (1, 100000))

        # Identificar outliers
        outliers = [(r[0], float(r[1])) for r in rows if float(r[1]) > upper_fence and float(r[1]) > faixa_max]

        if not outliers:
            continue

        print(f"\n  {pais.upper()} ({moeda_correta}): {len(outliers):,} outliers "
              f"(fence={upper_fence:,.2f}, faixa_max={faixa_max:,})")

        # Mostrar 10 exemplos
        exemplos = outliers[:10]
        for id_reg, preco in exemplos:
            p100 = preco / 100
            p1000 = preco / 1000
            corr = ""
            if faixa_min <= p100 <= faixa_max:
                corr = f" -> /100 = {p100:,.2f}"
            elif faixa_min <= p1000 <= faixa_max:
                corr = f" -> /1000 = {p1000:,.2f}"
            else:
                corr = " -> -1 (nao corrigivel)"
            print(f"    id={id_reg} preco={preco:>14,.2f}{corr}")

        # Aplicar correcoes
        corrigidos_100 = 0
        corrigidos_1000 = 0
        suspeitos = 0
        for id_reg, preco in outliers:
            p100 = preco / 100
            if faixa_min <= p100 <= faixa_max:
                if not dry_run:
                    cur.execute(f'UPDATE "{tabela}" SET preco = %s WHERE id = %s', (p100, id_reg))
                corrigidos_100 += 1
                continue

            p1000 = preco / 1000
            if faixa_min <= p1000 <= faixa_max:
                if not dry_run:
                    cur.execute(f'UPDATE "{tabela}" SET preco = %s WHERE id = %s', (p1000, id_reg))
                corrigidos_1000 += 1
                continue

            # Nao corrigivel
            if not dry_run:
                cur.execute(f'UPDATE "{tabela}" SET preco = -1 WHERE id = %s', (id_reg,))
            suspeitos += 1

        total_corrigidos = corrigidos_100 + corrigidos_1000
        print(f"    -> corrigidos: {total_corrigidos:,} (div/100: {corrigidos_100:,}, "
              f"div/1000: {corrigidos_1000:,}) | suspeitos: {suspeitos:,}")

        resultado[pais] = {
            "outliers": len(outliers),
            "corrigidos": total_corrigidos,
            "div100": corrigidos_100,
            "div1000": corrigidos_1000,
            "suspeitos": suspeitos,
        }

    return resultado


# ── PASSO 4: Validacao Benford ───────────────────────────────────────────────

def validacao_benford(cur, paises, benford_antes):
    print("\n" + "=" * 60)
    print("PASSO 4 -- VALIDACAO BENFORD (antes -> depois)")
    print("=" * 60)

    benford_depois = {}
    for pais in paises:
        tabela = f"vinhos_{pais}_fontes"
        if not tabela_existe(cur, tabela):
            continue

        precos = get_all_precos_valores(cur, tabela)
        if not precos:
            continue

        dev_depois, ok_depois = benford_check(precos)
        benford_depois[pais] = {"desvio": dev_depois, "ok": ok_depois}

        antes = benford_antes.get(pais, {})
        dev_antes = antes.get("benford_desvio", 0)

        melhorou = dev_depois < dev_antes
        status = "MELHOROU" if melhorou else ("IGUAL" if dev_depois == dev_antes else "PIOROU")
        marker = "OK" if ok_depois else "SUSPEITO"

        print(f"  {pais.upper()}: {dev_antes:.4f} -> {dev_depois:.4f} ({status}) [{marker}]")

    return benford_depois


# ── PASSO 5: Relatorio final ────────────────────────────────────────────────

def gerar_relatorio(moedas_result, precos_result, benford_antes, benford_depois, filepath):
    lines = []
    lines.append("=" * 60)
    lines.append("RELATORIO DE CORRECAO DE PRECOS")
    lines.append(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)

    # Moedas corrigidas
    lines.append("\nMOEDAS CORRIGIDAS:")
    total_moeda_paises = 0
    total_moeda_regs = 0
    if moedas_result:
        for pais, info in sorted(moedas_result.items()):
            lines.append(f"  {pais.upper()}: {info['de']} -> {info['para']} ({info['registros']:,} registros)")
            total_moeda_paises += 1
            total_moeda_regs += info['registros']
    else:
        lines.append("  Nenhuma moeda corrigida")

    # Precos corrigidos
    lines.append("\nPRECOS CORRIGIDOS (IQR):")
    total_preco_corr = 0
    total_suspeitos = 0
    if precos_result:
        for pais, info in sorted(precos_result.items()):
            if info['corrigidos'] > 0:
                lines.append(f"  {pais.upper()}: {info['corrigidos']:,} outliers corrigidos "
                             f"(div/100: {info['div100']:,}, div/1000: {info['div1000']:,})")
                total_preco_corr += info['corrigidos']
    else:
        lines.append("  Nenhum preco corrigido")

    # Suspeitos
    lines.append("\nPRECOS SUSPEITOS (nao corrigiveis, marcados como -1):")
    if precos_result:
        for pais, info in sorted(precos_result.items()):
            if info['suspeitos'] > 0:
                lines.append(f"  {pais.upper()}: {info['suspeitos']:,} marcados como -1")
                total_suspeitos += info['suspeitos']
    if total_suspeitos == 0:
        lines.append("  Nenhum preco suspeito")

    # Benford
    lines.append("\nBENFORD'S LAW (antes -> depois):")
    n_passou = 0
    n_total = 0
    for pais in sorted(set(list(benford_antes.keys()) + list(benford_depois.keys()))):
        antes_info = benford_antes.get(pais, {})
        depois_info = benford_depois.get(pais, {})
        dev_antes = antes_info.get("benford_desvio", antes_info.get("desvio", 0))
        dev_depois = depois_info.get("desvio", 0)
        ok_depois = depois_info.get("ok", True)
        melhorou = dev_depois < dev_antes
        status = "MELHOROU" if melhorou else ("IGUAL" if dev_depois == dev_antes else "PIOROU")
        lines.append(f"  {pais.upper()}: {dev_antes:.4f} -> {dev_depois:.4f} ({status})")
        n_total += 1
        if ok_depois:
            n_passou += 1

    # Totais
    lines.append(f"\nTOTAL:")
    lines.append(f"  Moedas corrigidas: {total_moeda_paises} paises, {total_moeda_regs:,} registros")
    lines.append(f"  Precos corrigidos: {total_preco_corr:,} registros")
    lines.append(f"  Precos suspeitos: {total_suspeitos:,} registros")
    lines.append(f"  Benford passou: {n_passou}/{n_total} paises")

    report = "\n".join(lines)
    print(f"\n{report}")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nRelatorio salvo em {filepath}")

    return report


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Correcao de precos e moedas -- WineGod")
    parser.add_argument("--pais", type=str, help="Rodar apenas para um pais (ex: br)")
    parser.add_argument("--dry-run", action="store_true", help="Simular sem alterar banco")
    args = parser.parse_args()

    db_url = os.environ.get(
        "WINEGOD_LOCAL_URL",
        "postgresql://postgres:postgres123@localhost:5432/winegod_db",
    )

    print(f"Conectando ao banco: {db_url.split('@')[1] if '@' in db_url else db_url}")
    if args.dry_run:
        print("*** MODO DRY-RUN -- nenhuma alteracao sera feita ***")

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()

    if args.pais:
        paises = [args.pais.lower()]
    else:
        paises = sorted(MOEDA_CORRETA.keys())

    script_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        # PASSO 1 -- Diagnostico
        diag = diagnostico(cur, paises)

        # Salvar diagnostico
        diag_path = os.path.join(script_dir, "prices_diagnostic.json")
        with open(diag_path, "w", encoding="utf-8") as f:
            json.dump(diag, f, indent=2, ensure_ascii=False, default=str)
        print(f"\nDiagnostico salvo em {diag_path}")

        # PASSO 2 -- Corrigir moedas
        moedas_result = corrigir_moedas(cur, paises, dry_run=args.dry_run)

        # PASSO 3 -- Corrigir precos gigantes
        precos_result = corrigir_precos(cur, paises, dry_run=args.dry_run)

        # PASSO 4 -- Validacao Benford
        benford_depois = validacao_benford(cur, paises, diag)

        # PASSO 5 -- Relatorio final
        report_path = os.path.join(script_dir, "prices_report.txt")
        gerar_relatorio(moedas_result, precos_result, diag, benford_depois, report_path)

        if args.dry_run:
            print("\n*** DRY-RUN: rollback (nenhuma alteracao salva) ***")
            conn.rollback()
        else:
            conn.commit()
            print("\n*** COMMIT: todas as alteracoes salvas ***")

    except Exception as e:
        conn.rollback()
        print(f"\nERRO: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
