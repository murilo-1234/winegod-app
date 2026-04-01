"""
Wine Classifier — Chrome 3o browser (8 abas).
4 ChatGPT + 4 Gemini Rapido.
Faixa: M-N apenas (Mistral=0-L, Edge=OPQRSWY, Codex=TUVXZ).

Uso:
  python wine_classifier/run_chrome.py
"""

import sys
import os
import re
import time
import psycopg2
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Path setup
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from wine_classifier.drivers import ChatGPTDriver, GeminiRapidoDriver

# === CONFIG ===
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "winegod_db"
DB_USER = "postgres"
DB_PASS = "postgres123"

BATCH_SIZE = 1000
BROWSER_STATE = os.path.join(SCRIPT_DIR, "browser_state_chrome")

# Layout: ChatGPT + Gemini (timeout 20 min)
TAB_CONFIG = [
    ("chatgpt", ChatGPTDriver, 4),
    ("gemini", GeminiRapidoDriver, 4),
]
TOTAL_TABS = sum(n for _, _, n in TAB_CONFIG)  # 8

MAX_TIMEOUT_SEC = 1200  # 20 min (override dos drivers)
STABLE_SEC = 30
CHECK_SEC = 3

# Ler prompt header do arquivo
PROMPT_FILE = os.path.join(PROJECT_ROOT, "scripts", "lotes_llm", "prompt_B_v2.txt")


# === HELPERS (copiados do mistral_classifier.py) ===

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def norm(s):
    if not s:
        return ""
    s = s.lower().strip()
    for o, n in [("á","a"),("à","a"),("â","a"),("ã","a"),("ä","a"),
                 ("é","e"),("è","e"),("ê","e"),("ë","e"),
                 ("í","i"),("ì","i"),("î","i"),("ï","i"),
                 ("ó","o"),("ò","o"),("ô","o"),("õ","o"),("ö","o"),
                 ("ú","u"),("ù","u"),("û","u"),("ü","u"),
                 ("ñ","n"),("ç","c")]:
        s = s.replace(o, n)
    return s.strip()


def qq_to_none(val):
    if not val or val.strip() in ("??", "?", ""):
        return None
    return val.strip()


def get_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
        options="-c client_encoding=UTF8",
    )


