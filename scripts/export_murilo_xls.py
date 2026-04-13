"""
Demanda 9 (higiene visual, versao .xls legado) -- Gera o pacote for_murilo
em formato Excel antigo (.xls) para ambientes que nao suportam .xlsx.

Le:
  reports/tail_pilot_120_for_murilo_2026-04-10.csv

Gera:
  reports/tail_pilot_120_for_murilo_2026-04-10.xls

Diferencas vs a versao .xlsx:
  - Formato Excel 97-2003 (.xls), compativel com versoes antigas
  - NAO tem dropdowns (xlwt nao suporta data validation)
  - Em compensacao, os headers das colunas murilo_* incluem os valores
    validos como comentario (cell note, hover-tooltip em Excel)
  - Resto do styling (cores, wrap, header congelado, column widths) mantido

Uso:
  python scripts/export_murilo_xls.py
"""

import csv
import os

import xlwt


REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports")
IN_CSV = os.path.join(REPORT_DIR, "tail_pilot_120_for_murilo_2026-04-10.csv")
OUT_XLS = os.path.join(REPORT_DIR, "tail_pilot_120_for_murilo_2026-04-10.xls")


MURILO_EDIT_COLS = {
    "murilo_business_class",
    "murilo_review_state",
    "murilo_confidence",
    "murilo_action",
    "murilo_notes",
}
R1_CTX_COLS = {
    "r1_business_class", "r1_review_state", "r1_confidence",
    "r1_action", "r1_data_quality", "r1_product_impact",
    "r1_recommended_universe", "r1_recommended_candidate_id",
    "r1_reason_short", "r1_reason_long", "r1_match_blockers",
    "murilo_review_reason",
}
RAW_FLAG_COLS = {
    "wine_filter_category", "y2_any_not_wine_or_spirit",
    "y2_status_set", "y2_present", "no_source_flag",
    "reason_short_proxy", "block", "overflow_from",
    "pilot_bucket_proxy",
}

# Largura em "caracteres Excel" (xlwt usa unidade de 256 = 1 char)
COL_WIDTH_CHARS = {
    "render_wine_id": 11,
    "pilot_bucket_proxy": 28,
    "block": 22,
    "overflow_from": 14,
    "nome": 45,
    "produtor": 30,
    "safra": 7,
    "tipo": 12,
    "preco_min": 10,
    "wine_sources_count_live": 7,
    "stores_count_live": 7,
    "no_source_flag": 7,
    "y2_present": 7,
    "y2_status_set": 14,
    "y2_any_not_wine_or_spirit": 9,
    "wine_filter_category": 16,
    "reason_short_proxy": 32,
    "top1_render_candidate_id": 11,
    "top1_render_channel": 20,
    "top1_render_score": 9,
    "top1_render_gap": 9,
    "top1_import_candidate_id": 11,
    "top1_import_channel": 20,
    "top1_import_score": 9,
    "top1_import_gap": 9,
    "best_overall_universe": 12,
    "best_overall_channel": 20,
    "best_overall_score": 9,
    "top1_render_human": 55,
    "top1_import_human": 55,
    "top3_render_summary": 80,
    "top3_import_summary": 80,
    "r1_business_class": 17,
    "r1_review_state": 16,
    "r1_confidence": 12,
    "r1_action": 18,
    "r1_data_quality": 12,
    "r1_product_impact": 12,
    "r1_recommended_universe": 12,
    "r1_recommended_candidate_id": 11,
    "r1_reason_short": 40,
    "r1_reason_long": 70,
    "r1_match_blockers": 30,
    "murilo_review_reason": 40,
    "murilo_business_class": 18,
    "murilo_review_state": 17,
    "murilo_confidence": 13,
    "murilo_action": 20,
    "murilo_notes": 50,
}
WRAP_COLS = {
    "nome", "produtor",
    "top1_render_human", "top1_import_human",
    "top3_render_summary", "top3_import_summary",
    "r1_reason_short", "r1_reason_long", "r1_match_blockers",
    "reason_short_proxy", "murilo_review_reason", "murilo_notes",
}


