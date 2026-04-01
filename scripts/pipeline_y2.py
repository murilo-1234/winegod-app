"""
Pipeline Y2: Classificacao de vinhos com Gemini Flash + Match Vivino.
Dashboard visual com progresso em tempo real.
50 workers paralelos. Start/Stop/Resume.
"""
import csv, os, time, re, sys, json, threading, queue
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, render_template_string
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
import google.generativeai as genai

# === CONFIG ===
API_KEY = "AIzaSyBsEL2932vDZcVGdkqUiDbXl_8BKZ-Pb94"
MODEL = "gemini-2.5-flash"
BATCH_SIZE = 20
WORKERS = 50
THRESHOLD = 0.30
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "winegod_db"
DB_USER = "postgres"
DB_PASS = "postgres123"
PORT = 8050

# === GLOBALS ===
app = Flask(__name__)
state = {
    "status": "stopped",  # stopped, running, paused
    "started_at": None,
    "total_items": 0,
    "processed": 0,
    "wines": 0,
    "not_wine": 0,
    "spirits": 0,
    "duplicates": 0,
    "unique_wines": 0,
    "match_vivino": 0,
    "match_errado": 0,
    "wine_new": 0,
    "errors": 0,
    "batches_total": 0,
    "batches_done": 0,
    "items_per_sec": 0,
    "eta_minutes": 0,
    "last_batch_time": 0,
}
stop_event = threading.Event()
worker_lock = threading.Lock()

# === PROMPT ===
PROMPT = """Exemplos do nosso banco:
  produtor: "chateau levangile"  vinho: "pomerol"
  produtor: "campo viejo"  vinho: "reserva rioja"
  produtor: "penfolds"  vinho: "grange shiraz"

TODOS os itens. Uma linha por item. Sem markdown.

Formato:
1. X
2. S
3. W|ProdBanco|VinhoBanco|Pais|Cor
4. W|ProdBanco|VinhoBanco|Pais|Cor|=3

ProdBanco/VinhoBanco = minusculo, sem acento, l' junto, saint junto.
=M=duplicata. X=nao vinho. S=destilado. ??=nao sabe. NAO invente.

"""

# === HELPERS ===