def setup_tables():
    """Verifica tabelas (rapido, sem lock exclusivo)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS y2_lotes_log (id SERIAL PRIMARY KEY, lote INTEGER NOT NULL, ia VARCHAR(20) NOT NULL, enviados INTEGER NOT NULL, recebidos INTEGER NOT NULL, faltantes INTEGER NOT NULL, processado_em TIMESTAMP NOT NULL DEFAULT NOW(), duracao_seg INTEGER, observacao TEXT)")
    conn.commit()
    for col_name, col_type in [("uva","TEXT"),("regiao","TEXT"),("subregiao","TEXT"),("safra","VARCHAR(10)"),("abv","VARCHAR(10)"),("denominacao","TEXT"),("corpo","VARCHAR(20)"),("harmonizacao","TEXT"),("docura","VARCHAR(20)"),("fonte_llm","VARCHAR(20) DEFAULT 'gemini'")]:
        try:
            cur.execute(f"ALTER TABLE y2_results ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
            conn.commit()
        except Exception:
            conn.rollback()
    conn.close()
    log("Tabelas verificadas")


# Chrome (3o browser) pega M-N apenas
FAIXA_LETRAS = "mn"

def fetch_next_batch(total_items):
    """Busca proximos N itens da wines_clean nao processados (faixa M-N)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT wc.id, wc.nome_normalizado
        FROM wines_clean wc
        LEFT JOIN y2_results yr ON yr.clean_id = wc.id
        WHERE yr.id IS NULL
          AND wc.nome_normalizado IS NOT NULL
          AND LENGTH(TRIM(wc.nome_normalizado)) > 3
          AND LOWER(LEFT(wc.nome_normalizado, 1)) = ANY(%s)
        ORDER BY wc.nome_normalizado
        LIMIT %s
    """, (list(FAIXA_LETRAS), total_items,))
    rows = cur.fetchall()
    conn.close()
    return [{"clean_id": r[0], "loja_nome": r[1] or ""} for r in rows]


def build_prompt(items, prompt_header):
    """Monta prompt: header + itens numerados."""
    lines = [f"{i+1}. {item['loja_nome']}" for i, item in enumerate(items)]
    return prompt_header + "\n".join(lines)


def parse_response(text, items, ia_name):
    """Parseia resposta da IA. Retorna (results_list, lines_parsed_count)."""
    results = []
    lines_parsed = {}

    sequential_num = 0
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^(\d+)\.\s*(.+)', line)
        if match:
            num = int(match.group(1))
            content = match.group(2).strip()
            lines_parsed[num] = content
        elif line.startswith(("W|", "X", "S", "=")):
            sequential_num += 1
            lines_parsed[sequential_num] = line

    for i, item in enumerate(items):
        num = i + 1
        clean_id = item["clean_id"]
        loja = item["loja_nome"]
        llm = lines_parsed.get(num, "")

        result = {
            "clean_id": clean_id,
            "loja_nome": loja,
            "classificacao": None,
            "prod_banco": None,
            "vinho_banco": None,
            "pais": None,
            "cor": None,
            "uva": None,
            "regiao": None,
            "subregiao": None,
            "safra": None,
            "abv": None,
            "denominacao": None,
            "corpo": None,
            "harmonizacao": None,
            "docura": None,
            "duplicata_de": None,
            "status": "error",
            "fonte_llm": ia_name,
        }

        if not llm:
            # Item sem resposta — NAO adicionar ao results (faltante)
            continue

        # Duplicata pura: "=N" (sem W| na frente)
        if llm.startswith("="):
            try:
                dup_ref_num = int(llm[1:].strip())
                if 1 <= dup_ref_num <= len(items):
                    result["classificacao"] = "W"
                    result["duplicata_de"] = items[dup_ref_num - 1]["clean_id"]
                    result["status"] = "duplicate"
                    results.append(result)
                    continue
            except (ValueError, IndexError):
                pass

        if llm.startswith("X"):
            result["classificacao"] = "X"
            result["status"] = "not_wine"

        elif llm.startswith("S"):
            result["classificacao"] = "S"
            result["status"] = "spirit"
            parts = llm.split("|")
            if len(parts) >= 3:
                result["prod_banco"] = qq_to_none(norm(parts[1]))
                result["vinho_banco"] = qq_to_none(norm(parts[2]))
            if len(parts) >= 4:
                result["pais"] = qq_to_none(parts[3].strip()[:5])

        elif llm.startswith("W"):
            parts = llm.split("|")
            if len(parts) < 5:
                result["classificacao"] = "W"
                result["status"] = "error"
                results.append(result)
                continue

            is_dup = False
            dup_ref = None
            last_part = parts[-1].strip()
            if last_part.startswith("="):
                is_dup = True
                try:
                    dup_ref_num = int(last_part[1:])
                    if 1 <= dup_ref_num <= len(items):
                        dup_ref = items[dup_ref_num - 1]["clean_id"]
                except (ValueError, IndexError):
                    pass
                parts = parts[:-1]

            result["classificacao"] = "W"
            result["prod_banco"] = qq_to_none(norm(parts[1])) if len(parts) > 1 else None
            result["vinho_banco"] = qq_to_none(norm(parts[2])) if len(parts) > 2 else None
            result["pais"] = qq_to_none(parts[3].strip()[:5]) if len(parts) > 3 else None
            result["cor"] = qq_to_none(parts[4].strip()[:1]) if len(parts) > 4 else None
            result["uva"] = qq_to_none(parts[5]) if len(parts) > 5 else None
            result["regiao"] = qq_to_none(parts[6]) if len(parts) > 6 else None
            result["subregiao"] = qq_to_none(parts[7]) if len(parts) > 7 else None
            result["safra"] = qq_to_none(parts[8]) if len(parts) > 8 else None
            result["abv"] = qq_to_none(parts[9]) if len(parts) > 9 else None
            result["denominacao"] = qq_to_none(parts[10]) if len(parts) > 10 else None
            result["corpo"] = qq_to_none(parts[11]) if len(parts) > 11 else None
            result["harmonizacao"] = qq_to_none(parts[12]) if len(parts) > 12 else None
            result["docura"] = qq_to_none(parts[13]) if len(parts) > 13 else None
            result["duplicata_de"] = dup_ref

            if is_dup:
                result["status"] = "duplicate"
            else:
                result["status"] = "pending_match"

        results.append(result)

    return results, len(lines_parsed)


def insert_results(results):
    """Insere resultados no y2_results."""
    conn = get_db()
    cur = conn.cursor()
    inserted = 0
    for r in results:
        try:
            cur.execute("""
                INSERT INTO y2_results (
                    clean_id, loja_nome, classificacao, prod_banco, vinho_banco,
                    pais, cor, uva, regiao, subregiao, safra, abv, denominacao,
                    corpo, harmonizacao, docura, duplicata_de, status, fonte_llm
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                ) ON CONFLICT DO NOTHING
            """, (
                r["clean_id"], r["loja_nome"], r["classificacao"],
                r["prod_banco"], r["vinho_banco"],
                r["pais"], r["cor"], r["uva"], r["regiao"], r["subregiao"],
                r["safra"], r["abv"], r["denominacao"],
                r["corpo"], r["harmonizacao"], r["docura"],
                r["duplicata_de"], r["status"], r["fonte_llm"],
            ))
            inserted += 1
        except Exception as e:
            log(f"  [ERRO] Insert clean_id={r['clean_id']}: {e}")
            conn.rollback()
    conn.commit()
    conn.close()
    return inserted


def log_lote(lote_num, ia_name, enviados, recebidos, duracao_seg, obs=""):
    """Registra lote no y2_lotes_log."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO y2_lotes_log (lote, ia, enviados, recebidos, faltantes, processado_em, duracao_seg, observacao)
        VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s)
    """, (lote_num, ia_name, enviados, recebidos, enviados - recebidos, duracao_seg, obs or None))
    conn.commit()
    conn.close()


def _processar_sessao(key, sess):
    """Parseia resposta e salva no banco. Chamado assim que a aba termina."""
    items = sess["items"]
    ia_name = sess["ia_name"]
    lote_num = sess["lote_num"]
    response = sess.get("response", "")
    duracao = int(time.time() - sess["start_time"])

    if not response:
        log_lote(lote_num, ia_name, len(items), 0, duracao, sess.get("status", "sem_resposta"))
        log(f"  [{key}] Sem resposta")
        return

    results, lines_out = parse_response(response, items, ia_name)

    if results:
        inserted = insert_results(results)
        wines = sum(1 for r in results if r["classificacao"] == "W")
        not_wine = sum(1 for r in results if r["classificacao"] == "X")
        spirits = sum(1 for r in results if r["classificacao"] == "S")

        log(f"  [{key}] Lote #{lote_num}: {lines_out} linhas, "
            f"W={wines} X={not_wine} S={spirits} | "
            f"Inseridos={inserted} ({duracao}s)")

        log_lote(lote_num, ia_name, len(items), len(results),
                 duracao, f"W={wines} X={not_wine} S={spirits}")
    else:
        log(f"  [{key}] Lote #{lote_num}: 0 linhas parseadas ({duracao}s)")
        log_lote(lote_num, ia_name, len(items), 0, duracao, "sem_linhas")


# === MAIN ===

def main():
    log("=" * 60)
    log("  WINE CLASSIFIER — Chrome 3o browser (ChatGPT + Gemini) [M-N]")
    log(f"  {TOTAL_TABS} abas x {BATCH_SIZE} itens = {TOTAL_TABS * BATCH_SIZE} itens/rodada")
    log("=" * 60)

    setup_tables()

    # Contar pendentes
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM wines_clean")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM y2_results")
    done = cur.fetchone()[0]
    conn.close()
    pending = total - done
    log(f"Total: {total:,} | Feito: {done:,} | Pendente: {pending:,}")
    log(f"Lotes estimados: {(pending + BATCH_SIZE - 1) // BATCH_SIZE}")
    log("")

    if pending == 0:
        log("Nada pendente!")
        return

    # Ler prompt header
    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        prompt_header = f.read()
    log(f"Prompt header: {len(prompt_header)} chars")

    # Contador global de lotes (pra y2_lotes_log)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(lote), 0) FROM y2_lotes_log")
    lote_counter = cur.fetchone()[0]
    conn.close()

    # Abrir browser
    from playwright.sync_api import sync_playwright

    os.makedirs(BROWSER_STATE, exist_ok=True)

    with sync_playwright() as p:
        log("Abrindo Chrome...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_STATE,
            channel="chrome",
            headless=False,
            viewport={"width": 1366, "height": 768},
            locale="pt-BR",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        # Fechar abas residuais da sessao anterior
        time.sleep(3)  # esperar browser restaurar abas
        old_pages = list(context.pages)
        if old_pages:
            log(f"Fechando {len(old_pages)} abas residuais...")
            for old_page in old_pages:
                try:
                    old_page.close()
                except Exception:
                    pass
            time.sleep(1)

        # Keepalive tab
        keepalive = context.new_page()
        keepalive.goto("about:blank")

        rodada = 0

        # Montar lista intercalada: chatgpt_1, gemini_1, chatgpt_2, gemini_2...
        tab_order = []
        max_tabs = max(n for _, _, n in TAB_CONFIG)
        for tab_num in range(max_tabs):
            for ia_name, DriverClass, n_tabs in TAB_CONFIG:
                if tab_num < n_tabs:
                    tab_order.append((ia_name, DriverClass, tab_num + 1))

        log(f"Ordem das abas: {' → '.join(f'{ia}_{n}' for ia, _, n in tab_order)}")

        try:
            while True:
                rodada += 1
                log(f"")
                log(f"{'='*60}")
                log(f"  RODADA {rodada} — buscando {TOTAL_TABS} lotes de {BATCH_SIZE}")
                log(f"{'='*60}")

                # Buscar itens
                all_items = fetch_next_batch(BATCH_SIZE * TOTAL_TABS)
                if not all_items:
                    log("Base completa! Nenhum item pendente.")
                    break

                # Dividir em lotes
                lotes = []
                for i in range(0, len(all_items), BATCH_SIZE):
                    chunk = all_items[i:i + BATCH_SIZE]
                    if chunk:
                        lotes.append(chunk)

                if not lotes:
                    break

                # === ABRIR UMA ABA POR VEZ (sequencial) ===
                sessions = {}
                for lote_idx, (ia_name, DriverClass, tab_num) in enumerate(tab_order):
                    if lote_idx >= len(lotes):
                        break

                    items = lotes[lote_idx]
                    lote_counter += 1
                    lote_num = lote_counter
                    key = f"{ia_name}_{tab_num}"
                    prompt = build_prompt(items, prompt_header)

                    log(f"  [{key}] Abrindo... Lote #{lote_num}: {len(items)} itens")

                    try:
                        driver = DriverClass()
                        page = context.new_page()
                        page.set_default_timeout(60000)

                        chat_ok = driver.abrir_novo_chat(page)
                        if not chat_ok:
                            log(f"  [{key}] Falha ao abrir chat, pulando")
                            page.close()
                            log_lote(lote_num, ia_name, len(items), 0, 0, "falha_abrir_chat")
                            continue

                        driver.colar_mensagem(page, prompt)
                        time.sleep(0.3)
                        driver.enviar_mensagem(page)

                        sessions[key] = {
                            "driver": driver,
                            "page": page,
                            "items": items,
                            "ia_name": ia_name,
                            "lote_num": lote_num,
                            "status": "waiting",
                            "last_text": "",
                            "stable_since": time.time(),
                            "start_time": time.time(),
                        }
                        log(f"  [{key}] Enviado! Abrindo proxima aba...")

                    except Exception as e:
                        log(f"  [{key}] FALHA: {e}")
                        log_lote(lote_num, ia_name, len(items), 0, 0, f"erro: {str(e)[:100]}")

                    # Pausa curta entre abas (dar tempo pro browser)
                    time.sleep(2)

                log(f"  {len(sessions)} abas disparadas, polling...")

                # === POLLING (todas ao mesmo tempo) ===
                waiting = {k: s for k, s in sessions.items() if s["status"] == "waiting"}
                while waiting:
                    for key, sess in list(waiting.items()):
                        elapsed = time.time() - sess["start_time"]
                        driver = sess["driver"]
                        page = sess["page"]

                        # Timeout (max 20 min, override do driver)
                        if elapsed > MAX_TIMEOUT_SEC:
                            log(f"  [{key}] TIMEOUT ({int(elapsed)}s)")
                            sess["status"] = "timeout"
                            try:
                                sess["response"] = driver._get_response_text(page)
                            except Exception:
                                sess["response"] = ""
                            del waiting[key]
                            continue

                        try:
                            current = driver._get_response_text(page)
                            loading = driver._is_loading(page)
                        except Exception:
                            continue

                        if current != sess["last_text"]:
                            sess["last_text"] = current
                            sess["stable_since"] = time.time()
                        elif loading:
                            sess["stable_since"] = time.time()
                        elif (elapsed >= driver.MIN_WAIT_SEC
                              and (time.time() - sess["stable_since"]) >= STABLE_SEC
                              and len(current or "") > 50):
                            log(f"  [{key}] Resposta completa ({int(elapsed)}s, {len(current)} chars)")
                            sess["status"] = "done"
                            sess["response"] = current
                            del waiting[key]

                            # Processar IMEDIATAMENTE ao terminar (nao espera as outras)
                            _processar_sessao(key, sess)
                            continue

                        # Log progresso a cada ~30s
                        if int(elapsed) > 0 and int(elapsed) % 30 < CHECK_SEC:
                            chars = len(current or "")
                            tag = " [gerando]" if loading else ""
                            log(f"  [{key}] {int(elapsed)}s, {chars} chars{tag}")

                    time.sleep(CHECK_SEC)

                # Processar timeouts que sobraram
                for key, sess in sessions.items():
                    if sess["status"] == "timeout":
                        _processar_sessao(key, sess)

                # Fechar todas as abas
                for key, sess in sessions.items():
                    if "page" in sess:
                        try:
                            sess["page"].close()
                        except Exception:
                            pass

                # Status da rodada
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM y2_results")
                total_done = cur.fetchone()[0]
                conn.close()
                log(f"  Rodada {rodada} concluida. Total processado: {total_done:,}")

                time.sleep(3)

        finally:
            try:
                context.close()
            except Exception:
                pass

    log("")
    log("=" * 60)
    log("  FINALIZADO — Chrome 3o browser (ChatGPT + Gemini) [M-N]")
    log("=" * 60)


if __name__ == "__main__":
    main()