# Ordem amigavel para Murilo: id + colunas que ele preenche primeiro,
# depois contexto essencial (nome/produtor/flags), depois top1/top3,
# depois classificacao R1 do Claude (referencia), depois metadata.
PREFERRED_ORDER = [
    # 1) identificacao
    "render_wine_id",

    # 2) colunas que VOCE preenche (verdes)
    "murilo_business_class",
    "murilo_review_state",
    "murilo_confidence",
    "murilo_action",
    "murilo_notes",

    # 3) contexto essencial do wine
    "nome",
    "produtor",
    "safra",
    "tipo",
    "preco_min",

    # 4) flags cruas que ajudam a decidir (amarelas)
    "wine_filter_category",
    "y2_any_not_wine_or_spirit",
    "no_source_flag",
    "y2_present",
    "y2_status_set",
    "reason_short_proxy",
    "pilot_bucket_proxy",
    "murilo_review_reason",

    # 5) melhor candidato Render (legivel)
    "top1_render_human",
    "top3_render_summary",
    "top1_render_score",
    "top1_render_gap",
    "top1_render_channel",
    "top1_render_candidate_id",

    # 6) melhor candidato Import (legivel)
    "top1_import_human",
    "top3_import_summary",
    "top1_import_score",
    "top1_import_gap",
    "top1_import_channel",
    "top1_import_candidate_id",

    # 7) classificacao R1 Claude (referencia, azul)
    "r1_business_class",
    "r1_review_state",
    "r1_confidence",
    "r1_action",
    "r1_reason_short",
    "r1_reason_long",
    "r1_match_blockers",
    "r1_data_quality",
    "r1_product_impact",
    "r1_recommended_universe",
    "r1_recommended_candidate_id",

    # 8) metadata operacional
    "wine_sources_count_live",
    "stores_count_live",
    "best_overall_universe",
    "best_overall_channel",
    "best_overall_score",
    "block",
    "overflow_from",
]


def reorder_headers(original):
    """Retorna os headers em PREFERRED_ORDER, com quaisquer colunas extras
    que apareceram no CSV mas nao estao na ordem preferida jogadas no fim."""
    seen = set()
    out = []
    for h in PREFERRED_ORDER:
        if h in original:
            out.append(h)
            seen.add(h)
    for h in original:
        if h not in seen:
            out.append(h)
    return out


# Valores validos (vao como hint no cell note do header)
VALID_VALUES = {
    "murilo_business_class": ["MATCH_RENDER", "MATCH_IMPORT", "STANDALONE_WINE", "NOT_WINE"],
    "murilo_review_state": ["RESOLVED", "SECOND_REVIEW", "UNRESOLVED"],
    "murilo_confidence": ["HIGH", "MEDIUM", "LOW"],
    "murilo_action": ["ALIAS", "IMPORT_THEN_ALIAS", "KEEP_STANDALONE", "SUPPRESS"],
}


def make_style(fg_color=None, bold=False, wrap=False, white=False, header=False):
    s = xlwt.XFStyle()
    if fg_color is not None:
        pat = xlwt.Pattern()
        pat.pattern = xlwt.Pattern.SOLID_PATTERN
        pat.pattern_fore_colour = fg_color
        s.pattern = pat
    font = xlwt.Font()
    if bold:
        font.bold = True
    if white:
        font.colour_index = xlwt.Style.colour_map["white"]
    font.name = "Calibri"
    font.height = 200  # 10pt = 200
    s.font = font
    al = xlwt.Alignment()
    al.wrap = 1 if wrap else 0
    al.horz = xlwt.Alignment.HORZ_LEFT
    al.vert = xlwt.Alignment.VERT_TOP
    s.alignment = al
    b = xlwt.Borders()
    b.left = xlwt.Borders.THIN
    b.right = xlwt.Borders.THIN
    b.top = xlwt.Borders.THIN
    b.bottom = xlwt.Borders.THIN
    b.left_colour = 22
    b.right_colour = 22
    b.top_colour = 22
    b.bottom_colour = 22
    s.borders = b
    return s


