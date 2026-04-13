"""
Demanda 9 -- Validador do CSV preenchido por Murilo.

READ-ONLY. Nao toca banco, nao mexe em producao.

Verifica schema e valores validos do CSV `tail_pilot_120_for_murilo_2026-04-10.csv`
(ou versao preenchida). Funciona tanto com CSV vazio (estado atual) quanto com
CSV preenchido parcial/totalmente.

Checa:
  - exatamente 120 rows
  - `render_wine_id` unico
  - colunas `murilo_*` obrigatorias presentes
  - valores validos (ou vazios) para:
      murilo_business_class in {MATCH_RENDER, MATCH_IMPORT, STANDALONE_WINE, NOT_WINE, ""}
      murilo_review_state   in {RESOLVED, SECOND_REVIEW, UNRESOLVED, ""}
      murilo_confidence     in {HIGH, MEDIUM, LOW, ""}
      murilo_action         in {ALIAS, IMPORT_THEN_ALIAS, KEEP_STANDALONE, SUPPRESS, ""}
  - `murilo_notes` aceito livre
  - conferencia de regras de coerencia (ex.: se business_class=MATCH_RENDER, action esperada=ALIAS; warning, nao fail)

Exit codes:
  0 -- todos os checks OK
  1 -- erro estrutural (rows faltando/duplicadas, colunas ausentes, valores invalidos)
  2 -- CSV totalmente vazio (todos os campos murilo_* em branco) -- util para CI dry-run

Uso:
  python scripts/validate_murilo_csv.py [--in reports/tail_pilot_120_for_murilo_2026-04-10.csv]
"""

import argparse
import csv
import os
import sys
from collections import Counter

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")
DEFAULT_CSV = os.path.join(REPORT_DIR, "tail_pilot_120_for_murilo_2026-04-10.csv")

EXPECTED_ROWS = 120

REQUIRED_MURILO_COLS = [
    "murilo_business_class",
    "murilo_review_state",
    "murilo_confidence",
    "murilo_action",
    "murilo_notes",
]

REQUIRED_CONTEXT_COLS = [
    "render_wine_id",
    "pilot_bucket_proxy",
    "nome",
    "produtor",
    "r1_business_class",
    "r1_review_state",
    "r1_confidence",
    "r1_action",
]

VALID_BUSINESS_CLASS = {"MATCH_RENDER", "MATCH_IMPORT", "STANDALONE_WINE", "NOT_WINE", ""}
VALID_REVIEW_STATE = {"RESOLVED", "SECOND_REVIEW", "UNRESOLVED", ""}
VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW", ""}
VALID_ACTION = {"ALIAS", "IMPORT_THEN_ALIAS", "KEEP_STANDALONE", "SUPPRESS", ""}