def norm(s):
    s = s.lower().strip()
    for o, n in [("\u00e1","a"),("\u00e0","a"),("\u00e2","a"),("\u00e3","a"),("\u00e4","a"),
                 ("\u00e9","e"),("\u00e8","e"),("\u00ea","e"),("\u00eb","e"),
                 ("\u00ed","i"),("\u00ec","i"),("\u00ee","i"),("\u00ef","i"),
                 ("\u00f3","o"),("\u00f2","o"),("\u00f4","o"),("\u00f5","o"),("\u00f6","o"),
                 ("\u00fa","u"),("\u00f9","u"),("\u00fb","u"),("\u00fc","u"),
                 ("\u00f1","n"),("\u00e7","c")]:
        s = s.replace(o, n)
    s = re.sub(r"['\u2019\u2018`]", "", s)
    s = re.sub(r"-", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def parse_llm(text):
    m = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        p = line.split(". ", 1)
        if len(p) == 2 and p[0].strip().isdigit():
            m[int(p[0].strip())] = p[1].strip()
    return m

def setup_db():
    """Criar tabelas de resultado se nao existem."""
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                            user=DB_USER, password=DB_PASS,
                            options="-c client_encoding=UTF8")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS y2_results (
            id SERIAL PRIMARY KEY,
            clean_id INTEGER,
            loja_nome TEXT,
            classificacao VARCHAR(1),  -- W, X, S
            prod_banco TEXT,
            vinho_banco TEXT,
            pais VARCHAR(5),
            cor VARCHAR(1),
            duplicata_de INTEGER,  -- clean_id do original
            vivino_id INTEGER,
            vivino_produtor TEXT,
            vivino_nome TEXT,
            match_score REAL,
            status VARCHAR(20),  -- matched, new, not_wine, spirit, duplicate, error
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_y2_clean_id ON y2_results(clean_id);
        CREATE INDEX IF NOT EXISTS idx_y2_status ON y2_results(status);
        CREATE INDEX IF NOT EXISTS idx_wines_clean_nome ON wines_clean(nome_normalizado);
        CREATE INDEX IF NOT EXISTS idx_wines_clean_id ON wines_clean(id);
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS y2_progress (
            id INTEGER PRIMARY KEY DEFAULT 1,
            last_offset INTEGER DEFAULT 0,
            total_items INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW()
        );
        INSERT INTO y2_progress (id, last_offset, total_items)
        VALUES (1, 0, 0) ON CONFLICT (id) DO NOTHING;
    """)
    conn.commit()
    conn.close()

def get_progress():
    """Ler de onde parou."""
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                            user=DB_USER, password=DB_PASS,
                            options="-c client_encoding=UTF8")
    cur = conn.cursor()
    cur.execute("SELECT last_offset, total_items FROM y2_progress WHERE id=1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0, row[1] if row else 0

def save_progress(offset, total):
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                            user=DB_USER, password=DB_PASS,
                            options="-c client_encoding=UTF8")
    cur = conn.cursor()
    cur.execute("UPDATE y2_progress SET last_offset=%s, total_items=%s, updated_at=NOW() WHERE id=1",
                (offset, total))
    conn.commit()
    conn.close()

def count_stats():
    """Contar stats das tabelas de resultado."""
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                            user=DB_USER, password=DB_PASS,
                            options="-c client_encoding=UTF8")
    cur = conn.cursor()
    cur.execute("""
        SELECT status, COUNT(*) FROM y2_results GROUP BY status
    """)
    stats = dict(cur.fetchall())
    conn.close()
    return stats


def process_batch(model, items, start_num, db_pool):
    """Processa 1 batch de 20 itens: APENAS LLM + INSERT simples (sem pg_trgm)."""
    if stop_event.is_set():
        return []

    txt = "\n".join(f"{start_num + i}. {it['loja_nome']}" for i, it in enumerate(items))

    # Chamar LLM
    lines = {}
    for att in range(5):
        if stop_event.is_set():
            return []
        try:
            r = model.generate_content(PROMPT + txt,
                generation_config=genai.types.GenerationConfig(temperature=0.1, max_output_tokens=4096))
            lines = parse_llm(r.text.strip())
            if len(lines) >= len(items) * 0.7:
                break
        except Exception as e:
            time.sleep(2)

    results = []
    conn = db_pool.getconn()
    cur = conn.cursor()

    for i, item in enumerate(items):
        num = start_num + i
        llm = lines.get(num, "MISSING")
        clean_id = int(item["clean_id"])
        loja = item["loja_nome"]

        if llm.startswith("X"):
            results.append({"clean_id": clean_id, "loja": loja, "class": "X", "status": "not_wine"})
            cur.execute("""INSERT INTO y2_results (clean_id, loja_nome, classificacao, status)
                          VALUES (%s, %s, 'X', 'not_wine') ON CONFLICT DO NOTHING""",
                       (clean_id, loja))

        elif llm.startswith("S"):
            results.append({"clean_id": clean_id, "loja": loja, "class": "S", "status": "spirit"})
            cur.execute("""INSERT INTO y2_results (clean_id, loja_nome, classificacao, status)
                          VALUES (%s, %s, 'S', 'spirit') ON CONFLICT DO NOTHING""",
                       (clean_id, loja))

        elif llm.startswith("W"):
            parts = llm.split("|")
            if len(parts) < 5:
                results.append({"clean_id": clean_id, "loja": loja, "class": "W", "status": "error"})
                cur.execute("""INSERT INTO y2_results (clean_id, loja_nome, classificacao, status)
                              VALUES (%s, %s, 'W', 'error') ON CONFLICT DO NOTHING""",
                           (clean_id, loja))
                continue

            prod = norm(parts[1].strip().split("=")[0].strip())
            vin = norm(parts[2].strip().split("=")[0].strip())
            pais = parts[3].strip()[:5] if len(parts) > 3 else "??"
            cor = parts[4].strip()[:1] if len(parts) > 4 else "?"
            is_dup = "=" in llm
            dup_ref = None
            if is_dup:
                try:
                    ref = llm.split("=")[-1].strip()
                    dup_ref = int(ref) if ref.isdigit() else None
                except:
                    pass

            # INSERT simples — match Vivino sera feito na Fase 2
            status = "duplicate" if is_dup else "pending_match"
            results.append({"clean_id": clean_id, "loja": loja, "class": "W", "status": status})
            cur.execute("""INSERT INTO y2_results (clean_id, loja_nome, classificacao, prod_banco, vinho_banco, pais, cor, duplicata_de, status)
                          VALUES (%s,%s,'W',%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                       (clean_id, loja, prod, vin, pais, cor, dup_ref, status))
        else:
            pass  # item sem resposta do LLM — nao conta como erro, sera reprocessado

    conn.commit()
    db_pool.putconn(conn)
    return results


def run_pipeline():
    """Roda o pipeline com 50 workers."""
    global state

    genai.configure(api_key=API_KEY)

    # Contar total
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                            user=DB_USER, password=DB_PASS,
                            options="-c client_encoding=UTF8")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM wines_clean")
    total = cur.fetchone()[0]
    conn.close()

    # Contar quantos ja foram processados (do banco, nao do progresso salvo)
    conn3 = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                             user=DB_USER, password=DB_PASS,
                             options="-c client_encoding=UTF8")
    cur3 = conn3.cursor()
    cur3.execute("SELECT COUNT(*) FROM y2_results")
    offset = cur3.fetchone()[0]
    conn3.close()
    save_progress(offset, total)

    state["total_items"] = total
    state["processed"] = offset
    state["batches_total"] = (total - offset + BATCH_SIZE - 1) // BATCH_SIZE
    state["status"] = "running"
    state["started_at"] = datetime.now().isoformat()

    # Pool de conexoes
    db_pool = ThreadedConnectionPool(10, WORKERS + 10,
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
        options="-c client_encoding=UTF8")

    # Carregar itens em chunks
    batch_queue = queue.Queue(maxsize=WORKERS * 2)
    start_time = time.time()

    def loader():
        """Thread que carrega itens. Keyset pagination por ID (sempre rapido)."""
        conn2 = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                                 user=DB_USER, password=DB_PASS,
                                 options="-c client_encoding=UTF8")

        # IDs ja feitos
        cur_ids = conn2.cursor()
        cur_ids.execute("SELECT clean_id FROM y2_results")
        done_ids = set(r[0] for r in cur_ids.fetchall())
        cur_ids.close()
        print(f"  Loader: {len(done_ids)} ja processados, pulando...")

        cur2 = conn2.cursor()
        last_id = 0
        batch_num = 0
        batch_items = []
        FETCH_SIZE = 5000

        while not stop_event.is_set():
            cur2.execute("SELECT id, nome_normalizado FROM wines_clean WHERE id > %s ORDER BY id LIMIT %s",
                        (last_id, FETCH_SIZE))
            rows = cur2.fetchall()
            if not rows:
                break

            last_id = rows[-1][0]

            for r in rows:
                if r[0] in done_ids:
                    continue
                batch_items.append({"clean_id": r[0], "loja_nome": r[1] or ""})
                if len(batch_items) >= BATCH_SIZE:
                    batch_queue.put((batch_num, batch_num * BATCH_SIZE, batch_items))
                    batch_items = []
                    batch_num += 1

        if batch_items and not stop_event.is_set():
            batch_queue.put((batch_num, batch_num * BATCH_SIZE, batch_items))

        batch_queue.put(None)
        conn2.close()

    loader_thread = threading.Thread(target=loader, daemon=True)
    loader_thread.start()

    def worker(model_instance):
        """Worker que processa batches da fila."""
        while not stop_event.is_set():
            try:
                item = batch_queue.get(timeout=5)
            except queue.Empty:
                continue
            if item is None:
                batch_queue.put(None)  # propagar sinal
                break

            batch_num, batch_offset, items = item
            start_num = 1  # numeros dentro do batch

            results = process_batch(model_instance, items, start_num, db_pool)

            with worker_lock:
                for r in results:
                    state["processed"] += 1
                    if r["class"] == "W":
                        state["wines"] += 1
                        if r["status"] == "pending_match":
                            state["wine_new"] += 1  # pendente match (Fase 2)
                        elif r["status"] == "duplicate":
                            state["duplicates"] += 1
                        elif r["status"] == "error":
                            state["match_errado"] += 1
                    elif r["class"] == "X":
                        state["not_wine"] += 1
                    elif r["class"] == "S":
                        state["spirits"] += 1

                state["batches_done"] += 1
                elapsed = time.time() - start_time
                if elapsed > 0:
                    state["items_per_sec"] = round(state["processed"] / elapsed, 1)
                remaining = state["total_items"] - state["processed"]
                if state["items_per_sec"] > 0:
                    state["eta_minutes"] = round(remaining / state["items_per_sec"] / 60, 1)

                # Salvar progresso a cada 10 batches
                if state["batches_done"] % 10 == 0:
                    save_progress(state["processed"], state["total_items"])

    # Criar modelos (1 por worker)
    models = [genai.GenerativeModel(MODEL) for _ in range(WORKERS)]

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = [executor.submit(worker, models[i]) for i in range(WORKERS)]
        for f in as_completed(futures):
            pass

    save_progress(state["processed"], state["total_items"])
    state["status"] = "stopped" if stop_event.is_set() else "completed"
    db_pool.closeall()


