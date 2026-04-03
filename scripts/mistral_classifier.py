"""
Mistral Classifier: Classificacao de vinhos via Mistral Le Chat (browser).
4 abas simultaneas, 1000 itens por lote, insere no y2_results.

Integra com pipeline_y2.py existente (mesma tabela, dashboard, match Vivino).

Uso:
  python scripts/mistral_classifier.py

Ou via BAT:
  scripts/run_mistral_classifier.bat
"""

import sys
import os
import json
import time
import re
import psycopg2
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# === CONFIG ===
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "winegod_db"
DB_USER = "postgres"
DB_PASS = "postgres123"

BATCH_SIZE = 1000          # itens por lote
TABS = 4                   # abas simultaneas
GENERATE_AHEAD = 40        # gerar N lotes por rodada
TIMEOUT_SEC = 420           # 7 min timeout por resposta
STABLE_SEC = 30             # texto estavel por 30s = resposta completa
MIN_WAIT_SEC = 240          # esperar MINIMO 4 min antes de checar estabilidade
CHECK_SEC = 3               # poll a cada 3s
MAX_CONSECUTIVE_FAIL = 3    # parar apos N falhas seguidas
MIN_LINES_RATIO = 0.70      # minimo 70% de linhas pra considerar sucesso

BROWSER_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mistral_browser_state")
TRACKING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mistral_tracking.json")

# === PROMPT (expandido com 14 campos) ===
PROMPT_HEADER = """Classifique e extraia dados dos itens abaixo. Sao produtos de lojas de vinho — podem ser vinhos, destilados, cervejas, acessorios, agua, etc.

Exemplos do nosso banco (para referencia de formato):
  produtor: "chateau levangile"  vinho: "pomerol"
  produtor: "campo viejo"  vinho: "reserva rioja"
  produtor: "penfolds"  vinho: "grange shiraz"
  produtor: "pizzato"  vinho: "fausto brut branco"
  produtor: "inniskillin"  vinho: "riesling icewine"
  produtor: "chateau montrose"  vinho: "montrose"
  produtor: "quinta do noval"  vinho: "noval"
  produtor: "gaja"  vinho: "gaia & rey chardonnay"
  produtor: "michele chiarlo"  vinho: "nivole moscato d'asti"
  produtor: "felton road"  vinho: "block 3 pinot noir"

TODOS os itens. Uma linha por item. Sem markdown. Sem explicacoes.

Formato:
1. X
2. S
3. W|Produtor|Vinho|Pais|Cor|Uva|Regiao|SubRegiao|Safra|ABV|Classificacao|Corpo|Harmonizacao|Docura
4. W|Produtor|Vinho|Pais|Cor|Uva|Regiao|SubRegiao|Safra|ABV|Classificacao|Corpo|Harmonizacao|Docura|=3

Campos:
- Produtor = vinicola/bodega/domaine/chateau, minusculo, sem acento. O produtor e quem FAZ o vinho, nao o nome do vinho.
  Ex: gaja (nao "gaia & rey"), michele chiarlo (nao "nivole"), felton road (nao "block 3"), castello di ama (nao "ama"), banfi (nao "fonte alla selva")
- Vinho = nome do vinho SEM o produtor, minusculo, sem acento.
  NUNCA deixe ?? se o nome e derivavel do input.
  Se produtor e vinho sao o mesmo nome, repita sem prefixo:
    "chateau montrose" → produtor: chateau montrose, vinho: montrose
    "quinta do noval" → produtor: quinta do noval, vinho: noval
    "dom perignon" → produtor: dom perignon, vinho: dom perignon
  Se o input so tem produtor+uva:
    "larentis malbec" → produtor: larentis, vinho: malbec
  Se o input tem produtor+linha+uva:
    "norton barrel select malbec" → produtor: norton, vinho: barrel select malbec
- Pais = 2 letras (fr, it, ar, us, au, br, ca, es, cl, pt, de, za, nz, at, hu, gr, hr, gb, jp, etc). ?? se nao sabe
- Cor: r=tinto w=branco p=rose s=espumante f=fortificado d=sobremesa
- Uva = uva(s) principal(is). Ex: malbec, cabernet sauvignon, chardonnay. Para blends listar as 2-3 principais: merlot, cabernet franc. ?? se nao sabe
- Regiao = regiao vinicola. Ex: bordeaux, mendoza, okanagan valley, serra gaucha. ?? se nao sabe
- SubRegiao = sub-regiao especifica. Ex: pauillac, saint-estephe, lujan de cuyo, golden mile bench. ?? se nao sabe
- Safra = ano (ex: 2019, 2020). NV se sem safra. ?? se nao sabe
- ABV = teor alcoolico estimado em %. Estimar pelo estilo se nao souber o valor exato (champagne ~12, bordeaux ~13.5, amarone ~15, porto ~20, riesling alemao ~10). ?? so se nao tem como estimar
- Classificacao = DOC, DOCG, AOC, DO, DOCa, DOQ, DOP, IGT, IGP, AVA, VDP, Grand Cru, 1er Grand Cru Classe, 2eme Grand Cru Classe, 3eme Grand Cru Classe, Cru Bourgeois, Grand Cru Classe, Reserva, Gran Reserva, Icewine, etc. ?? se nao tem
- Corpo = leve, medio, encorpado. ?? se nao sabe
- Harmonizacao = 1-3 pratos (ex: carne vermelha, queijo, frutos do mar). ?? se nao sabe
- Docura = seco, demi-sec, doce, brut, extra brut, brut nature. ?? se nao sabe
- X = NAO e vinho (cerveja, seltzer, cooler, sidra, agua, acessorio, caixa, gift basket, UI de site, desconto, roupa, comida)
- S = destilado (whisky, gin, rum, vodka, tequila, grappa, cachaca, brandy, calvados, pisco, soju, baijiu, shochu)
- W = vinho. Inclui: espumante, champagne, cava, prosecco, cremant, pet-nat, fortificado (sherry, porto, madeira, marsala, manzanilla, jerez fino, oloroso, amontillado), sobremesa, icewine, sake, yakju, huangjiu
- NAO invente dados. Se nao sabe, use ??.

FORTIFICADOS — ATENCAO:
Sherry, porto, madeira, marsala, manzanilla, fino, oloroso, amontillado, palo cortado = W (cor f)
Exemplos:
  "manzanilla en rama" → W|??|manzanilla en rama|es|f|palomino|andalucia|sanlucar de barrameda|...
  "porto tawny 10 years" → W|??|tawny 10 years|pt|f|??|douro|...|doce
  "marsala rubino" → W|pellegrino|rubino marsala|it|f|??|sicily|...|doce
NAO classificar fortificados como S. Calvados, brandy, grappa = S.

DUPLICATAS — IMPORTANTE:
=M significa que o item e o MESMO vinho do item M (duplicata).
Marque =M mesmo se o nome estiver escrito diferente.
Exemplos de duplicata:
  "2016 chateau montrose" e "chateau montrose 2016" → mesmo vinho, marcar =M
  "larentis malbec preco" e "larentis malbec" → mesmo vinho, "preco" e lixo do site
  "peller cabernet sauvignon" e "peller estates cabernet sauvignon" → mesmo produtor e vinho
Exemplos que NAO sao duplicata:
  "larentis malbec" e "larentis merlot" → uvas diferentes = vinhos diferentes
  "chateau montrose 2016" e "chateau montrose 2014" → safras diferentes = vinhos diferentes
ATENCAO: mesmo produtor com uvas diferentes NAO e duplicata.

"""