# Coerencia esperada (warning, nao fail)
EXPECTED_ACTION_BY_BC = {
    "MATCH_RENDER": "ALIAS",
    "MATCH_IMPORT": "IMPORT_THEN_ALIAS",
    "STANDALONE_WINE": "KEEP_STANDALONE",
    "NOT_WINE": "SUPPRESS",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="csv_in", default=DEFAULT_CSV)
    args = ap.parse_args()

    if not os.path.exists(args.csv_in):
        print(f"ERROR: arquivo nao encontrado: {args.csv_in}")
        sys.exit(1)

    errors = []
    warnings = []

    with open(args.csv_in, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        rows = list(reader)

    print(f"[validate] arquivo: {args.csv_in}")
    print(f"[validate] rows lidas: {len(rows)}")
    print(f"[validate] colunas: {len(cols)}")

    # --- Check 1: row count ---
    if len(rows) != EXPECTED_ROWS:
        errors.append(f"row count = {len(rows)} (esperado {EXPECTED_ROWS})")

    # --- Check 2: required columns present ---
    missing_req_mur = [c for c in REQUIRED_MURILO_COLS if c not in cols]
    if missing_req_mur:
        errors.append(f"colunas murilo_* ausentes: {missing_req_mur}")

    missing_req_ctx = [c for c in REQUIRED_CONTEXT_COLS if c not in cols]
    if missing_req_ctx:
        errors.append(f"colunas de contexto ausentes: {missing_req_ctx}")

    # --- Check 3: render_wine_id unique ---
    wids = [r.get("render_wine_id", "") for r in rows]
    dup = [wid for wid, count in Counter(wids).items() if count > 1]
    if dup:
        errors.append(f"render_wine_id duplicado: {dup[:5]}")

    empty_wids = sum(1 for w in wids if not w.strip())
    if empty_wids:
        errors.append(f"{empty_wids} rows com render_wine_id vazio")

    # --- Check 4: values inside taxonomies ---
    def check_col(col, valid_set, name):
        invalid = []
        for i, r in enumerate(rows):
            v = (r.get(col, "") or "").strip()
            if v not in valid_set:
                invalid.append((i, r.get("render_wine_id", "?"), v))
        if invalid:
            errors.append(
                f"{col}: {len(invalid)} valores invalidos. Exemplos: "
                f"{invalid[:3]}. Valores validos: {sorted(v for v in valid_set if v)}"
            )

    if "murilo_business_class" in cols:
        check_col("murilo_business_class", VALID_BUSINESS_CLASS, "murilo_business_class")
    if "murilo_review_state" in cols:
        check_col("murilo_review_state", VALID_REVIEW_STATE, "murilo_review_state")
    if "murilo_confidence" in cols:
        check_col("murilo_confidence", VALID_CONFIDENCE, "murilo_confidence")
    if "murilo_action" in cols:
        check_col("murilo_action", VALID_ACTION, "murilo_action")

    # --- Check 5: coerencia business_class x action (warning only) ---
    incoherent = []
    for r in rows:
        bc = (r.get("murilo_business_class", "") or "").strip()
        act = (r.get("murilo_action", "") or "").strip()
        if bc and act and EXPECTED_ACTION_BY_BC.get(bc) != act:
            incoherent.append((r.get("render_wine_id"), bc, act, EXPECTED_ACTION_BY_BC.get(bc)))
    if incoherent:
        warnings.append(
            f"{len(incoherent)} rows com action diferente da esperada para business_class. "
            f"Exemplos (wid, bc, act_recebida, act_esperada): {incoherent[:3]}. "
            f"Pode ser valido em casos especiais mas confirmar."
        )

    # --- Check 6: quanto foi preenchido ---
    filled_bc = sum(1 for r in rows if (r.get("murilo_business_class", "") or "").strip())
    filled_rs = sum(1 for r in rows if (r.get("murilo_review_state", "") or "").strip())
    filled_conf = sum(1 for r in rows if (r.get("murilo_confidence", "") or "").strip())
    filled_act = sum(1 for r in rows if (r.get("murilo_action", "") or "").strip())
    filled_notes = sum(1 for r in rows if (r.get("murilo_notes", "") or "").strip())

    print()
    print(f"[preenchimento]")
    print(f"  murilo_business_class: {filled_bc}/{EXPECTED_ROWS}")
    print(f"  murilo_review_state:   {filled_rs}/{EXPECTED_ROWS}")
    print(f"  murilo_confidence:     {filled_conf}/{EXPECTED_ROWS}")
    print(f"  murilo_action:         {filled_act}/{EXPECTED_ROWS}")
    print(f"  murilo_notes:          {filled_notes}/{EXPECTED_ROWS}")

    empty_mode = (filled_bc + filled_rs + filled_conf + filled_act == 0)

    # --- Report ---
    print()
    if errors:
        print(f"[FAIL] {len(errors)} erro(s):")
        for e in errors:
            print(f"  - {e}")
    if warnings:
        print(f"[WARN] {len(warnings)} aviso(s):")
        for w in warnings:
            print(f"  - {w}")
    if not errors and not warnings:
        print("[OK] nenhum erro estrutural encontrado.")

    print()
    if errors:
        print("=== validator: FAIL (estrutural) ===")
        sys.exit(1)
    elif empty_mode:
        print("=== validator: PENDING (CSV estruturalmente ok, nao preenchido) ===")
        sys.exit(2)
    else:
        print("=== validator: OK ===")
        sys.exit(0)


if __name__ == "__main__":
    main()
