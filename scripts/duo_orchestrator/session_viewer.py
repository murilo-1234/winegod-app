"""
Session Viewer - Duo Orchestrator V1.x

Gera um arquivo session.html dentro da pasta da sessao, exibindo a timeline
de perguntas e respostas entre Codex (admin) e Claude (executor) em estilo
chat, parecido com claude.ai.

Uso:
    python session_viewer.py              # lista sessoes disponiveis
    python session_viewer.py S-0015       # gera e abre a sessao S-0015
    python session_viewer.py S-0015 --no-open   # so gera, nao abre

Zero dependencia externa. Renderiza markdown no browser via CDN marked.js.

O viewer e read-only: apenas le os arquivos da sessao. Nao altera nada.
"""
import os
import sys
import re
import html
import json
import webbrowser
from datetime import datetime

SESSIONS_DIR = r"C:\winegod-app\orchestrator_sessions"


def list_sessions():
    if not os.path.isdir(SESSIONS_DIR):
        print(f"Pasta nao encontrada: {SESSIONS_DIR}")
        return []
    items = []
    for name in sorted(os.listdir(SESSIONS_DIR)):
        full = os.path.join(SESSIONS_DIR, name)
        if os.path.isdir(full) and name.startswith("S-"):
            items.append(name)
    return items


def find_session_dir(session_id):
    """Aceita 'S-0015' ou nome completo 'S-0015-BuscaSafeRecall'."""
    if os.path.isdir(os.path.join(SESSIONS_DIR, session_id)):
        return os.path.join(SESSIONS_DIR, session_id)
    for name in os.listdir(SESSIONS_DIR):
        if name.startswith(session_id):
            full = os.path.join(SESSIONS_DIR, name)
            if os.path.isdir(full):
                return full
    return None


def read_text(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"(erro ao ler: {e})"


def file_mtime(path):
    try:
        ts = os.path.getmtime(path)
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _has_marker(text, marker):
    """Usa o mesmo criterio robusto do orquestrador para evitar falso positivo.

    Nao considera marker embutido em frase comum, por exemplo:
    - "Nao chame parcial de concluido"
    - "escreva HUMANO se precisar"
    """
    if not text:
        return False
    up = text.upper()
    patterns = [
        rf"^\s*[*_`\"']*{marker}[*_`\"'.!]*\s*$",
        rf"^\s*STATUS:\s*{marker}\b",
        rf"^\s*FINAL:\s*{marker}\b",
        rf"^\s*DECISAO:\s*{marker}\b",
        rf"^\s*RESPOSTA:\s*{marker}\b",
        rf"^\s*\**\s*{marker}\s*\**\s*(?:-|:|\.|\u2014)",
    ]
    for line in up.splitlines():
        for pat in patterns:
            if re.match(pat, line):
                return True
    return False


def extract_status(text):
    """Extrai status visual sem falso positivo por substring solta."""
    if not text:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("STATUS:"):
            return stripped.replace("STATUS:", "").strip().upper()
    if _has_marker(text, "CONCLUIDO"):
        return "CONCLUIDO"
    if _has_marker(text, "HUMANO"):
        return "HUMANO"
    return None


def collect_messages(session_dir):
    """Retorna lista ordenada de mensagens. Cada item:
    {
      'role': 'project' | 'codex' | 'claude' | 'final',
      'title': str,
      'status': str or None,
      'body': str (markdown),
      'time': str,
      'file': str
    }
    """
    msgs = []

    # 1) Projeto refinado
    proj = os.path.join(session_dir, "project.md")
    if os.path.isfile(proj):
        msgs.append({
            "role": "project",
            "title": "Projeto refinado (brief)",
            "status": None,
            "body": read_text(proj) or "",
            "time": file_mtime(proj),
            "file": "project.md",
        })

    # 2) Entendimento - V1.1 guarda por tentativa
    files = os.listdir(session_dir)

    # Tentativas numeradas de entendimento
    attempts = []
    for f in files:
        m = re.match(r"round-000-(claude-understanding|codex-review)-attempt-(\d+)\.md$", f)
        if m:
            attempts.append((int(m.group(2)), m.group(1), f))
    attempts.sort(key=lambda x: (x[0], 0 if x[1] == "claude-understanding" else 1))
    for attempt_num, kind, fname in attempts:
        path = os.path.join(session_dir, fname)
        body = read_text(path) or ""
        if kind == "claude-understanding":
            msgs.append({
                "role": "claude",
                "title": f"Claude - Entendimento (tentativa {attempt_num})",
                "status": extract_status(body),
                "body": body,
                "time": file_mtime(path),
                "file": fname,
            })
        else:
            msgs.append({
                "role": "codex",
                "title": f"Codex - Julgamento do entendimento (tentativa {attempt_num})",
                "status": extract_status(body),
                "body": body,
                "time": file_mtime(path),
                "file": fname,
            })

    # Se nao ha arquivos attempt-*, cai no esquema antigo (sobrescrito)
    if not attempts:
        und = os.path.join(session_dir, "round-000-claude-understanding.md")
        rev = os.path.join(session_dir, "round-000-codex-review.md")
        if os.path.isfile(und):
            body = read_text(und) or ""
            msgs.append({
                "role": "claude",
                "title": "Claude - Entendimento",
                "status": extract_status(body),
                "body": body,
                "time": file_mtime(und),
                "file": "round-000-claude-understanding.md",
            })
        if os.path.isfile(rev):
            body = read_text(rev) or ""
            msgs.append({
                "role": "codex",
                "title": "Codex - Julgamento do entendimento",
                "status": extract_status(body),
                "body": body,
                "time": file_mtime(rev),
                "file": "round-000-codex-review.md",
            })

    # 3a) Bootstrap V2 (dumb-pipe)
    for special_name, role, title in [
        ("round-000-claude-bootstrap.md", "claude", "Claude - Bootstrap (leu o brief)"),
        ("round-000-claude-activation.md", "claude", "Claude - Ativado como executor"),
        ("round-000-codex-bootstrap.md", "codex", "Codex - Bootstrap (leu o brief)"),
        ("round-000-codex-activation.md", "codex", "Codex - Ativado como admin (1o prompt)"),
    ]:
        p = os.path.join(session_dir, special_name)
        if os.path.isfile(p):
            body = read_text(p) or ""
            msgs.append({
                "role": role,
                "title": title,
                "status": extract_status(body),
                "body": body,
                "time": file_mtime(p),
                "file": special_name,
            })

    # 3b) Rounds do loop principal — suporta V1 (admin/exec/review) e V2 (codex/claude)
    v1_rounds = set()
    v2_rounds = set()
    for f in files:
        m1 = re.match(r"round-(\d{3})-(admin|exec|review)\.md$", f)
        m2 = re.match(r"round-(\d{3})-(codex|claude)\.md$", f)
        if m1 and m1.group(1) != "000":
            v1_rounds.add(int(m1.group(1)))
        if m2 and m2.group(1) != "000":
            v2_rounds.add(int(m2.group(1)))

    # V2 first (new format): codex then claude per round
    for num in sorted(v2_rounds):
        padded = f"{num:03d}"
        codex_f = os.path.join(session_dir, f"round-{padded}-codex.md")
        claude_f = os.path.join(session_dir, f"round-{padded}-claude.md")
        if os.path.isfile(codex_f):
            body = read_text(codex_f) or ""
            msgs.append({
                "role": "codex",
                "title": f"Codex - Round {padded}",
                "status": extract_status(body),
                "body": body,
                "time": file_mtime(codex_f),
                "file": f"round-{padded}-codex.md",
            })
        if os.path.isfile(claude_f):
            body = read_text(claude_f) or ""
            msgs.append({
                "role": "claude",
                "title": f"Claude - Round {padded}",
                "status": extract_status(body),
                "body": body,
                "time": file_mtime(claude_f),
                "file": f"round-{padded}-claude.md",
            })

    # V1 (legacy): admin → exec → review
    for num in sorted(v1_rounds):
        padded = f"{num:03d}"
        admin = os.path.join(session_dir, f"round-{padded}-admin.md")
        execf = os.path.join(session_dir, f"round-{padded}-exec.md")
        revf = os.path.join(session_dir, f"round-{padded}-review.md")
        if os.path.isfile(admin):
            body = read_text(admin) or ""
            msgs.append({
                "role": "codex",
                "title": f"Codex - Tarefa do round {padded}",
                "status": None,
                "body": body,
                "time": file_mtime(admin),
                "file": f"round-{padded}-admin.md",
            })
        if os.path.isfile(execf):
            body = read_text(execf) or ""
            msgs.append({
                "role": "claude",
                "title": f"Claude - Execucao do round {padded}",
                "status": extract_status(body),
                "body": body,
                "time": file_mtime(execf),
                "file": f"round-{padded}-exec.md",
            })
        if os.path.isfile(revf):
            body = read_text(revf) or ""
            msgs.append({
                "role": "codex",
                "title": f"Codex - Julgamento do round {padded}",
                "status": extract_status(body),
                "body": body,
                "time": file_mtime(revf),
                "file": f"round-{padded}-review.md",
            })

    # 4) Final review
    final = os.path.join(session_dir, "final-review.md")
    if os.path.isfile(final):
        body = read_text(final) or ""
        msgs.append({
            "role": "final",
            "title": "Final review",
            "status": None,
            "body": body,
            "time": file_mtime(final),
            "file": "final-review.md",
        })

    return msgs


def read_session_log_tail(session_dir, max_lines=30):
    path = os.path.join(session_dir, "session.log")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:])
    except Exception:
        return ""