# === HELPERS ===

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def norm(s):
    """Normaliza texto: minusculo, sem acento, sem caracteres especiais."""
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
    """Converte '??' pra None (NULL no banco)."""
    if not val or val.strip() in ("??", "?", ""):
        return None
    return val.strip()


def load_tracking():
    """Carrega tracking.json ou cria novo."""
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "config": {
            "batch_size": BATCH_SIZE,
            "max_tabs": TABS,
            "max_consecutive_failures": MAX_CONSECUTIVE_FAIL,
        },
        "batches": {},
        "stats": {
            "total_batches": 0,
            "completed": 0,
            "failed": 0,
            "partial": 0,
            "pending": 0,
            "consecutive_failures": 0,
            "last_run": None,
        },
    }


def save_tracking(tracking):
    with open(TRACKING_FILE, "w", encoding="utf-8") as f:
        json.dump(tracking, f, ensure_ascii=False, indent=2)


def get_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
        options="-c client_encoding=UTF8",
    )


def setup_new_columns():
    """Adiciona colunas novas na y2_results (se nao existem)."""
    conn = get_db()
    cur = conn.cursor()
    new_cols = [
        ("uva", "TEXT"),
        ("regiao", "TEXT"),
        ("subregiao", "TEXT"),
        ("safra", "VARCHAR(10)"),
        ("abv", "VARCHAR(10)"),
        ("denominacao", "TEXT"),
        ("corpo", "VARCHAR(20)"),
        ("harmonizacao", "TEXT"),
        ("docura", "VARCHAR(20)"),
        ("fonte_llm", "VARCHAR(20) DEFAULT 'gemini'"),
    ]
    for col_name, col_type in new_cols:
        try:
            cur.execute(f"ALTER TABLE y2_results ADD COLUMN {col_name} {col_type}")
            log(f"  Coluna {col_name} adicionada")
        except psycopg2.errors.DuplicateColumn:
            conn.rollback()
        except Exception as e:
            conn.rollback()
            log(f"  [AVISO] Coluna {col_name}: {e}")
    conn.commit()
    conn.close()
    log("Colunas verificadas/criadas")