def run_vivino_match():
    """Fase 2: Match Vivino em background. 1 conexao, sem afetar workers."""
    conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                            user=DB_USER, password=DB_PASS,
                            options="-c client_encoding=UTF8")
    cur = conn.cursor()

    while not stop_event.is_set():
        # Pegar 100 itens pendentes
        cur.execute("""
            SELECT id, prod_banco, vinho_banco
            FROM y2_results
            WHERE status = 'pending_match'
            AND prod_banco IS NOT NULL AND prod_banco != '' AND prod_banco != '??'
            LIMIT 100
        """)
        rows = cur.fetchall()

        if not rows:
            time.sleep(5)  # esperar mais itens
            continue

        for row_id, prod, vin in rows:
            if stop_event.is_set():
                break

            search = f"{prod} {vin}".strip()
            if len(search) < 4:
                cur.execute("UPDATE y2_results SET status='new' WHERE id=%s", (row_id,))
                continue

            cur.execute("""
                SELECT id, produtor_normalizado, nome_normalizado,
                       similarity(texto_busca, %s) as ts
                FROM vivino_match WHERE texto_busca %% %s
                ORDER BY similarity(texto_busca, %s) DESC LIMIT 1
            """, (search, search, search))
            cand = cur.fetchone()

            if cand and cand[3] >= THRESHOLD:
                cur.execute("""
                    UPDATE y2_results
                    SET vivino_id=%s, vivino_produtor=%s, vivino_nome=%s, match_score=%s, status='matched'
                    WHERE id=%s
                """, (cand[0], cand[1], cand[2], round(cand[3], 3), row_id))
                with worker_lock:
                    state["match_vivino"] += 1
                    state["wine_new"] -= 1
            else:
                cur.execute("UPDATE y2_results SET status='new' WHERE id=%s", (row_id,))

        conn.commit()

    conn.close()