def main():
    # Add custom palette colors (xlwt tem paleta limitada de 8 - 63)
    xlwt.add_palette_colour("green_soft", 0x21)    # DFF0D8
    xlwt.add_palette_colour("blue_soft", 0x22)     # D9E8F5
    xlwt.add_palette_colour("yellow_soft", 0x23)   # FFF3CD
    xlwt.add_palette_colour("header_dark", 0x24)   # 343A40
    xlwt.add_palette_colour("header_green", 0x25)  # 198754
    xlwt.add_palette_colour("header_blue", 0x26)   # 0D6EFD
    xlwt.add_palette_colour("header_yellow", 0x27) # FFC107

    wb = xlwt.Workbook(encoding="utf-8")
    wb.set_colour_RGB(0x21, 223, 240, 216)
    wb.set_colour_RGB(0x22, 217, 232, 245)
    wb.set_colour_RGB(0x23, 255, 243, 205)
    wb.set_colour_RGB(0x24, 52, 58, 64)
    wb.set_colour_RGB(0x25, 25, 135, 84)
    wb.set_colour_RGB(0x26, 13, 110, 253)
    wb.set_colour_RGB(0x27, 255, 193, 7)

    # ---------- Sheet leia_primeiro ----------
    ws_ins = wb.add_sheet("leia_primeiro")
    ws_ins.col(0).width = 256 * 110  # 110 chars
    title_style = make_style(fg_color=0x24, bold=True, white=True)
    bold_style = make_style(bold=True)
    green_bg = make_style(fg_color=0x21)
    yellow_bg = make_style(fg_color=0x23)
    blue_bg = make_style(fg_color=0x22)
    plain = make_style()
    mono = xlwt.XFStyle()
    mono_font = xlwt.Font(); mono_font.name = "Consolas"; mono_font.height = 200
    mono.font = mono_font

    instructions = [
        ("Pilot 120 -- Instrucoes rapidas para Murilo", title_style),
        ("", plain),
        ("Preencha APENAS as 5 colunas em VERDE (murilo_*).", green_bg),
        ("As colunas em AMARELO sao flags cruas operacionais (contexto).", yellow_bg),
        ("As colunas em AZUL sao a classificacao R1 do Claude (referencia).", blue_bg),
        ("", plain),
        ("Colunas obrigatorias para preencher:", bold_style),
        ("  murilo_business_class  -> MATCH_RENDER / MATCH_IMPORT / STANDALONE_WINE / NOT_WINE", plain),
        ("  murilo_review_state    -> RESOLVED / SECOND_REVIEW / UNRESOLVED", plain),
        ("  murilo_confidence      -> HIGH / MEDIUM / LOW", plain),
        ("  murilo_action          -> ALIAS / IMPORT_THEN_ALIAS / KEEP_STANDALONE / SUPPRESS", plain),
        ("  murilo_notes           -> texto livre (opcional mas util)", plain),
        ("", plain),
        ("Regras sagradas:", bold_style),
        ("  1. NAO renomeie o arquivo nem a aba 'pilot_120'.", plain),
        ("  2. NAO altere colunas fora das cinco murilo_*.", plain),
        ("  3. NAO apague linhas.", plain),
        ("  4. UNRESOLVED vai em review_state, nunca em business_class.", plain),
        ("  5. y2_any_not_wine_or_spirit e baseline, nao verdade.", plain),
        ("", plain),
        ("Atencao: este arquivo .xls nao suporta dropdown (formato Excel 97-2003).", plain),
        ("Os valores validos estao listados acima. Digite exatamente como mostrado", plain),
        ("(maiusculas, underscores). O validador vai pegar qualquer valor fora da lista.", plain),
        ("", plain),
        ("Relacao canonica business_class -> action:", bold_style),
        ("  MATCH_RENDER    -> ALIAS", plain),
        ("  MATCH_IMPORT    -> IMPORT_THEN_ALIAS", plain),
        ("  STANDALONE_WINE -> KEEP_STANDALONE", plain),
        ("  NOT_WINE        -> SUPPRESS", plain),
        ("", plain),
        ("Quando terminar, salve como CSV UTF-8 com o nome:", bold_style),
        ("  tail_pilot_120_for_murilo_2026-04-10.csv", mono),
        ("", plain),
        ("Depois rode no Python:", bold_style),
        ("  python scripts/validate_murilo_csv.py", mono),
        ("  python scripts/compare_claude_vs_murilo.py", mono),
        ("  python scripts/build_adjudication_template.py", mono),
        ("", plain),
        ("(detalhes completos em reports/tail_pilot_120_murilo_instructions_2026-04-10.md)", plain),
    ]
    for i, (text, st) in enumerate(instructions):
        ws_ins.write(i, 0, text, st)
        ws_ins.row(i).height_mismatch = True
        ws_ins.row(i).height = 300

    # ---------- Sheet pilot_120 ----------
    ws = wb.add_sheet("pilot_120")

    # Read CSV
    with open(IN_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        original_headers = reader.fieldnames
        rows = list(reader)
    headers = reorder_headers(original_headers)
    print(f"[read] {len(rows)} rows, {len(headers)} cols")
    print(f"[reorder] ordem amigavel aplicada (murilo_* na frente)")

    # Styles por tipo
    header_default_style = make_style(fg_color=0x24, bold=True, white=True, wrap=True)
    header_murilo_style = make_style(fg_color=0x25, bold=True, white=True, wrap=True)
    header_r1_style = make_style(fg_color=0x26, bold=True, white=True, wrap=True)
    header_flag_style = make_style(fg_color=0x27, bold=True, wrap=True)

    def cell_style(col_name):
        wrap = col_name in WRAP_COLS
        if col_name in MURILO_EDIT_COLS:
            return make_style(fg_color=0x21, wrap=wrap)
        if col_name in R1_CTX_COLS:
            return make_style(fg_color=0x22, wrap=wrap)
        if col_name in RAW_FLAG_COLS:
            return make_style(fg_color=0x23, wrap=wrap)
        return make_style(wrap=wrap)

    # Build header text: for categoricas do Murilo, incluir valores validos em multilinhas
    def header_text(h):
        if h in VALID_VALUES:
            return h + "\n(" + " | ".join(VALID_VALUES[h]) + ")"
        return h

    # Write header
    for ci, h in enumerate(headers):
        if h in MURILO_EDIT_COLS:
            st = header_murilo_style
        elif h in R1_CTX_COLS:
            st = header_r1_style
        elif h in RAW_FLAG_COLS:
            st = header_flag_style
        else:
            st = header_default_style
        ws.write(0, ci, header_text(h), st)
        ws.col(ci).width = 256 * COL_WIDTH_CHARS.get(h, 18)
    ws.row(0).height_mismatch = True
    ws.row(0).height = 900  # header mais alto para acomodar valores validos

    # Write data rows
    styles_cache = {h: cell_style(h) for h in headers}
    for ri, row in enumerate(rows, 1):
        for ci, h in enumerate(headers):
            v = row.get(h, "")
            ws.write(ri, ci, v, styles_cache[h])
        ws.row(ri).height_mismatch = True
        ws.row(ri).height = 900  # ~45 pt -- suficiente pra wrap

    # Freeze header row
    ws.set_panes_frozen(True)
    ws.set_horz_split_pos(1)

    # Tenta salvar no nome padrao; se o arquivo estiver aberto (lock), salva
    # numa cópia com sufixo _v2.xls e avisa.
    target = OUT_XLS
    try:
        wb.save(target)
    except PermissionError:
        alt = OUT_XLS.replace(".xls", "_v2.xls")
        wb.save(alt)
        target = alt
        print(f"[AVISO] {OUT_XLS} estava bloqueado (aberto em algum editor?).")
        print(f"[AVISO] Salvei em {alt}. Feche o Excel e rode de novo se quiser o nome original.")
    print(f"[write] {target}")
    print()
    print("Abra em Excel, LibreOffice Calc, Google Sheets (upload), ou qualquer editor que entenda .xls 97-2003.")


if __name__ == "__main__":
    main()