def fetch_next_batch(batch_size=BATCH_SIZE):
    """Busca proximos N itens da wines_clean que NAO estao no y2_results."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT wc.id, wc.nome_normalizado
        FROM wines_clean wc
        LEFT JOIN y2_results yr ON yr.clean_id = wc.id
        WHERE yr.id IS NULL
        ORDER BY wc.nome_normalizado
        LIMIT %s
    """, (batch_size,))
    rows = cur.fetchall()
    conn.close()
    return [{"clean_id": r[0], "loja_nome": r[1] or ""} for r in rows]


def parse_response(text, items):
    """Parseia resposta do Mistral e retorna lista de dicts.

    Cada dict tem: clean_id, classificacao, prod_banco, vinho_banco, pais, cor,
                   uva, regiao, subregiao, safra, abv, denominacao, corpo,
                   harmonizacao, docura, duplicata_de, status
    """
    results = []
    lines_parsed = {}

    # Debug: salvar primeiras 500 chars da resposta pra diagnostico
    if not lines_parsed:
        debug_path = os.path.join(os.path.dirname(TRACKING_FILE), "_debug_mistral_response.txt")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(text[:2000])

    # Parsear linhas: aceita "N. CONTEUDO" ou apenas "CONTEUDO" (sem numero)
    sequential_num = 0
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Tentar formato com numero: "1. W|..."
        match = re.match(r'^(\d+)\.\s*(.+)', line)
        if match:
            num = int(match.group(1))
            content = match.group(2).strip()
            lines_parsed[num] = content
        # Formato sem numero: "W|...", "X", "S" (atribui sequencial)
        elif line.startswith(("W|", "X", "S")):
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
            "fonte_llm": "mistral",
        }

        if not llm:
            results.append(result)
            continue

        if llm.startswith("X"):
            result["classificacao"] = "X"
            result["status"] = "not_wine"

        elif llm.startswith("S"):
            result["classificacao"] = "S"
            result["status"] = "spirit"
            # S pode ter campos opcionais
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

            # Checar duplicata (ultimo campo pode ser =N)
            is_dup = False
            dup_ref = None
            last_part = parts[-1].strip()
            if last_part.startswith("="):
                is_dup = True
                try:
                    dup_ref_num = int(last_part[1:])
                    # Converter numero do lote pra clean_id
                    if 1 <= dup_ref_num <= len(items):
                        dup_ref = items[dup_ref_num - 1]["clean_id"]
                except (ValueError, IndexError):
                    pass
                parts = parts[:-1]  # remover o =N do parsing

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


def build_prompt(items):
    """Monta prompt completo: header + itens numerados."""
    lines = [f"{i+1}. {item['loja_nome']}" for i, item in enumerate(items)]
    return PROMPT_HEADER + "\n".join(lines)


# === MAIN ===