# === DASHBOARD ===

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>WineGod Pipeline Y2</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#0D0D1A; color:#E0E0E0; font-family:'Segoe UI',sans-serif; padding:20px; }
  h1 { color:#8B1A4A; margin-bottom:5px; font-size:28px; }
  .subtitle { color:#666; margin-bottom:20px; font-size:14px; }
  .status-bar { display:flex; align-items:center; gap:15px; margin-bottom:25px; }
  .status-badge { padding:6px 16px; border-radius:20px; font-weight:bold; font-size:14px; }
  .status-running { background:#1B5E20; color:#A5D6A7; }
  .status-stopped { background:#4A1A1A; color:#EF9A9A; }
  .status-completed { background:#1A237E; color:#90CAF9; }
  .status-paused { background:#E65100; color:#FFCC80; }
  .btn { padding:8px 24px; border:none; border-radius:8px; font-size:14px; cursor:pointer; font-weight:bold; }
  .btn-start { background:#2E7D32; color:white; }
  .btn-start:hover { background:#388E3C; }
  .btn-stop { background:#C62828; color:white; }
  .btn-stop:hover { background:#D32F2F; }

  .progress-container { background:#1A1A2E; border-radius:12px; padding:20px; margin-bottom:25px; border:1px solid #2A2A4E; }
  .progress-bar-bg { background:#2A2A4E; border-radius:8px; height:40px; overflow:hidden; position:relative; }
  .progress-bar-fill { height:100%; border-radius:8px; transition:width 0.5s; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:16px; }
  .progress-bar-fill.low { background:linear-gradient(90deg,#C62828,#E53935); }
  .progress-bar-fill.mid { background:linear-gradient(90deg,#E65100,#FF9800); }
  .progress-bar-fill.high { background:linear-gradient(90deg,#2E7D32,#66BB6A); }
  .progress-stats { display:flex; justify-content:space-between; margin-top:10px; font-size:13px; color:#888; }

  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:15px; margin-bottom:25px; }
  .card { background:#1A1A2E; border:1px solid #2A2A4E; border-radius:12px; padding:18px; text-align:center; }
  .card-value { font-size:32px; font-weight:bold; margin:8px 0; }
  .card-label { font-size:12px; color:#888; text-transform:uppercase; letter-spacing:1px; }
  .card-pct { font-size:14px; color:#666; }
  .card.wine .card-value { color:#8B1A4A; }
  .card.match .card-value { color:#2E7D32; }
  .card.new .card-value { color:#1565C0; }
  .card.dup .card-value { color:#FF8F00; }
  .card.notwine .card-value { color:#616161; }
  .card.spirit .card-value { color:#4E342E; }
  .card.error .card-value { color:#C62828; }
  .card.speed .card-value { color:#00ACC1; }

  .section-title { color:#8B1A4A; font-size:18px; margin:20px 0 10px; }
  .eta { color:#00ACC1; font-size:14px; }
</style>
</head>
<body>

<h1>WineGod Pipeline Y2</h1>
<p class="subtitle">Fase 1: LLM (100 workers) + Fase 2: Match Vivino (background) | Gemini 2.5 Flash</p>

<div class="status-bar">
  <span id="badge" class="status-badge status-stopped">PARADO</span>
  <button id="btnStart" class="btn btn-start" onclick="startPipeline()">START</button>
  <button id="btnStop" class="btn btn-stop" onclick="stopPipeline()">STOP</button>
  <span class="eta" id="eta"></span>
</div>

<div class="progress-container">
  <div class="progress-bar-bg">
    <div id="progressBar" class="progress-bar-fill low" style="width:0%">0%</div>
  </div>
  <div class="progress-stats">
    <span id="progressProcessed">0 / 0 itens</span>
    <span id="progressBatches">0 / 0 batches</span>
    <span id="progressSpeed">0 itens/seg</span>
  </div>
</div>

<div class="section-title" style="margin-top:10px;">Wine Classifier (3 Browsers — Mistral + Chrome + Edge)</div>
<div class="progress-container" style="border-color:#8B1A4A;">
  <div class="progress-bar-bg">
    <div id="progressBar2" class="progress-bar-fill low" style="width:0%">0%</div>
  </div>
  <div class="progress-stats">
    <span id="prog2Processed">0 / 0 itens</span>
    <span id="prog2Lotes">0 lotes</span>
    <span id="prog2Speed">0 itens/seg</span>
  </div>
  <div style="display:flex;gap:12px;margin-top:10px;flex-wrap:wrap;" id="iaBreakdown"></div>
</div>

<div class="section-title">Resultado</div>
<div class="cards">
  <div class="card wine"><div class="card-label">Vinhos (W)</div><div class="card-value" id="cWines">0</div><div class="card-pct" id="cWinesPct"></div></div>
  <div class="card match"><div class="card-label">Match Vivino (Fase 2)</div><div class="card-value" id="cMatch">0</div><div class="card-pct" id="cMatchPct"></div></div>
  <div class="card new"><div class="card-label">Pendente Match</div><div class="card-value" id="cNew">0</div><div class="card-pct" id="cNewPct"></div></div>
  <div class="card dup"><div class="card-label">Duplicatas</div><div class="card-value" id="cDup">0</div><div class="card-pct" id="cDupPct"></div></div>
  <div class="card notwine"><div class="card-label">Nao-Vinho (X)</div><div class="card-value" id="cNotWine">0</div><div class="card-pct" id="cNotWinePct"></div></div>
  <div class="card spirit"><div class="card-label">Destilados (S)</div><div class="card-value" id="cSpirits">0</div><div class="card-pct" id="cSpiritsPct"></div></div>
  <div class="card error"><div class="card-label">Erros</div><div class="card-value" id="cErrors">0</div><div class="card-pct" id="cErrorsPct"></div></div>
  <div class="card speed"><div class="card-label">Velocidade</div><div class="card-value" id="cSpeed">0</div><div class="card-pct">itens/seg</div></div>
</div>

<div class="section-title">Verificacao (amostra de 300)</div>
<div class="cards">
  <div class="card match"><div class="card-label">Match Correto</div><div class="card-value">172</div><div class="card-pct">97%</div></div>
  <div class="card error"><div class="card-label">Match Errado</div><div class="card-value">2</div><div class="card-pct">1%</div></div>
  <div class="card new"><div class="card-label">Vinhos Novos</div><div class="card-value">3</div><div class="card-pct">2%</div></div>
  <div class="card notwine"><div class="card-label">LLM Errou Classif</div><div class="card-value">0</div><div class="card-pct">0%</div></div>
</div>

<script>
function fmt(n) { return n.toLocaleString('pt-BR'); }
function pct(n, total) { return total > 0 ? Math.round(n*100/total)+'%' : ''; }

function updateDashboard() {
  fetch('/api/status').then(r=>r.json()).then(d => {
    // Status badge
    const badge = document.getElementById('badge');
    badge.className = 'status-badge status-' + d.status;
    badge.textContent = {running:'RODANDO',stopped:'PARADO',completed:'COMPLETO',paused:'PAUSADO'}[d.status] || d.status;

    // Progress bar
    const p = d.total_items > 0 ? Math.round(d.processed*100/d.total_items) : 0;
    const bar = document.getElementById('progressBar');
    bar.style.width = p + '%';
    bar.textContent = p + '%';
    bar.className = 'progress-bar-fill ' + (p < 33 ? 'low' : p < 66 ? 'mid' : 'high');

    document.getElementById('progressProcessed').textContent = fmt(d.processed) + ' / ' + fmt(d.total_items) + ' itens';
    document.getElementById('progressBatches').textContent = fmt(d.batches_done) + ' / ' + fmt(d.batches_total) + ' batches';
    document.getElementById('progressSpeed').textContent = d.items_per_sec + ' itens/seg';
    document.getElementById('eta').textContent = d.eta_minutes > 0 ? 'ETA: ' + d.eta_minutes + ' min' : '';

    // Cards
    const total = d.processed || 1;
    document.getElementById('cWines').textContent = fmt(d.wines);
    document.getElementById('cWinesPct').textContent = pct(d.wines, total);
    document.getElementById('cMatch').textContent = fmt(d.match_vivino);
    document.getElementById('cMatchPct').textContent = pct(d.match_vivino, d.wines || 1);
    document.getElementById('cNew').textContent = fmt(d.wine_new);
    document.getElementById('cNewPct').textContent = pct(d.wine_new, d.wines || 1);
    document.getElementById('cDup').textContent = fmt(d.duplicates);
    document.getElementById('cDupPct').textContent = pct(d.duplicates, d.wines || 1);
    document.getElementById('cNotWine').textContent = fmt(d.not_wine);
    document.getElementById('cNotWinePct').textContent = pct(d.not_wine, total);
    document.getElementById('cSpirits').textContent = fmt(d.spirits);
    document.getElementById('cSpiritsPct').textContent = pct(d.spirits, total);
    document.getElementById('cErrors').textContent = fmt(d.errors + d.match_errado);
    document.getElementById('cErrorsPct').textContent = pct(d.errors + d.match_errado, total);
    document.getElementById('cSpeed').textContent = d.items_per_sec;
  });
}

function updateBrowserBar() {
  fetch('/api/browser_status').then(r=>r.json()).then(d => {
    if (d.error) return;
    const total = d.restante_total || 1;
    const done = d.browser_total || 0;
    const p = Math.round(done*100/total);
    const bar2 = document.getElementById('progressBar2');
    bar2.style.width = Math.max(p, 1) + '%';
    bar2.textContent = p + '%';
    bar2.className = 'progress-bar-fill ' + (p < 33 ? 'low' : p < 66 ? 'mid' : 'high');

    document.getElementById('prog2Processed').textContent = fmt(done) + ' / ' + fmt(total) + ' itens';
    document.getElementById('prog2Lotes').textContent = fmt(d.total_lotes) + ' lotes';
    document.getElementById('prog2Speed').textContent = d.speed + ' itens/seg' + (d.eta_minutes > 0 ? ' (ETA: ' + fmt(d.eta_minutes) + ' min)' : '');

    // Breakdown por IA
    const container = document.getElementById('iaBreakdown');
    const colors = {mistral:'#8B1A4A',gemini:'#4285F4',grok:'#FF6B00',qwen:'#7C3AED',chatgpt:'#10A37F',glm:'#E53935'};
    let html = '';
    for (const [ia, stats] of Object.entries(d.ias || {})) {
      const color = colors[ia] || '#666';
      html += '<div style="background:#1A1A2E;border:1px solid '+color+';border-radius:8px;padding:8px 12px;font-size:12px;">' +
        '<span style="color:'+color+';font-weight:bold;text-transform:uppercase;">'+ia+'</span> ' +
        '<span style="color:#E0E0E0;">'+fmt(stats.total)+'</span> ' +
        '<span style="color:#888;">(W='+fmt(stats.W)+' X='+fmt(stats.X)+' S='+fmt(stats.S)+')</span></div>';
    }
    container.innerHTML = html;
  });
}

function startPipeline() { fetch('/api/start', {method:'POST'}).then(()=>updateDashboard()); }
function stopPipeline() { fetch('/api/stop', {method:'POST'}).then(()=>updateDashboard()); }

setInterval(updateDashboard, 2000);
setInterval(updateBrowserBar, 3000);
updateDashboard();
updateBrowserBar();
</script>
</body>
</html>
"""

@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/status")
def api_status():
    # Se pipeline esta rodando, usa state interno (tempo real do worker)
    if state["status"] == "running":
        return jsonify(state)

    # Se parado, ler do banco (pega dados do wine_classifier tambem)
    try:
        stats = count_stats()
        match_vivino = stats.get("matched", 0)
        wine_new = stats.get("new", 0) + stats.get("pending_match", 0)
        not_wine = stats.get("not_wine", 0)
        spirits = stats.get("spirit", 0)
        duplicates = stats.get("duplicate", 0)
        errors = stats.get("error", 0)
        wines = match_vivino + wine_new + duplicates
        processed = wines + not_wine + spirits + errors

        # Ler lotes_log pra velocidade
        lotes_info = {"items_per_sec": 0, "batches_done": 0, "last_batch_time": 0}
        try:
            conn_l = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                                      user=DB_USER, password=DB_PASS,
                                      options="-c client_encoding=UTF8")
            cur_l = conn_l.cursor()
            cur_l.execute("SELECT COUNT(*), SUM(recebidos) FROM y2_lotes_log")
            row = cur_l.fetchone()
            lotes_info["batches_done"] = row[0] or 0
            # Velocidade dos ultimos 5 min
            cur_l.execute("""
                SELECT SUM(recebidos), EXTRACT(EPOCH FROM MAX(processado_em) - MIN(processado_em))
                FROM y2_lotes_log
                WHERE processado_em > NOW() - INTERVAL '5 minutes' AND recebidos > 0
            """)
            row2 = cur_l.fetchone()
            if row2[0] and row2[1] and row2[1] > 0:
                lotes_info["items_per_sec"] = round(row2[0] / row2[1], 1)
            conn_l.close()
        except Exception:
            pass

        _, total = get_progress()
        eta = 0
        if lotes_info["items_per_sec"] > 0:
            remaining = total - processed
            eta = round(remaining / lotes_info["items_per_sec"] / 60)

        return jsonify({
            "status": "running" if lotes_info["items_per_sec"] > 0 else state["status"],
            "started_at": state["started_at"],
            "total_items": total or 3962334,
            "processed": processed,
            "wines": wines,
            "not_wine": not_wine,
            "spirits": spirits,
            "duplicates": duplicates,
            "unique_wines": 0,
            "match_vivino": match_vivino,
            "match_errado": 0,
            "wine_new": wine_new,
            "errors": errors,
            "batches_total": 0,
            "batches_done": lotes_info["batches_done"],
            "items_per_sec": lotes_info["items_per_sec"],
            "eta_minutes": eta,
            "last_batch_time": lotes_info["last_batch_time"],
        })
    except Exception:
        return jsonify(state)

@app.route("/api/browser_status")
def api_browser_status():
    """Stats do wine_classifier (3 browsers). Exclui Gemini API antigo."""
    try:
        conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                                user=DB_USER, password=DB_PASS,
                                options="-c client_encoding=UTF8")
        cur = conn.cursor()

        # Total que o wine_classifier precisa fazer (tudo menos Gemini API)
        cur.execute("SELECT COUNT(*) FROM y2_results WHERE fonte_llm = 'gemini' AND uva IS NULL")
        gemini_api = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM wines_clean")
        total_wc = cur.fetchone()[0]
        restante_total = total_wc - gemini_api  # o que o wine_classifier precisa cobrir

        # Total feito pelo wine_classifier
        cur.execute("""
            SELECT fonte_llm, COUNT(*) as total,
                   SUM(CASE WHEN classificacao='W' THEN 1 ELSE 0 END) as W,
                   SUM(CASE WHEN classificacao='X' THEN 1 ELSE 0 END) as X,
                   SUM(CASE WHEN classificacao='S' THEN 1 ELSE 0 END) as S
            FROM y2_results
            WHERE NOT (fonte_llm = 'gemini' AND uva IS NULL)
            GROUP BY fonte_llm ORDER BY total DESC
        """)
        ias = {}
        browser_total = 0
        for r in cur.fetchall():
            ias[r[0]] = {"total": r[1], "W": r[2], "X": r[3], "S": r[4]}
            browser_total += r[1]

        # Lotes e velocidade do wine_classifier (ultimos 5 min)
        cur.execute("SELECT COUNT(*), SUM(recebidos) FROM y2_lotes_log")
        log_row = cur.fetchone()
        total_lotes = log_row[0] or 0

        speed = 0
        cur.execute("""
            SELECT SUM(recebidos), EXTRACT(EPOCH FROM MAX(processado_em) - MIN(processado_em))
            FROM y2_lotes_log
            WHERE processado_em > NOW() - INTERVAL '5 minutes' AND recebidos > 0
        """)
        speed_row = cur.fetchone()
        if speed_row[0] and speed_row[1] and speed_row[1] > 0:
            speed = round(speed_row[0] / speed_row[1], 1)

        conn.close()

        eta = 0
        pendente = restante_total - browser_total
        if speed > 0 and pendente > 0:
            eta = round(pendente / speed / 60)

        return jsonify({
            "restante_total": restante_total,
            "browser_total": browser_total,
            "pendente": pendente,
            "total_lotes": total_lotes,
            "speed": speed,
            "eta_minutes": eta,
            "ias": ias,
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/start", methods=["POST"])
def api_start():
    if state["status"] == "running":
        return jsonify({"error": "ja rodando"})
    stop_event.clear()
    t = threading.Thread(target=run_pipeline, daemon=True)
    t.start()
    # Fase 2: match Vivino em background (1 conexao, sem afetar velocidade)
    t2 = threading.Thread(target=run_vivino_match, daemon=True)
    t2.start()
    return jsonify({"ok": True})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    stop_event.set()
    state["status"] = "stopped"
    return jsonify({"ok": True})


if __name__ == "__main__":
    setup_db()
    # Carregar stats existentes
    offset, total = get_progress()
    if offset > 0:
        state["total_items"] = total
        stats = count_stats()
        state["match_vivino"] = stats.get("matched", 0)
        state["wine_new"] = stats.get("new", 0) + stats.get("pending_match", 0)
        state["not_wine"] = stats.get("not_wine", 0)
        state["spirits"] = stats.get("spirit", 0)
        state["duplicates"] = stats.get("duplicate", 0)
        state["errors"] = stats.get("error", 0)
        state["match_errado"] = 0
        state["wines"] = state["match_vivino"] + state["wine_new"] + state["duplicates"]
        state["processed"] = state["wines"] + state["not_wine"] + state["spirits"] + state["errors"]
        print(f"Retomando: {state['processed']}/{total} processados")
        print(f"  W={state['wines']} (match={state['match_vivino']} pending={state['wine_new']} dup={state['duplicates']})")
        print(f"  X={state['not_wine']} S={state['spirits']} err={state['errors']}")

    print(f"\n  Dashboard: http://localhost:{PORT}")
    print(f"  Workers: {WORKERS}")
    print(f"  Batch: {BATCH_SIZE}")
    print(f"  Modelo: {MODEL}\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
