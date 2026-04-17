"""
D17 QA closeout summarizer.

Reads a reviewed QA CSV (qa_verdict filled by human reviewer) and emits:
  - per-lane / per-stratum / per-evidence error rates
  - gate decision vs 3% threshold
  - list of ERROR rows
Output: reports/tail_d17_alias_qa_closeout_2026-04-16.md
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
DATE = "2026-04-16"
DEFAULT_IN = REPORTS / f"tail_d17_alias_qa_pack_{DATE}.csv"
OUT_MD = REPORTS / f"tail_d17_alias_qa_closeout_{DATE}.md"
ERROR_CSV = REPORTS / f"tail_d17_alias_qa_errors_{DATE}.csv"
FINAL_APPROVED = REPORTS / f"tail_d17_alias_approved_{DATE}.csv.gz"

MAX_ERROR_RATE = 0.03


def fmt(n):
    return f"{int(n):,}".replace(",", ".")


def pct(n, d):
    if not d:
        return "-"
    return f"{100 * n / d:.2f}%"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, default=str(DEFAULT_IN))
    args = parser.parse_args()

    in_path = Path(args.input)
    rows = list(csv.DictReader(open(in_path, "r", encoding="utf-8", newline="")))
    reviewed = [r for r in rows if r.get("qa_verdict") in {"CORRECT", "ERROR"}]
    errors = [r for r in rows if r.get("qa_verdict") == "ERROR"]
    corrects = [r for r in rows if r.get("qa_verdict") == "CORRECT"]
    pending = [r for r in rows if not r.get("qa_verdict")]

    by_lane = defaultdict(lambda: [0, 0])
    by_stratum = defaultdict(lambda: [0, 0])
    by_evidence = defaultdict(lambda: [0, 0])
    for r in reviewed:
        lane = r["lane"]
        stratum = r["source_stratum"]
        evidence = r["evidence_reason"]
        idx = 0 if r["qa_verdict"] == "CORRECT" else 1
        by_lane[lane][idx] += 1
        by_stratum[stratum][idx] += 1
        by_evidence[evidence][idx] += 1

    total_reviewed = len(reviewed)
    total_errors = len(errors)
    error_rate = total_errors / total_reviewed if total_reviewed else 0.0
    gate = "PASS" if error_rate <= MAX_ERROR_RATE and not pending else ("FAIL" if error_rate > MAX_ERROR_RATE else "INCOMPLETE")

    if errors:
        with open(ERROR_CSV, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(errors)

    lines = [
        f"# D17 QA Closeout -- {DATE}",
        "",
        f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Input: `{in_path}`",
        f"Threshold: `{int(MAX_ERROR_RATE*100)}%`",
        "",
        f"## Gate: `{gate}`",
        "",
        f"- QA linhas totais: `{fmt(len(rows))}`",
        f"- Revisados (CORRECT+ERROR): `{fmt(total_reviewed)}`",
        f"- CORRECT: `{fmt(len(corrects))}`",
        f"- ERROR: `{fmt(total_errors)}`",
        f"- Pendentes: `{fmt(len(pending))}`",
        f"- Error rate: `{pct(total_errors, total_reviewed)}`",
        "",
        "## Por lane",
        "",
        "| lane | correct | error | error_rate |",
        "| --- | --- | --- | --- |",
    ]
    for name in sorted(by_lane):
        c, e = by_lane[name]
        lines.append(f"| {name} | {fmt(c)} | {fmt(e)} | {pct(e, c + e)} |")
    lines += ["", "## Por estrato", "", "| estrato | correct | error | error_rate |", "| --- | --- | --- | --- |"]
    for name, (c, e) in sorted(by_stratum.items(), key=lambda x: -(x[1][1])):
        lines.append(f"| {name} | {fmt(c)} | {fmt(e)} | {pct(e, c + e)} |")
    lines += ["", "## Por evidencia", "", "| evidencia | correct | error | error_rate |", "| --- | --- | --- | --- |"]
    for name, (c, e) in sorted(by_evidence.items(), key=lambda x: -(x[1][1])):
        lines.append(f"| {name} | {fmt(c)} | {fmt(e)} | {pct(e, c + e)} |")

    lines += [
        "",
        "## Decisao",
        "",
    ]
    if gate == "PASS":
        lines.append("- Gate passou. Autorizado construir o lote final aprovado (ALIAS_AUTO - ERROR_SOURCES).")
        lines.append(f"- Para materializar: `python scripts/summarize_d17_qa.py --freeze`")
    elif gate == "FAIL":
        lines.append("- Gate reprovou. Investigar por evidencia/estrato acima antes de endurecer D17 de novo.")
    else:
        lines.append("- QA incompleto. Terminar revisao antes de qualquer decisao de gate.")

    if errors:
        lines += ["", f"- Erros exportados para: `{ERROR_CSV}`"]

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK closeout: {OUT_MD}")
    if errors:
        print(f"OK errors:   {ERROR_CSV}")


if __name__ == "__main__":
    main()