def main():
    log("=" * 60)
    log("  MISTRAL CLASSIFIER — Wine Classification via Browser")
    log(f"  {BATCH_SIZE} itens/lote × {TABS} abas = {BATCH_SIZE * TABS} itens/rodada")
    log("=" * 60)

    # Setup DB
    setup_new_columns()

    # Contar pendentes
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM wines_clean")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM y2_results")
    done = cur.fetchone()[0]
    conn.close()
    pending = total - done
    log(f"Total: {total} | Feito: {done} | Pendente: {pending}")
    log(f"Lotes estimados: {(pending + BATCH_SIZE - 1) // BATCH_SIZE}")
    log("")

    if pending == 0:
        log("Nada pendente. Encerrando.")
        return

    # Tracking
    tracking = load_tracking()

    # Abrir browser
    from playwright.sync_api import sync_playwright

    os.makedirs(BROWSER_STATE, exist_ok=True)

    with sync_playwright() as p:
        log("Abrindo Chrome (perfil mistral)...")
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

        # Keepalive tab
        keepalive = context.new_page()
        keepalive.goto("about:blank")

        consecutive_failures = 0
        rodada = 0

        try:
            while True:
                rodada += 1
                log(f"")
                log(f"{'='*50}")
                log(f"  RODADA {rodada} — buscando {TABS} lotes de {BATCH_SIZE}")
                log(f"{'='*50}")

                # Buscar itens para N lotes
                all_items = fetch_next_batch(BATCH_SIZE * TABS)
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

                actual_tabs = min(len(lotes), TABS)
                log(f"  {len(all_items)} itens em {len(lotes)} lotes, abrindo {actual_tabs} abas")

                # Abrir abas e colar prompts
                sessions = {}
                for tab_idx in range(actual_tabs):
                    items = lotes[tab_idx]
                    prompt = build_prompt(items)
                    lote_id = f"rodada{rodada}_tab{tab_idx+1}"

                    log(f"  [{lote_id}] {len(items)} itens, prompt: {len(prompt)} chars")

                    try:
                        page = context.new_page()
                        page.goto("https://chat.mistral.ai/chat",
                                  wait_until="domcontentloaded", timeout=60000)
                        time.sleep(5)

                        # Focar e colar
                        focused = page.evaluate("""() => {
                            const el = document.querySelector('div.ProseMirror[contenteditable="true"]') ||
                                       document.querySelector('div[contenteditable="true"]');
                            if (el) { el.focus(); el.click(); return true; }
                            return false;
                        }""")

                        if not focused:
                            log(f"  [{lote_id}] FALHA — campo input nao encontrado")
                            page.close()
                            sessions[lote_id] = {"status": "fail_no_input", "items": items}
                            continue

                        time.sleep(0.3)
                        page.keyboard.press("Control+a")
                        time.sleep(0.1)
                        page.keyboard.press("Backspace")
                        time.sleep(0.2)

                        # Colar via clipboard
                        page.evaluate("""(text) => {
                            navigator.clipboard.writeText(text);
                        }""", prompt)
                        time.sleep(0.5)
                        page.keyboard.press("Control+v")
                        time.sleep(4)  # prompt grande

                        # Enviar
                        sent = page.evaluate("""() => {
                            const btns = document.querySelectorAll('button[type="submit"]');
                            for (const btn of btns) {
                                const text = btn.innerText.trim();
                                if (!text || text.length < 3) { btn.click(); return true; }
                            }
                            return false;
                        }""")
                        if not sent:
                            page.keyboard.press("Enter")

                        time.sleep(2)
                        log(f"  [{lote_id}] Prompt enviado")

                        sessions[lote_id] = {
                            "page": page,
                            "items": items,
                            "status": "waiting",
                            "last_text": "",
                            "stable_since": time.time(),
                            "start_time": time.time(),
                        }

                    except Exception as e:
                        log(f"  [{lote_id}] FALHA ao abrir: {e}")
                        sessions[lote_id] = {"status": "fail_open", "items": items}

                # Poll todas as abas
                waiting = {k: s for k, s in sessions.items() if s["status"] == "waiting"}
                while waiting:
                    for lote_id, sess in list(waiting.items()):
                        elapsed = time.time() - sess["start_time"]
                        if elapsed > TIMEOUT_SEC:
                            log(f"  [{lote_id}] TIMEOUT ({int(elapsed)}s)")
                            sess["status"] = "timeout"
                            del waiting[lote_id]
                            continue

                        try:
                            page = sess["page"]
                            # Pegar ultima resposta
                            md = page.locator("div[class*='markdown-container']")
                            count = md.count()
                            current = ""
                            if count > 0:
                                current = md.nth(count - 1).inner_text(timeout=3000)

                            # Verificar loading
                            loading = False
                            stop_btn = page.locator("button[aria-label*='Stop' i], button[aria-label*='Parar' i]")
                            if stop_btn.count() > 0:
                                try:
                                    loading = stop_btn.first.is_visible(timeout=1000)
                                except Exception:
                                    pass
                        except Exception:
                            continue

                        if current != sess["last_text"]:
                            sess["last_text"] = current
                            sess["stable_since"] = time.time()
                        elif loading:
                            sess["stable_since"] = time.time()
                        elif elapsed >= MIN_WAIT_SEC and (time.time() - sess["stable_since"]) >= STABLE_SEC and len(current or "") > 50:
                            log(f"  [{lote_id}] Resposta completa ({int(elapsed)}s, {len(current)} chars)")
                            sess["status"] = "done"
                            sess["response"] = current
                            del waiting[lote_id]
                            continue

                        # Log progresso
                        if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                            chars = len(current or "")
                            tag = " [gerando]" if loading else ""
                            log(f"  [{lote_id}] {int(elapsed)}s, {chars} chars{tag}")

                    time.sleep(CHECK_SEC)

                # Processar resultados
                rodada_ok = 0
                rodada_fail = 0

                for lote_id, sess in sessions.items():
                    items = sess["items"]
                    response = sess.get("response", "")

                    batch_record = {
                        "lines_in": len(items),
                        "started_at": datetime.fromtimestamp(sess.get("start_time", time.time())).isoformat(),
                        "finished_at": datetime.now().isoformat(),
                        "attempt": 1,
                    }

                    if sess["status"] in ("fail_no_input", "fail_open"):
                        batch_record["status"] = sess["status"]
                        batch_record["lines_out"] = 0
                        batch_record["error"] = sess["status"]
                        rodada_fail += 1

                    elif sess["status"] == "timeout":
                        # Tentar parsear o que veio
                        if response:
                            results, lines_out = parse_response(response, items)
                            batch_record["lines_out"] = lines_out
                            if lines_out >= len(items) * MIN_LINES_RATIO:
                                insert_results(results)
                                batch_record["status"] = "partial"
                                log(f"  [{lote_id}] Timeout mas parseou {lines_out}/{len(items)} — salvo como parcial")
                                rodada_ok += 1
                            else:
                                batch_record["status"] = "fail_truncated"
                                batch_record["error"] = f"timeout + truncado: {lines_out}/{len(items)}"
                                rodada_fail += 1
                        else:
                            batch_record["status"] = "fail_no_response"
                            batch_record["lines_out"] = 0
                            rodada_fail += 1

                    elif sess["status"] == "done":
                        results, lines_out = parse_response(response, items)
                        batch_record["lines_out"] = lines_out

                        if lines_out >= len(items) * MIN_LINES_RATIO:
                            inserted = insert_results(results)
                            wines = sum(1 for r in results if r["classificacao"] == "W")
                            not_wine = sum(1 for r in results if r["classificacao"] == "X")
                            spirits = sum(1 for r in results if r["classificacao"] == "S")
                            errors = sum(1 for r in results if r["status"] == "error")

                            batch_record["status"] = "success"
                            batch_record["wines"] = wines
                            batch_record["not_wine"] = not_wine
                            batch_record["spirits"] = spirits
                            batch_record["errors_parse"] = errors
                            batch_record["inserted"] = inserted

                            log(f"  [{lote_id}] OK: {lines_out} linhas, W={wines} X={not_wine} S={spirits} E={errors}")
                            rodada_ok += 1
                        else:
                            batch_record["status"] = "fail_truncated"
                            batch_record["error"] = f"truncado: {lines_out}/{len(items)}"
                            log(f"  [{lote_id}] FALHA: truncado {lines_out}/{len(items)}")
                            rodada_fail += 1

                    tracking["batches"][lote_id] = batch_record

                    # Fechar aba
                    if "page" in sess:
                        try:
                            sess["page"].close()
                        except Exception:
                            pass

                # Atualizar tracking
                if rodada_fail > 0 and rodada_ok == 0:
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0

                tracking["stats"]["completed"] = sum(1 for b in tracking["batches"].values() if b.get("status") in ("success", "partial"))
                tracking["stats"]["failed"] = sum(1 for b in tracking["batches"].values() if b.get("status", "").startswith("fail"))
                tracking["stats"]["consecutive_failures"] = consecutive_failures
                tracking["stats"]["last_run"] = datetime.now().isoformat()
                save_tracking(tracking)

                log(f"  Rodada {rodada}: OK={rodada_ok} FAIL={rodada_fail} (consecutivas: {consecutive_failures}/{MAX_CONSECUTIVE_FAIL})")

                # Regra de parada
                if consecutive_failures >= MAX_CONSECUTIVE_FAIL:
                    log(f"")
                    log(f"!!! PARANDO — {MAX_CONSECUTIVE_FAIL} falhas consecutivas !!!")
                    log(f"Verifique o Mistral e reinicie.")
                    break

                # Pausa entre rodadas
                time.sleep(3)

        finally:
            try:
                context.close()
            except Exception:
                pass

    log("")
    log("=" * 60)
    log("  FINALIZADO")
    log(f"  Tracking salvo em: {TRACKING_FILE}")
    log("=" * 60)


if __name__ == "__main__":
    main()