def session_header_info(session_dir):
    log = os.path.join(session_dir, "session.log")
    info = {
        "session_name": os.path.basename(session_dir),
        "run_label": "",
        "mission": "",
        "started_at": "",
    }
    if os.path.isfile(log):
        try:
            with open(log, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "run_label:" in line:
                        info["run_label"] = line.split("run_label:", 1)[1].strip()
                    elif "mission:" in line:
                        info["mission"] = line.split("mission:", 1)[1].strip()
                    elif "Sessao iniciada:" in line and not info["started_at"]:
                        m = re.match(r"\[(.*?)\]", line)
                        if m:
                            info["started_at"] = m.group(1)
                    if all(info.values()):
                        break
        except Exception:
            pass
    return info


STATUS_CLASS = {
    "APROVADO": "ok",
    "CONCLUIDO": "ok",
    "EXECUTED": "ok",
    "REPROVADO": "bad",
    "BLOCKED": "warn",
    "NEEDS_HUMAN": "warn",
    "REVISAO_HUMANA": "warn",
    "READY": "ok",
}


def render_html(session_dir, msgs, info, log_tail):
    messages_json = json.dumps(msgs, ensure_ascii=False)

    page = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root {
  --bg: #0f1115;
  --panel: #161a22;
  --panel2: #1b2030;
  --text: #e6e9ef;
  --muted: #8b93a7;
  --border: #262c3a;
  --codex: #8b5cf6;
  --codex-bg: #241b38;
  --claude: #f59e0b;
  --claude-bg: #2d2310;
  --ok: #22c55e;
  --bad: #ef4444;
  --warn: #eab308;
  --project: #3b82f6;
  --project-bg: #162036;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0;
  background: var(--bg); color: var(--text);
  font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  font-size: 14px; line-height: 1.5;
}
header {
  position: sticky; top: 0; z-index: 10;
  background: var(--panel); border-bottom: 1px solid var(--border);
  padding: 14px 24px; display: flex; align-items: center; justify-content: space-between;
}
header h1 { margin: 0; font-size: 16px; font-weight: 600; }
header .meta { color: var(--muted); font-size: 12px; margin-top: 2px; }
header .refresh { color: var(--muted); font-size: 11px; }
.container { max-width: 1100px; margin: 0 auto; padding: 24px; }
.msg { margin-bottom: 20px; display: flex; gap: 12px; }
.msg.left  { justify-content: flex-start; }
.msg.right { justify-content: flex-end; }
.bubble {
  max-width: 78%; border-radius: 12px; padding: 14px 16px;
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: 0 1px 2px rgba(0,0,0,0.2);
}
.bubble.codex   { background: var(--codex-bg);   border-color: var(--codex); }
.bubble.claude  { background: var(--claude-bg);  border-color: var(--claude); }
.bubble.project { background: var(--project-bg); border-color: var(--project); max-width: 100%; }
.bubble.final   { background: #1b2030; border-color: var(--muted); max-width: 100%; }
.head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
  font-size: 12px; color: var(--muted);
}
.who { font-weight: 700; }
.who.codex   { color: var(--codex); }
.who.claude  { color: var(--claude); }
.who.project { color: var(--project); }
.who.final   { color: var(--muted); }
.status {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.4px;
}
.status.ok   { background: rgba(34,197,94,0.15);  color: var(--ok);   border: 1px solid var(--ok); }
.status.bad  { background: rgba(239,68,68,0.15);  color: var(--bad);  border: 1px solid var(--bad); }
.status.warn { background: rgba(234,179,8,0.15);  color: var(--warn); border: 1px solid var(--warn); }
.time { margin-left: auto; font-variant-numeric: tabular-nums; }
.filepath { color: var(--muted); font-family: Consolas, monospace; font-size: 11px; }
.body { color: var(--text); overflow-wrap: anywhere; }
.body h1,.body h2,.body h3,.body h4 { margin: 12px 0 6px; }
.body h1 { font-size: 18px; } .body h2 { font-size: 16px; } .body h3 { font-size: 14px; }
.body p { margin: 6px 0; }
.body ul,.body ol { margin: 6px 0; padding-left: 22px; }
.body code { background: #0b0d12; padding: 1px 5px; border-radius: 3px; font-size: 12px; }
.body pre  { background: #0b0d12; padding: 10px; border-radius: 6px; overflow-x: auto; }
.body pre code { background: transparent; padding: 0; }
.body blockquote { border-left: 3px solid var(--border); padding-left: 10px; color: var(--muted); }
.footer { margin-top: 40px; padding: 16px; border-top: 1px solid var(--border); color: var(--muted); font-size: 12px; }
details.log { background: var(--panel2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; margin-top: 10px; }
details.log pre { white-space: pre-wrap; font-size: 11px; color: var(--muted); margin: 8px 0 0; }
.toggle { cursor: pointer; color: var(--muted); font-size: 12px; user-select: none; }
.collapsed .body { display: none; }
</style>
</head>
<body>
<header>
  <div>
    <h1>__TITLE__</h1>
    <div class="meta">__META__</div>
  </div>
  <div class="refresh">auto-refresh 5s</div>
</header>
<div class="container" id="chat"></div>
<div class="container">
  <details class="log">
    <summary class="toggle">Tail do session.log</summary>
    <pre>__LOG_TAIL__</pre>
  </details>
  <div class="footer">
    Pasta: <span class="filepath">__SESSION_DIR__</span><br>
    Gerado em __GENERATED_AT__ - viewer read-only, nao altera nada.
  </div>
</div>
<script>
const MSGS = __MESSAGES_JSON__;

const STATUS_CLASS = {
  "APROVADO": "ok", "CONCLUIDO": "ok", "EXECUTED": "ok", "READY": "ok",
  "REPROVADO": "bad",
  "BLOCKED": "warn", "NEEDS_HUMAN": "warn", "REVISAO_HUMANA": "warn"
};

function esc(s){
  return String(s).replace(/[&<>\"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]));
}

function roleMeta(role){
  if (role === "codex")   return {side: "left",  label: "CODEX (admin)"};
  if (role === "claude")  return {side: "right", label: "CLAUDE (executor)"};
  if (role === "project") return {side: "left",  label: "PROJETO"};
  if (role === "final")   return {side: "left",  label: "FINAL"};
  return {side: "left", label: role};
}

const chat = document.getElementById("chat");
marked.setOptions({breaks: true, gfm: true});

for (const m of MSGS){
  const meta = roleMeta(m.role);
  const wrap = document.createElement("div");
  wrap.className = "msg " + meta.side;

  const bub = document.createElement("div");
  bub.className = "bubble " + m.role;

  const head = document.createElement("div");
  head.className = "head";
  head.innerHTML =
    '<span class="who ' + m.role + '">' + esc(meta.label) + '</span>' +
    '<span>&middot;</span>' +
    '<span>' + esc(m.title) + '</span>' +
    (m.status ? ' <span class="status ' + (STATUS_CLASS[m.status] || "warn") + '">' + esc(m.status) + '</span>' : '') +
    '<span class="time">' + esc(m.time) + '</span>';

  const filep = document.createElement("div");
  filep.className = "filepath";
  filep.textContent = m.file;

  const body = document.createElement("div");
  body.className = "body";
  body.innerHTML = marked.parse(m.body || "");

  bub.appendChild(head);
  bub.appendChild(filep);
  bub.appendChild(body);
  wrap.appendChild(bub);
  chat.appendChild(wrap);
}

// preservar scroll entre auto-refreshes
const KEY = "viewer_scroll_" + location.pathname;
window.addEventListener("beforeunload", () => sessionStorage.setItem(KEY, String(window.scrollY)));
window.addEventListener("load", () => {
  const y = sessionStorage.getItem(KEY);
  if (y) window.scrollTo(0, parseInt(y, 10) || 0);
});
</script>
</body>
</html>
"""

    title = f"Duo Orchestrator - {info['session_name']}"
    meta_line = " | ".join(x for x in [
        f"Label: {info['run_label']}" if info["run_label"] else "",
        f"Iniciada: {info['started_at']}" if info["started_at"] else "",
        info["mission"],
    ] if x)

    page = page.replace("__TITLE__", html.escape(title))
    page = page.replace("__META__", html.escape(meta_line))
    page = page.replace("__LOG_TAIL__", html.escape(log_tail))
    page = page.replace("__SESSION_DIR__", html.escape(session_dir))
    page = page.replace("__GENERATED_AT__", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    page = page.replace("__MESSAGES_JSON__", messages_json)
    return page


# === V2.3: Dashboard de checkpoints ===

STATE_COLORS = {
    "BOOTSTRAP":           ("#6b7280", "Bootstrap"),
    "RUNNING":             ("#22c55e", "Rodando"),
    "RETRY_BACKOFF":       ("#eab308", "Retry (aguardando backoff)"),
    "PAUSED_RECOVERABLE":  ("#f97316", "Pausado (erro desconhecido)"),
    "WAITING_HUMAN":       ("#3b82f6", "Aguardando humano"),
    "READY_FOR_HUMAN_CLOSE": ("#8b5cf6", "Pronto para fechar"),
    "CLOSED_BY_HUMAN":     ("#94a3b8", "Fechada"),
}


def _read_last(session_dir, filename, n_chars=600):
    """Le os primeiros n_chars de um arquivo, ou string vazia se nao existir."""
    path = os.path.join(session_dir, filename)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(n_chars).strip()
    except Exception:
        return ""


def _last_round_files(session_dir):
    """Encontra os ultimos round-NNN-codex.md e round-NNN-claude.md (maior NNN)."""
    try:
        files = os.listdir(session_dir)
    except Exception:
        return None, None
    rx = re.compile(r"^round-(\d{3})-(codex|claude)\.md$")
    by_role = {"codex": (-1, None), "claude": (-1, None)}
    for f in files:
        m = rx.match(f)
        if not m:
            continue
        n = int(m.group(1))
        role = m.group(2)
        if n > by_role[role][0]:
            by_role[role] = (n, f)
    return by_role["codex"][1], by_role["claude"][1]


def _stage_label(current_round, last_codex_file, last_claude_file):
    """Descreve em texto onde o sistema esta na cronologia do projeto."""
    if current_round == 0:
        # ainda na ativacao
        if last_codex_file and "activation" in last_codex_file:
            return "Bootstrap concluido. Codex ja enviou o primeiro prompt para Claude (round-000-codex-activation.md)."
        return "Bootstrap em andamento (lendo brief, ativando agentes)."
    return f"Round {current_round}."


def _collapse_ws(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _first_meaningful_line(text):
    if not text:
        return ""
    skip_prefixes = (
        "envie isto ao claude",
        "use este prompt com o claude",
        "use este prompt para o claude",
        "```",
        "---",
    )
    for raw in text.splitlines():
        line = raw.strip().strip("> ").strip()
        if not line:
            continue
        lowered = line.lower()
        if any(lowered.startswith(prefix) for prefix in skip_prefixes):
            continue
        if line.startswith("#"):
            continue
        return _collapse_ws(line)
    return _collapse_ws(text[:200])


def _extract_phase(text):
    text = text or ""
    preferred_patterns = [
        r"^\s*Fase\s+(\d+)\b(?:\s+[—-]|\s+—|\s+ainda|\s+segue|\s+aprovada|\s+reprovada|\s+em|\s+APROVADA|\s+REPROVADA)",
        r"^##\s*Fase\s*$.*?^\s*Fase\s+(\d+)\b",
        r"Avance .*?\bFase\s+(\d+)\b",
        r"Objetivo da Fase\s+(\d+)\b",
        r"Execute AGORA somente a Fase\s+(\d+)\b",
        r"iniciar Fase\s+(\d+)\b",
    ]
    for pat in preferred_patterns:
        flags = re.IGNORECASE | re.DOTALL
        if pat.startswith("^"):
            flags |= re.MULTILINE
        m = re.search(pat, text, flags)
        if m:
            return f"Fase {m.group(1)}"
    m = re.search(r"\bFase\s+(\d+)\b", text, re.IGNORECASE)
    return f"Fase {m.group(1)}" if m else ""


def _extract_backticked_files(text, limit=3):
    seen = []
    for candidate in re.findall(r"`([^`]+)`", text or ""):
        if candidate in seen:
            continue
        if ("\\" in candidate or "/" in candidate or
                re.search(r"\.(md|csv|csv\.gz|json|py)$", candidate, re.IGNORECASE)):
            seen.append(candidate)
        if len(seen) >= limit:
            break
    return seen


def _extract_required_deliverables(text, limit=3):
    if not text:
        return []
    m = re.search(
        r"Entregas obrigatorias.*?:\s*(.*?)(?=\n\s*\n|\n[A-Z][^\n]{0,80}:|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return []
    items = []
    for raw in m.group(1).splitlines():
        line = raw.strip()
        if not line.startswith("-"):
            continue
        cleaned = _collapse_ws(line[1:].strip()).strip("`")
        if cleaned and cleaned not in items:
            items.append(cleaned)
        if len(items) >= limit:
            break
    return items


def _extract_checkpoint_section(checkpoint_md, section_name):
    if not checkpoint_md:
        return ""
    pattern = rf"^##\s+{re.escape(section_name)}.*?\n(.*?)(?=^##\s+|\Z)"
    m = re.search(pattern, checkpoint_md, re.IGNORECASE | re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _extract_checkpoint_round_lines(checkpoint_md):
    section = _extract_checkpoint_section(checkpoint_md, "Secao D")
    if not section:
        return []
    lines = []
    for raw in section.splitlines():
        line = raw.strip()
        if line.startswith("- Round "):
            lines.append(_collapse_ws(line[2:]))
    return lines


def _extract_checkpoint_repo_files(checkpoint_md, limit=4):
    section = _extract_checkpoint_section(checkpoint_md, "Secao C")
    if not section:
        return []
    files = []
    for raw in section.splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        item = _collapse_ws(line[2:])
        if item.startswith("*Heuristica"):
            continue
        normalized_item = item.strip("`")
        if normalized_item.startswith(".duo_orchestrator.lock"):
            continue
        files.append(item)
        if len(files) >= limit:
            break
    return files


def _extract_bullet_block(text, header_line, limit=3):
    if not text:
        return []
    m = re.search(
        rf"{re.escape(header_line)}\s*(.*?)(?=\n\s*\n|\n[A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][^\n]*:|\n##\s+|\Z)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return []
    items = []
    for raw in m.group(1).splitlines():
        line = raw.strip()
        if not line.startswith("-"):
            continue
        cleaned = _collapse_ws(line[1:].strip())
        if cleaned and cleaned not in items:
            items.append(cleaned)
        if len(items) >= limit:
            break
    return items


def _extract_table_value(text, row_name):
    if not text:
        return ""
    pat = rf"\|\s*{re.escape(row_name)}\s*\|\s*([^|]+?)\s*\|"
    m = re.search(pat, text, re.IGNORECASE)
    return _collapse_ws(m.group(1)) if m else ""


def _extract_metric_equation(text, metric_name):
    if not text:
        return ""
    pat = rf"\*\*{re.escape(metric_name)}\s*=\s*([^*]+)\*\*"
    m = re.search(pat, text, re.IGNORECASE)
    return _collapse_ws(m.group(1)) if m else ""


def _basenameish(path_text):
    if not path_text:
        return ""
    normalized = path_text.strip().strip("`").rstrip(".")
    normalized = normalized.replace("\\", "/")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def _extract_project_achievement_bits(claude_text):
    if not claude_text:
        return {}
    data = {
        "artifacts": [],
        "coverage": "",
        "metrics": "",
    }

    created = _extract_bullet_block(claude_text, "## Arquivos criados/alterados", limit=3)
    created = [_basenameish(item.split("—", 1)[0].strip()) for item in created]
    created = [_basenameish(item.split("â€”", 1)[0].strip()) for item in created]
    created = [item for item in created if item]
    created = [item.split("—", 1)[0].strip().strip("`") for item in created]
    artifacts = []
    for item in created:
        normalized = _basenameish(item)
        if normalized and normalized not in artifacts:
            artifacts.append(normalized)
    if artifacts:
        data["artifacts"] = artifacts

    per_case = _extract_table_value(claude_text, "Per-case rows")
    summary_rows = _extract_table_value(claude_text, "Summary rows")
    channels = _extract_table_value(claude_text, "Canais cobertos")
    states = _extract_table_value(claude_text, "Estados rodados")
    if per_case or summary_rows or channels or states:
        parts = []
        if per_case:
            parts.append(f"{per_case} resultados por caso")
        if summary_rows:
            parts.append(f"{summary_rows} linhas agregadas")
        if channels:
            parts.append(f"cobrindo {channels} canais")
        if states:
            parts.append(f"com {states} estados medidos")
        data["coverage"] = "A entrega mais recente do projeto trouxe " + ", ".join(parts) + "."

    search_recall = _extract_metric_equation(claude_text, "search_top1_recall")
    pre_resolve = _extract_metric_equation(claude_text, "pre_resolve_safe_recall")
    api_final = _extract_metric_equation(claude_text, "api_final_safe_recall")
    auto_create_bad = _extract_table_value(claude_text, "auto_create_ruim")
    metric_parts = []
    if search_recall:
        metric_parts.append(f"`search_top1_recall` {search_recall}")
    if pre_resolve:
        metric_parts.append(f"`pre_resolve_safe_recall` {pre_resolve}")
    if api_final:
        metric_parts.append(f"`api_final_safe_recall` {api_final}")
    if auto_create_bad:
        metric_parts.append(f"`auto_create_ruim` {auto_create_bad}")
    if metric_parts:
        data["metrics"] = "Em numeros, o que ja apareceu foi: " + ", ".join(metric_parts) + "."

    return data


def _extract_project_gap_bits(codex_text):
    if not codex_text:
        return []
    for header in (
        "Os 3 pontos que precisam ser fechados antes da aprovacao:",
        "Os pontos que precisam ser fechados antes da aprovacao:",
    ):
        m = re.search(
            rf"{re.escape(header)}\s*(.*?)(?=\n\s*\n|\nUse este prompt|\Z)",
            codex_text,
            re.IGNORECASE | re.DOTALL,
        )
        if not m:
            continue
        numbered = []
        for raw in m.group(1).splitlines():
            line = raw.strip()
            match = re.match(r"\d+\.\s*(.+)", line)
            if not match:
                continue
            cleaned = _collapse_ws(match.group(1)).rstrip(":")
            if cleaned:
                numbered.append(cleaned)
            if len(numbered) >= 4:
                break
        if numbered:
            return numbered
    gaps = _extract_bullet_block(codex_text, "Os gaps que impedem aprovacao:", limit=4)
    if not gaps:
        gaps = _extract_bullet_block(codex_text, "Os 3 gaps que precisam ser fechados:", limit=4)
    if not gaps:
        gaps = _extract_bullet_block(
            codex_text,
            "Os 3 pontos que precisam ser fechados antes da aprovacao:",
            limit=4,
        )
    if not gaps:
        gaps = _extract_bullet_block(
            codex_text,
            "Os pontos que precisam ser fechados antes da aprovacao:",
            limit=4,
        )
    return gaps


def _extract_project_decision_text(codex_text):
    if not codex_text:
        return ""
    has_path_a = re.search(r"CAMINHO A", codex_text, re.IGNORECASE)
    has_path_b = re.search(r"CAMINHO B", codex_text, re.IGNORECASE)
    if has_path_a and has_path_b:
        return (
            "A decisao atual do projeto e objetiva: ou o Claude completa a baseline "
            "nos estados aplicaveis, ou para e prova bloqueio externo real."
        )
    if re.search(r"STATUS:\s*BLOCKED", codex_text, re.IGNORECASE):
        return "O Codex so aceita bloqueio agora se vier com prova objetiva e delimitada."
    return ""


def _extract_phase_num(text):
    phase = _extract_phase(text)
    if not phase:
        return None
    m = re.search(r"(\d+)", phase)
    return int(m.group(1)) if m else None


def _extract_project_phase_catalog(project_text):
    if not project_text:
        return []
    matches = list(re.finditer(r"^###\s+Fase\s+(\d+)\s*-\s*(.+?)\s*$",
                               project_text, re.MULTILINE))
    phases = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(project_text)
        section = project_text[start:end]
        phases.append({
            "num": int(match.group(1)),
            "title": _collapse_ws(match.group(2)),
            "preapproved": bool(re.search(
                r"STATUS:\s*JA\s+CONCLUIDA\s+E\s+APROVADA",
                section,
                re.IGNORECASE,
            )),
        })
    return phases


def _collect_round_role_files(session_dir, role):
    if not session_dir:
        return []
    try:
        names = os.listdir(session_dir)
    except Exception:
        return []
    rx = re.compile(rf"^round-(\d{{3}})-{re.escape(role)}\.md$")
    out = []
    for name in names:
        m = rx.match(name)
        if not m:
            continue
        out.append((int(m.group(1)), name))
    out.sort(key=lambda item: item[0])
    return out


def _collect_codex_phase_approvals(session_dir):
    approvals = {}
    for round_num, filename in _collect_round_role_files(session_dir, "codex"):
        text = read_text(os.path.join(session_dir, filename)) or ""
        for match in re.finditer(r"^\s*Fase\s+(\d+)\s+APROVADA\b",
                                 text, re.IGNORECASE | re.MULTILINE):
            approvals[int(match.group(1))] = round_num
    return approvals


def _infer_current_phase_num(phases, last_codex_preview, last_claude_preview,
                             approved_nums):
    for text in (last_codex_preview, last_claude_preview):
        phase_num = _extract_phase_num(text)
        if phase_num is not None:
            return phase_num
    phase_nums = [phase["num"] for phase in phases]
    if not phase_nums:
        return None
    if approved_nums:
        candidate = max(approved_nums) + 1
        for phase_num in phase_nums:
            if phase_num >= candidate:
                return phase_num
        return phase_nums[-1]
    return phase_nums[0]


def _phase_label(phase, include_title=True):
    if not phase:
        return ""
    if include_title and phase.get("title"):
        return f"Fase {phase['num']} - {phase['title']}"
    return f"Fase {phase['num']}"


def _format_phase_list(phases, limit=4):
    if not phases:
        return ""
    labels = [_phase_label(phase) for phase in phases]
    if len(labels) <= limit:
        return "; ".join(labels)
    return "; ".join(labels[:limit]) + f"; +{len(labels) - limit} fase(s)"


def _build_phase_snapshot(session_dir, last_codex_preview, last_claude_preview):
    project_text = ""
    if session_dir:
        project_text = read_text(os.path.join(session_dir, "project.md")) or ""
    phases = _extract_project_phase_catalog(project_text)
    approvals = _collect_codex_phase_approvals(session_dir)
    approved_nums = set(approvals)
    for phase in phases:
        if phase.get("preapproved"):
            approved_nums.add(phase["num"])
    current_phase_num = _infer_current_phase_num(
        phases, last_codex_preview, last_claude_preview, approved_nums
    )
    current_phase = next((phase for phase in phases
                          if phase["num"] == current_phase_num), None)
    approved_phases = [phase for phase in phases if phase["num"] in approved_nums]
    remaining_after_current = []
    if current_phase_num is not None:
        remaining_after_current = [
            phase for phase in phases
            if phase["num"] > current_phase_num and phase["num"] not in approved_nums
        ]
    next_phase = remaining_after_current[0] if remaining_after_current else None
    return {
        "phases": phases,
        "approved_nums": approved_nums,
        "approved_phases": approved_phases,
        "current_phase_num": current_phase_num,
        "current_phase": current_phase,
        "next_phase": next_phase,
        "remaining_after_current": remaining_after_current,
    }


def _parse_iso_datetime(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _format_elapsed(started_at):
    started_dt = _parse_iso_datetime(started_at)
    if not started_dt:
        return ""
    now = datetime.now(started_dt.tzinfo) if started_dt.tzinfo else datetime.now()
    delta = now - started_dt
    total_seconds = max(0, int(delta.total_seconds()))
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _format_datetime_short(value):
    dt = _parse_iso_datetime(value)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else (value or "")


def _format_int(value):
    try:
        return f"{int(value):,}".replace(",", ".")
    except Exception:
        return str(value)


def _format_age_short(seconds):
    try:
        total = int(seconds)
    except Exception:
        return ""
    if total < 60:
        return f"{total}s"
    minutes, _ = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def _pid_alive(pid):
    try:
        pid = int(pid or 0)
    except Exception:
        return False
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    except Exception:
        return False
    return True


def _parse_epoch_age(value):
    try:
        ts = float(value or 0)
    except Exception:
        return None
    if ts <= 0:
        return None
    return max(0, int(datetime.now().timestamp() - ts))


def _running_runtime_health(data):
    state = ((data or {}).get("state") or "").upper()
    result = {
        "kind": "healthy",
        "banner_label": None,
        "banner_color": None,
        "note": "",
        "suggested_action": "",
    }
    if state != "RUNNING":
        return result

    pid_alive = _pid_alive((data or {}).get("orchestrator_pid"))
    heartbeat_dt = _parse_iso_datetime((data or {}).get("last_heartbeat"))
    heartbeat_age = None
    if heartbeat_dt:
        now = datetime.now(heartbeat_dt.tzinfo) if heartbeat_dt.tzinfo else datetime.now()
        heartbeat_age = max(0, int((now - heartbeat_dt).total_seconds()))

    active_agent = (data or {}).get("active_agent")
    active_call_started_at = (data or {}).get("active_call_started_at")
    last_stream_event_at = (data or {}).get("last_stream_event_at")
    last_jsonl_mtime = (data or {}).get("last_jsonl_mtime")
    call_age = _parse_epoch_age(active_call_started_at)
    signal_ref = max(float(last_stream_event_at or 0), float(last_jsonl_mtime or 0))
    if active_agent == "claude":
        try:
            call_started = float(active_call_started_at or 0)
        except Exception:
            call_started = 0
        if call_started > 0:
            signal_ref = max(signal_ref, call_started)
    signal_age = None
    if signal_ref > 0:
        signal_age = max(0, int(datetime.now().timestamp() - signal_ref))

    if not pid_alive:
        note = "O state ainda diz `RUNNING`, mas o processo dono nao esta vivo."
        if heartbeat_age is not None:
            note += f" Ultimo heartbeat ha {_format_age_short(heartbeat_age)}."
        note += " Acao sugerida: `Continue`."
        result.update({
            "kind": "process_dead",
            "banner_label": "Parada",
            "banner_color": "#dc2626",
            "note": note,
            "suggested_action": "Continue",
        })
        return result

    if active_agent == "claude" and call_age is not None and signal_age is not None and signal_age > 600:
        action = "Recover" if signal_age > 1800 else "Observe"
        note = (
            f"O processo ainda esta vivo, mas a call atual do Claude esta sem sinal novo "
            f"ha {_format_age_short(signal_age)}."
        )
        if heartbeat_age is not None:
            note += f" Ultimo heartbeat ha {_format_age_short(heartbeat_age)}."
        if action == "Recover":
            note += " Acao sugerida: `Recover`."
        else:
            note += " Acao sugerida: observar; se continuar assim, use `Recover`."
        result.update({
            "kind": "stale_alive",
            "banner_label": "Vivo, mas parado",
            "banner_color": "#d97706",
            "note": note,
            "suggested_action": action,
        })
        return result

    if heartbeat_age is not None and heartbeat_age > 180:
        action = "Recover" if heartbeat_age > 600 else "Observe"
        note = f"O processo esta vivo, mas o heartbeat nao atualiza ha {_format_age_short(heartbeat_age)}."
        if action == "Recover":
            note += " Acao sugerida: `Recover`."
        else:
            note += " Acao sugerida: observar; se continuar assim, use `Recover`."
        result.update({
            "kind": "stale_alive",
            "banner_label": "Vivo, mas parado",
            "banner_color": "#d97706",
            "note": note,
            "suggested_action": action,
        })
        return result

    return result


def _find_claude_jsonl_for_uuid(session_uuid):
    if not session_uuid:
        return None
    base = os.path.expanduser("~/.claude/projects")
    if not os.path.isdir(base):
        return None
    try:
        for root, _, files in os.walk(base):
            if f"{session_uuid}.jsonl" in files:
                return os.path.join(root, f"{session_uuid}.jsonl")
    except Exception:
        return None
    return None


def _estimate_claude_usage(session_uuid):
    path = _find_claude_jsonl_for_uuid(session_uuid)
    if not path or not os.path.isfile(path):
        return None
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "events": 0,
        "model": "",
        "path": path,
    }
    models = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                message = obj.get("message") if isinstance(obj, dict) else None
                usage = message.get("usage") if isinstance(message, dict) else None
                if isinstance(usage, dict):
                    for key in (
                        "input_tokens",
                        "output_tokens",
                        "cache_creation_input_tokens",
                        "cache_read_input_tokens",
                    ):
                        value = usage.get(key)
                        if isinstance(value, (int, float)):
                            totals[key] += int(value)
                    totals["events"] += 1
                model = ""
                if isinstance(message, dict):
                    model = message.get("model") or ""
                if not model and isinstance(obj, dict):
                    model = obj.get("model") or ""
                if model and not str(model).startswith("<"):
                    models[str(model)] = models.get(str(model), 0) + 1
    except Exception:
        return None
    if models:
        totals["model"] = sorted(models.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return totals


def _remaining_complexity_note(current_phase_num):
    if current_phase_num is None:
        return ""
    if current_phase_num <= 2:
        return (
            "A parte mais cara em runtime ainda esta por vir: a baseline completa da "
            "Fase 3 e o primeiro trecho realmente pesado."
        )
    if current_phase_num == 3:
        return (
            "O trecho mais caro em runtime esta acontecendo agora. Depois disso entram "
            "analise e codigo, mas ainda existe outro rerun completo na Fase 6."
        )
    if current_phase_num in (4, 5):
        return (
            "O benchmark baseline pesado ja passou. Ainda falta a revalidacao completa "
            "da Fase 6, que volta a ser cara em tempo."
        )
    if current_phase_num == 6:
        return (
            "Outra fase pesada em runtime esta em andamento agora. Depois dela, o que "
            "resta e rollout controlado e possivel fechamento."
        )
    return (
        "As fases mais pesadas de benchmark ja passaram. O que resta tende a ser mais "
        "curto em volume, embora ainda possa ser sensivel em risco operacional."
    )


def _build_running_exec_summary(data, current_round, last_ok, started_at,
                                last_codex_file, last_codex_preview,
                                last_claude_file, last_claude_preview,
                                longrun_narrative, recovery_narrative,
                                project_achievement, project_gap_bits,
                                project_decision_text):
    runtime_health = _running_runtime_health(data)
    phase_snapshot = _build_phase_snapshot(
        data.get("_session_dir"), last_codex_preview, last_claude_preview
    )
    current_phase = phase_snapshot["current_phase"]
    phase_headline = _phase_label(current_phase, include_title=False) or "Fase atual nao inferida"
    headline = f"Round {current_round} em execucao - {phase_headline}"
    if runtime_health["kind"] == "process_dead":
        headline = f"Round {current_round} parado - processo do orquestrador morreu"
    elif runtime_health["kind"] == "stale_alive":
        headline = f"Sistema vivo, mas parado - round {current_round} sem sinal novo"
    elif data.get("active_agent") == "claude":
        headline = f"Claude executando {phase_headline} no round {current_round}"
    elif data.get("active_agent") == "codex":
        headline = f"Codex revisando {phase_headline} no round {current_round}"

    phase_lines = []
    phases = phase_snapshot["phases"]
    if phases:
        first_num = phases[0]["num"]
        last_num = phases[-1]["num"]
        phase_lines.append(
            f"O projeto tem {len(phases)} fases no total ({first_num} a {last_num})."
        )
    if current_phase:
        phase_lines.append(f"Fase atual: {_phase_label(current_phase)}.")
    if phase_snapshot["approved_phases"]:
        phase_lines.append(
            "Fases ja aprovadas: "
            + _format_phase_list(phase_snapshot["approved_phases"])
            + "."
        )
    if phase_snapshot["remaining_after_current"]:
        phase_lines.append(
            f"Restam {len(phase_snapshot['remaining_after_current'])} fase(s) depois desta."
        )
    if phase_snapshot["next_phase"]:
        phase_lines.append(
            f"Se esta fase for aprovada, libera {_phase_label(phase_snapshot['next_phase'])}."
        )

    where_lines = [f"Round atual: {current_round}."]
    if last_ok:
        where_lines.append(f"Ultimo round completo com sucesso: {last_ok}.")
    if runtime_health.get("note"):
        where_lines.append(runtime_health["note"])
    if longrun_narrative:
        where_lines.append(longrun_narrative)
    if recovery_narrative:
        where_lines.append(recovery_narrative)
    where_lines.extend(phase_lines)

    done_lines = []
    if project_achievement.get("artifacts"):
        done_lines.append(
            "Entrega mais recente da fase atual: "
            + ", ".join(f"`{name}`" for name in project_achievement["artifacts"])
            + "."
        )
    if project_achievement.get("coverage"):
        done_lines.append(project_achievement["coverage"])
    if project_achievement.get("metrics"):
        done_lines.append(project_achievement["metrics"])

    now_lines = []
    if runtime_health["kind"] == "process_dead":
        now_lines.append(
            "O processo do orquestrador morreu antes de concluir esta etapa; a sessao precisa de `Continue`."
        )
    elif runtime_health["kind"] == "stale_alive":
        now_lines.append(
            "A sessao entrou numa chamada sem progresso observavel; trate como parado ate voltar a emitir sinal."
        )
    elif data.get("active_agent") == "claude" and last_codex_file:
        now_lines.append(
            f"Claude esta respondendo ao pedido mais recente do Codex em `{last_codex_file}`."
        )
    elif data.get("active_agent") == "codex" and last_claude_file:
        now_lines.append(
            f"Codex esta avaliando a resposta mais recente do Claude em `{last_claude_file}`."
        )
    if project_gap_bits:
        now_lines.append("Pontos que ainda faltam para liberar a proxima fase:")
        for gap in project_gap_bits[:3]:
            now_lines.append(gap.lstrip("- ").strip())
    elif project_decision_text:
        now_lines.append(project_decision_text)
    else:
        codex_line = _first_meaningful_line(last_codex_preview)
        if codex_line:
            now_lines.append(f"Pedido atual do Codex: {codex_line}")

    timing_lines = []
    elapsed = _format_elapsed(started_at)
    started_at_text = _format_datetime_short(started_at)
    if elapsed:
        timing_lines.append(f"Tempo decorrido: {elapsed} desde {started_at_text}.")
    usage = _estimate_claude_usage(data.get("claude_session_uuid"))
    if usage and usage.get("events"):
        token_line = (
            "Tokens Claude medidos ate agora: "
            f"output {_format_int(usage['output_tokens'])}, "
            f"input {_format_int(usage['input_tokens'])}"
        )
        cache_bits = []
        if usage.get("cache_read_input_tokens"):
            cache_bits.append(f"cache-read {_format_int(usage['cache_read_input_tokens'])}")
        if usage.get("cache_creation_input_tokens"):
            cache_bits.append(
                f"cache-create {_format_int(usage['cache_creation_input_tokens'])}"
            )
        if cache_bits:
            token_line += ", " + ", ".join(cache_bits)
        if usage.get("model"):
            token_line += f" (modelo dominante: {usage['model']})"
        token_line += "."
        timing_lines.append(token_line)
        timing_lines.append(
            "O orquestrador nao adiciona chamadas extras; esse consumo seria "
            "praticamente o mesmo numa sessao manual longa do Claude Code."
        )

    remaining_lines = []
    complexity_note = _remaining_complexity_note(phase_snapshot["current_phase_num"])
    if complexity_note:
        remaining_lines.append(complexity_note)

    detail_blocks = []
    if where_lines:
        detail_blocks.append("**Onde esta agora**\n" + "\n".join(f"- {line}" for line in where_lines))
    if done_lines:
        detail_blocks.append("**O que ja foi realizado**\n" + "\n".join(f"- {line}" for line in done_lines))
    if now_lines:
        detail_blocks.append("**O que esta sendo feito agora**\n" + "\n".join(f"- {line}" for line in now_lines))
    if timing_lines:
        detail_blocks.append("**Tempo e tokens**\n" + "\n".join(f"- {line}" for line in timing_lines))
    if remaining_lines:
        detail_blocks.append("**Complexidade restante**\n" + "\n".join(f"- {line}" for line in remaining_lines))

    if runtime_health["kind"] == "process_dead":
        what_to_do = (
            "O `state` ainda esta `RUNNING`, mas o processo dono morreu. "
            "Acao sugerida: rode `Continue` para retomar a sessao."
        )
    elif runtime_health["kind"] == "stale_alive":
        action = runtime_health.get("suggested_action") or "Observe"
        if action == "Recover":
            what_to_do = (
                "O processo ainda existe, mas a sessao nao mostra progresso real. "
                "Acao sugerida: rode `Recover`."
            )
        else:
            what_to_do = (
                "A sessao ainda esta viva, mas sem sinal novo suficiente para chamar isso "
                "de execucao saudavel. Observe por mais um pouco; se continuar assim, rode `Recover`."
            )
    else:
        what_to_do = (
            "A pagina se atualiza sozinha. Intervenha apenas se a sessao mudar para "
            "`WAITING_HUMAN`/`PAUSED_RECOVERABLE`, ou se o round ficar longo demais "
            "sem sinais de vida."
        )
    detail = "\n\n".join(block for block in detail_blocks if block)
    return headline, detail, what_to_do


def humanize_state(state, data, session_dir=None, checkpoint_md=""):
    """V2.3+: narrativa rica que le arquivos da sessao para contar
    a historia do que aconteceu, nao so o estado tecnico."""
    s = (state or "").upper()
    current_round = (data or {}).get("current_round", 0)
    paused_reason = (data or {}).get("paused_reason") or ""
    retry_count = (data or {}).get("retry_count", 0)
    next_retry = (data or {}).get("next_retry_at") or ""
    last_ok = (data or {}).get("last_successful_round", 0)
    started_at = (data or {}).get("started_at") or ""

    last_codex_file = last_claude_file = None
    last_codex_preview = last_claude_preview = ""
    if session_dir:
        last_codex_file, last_claude_file = _last_round_files(session_dir)
        if not last_codex_file and current_round == 0:
            # cair em activation/bootstrap
            for f in ("round-000-codex-activation.md", "round-000-codex-bootstrap.md"):
                if os.path.isfile(os.path.join(session_dir, f)):
                    last_codex_file = f
                    break
        if not last_claude_file and current_round == 0:
            for f in ("round-000-claude-activation.md", "round-000-claude-bootstrap.md"):
                if os.path.isfile(os.path.join(session_dir, f)):
                    last_claude_file = f
                    break
        if last_codex_file:
            last_codex_preview = _read_last(session_dir, last_codex_file, 2000)
        if last_claude_file:
            last_claude_preview = _read_last(session_dir, last_claude_file, 1200)

    stage = _stage_label(current_round, last_codex_file, last_claude_file)
    last_codex_line = _first_meaningful_line(last_codex_preview)
    last_claude_line = _first_meaningful_line(last_claude_preview)
    phase_from_codex = _extract_phase(last_codex_preview)
    phase_in_decision = _extract_phase(last_codex_line)
    checkpoint_rounds = _extract_checkpoint_round_lines(checkpoint_md)
    last_checkpoint_round = checkpoint_rounds[-1] if checkpoint_rounds else ""
    checkpoint_repo_files = _extract_checkpoint_repo_files(checkpoint_md)
    project_achievement = {}
    project_gap_bits = []
    project_decision_text = ""
    if session_dir and last_ok:
        last_ok_claude_file = f"round-{int(last_ok):03d}-claude.md"
        last_ok_claude_text = _read_last(session_dir, last_ok_claude_file, 12000)
        project_achievement = _extract_project_achievement_bits(last_ok_claude_text)
    if last_codex_preview:
        project_gap_bits = _extract_project_gap_bits(last_codex_preview)
        project_decision_text = _extract_project_decision_text(last_codex_preview)

    # V2.3 hotfix: observabilidade de long-run (narrativa se Claude esta em call ativa)
    active_agent = (data or {}).get("active_agent")
    active_call_status = (data or {}).get("active_call_status")
    active_call_started_at = (data or {}).get("active_call_started_at")
    last_stream_event_at = (data or {}).get("last_stream_event_at")
    last_jsonl_mtime = (data or {}).get("last_jsonl_mtime")
    recovery_strategy = (data or {}).get("recovery_strategy") or ""
    recovery_note = (data or {}).get("recovery_note") or ""
    recovery_confidence = (data or {}).get("recovery_confidence") or ""
    longrun_narrative = ""
    if active_agent == "claude" and active_call_started_at:
        try:
            import time as _t
            now = _t.time()
            call_dur = int(max(0, now - float(active_call_started_at)))
            parts = [f"Claude esta ativo ha {call_dur}s nesta call (status={active_call_status or 'in_call'})."]
            sig_at = max(float(last_stream_event_at or 0),
                         float(last_jsonl_mtime or 0))
            if sig_at > 0:
                idle = int(max(0, now - sig_at))
                parts.append(f"Ultimo sinal de vida ha {idle}s.")
            parts.append(
                "Sessao NAO esta travada — call longa com atividade recente continua viva "
                "por desenho (watchdog so mata por inatividade dupla prolongada ou arquivo STOP)."
            )
            longrun_narrative = " ".join(parts)
        except Exception:
            longrun_narrative = ""
    recovery_narrative = ""
    if recovery_strategy:
        recovery_narrative = (
            f"Recovery automatico V2.5 foi acionado com estrategia "
            f"`{recovery_strategy}`"
            + (f" ({recovery_confidence})." if recovery_confidence else ".")
            + (f" Nota: {recovery_note}" if recovery_note else "")
        )

    if s == "BOOTSTRAP":
        headline = "Inicializando a sessao"
        detail = (
            f"Iniciada em {started_at}. Esta carregando o brief, conectando Claude e Codex "
            f"e configurando as sessoes persistentes. Geralmente leva 1 a 3 minutos."
        )
        what_to_do = "Nada por enquanto. A pagina atualiza sozinha a cada 5 segundos."
        verify = ""

    elif s == "RUNNING":
        headline = f"Tudo rodando — {stage.lower()}"
        if project_achievement.get("artifacts") and project_gap_bits:
            headline = (
                "Ja existe entrega concreta do projeto, mas o Codex ainda nao aceitou "
                f"o que foi produzido no round {last_ok}."
            )
        elif phase_from_codex:
            headline = f"{phase_from_codex} em execucao - Claude esta trabalhando no round {current_round}."
        progress_bits = []
        if longrun_narrative:
            progress_bits.append(longrun_narrative)
        if recovery_narrative:
            progress_bits.append(recovery_narrative)
        achievement_lines = []
        if project_achievement.get("artifacts"):
            achievement_lines.append(
                "Ja foi conseguido no projeto: "
                + ", ".join(f"`{name}`" for name in project_achievement["artifacts"]) + "."
            )
        if project_achievement.get("coverage"):
            achievement_lines.append(project_achievement["coverage"])
        if project_achievement.get("metrics"):
            achievement_lines.append(project_achievement["metrics"])
        if achievement_lines:
            progress_bits.append("O projeto ja entregou isto:\n- " + "\n- ".join(achievement_lines))
        if last_checkpoint_round:
            progress_bits.append(f"Ate o checkpoint mais recente, o projeto estava assim: {last_checkpoint_round}")
        gap_lines = []
        if project_gap_bits:
            gap_lines.append("Ainda falta fechar estes pontos para o projeto andar:")
            gap_lines.extend(f"- {gap}" for gap in project_gap_bits[:3])
        if project_decision_text:
            gap_lines.append(project_decision_text)
        elif last_codex_line:
            gap_lines.append(f"Dilema atual do Codex em `{last_codex_file}`: {last_codex_line}")
        elif last_claude_line:
            gap_lines.append(f"Ultima resposta do Claude em `{last_claude_file}`: {last_claude_line}")
        if gap_lines:
            progress_bits.append("\n".join(gap_lines))
        if last_ok:
            progress_bits.append(f"Ultimo round completo com sucesso: {last_ok}.")
        detail = " ".join(progress_bits) if progress_bits else (
            f"O loop esta ativo. Claude e Codex estao conversando normalmente. "
            f"Ultimo round completo com sucesso: {last_ok}."
        )
        what_to_do = (
            "Nao precisa agir agora. O acompanhamento util e verificar se o Claude "
            "consegue transformar essa duvida do Codex em uma resposta objetiva: "
            "ou baseline completa, ou bloqueio real provado."
        )
        verify = ""

    elif s == "RETRY_BACKOFF":
        # V2.7: se quota_attempt > 0, renderiza em linguagem de creditos.
        quota_attempt = (data or {}).get("quota_attempt", 0) or 0
        if quota_attempt > 0:
            quota_since = (data or {}).get("quota_since") or "(nao registrado)"
            quota_last_error = (data or {}).get("quota_last_error") or "(nao registrado)"
            quota_next_ping = (data or {}).get("quota_next_ping_at") or next_retry or "em breve"
            headline = (
                f"Creditos Claude/Codex esgotados — "
                f"aguardando recarga (ping #{quota_attempt})"
            )
            detail = (
                f"A ultima chamada falhou por FALTA DE CREDITO (nao e erro de infra, e conta zerada ou limite de billing atingido).\n"
                f"O orquestrador NAO fechou a sessao — ele esta dormindo e vai fazer um ping leve ate **{quota_next_ping}**.\n"
                f"Schedule de backoff: 1min → 10min → 30min → 30min → 30min... (infinito).\n"
                f"Se o ping responder (API aceitou), a sessao retoma sozinha de onde parou, no MESMO round.\n"
                f"**Desde:** {quota_since}\n"
                f"**Ultima mensagem de erro:** {quota_last_error}"
            )
            what_to_do = (
                "Recarregue creditos na sua conta Anthropic/OpenAI quando puder. "
                "Nao precisa clicar em nada — o sistema detecta automaticamente e continua. "
                "Se quiser parar mesmo assim, rode `close S-XXXX` em outra aba."
            )
            verify = ""
        else:
            headline = f"API com problema — esperando para tentar de novo (tentativa {retry_count})"
            detail = (
                f"A ultima chamada para Claude ou Codex deu erro de infraestrutura "
                f"(API 500, sobrecarga, rate limit ou rede). Isso e comum e geralmente passa em alguns minutos.\n"
                f"O orquestrador esta dormindo ate {next_retry or 'em breve'} e vai retentar a mesma mensagem na mesma sessao quando acordar.\n"
                f"**Voce nao esta gastando tokens enquanto isso.**\n"
                f"**Detalhe tecnico do erro:** {paused_reason or '(nao registrado)'}"
            )
            what_to_do = (
                "Nao precisa fazer nada — retry e automatico e infinito. "
                "Se quiser parar mesmo assim, faca Ctrl+C na aba do orquestrador ou rode `close` em outra aba."
            )
            verify = ""

    elif s == "PAUSED_RECOVERABLE":
        headline = "Sessao pausada — algo deu errado e o orquestrador nao soube classificar"
        detail = (
            f"O orquestrador tentou {((data or {}).get('unknown_error_count') or 0)} vez(es) "
            f"a mesma operacao mas o erro nao parece ser de infra (nao e 500, nao e rate limit). "
            f"Pode ser bug local, permissao, prompt corrompido, ou algo inesperado.\n"
            f"O sistema parou para nao seguir tentando as cegas e gerou um checkpoint para voce analisar.\n"
            f"**Motivo registrado:** {paused_reason or '(nao informado)'}"
        )
        if recovery_narrative:
            detail += f"\n\n{recovery_narrative}"
        what_to_do = (
            "Abra o checkpoint mais recente abaixo, leia a Secao F (logs) e a Secao E (estado atual). "
            "Identifique o erro real. Se conseguir corrigir o ambiente, rode `continue` para retomar. "
            "Se nao fizer sentido, rode `close` e abra nova sessao."
        )
        verify = ""

    elif s == "WAITING_HUMAN":
        headline = "Codex pediu sua intervencao para continuar"
        detail = (
            f"O Codex (admin) escreveu HUMANO em uma resposta porque encontrou um bloqueio "
            f"que so voce pode resolver — pode ser falta de credencial, decisao de escopo, "
            f"ou algo externo ao sistema."
        )
        if last_codex_preview:
            detail += f"\n\n**Texto que o Codex enviou ({last_codex_file}):**\n> " + (last_codex_preview[:300].replace('\n', '\n> '))
        what_to_do = (
            "Leia o texto do Codex acima. Faca a acao que ele pediu (criar arquivo, "
            "ajustar .env, etc) e rode `continue` para retomar. Se nao for possivel, rode `close`."
        )
        verify = ""

    elif s == "READY_FOR_HUMAN_CLOSE":
        # Caso especial: zero rounds + CONCLUIDO = quase certamente falso positivo
        if current_round == 0:
            headline = "Codex disse 'concluido' antes mesmo de comecar — provavel falso positivo"
            detail = (
                "O orquestrador detectou a palavra `CONCLUIDO` na primeira mensagem do Codex "
                "e por seguranca interpretou como 'projeto inteiro acabado'. **Mas nenhum round "
                "de trabalho aconteceu ainda** — entao quase certamente foi falso positivo "
                "(provavelmente Codex usou a palavra dentro de uma instrucao para o Claude, "
                "como 'nao chame parcial de concluido')."
            )
            if last_codex_preview:
                detail += f"\n\n**Olha o que o Codex enviou ({last_codex_file}):**\n> " + (last_codex_preview[:400].replace('\n', '\n> '))
            what_to_do = (
                "Recomendacao: rode `close S-XXXX` para fechar essa sessao com seguranca e "
                "abra uma nova. O detector ja foi corrigido e a proxima sessao nao vai cair "
                "no mesmo problema. Se voce quiser tentar continuar essa mesma sessao, "
                "rode `continue` — o sistema vai retomar do round 1 (Claude finalmente recebe a tarefa)."
            )
        else:
            headline = "Codex sinalizou que o projeto terminou"
            detail = (
                f"O Codex (admin) escreveu CONCLUIDO no fim de uma resposta, depois de {current_round} round(s). "
                f"O sistema nao fechou sozinho — guardou tudo e esta esperando voce validar."
            )
            if last_codex_preview:
                detail += f"\n\n**Texto final do Codex ({last_codex_file}):**\n> " + (last_codex_preview[:300].replace('\n', '\n> '))
            what_to_do = (
                "Revise o trabalho gerado no repositorio (Secao C do checkpoint lista os arquivos tocados). "
                "Se estiver OK: rode `close` para gerar `final-review.md` e encerrar formalmente. "
                "Se quiser revisar mais rodadas: rode `continue`."
            )
        verify = ""

    elif s == "CLOSED_BY_HUMAN":
        headline = "Sessao fechada formalmente"
        detail = (
            "Voce fechou esta sessao (via Ctrl+C ou comando `close`). "
            f"O `final-review.md` foi gerado. O lock foi liberado.\n"
            f"Razao registrada: {paused_reason or '-'}"
        )
        what_to_do = "Nada. Para abrir uma nova sessao, use `INICIAR_ORQUESTRADOR.bat`."
        verify = ""

    else:
        headline = f"Estado desconhecido: {s}"
        detail = "O viewer nao reconhece esse estado. Pode ser corrupcao do session-state.json."
        what_to_do = "Abra session-state.json manualmente e cole em outra aba para diagnostico."
        verify = ""

    return headline, detail, what_to_do


def humanize_state_v2(state, data, session_dir=None, checkpoint_md=""):
    s = (state or "").upper()
    if s != "RUNNING":
        return humanize_state(state, data, session_dir, checkpoint_md)

    current_round = (data or {}).get("current_round", 0)
    last_ok = (data or {}).get("last_successful_round", 0)
    started_at = (data or {}).get("started_at") or ""

    last_codex_file = last_claude_file = None
    last_codex_preview = last_claude_preview = ""
    if session_dir:
        last_codex_file, last_claude_file = _last_round_files(session_dir)
        if last_codex_file:
            last_codex_preview = _read_last(session_dir, last_codex_file, 12000)
        if last_claude_file:
            last_claude_preview = _read_last(session_dir, last_claude_file, 4000)

    project_achievement = {}
    if session_dir and last_ok:
        last_ok_claude_file = f"round-{int(last_ok):03d}-claude.md"
        last_ok_claude_text = _read_last(session_dir, last_ok_claude_file, 12000)
        project_achievement = _extract_project_achievement_bits(last_ok_claude_text)

    project_gap_bits = _extract_project_gap_bits(last_codex_preview) if last_codex_preview else []
    project_decision_text = (
        _extract_project_decision_text(last_codex_preview) if last_codex_preview else ""
    )

    active_agent = (data or {}).get("active_agent")
    active_call_status = (data or {}).get("active_call_status")
    active_call_started_at = (data or {}).get("active_call_started_at")
    last_stream_event_at = (data or {}).get("last_stream_event_at")
    last_jsonl_mtime = (data or {}).get("last_jsonl_mtime")
    recovery_strategy = (data or {}).get("recovery_strategy") or ""
    recovery_note = (data or {}).get("recovery_note") or ""
    recovery_confidence = (data or {}).get("recovery_confidence") or ""

    longrun_narrative = ""
    if active_agent == "claude" and active_call_started_at:
        try:
            import time as _t
            now = _t.time()
            call_dur = int(max(0, now - float(active_call_started_at)))
            parts = [
                f"Claude esta ativo ha {call_dur}s nesta call (status={active_call_status or 'in_call'})."
            ]
            sig_at = max(float(last_stream_event_at or 0), float(last_jsonl_mtime or 0))
            try:
                sig_at = max(sig_at, float(active_call_started_at or 0))
            except Exception:
                pass
            if sig_at > 0:
                idle = int(max(0, now - sig_at))
                parts.append(f"Ultimo sinal de vida ha {idle}s.")
                if idle <= 600:
                    parts.append("A call ainda parece viva por telemetria recente.")
                else:
                    parts.append(
                        "Esse sinal de vida ja ficou antigo; vale observar se o round evolui "
                        "ou se a sessao migra para pausa/recovery."
                    )
            else:
                parts.append("Sem telemetria recente suficiente para afirmar liveness.")
            longrun_narrative = " ".join(parts)
        except Exception:
            longrun_narrative = ""

    recovery_narrative = ""
    if recovery_strategy:
        recovery_narrative = (
            f"Recovery automatico V2.5 foi acionado com estrategia "
            f"`{recovery_strategy}`"
            + (f" ({recovery_confidence})." if recovery_confidence else ".")
            + (f" Nota: {recovery_note}" if recovery_note else "")
        )

    running_data = dict(data or {})
    running_data["_session_dir"] = session_dir
    return _build_running_exec_summary(
        running_data, current_round, last_ok, started_at,
        last_codex_file, last_codex_preview,
        last_claude_file, last_claude_preview,
        longrun_narrative, recovery_narrative,
        project_achievement, project_gap_bits,
        project_decision_text,
    )


def load_session_state(session_dir):
    path = os.path.join(session_dir, "session-state.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def find_latest_checkpoint(session_dir):
    """Retorna (caminho, nome) do summary_*.md mais recente, ou (None, None)."""
    try:
        files = [f for f in os.listdir(session_dir)
                 if f.startswith("summary_") and f.endswith(".md")]
        if not files:
            return None, None
        files.sort()  # ordem alfabetica = ordem cronologica (timestamp ISO)
        latest = files[-1]
        return os.path.join(session_dir, latest), latest
    except Exception:
        return None, None


def list_checkpoints(session_dir):
    try:
        files = [f for f in os.listdir(session_dir)
                 if f.startswith("summary_") and f.endswith(".md")]
        files.sort(reverse=True)
        return files
    except Exception:
        return []


def render_dashboard(session_dir, info, state, checkpoint_md, checkpoint_name,
                    checkpoints_all):
    """Renderiza a pagina de dashboard (substitui a view de bolhas)."""
    state_name = (state or {}).get("state") or "UNKNOWN"
    color, label = STATE_COLORS.get(state_name, ("#6b7280", state_name))
    runtime_health = _running_runtime_health(state or {})
    if runtime_health.get("banner_label"):
        label = runtime_health["banner_label"]
    if runtime_health.get("banner_color"):
        color = runtime_health["banner_color"]
    # V2.7: diferencia RETRY_BACKOFF de quota no banner.
    if state_name == "RETRY_BACKOFF" and ((state or {}).get("quota_attempt") or 0) > 0:
        label = "Creditos esgotados (aguardando recarga)"
        color = "#9333ea"  # roxo pra diferenciar de retry transitorio (amarelo)
    session_name = info["session_name"]
    run_label = info.get("run_label") or ""
    current_round = (state or {}).get("current_round", 0)
    last_ok_round = (state or {}).get("last_successful_round", 0)
    round_stage = (state or {}).get("round_stage") or "-"
    next_retry = (state or {}).get("next_retry_at") or ""
    paused_reason = (state or {}).get("paused_reason") or ""
    recovered_from = (state or {}).get("recovered_from") or ""
    recovery_at = (state or {}).get("recovery_at") or ""
    recovery_confidence = (state or {}).get("recovery_confidence") or ""
    recovery_strategy = (state or {}).get("recovery_strategy") or ""
    recovery_note = (state or {}).get("recovery_note") or ""
    claude_uuid = (state or {}).get("claude_session_uuid") or ""
    codex_uuid = (state or {}).get("codex_session_uuid") or ""
    suggested_action = runtime_health.get("suggested_action") or ""

    checkpoint_name_safe = html.escape(checkpoint_name or "(nenhum)")
    checkpoint_body = checkpoint_md or ""

    checkpoints_list_html = ""
    if checkpoints_all:
        items = []
        for f in checkpoints_all:
            items.append(f'<li><code>{html.escape(f)}</code></li>')
        checkpoints_list_html = "<ul>" + "".join(items) + "</ul>"
    else:
        checkpoints_list_html = "<p class='muted'>Nenhum checkpoint gerado ainda.</p>"

    # Card explicativo (o que aconteceu + o que fazer) — le arquivos da sessao
    headline, detail, what_to_do = humanize_state_v2(
        state_name, state, session_dir, checkpoint_md=checkpoint_body
    )
    import re as _re
    def _md_bold(txt):
        # converte **foo** para <strong>foo</strong> depois do escape
        esc = html.escape(txt)
        return _re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', esc).replace('\n', '<br>')
    status_headline_html = _md_bold(headline)
    status_detail_html = _md_bold(detail)
    status_what_html = _md_bold(what_to_do)

    data = {
        "TITLE": f"Dashboard - {session_name}",
        "SESSION_NAME": session_name,
        "RUN_LABEL": run_label,
        "STATE_NAME": state_name,
        "STATE_LABEL": label,
        "STATE_COLOR": color,
        "CURRENT_ROUND": str(current_round),
        "LAST_OK_ROUND": str(last_ok_round),
        "ROUND_STAGE": round_stage,
        "NEXT_RETRY": next_retry,
        "RECOVERED_FROM": recovered_from,
        "RECOVERY_AT": recovery_at,
        "RECOVERY_CONFIDENCE": recovery_confidence,
        "RECOVERY_STRATEGY": recovery_strategy,
        "RECOVERY_NOTE": html.escape(recovery_note),
        "SUGGESTED_ACTION": html.escape(suggested_action or "-"),
        "PAUSED_REASON": html.escape(paused_reason),
        "SESSION_DIR": session_dir,
        "CLAUDE_UUID": claude_uuid,
        "CODEX_UUID": codex_uuid,
        "CHECKPOINT_NAME": checkpoint_name_safe,
        "CHECKPOINT_MD_JSON": json.dumps(checkpoint_body, ensure_ascii=False),
        "CHECKPOINTS_LIST": checkpoints_list_html,
        "GENERATED_AT": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "STATUS_HEADLINE": status_headline_html,
        "STATUS_DETAIL": status_detail_html,
        "STATUS_WHAT_TO_DO": status_what_html,
        "PAUSED_REASON_RAW": (paused_reason or "(nenhum)").replace("\n", " "),
    }

    page = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root {
  --bg: #0f1115;
  --panel: #161a22;
  --panel2: #1b2030;
  --text: #e6e9ef;
  --muted: #8b93a7;
  --border: #262c3a;
  --state-color: __STATE_COLOR__;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0;
  background: var(--bg); color: var(--text);
  font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  font-size: 14px; line-height: 1.5;
}
.banner {
  background: var(--state-color); color: #0f1115;
  padding: 20px 24px; font-weight: 700; font-size: 18px;
  display: flex; align-items: center; justify-content: space-between;
}
.banner .state-name { font-size: 20px; }
.banner .actions { font-size: 12px; font-weight: 500; }
.banner .actions code { background: rgba(0,0,0,0.2); padding: 2px 6px; border-radius: 4px; }
.topbar {
  background: var(--panel); border-bottom: 1px solid var(--border);
  padding: 12px 24px; display: flex; gap: 16px; flex-wrap: wrap;
  font-size: 13px;
}
.topbar .item { color: var(--muted); }
.topbar .item b { color: var(--text); }
.container { max-width: 1100px; margin: 0 auto; padding: 24px; }
.card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px 20px; margin-bottom: 16px;
}
.card h2 { margin-top: 0; font-size: 15px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.status-card { border-left: 4px solid var(--state-color); }
.status-headline { font-size: 20px; font-weight: 700; margin-bottom: 10px; color: #f1f5f9; }
.status-detail { font-size: 14px; margin-bottom: 16px; line-height: 1.6; color: #e2e8f0; }
.status-what { font-size: 13px; padding: 12px 14px; background: var(--panel2); border-radius: 6px; color: #cbd5e1; line-height: 1.5; }
.status-what b { color: #fbbf24; }
.path-row { margin: 14px 0; }
.path-label { font-size: 12px; color: var(--muted); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.path-value { display: flex; align-items: center; gap: 8px; }
.path-value code { flex: 1; background: var(--panel2); padding: 8px 12px; border-radius: 6px; font-size: 13px; word-break: break-all; }
.mini-btn { background: var(--panel2); color: var(--text); border: 1px solid var(--border); padding: 6px 12px; border-radius: 5px; cursor: pointer; font-size: 12px; }
.mini-btn:hover { background: var(--border); }
.mini-btn.copied { background: #22c55e; color: #0f1115; border-color: #22c55e; }
.ask-prompt { width: 100%; min-height: 220px; background: var(--panel2); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-family: Consolas, monospace; font-size: 12px; line-height: 1.5; resize: vertical; }
.muted { color: var(--muted); }
.btn {
  display: inline-block; background: var(--panel2); color: var(--text);
  padding: 8px 14px; border-radius: 6px; text-decoration: none;
  font-size: 13px; border: 1px solid var(--border);
}
.btn:hover { background: var(--border); }
.checkpoint-body h1 { font-size: 22px; margin-top: 16px; }
.checkpoint-body h2 { font-size: 17px; margin-top: 20px; color: #cbd5e1; }
.checkpoint-body h3 { font-size: 14px; margin-top: 14px; }
.checkpoint-body p { margin: 6px 0; }
.checkpoint-body ul,.checkpoint-body ol { margin: 6px 0; padding-left: 22px; }
.checkpoint-body code { background: #0b0d12; padding: 1px 5px; border-radius: 3px; font-size: 12px; }
.checkpoint-body pre { background: #0b0d12; padding: 10px; border-radius: 6px; overflow-x: auto; font-size: 12px; }
.checkpoint-body pre code { background: transparent; padding: 0; }
.checkpoint-body blockquote { border-left: 3px solid var(--border); padding-left: 10px; color: var(--muted); }
.copy-btn {
  cursor: pointer; background: var(--state-color); color: #0f1115;
  border: none; padding: 8px 14px; border-radius: 6px;
  font-weight: 600; font-size: 13px;
}
.copy-btn.copied { background: #22c55e; }
.small { font-size: 11px; color: var(--muted); }
</style>
</head>
<body>
<div class="banner">
  <div>
    <div>__STATE_LABEL__</div>
    <div class="state-name small">state: __STATE_NAME__ | sessao: __SESSION_NAME__</div>
  </div>
  <div class="actions">
    <code>start_dupla.cmd continue __SESSION_NAME__</code> &nbsp;|&nbsp;
    <code>start_dupla.cmd close __SESSION_NAME__</code>
  </div>
</div>

<div class="topbar">
  <div class="item"><b>Round:</b> __CURRENT_ROUND__ (ultimo OK: __LAST_OK_ROUND__)</div>
  <div class="item"><b>Stage:</b> __ROUND_STAGE__</div>
  <div class="item"><b>Proxima tentativa:</b> __NEXT_RETRY__</div>
  <div class="item"><b>Recovery:</b> __RECOVERED_FROM__ __RECOVERY_CONFIDENCE__</div>
  <div class="item"><b>Strategy:</b> __RECOVERY_STRATEGY__</div>
  <div class="item"><b>Recovery at:</b> __RECOVERY_AT__</div>
  <div class="item"><b>Acao sugerida:</b> __SUGGESTED_ACTION__</div>
  <div class="item"><b>Label:</b> __RUN_LABEL__</div>
  <div class="item"><a class="btn" href="session_conversation.html">Ver conversa completa →</a></div>
</div>

<div class="container">

  <div class="card status-card">
    <h2>O que esta acontecendo</h2>
    <div class="status-headline">__STATUS_HEADLINE__</div>
    <div class="status-detail">__STATUS_DETAIL__</div>
    <div class="status-what">
      <b>O que voce deve fazer:</b><br>
      __STATUS_WHAT_TO_DO__
    </div>
  </div>

  <div class="card">
    <h2>Para pedir ajuda em outra aba de Claude/Codex</h2>
    <p class="muted">Use os caminhos abaixo no seu prompt — clique em copiar em cada um.</p>

    <div class="path-row">
      <div class="path-label">Pasta desta sessao:</div>
      <div class="path-value">
        <code id="pathSession">__SESSION_DIR__</code>
        <button class="mini-btn" onclick="copyText('pathSession', this)">copiar</button>
      </div>
    </div>

    <div class="path-row">
      <div class="path-label">Handoff do orquestrador (manual fixo):</div>
      <div class="path-value">
        <code id="pathHandoff">C:\\winegod-app\\docs\\ORQUESTRADOR_HANDOFF.md</code>
        <button class="mini-btn" onclick="copyText('pathHandoff', this)">copiar</button>
      </div>
    </div>

    <div class="path-row">
      <div class="path-label">Prompt pronto pra colar em outra IA:</div>
      <textarea id="askPrompt" class="ask-prompt" readonly>Preciso de ajuda investigando uma sessao do Duo Orchestrator.

Leia primeiro o handoff que explica o sistema:
C:\\winegod-app\\docs\\ORQUESTRADOR_HANDOFF.md

Depois leia TODOS os arquivos do diretorio da sessao (em ordem cronologica de mtime, sem assumir nenhuma lista — varra o diretorio completo):
__SESSION_DIR__

Estado atual: __STATE_NAME__
Round atual: __CURRENT_ROUND__
Motivo da pausa (se houver): __PAUSED_REASON_RAW__

Me responda:
1. Em que fase do projeto a sessao esta?
2. O que foi efetivamente produzido no repo? Liste os arquivos.
3. Por que a sessao esta nesse estado? Causa raiz.
4. Qual a proxima acao concreta: esperar retry, intervir, ou fechar?
5. Comando exato para continuar ou fechar:
   - start_dupla.cmd continue __SESSION_NAME__
   - start_dupla.cmd close __SESSION_NAME__</textarea>
      <button class="copy-btn" onclick="copyText('askPrompt', this)">copiar prompt completo</button>
    </div>
  </div>

  <div class="card">
    <h2>Checkpoint mais recente</h2>
    <p class="muted">Arquivo: <code>__CHECKPOINT_NAME__</code></p>
    <p><button class="copy-btn" id="copyBtn" onclick="copyCheckpoint()">Copiar checkpoint completo</button></p>
    <div id="checkpointBody" class="checkpoint-body">Carregando...</div>
  </div>

  <div class="card">
    <h2>Historico de checkpoints</h2>
    __CHECKPOINTS_LIST__
  </div>

  <div class="card small">
    <b>Pasta:</b> <code>__SESSION_DIR__</code><br>
    <b>Claude UUID:</b> <code>__CLAUDE_UUID__</code><br>
    <b>Codex UUID:</b> <code>__CODEX_UUID__</code><br>
    Gerado em __GENERATED_AT__ | viewer V2.3 read-only.
  </div>
</div>

<script>
const CHECKPOINT_MD = __CHECKPOINT_MD_JSON__;

marked.setOptions({breaks: true, gfm: true});
const bodyEl = document.getElementById("checkpointBody");
if (CHECKPOINT_MD && CHECKPOINT_MD.trim()) {
  bodyEl.innerHTML = marked.parse(CHECKPOINT_MD);
} else {
  bodyEl.innerHTML = "<p class='muted'>Nenhum checkpoint ainda. O primeiro sera gerado no round 5 ou em evento critico.</p>";
}

function copyCheckpoint() {
  navigator.clipboard.writeText(CHECKPOINT_MD).then(() => {
    const btn = document.getElementById("copyBtn");
    btn.textContent = "Copiado!";
    btn.classList.add("copied");
    setTimeout(() => {
      btn.textContent = "Copiar checkpoint completo";
      btn.classList.remove("copied");
    }, 2000);
  });
}

function copyText(elemId, btn) {
  const el = document.getElementById(elemId);
  const txt = el.value !== undefined ? el.value : el.textContent;
  navigator.clipboard.writeText(txt).then(() => {
    const original = btn.textContent;
    btn.textContent = "copiado!";
    btn.classList.add("copied");
    setTimeout(() => {
      btn.textContent = original;
      btn.classList.remove("copied");
    }, 1500);
  });
}

// preservar scroll entre auto-refreshes
const KEY = "viewer_scroll_" + location.pathname;
window.addEventListener("beforeunload", () => sessionStorage.setItem(KEY, String(window.scrollY)));
window.addEventListener("load", () => {
  const y = sessionStorage.getItem(KEY);
  if (y) window.scrollTo(0, parseInt(y, 10) || 0);
});
</script>
</body>
</html>
"""

    for k, v in data.items():
        page = page.replace(f"__{k}__", v if isinstance(v, str) else str(v))
    return page


def build(session_id, open_browser=True, mode="dashboard"):
    """V2.3: duas modalidades:
    - mode='dashboard' (default): gera session.html (novo)
    - mode='conversation': gera session_conversation.html (view antiga de bolhas)
    """
    session_dir = find_session_dir(session_id)
    if not session_dir:
        print(f"Sessao nao encontrada: {session_id}")
        print("Sessoes disponiveis:")
        for s in list_sessions():
            print(f"  {s}")
        return 1

    info = session_header_info(session_dir)

    # Sempre gera conversation.html (view antiga, para quem quiser)
    msgs = collect_messages(session_dir)
    log_tail = read_session_log_tail(session_dir)
    conv_html = render_html(session_dir, msgs, info, log_tail)
    conv_path = os.path.join(session_dir, "session_conversation.html")
    with open(conv_path, "w", encoding="utf-8") as f:
        f.write(conv_html)

    # Gera dashboard como session.html (novo padrao)
    state = load_session_state(session_dir)
    ckpt_path, ckpt_name = find_latest_checkpoint(session_dir)
    ckpt_md = ""
    if ckpt_path:
        try:
            with open(ckpt_path, "r", encoding="utf-8", errors="replace") as f:
                ckpt_md = f.read()
        except Exception:
            pass
    all_ckpts = list_checkpoints(session_dir)
    dash_html = render_dashboard(session_dir, info, state, ckpt_md, ckpt_name,
                                 all_ckpts)
    dash_path = os.path.join(session_dir, "session.html")
    with open(dash_path, "w", encoding="utf-8") as f:
        f.write(dash_html)

    target = dash_path if mode == "dashboard" else conv_path
    print(f"Dashboard: {dash_path}")
    print(f"Conversa: {conv_path}")
    print(f"Mensagens (conversa): {len(msgs)}")
    if ckpt_name:
        print(f"Checkpoint ativo: {ckpt_name}")

    if open_browser:
        webbrowser.open("file:///" + target.replace("\\", "/"))
    return 0


def main(argv):
    if len(argv) < 2:
        print("Uso: python session_viewer.py <SESSION_ID> [--no-open] [--conversation]")
        print("")
        print("Sessoes disponiveis:")
        for s in list_sessions():
            print(f"  {s}")
        return 0

    session_id = argv[1]
    open_browser = "--no-open" not in argv
    mode = "conversation" if "--conversation" in argv else "dashboard"
    return build(session_id, open_browser=open_browser, mode=mode)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
