#!/usr/bin/env python3
"""
Duo Orchestrator V1 - Fases 1-5: Bootstrap + CLI + Entendimento + Workflow + Resume.
Sem dependencias externas. Arquivo unico.

Modos de execucao:
  - Normal: valida brief, detecta wt, relanca como --internal dentro da aba Orq.
  - --internal: roda o bootstrap real dentro da aba Orq do Windows Terminal.
  - Fallback: se wt nao existir, roda tudo no terminal atual.
  - --probe-clis <brief>: cria sessao e testa chamada minima a cada CLI.
  - --run-understanding <brief>: cria sessao e executa fase de entendimento.
  - --run-workflow <brief>: executa workflow completo (entendimento + loop).
"""

import os
import sys
import re
import html
import shutil
import unicodedata
import datetime
import subprocess
import json
import signal
import hashlib


# === Constantes ===

SESSIONS_DIR = os.path.join("C:\\winegod-app", "orchestrator_sessions")
LOCK_FILE_NAME = ".duo_orchestrator.lock"
STATE_FILE_NAME = "session-state.json"
DEFAULT_TIMEOUT_S = 1200  # 20 minutos
PROBE_TIMEOUT_S = 120     # 2 minutos para probe
MAX_UNDERSTANDING_ATTEMPTS = 6
MAX_REJECTIONS_PER_ROUND = 3
MAX_WORKFLOW_ROUNDS = 50
VALID_CLAUDE_STATUSES = ["EXECUTED", "READY", "NEEDS_HUMAN", "BLOCKED"]
VALID_CODEX_STATUSES = ["APROVADO", "REPROVADO", "REVISAO_HUMANA"]
VALID_EXEC_STATUSES = ["EXECUTED", "BLOCKED", "NEEDS_HUMAN"]
VALID_REVIEW_STATUSES = ["APROVADO", "REPROVADO", "REVISAO_HUMANA", "CONCLUIDO"]

# === Estados da sessao (V2.3) ===
# A sessao so se fecha por ato humano explicito: Ctrl+C ou comando `close`.
STATE_BOOTSTRAP = "BOOTSTRAP"
STATE_RUNNING = "RUNNING"
STATE_RETRY_BACKOFF = "RETRY_BACKOFF"
STATE_PAUSED_RECOVERABLE = "PAUSED_RECOVERABLE"
STATE_WAITING_HUMAN = "WAITING_HUMAN"
STATE_READY_FOR_HUMAN_CLOSE = "READY_FOR_HUMAN_CLOSE"
STATE_CLOSED_BY_HUMAN = "CLOSED_BY_HUMAN"

# === Estagios do round (V2.4) ===
ROUND_STAGE_BOOTSTRAP = "bootstrap"
ROUND_STAGE_CODEX_PROMPT_SAVED = "codex_prompt_saved"
ROUND_STAGE_CLAUDE_IN_FLIGHT = "claude_in_flight"
ROUND_STAGE_CLAUDE_DONE = "claude_done"
ROUND_STAGE_CODEX_IN_FLIGHT = "codex_in_flight"
ROUND_STAGE_CODEX_DONE = "codex_done"
ROUND_STAGE_WAITING_HUMAN = "waiting_human"
ROUND_STAGE_READY_FOR_CLOSE = "ready_for_close"

# === Confidence gates de recovery (V2.4) ===
RECOVERY_CONFIDENCE_HIGH = "HIGH_CONFIDENCE"
RECOVERY_CONFIDENCE_MEDIUM = "MEDIUM_CONFIDENCE"
RECOVERY_CONFIDENCE_LOW = "LOW_CONFIDENCE"

# === Estrategias de recovery agressivo (V2.5) ===
RECOVERY_STRATEGY_JSONL_EXACT = "jsonl_exact"
RECOVERY_STRATEGY_PARTIAL_TO_CODEX = "partial_to_codex"
RECOVERY_STRATEGY_FILESYSTEM_REBUILD = "filesystem_rebuild"
RECOVERY_STRATEGY_CHECKPOINT_REPROMPT = "checkpoint_reprompt"
RECOVERY_STRATEGY_LAST_PROMPT_REPLAY = "last_prompt_replay"
RECOVERY_STRATEGY_HUMAN_REQUIRED = "human_required"

OPEN_STATES = {
    STATE_BOOTSTRAP, STATE_RUNNING, STATE_RETRY_BACKOFF,
    STATE_PAUSED_RECOVERABLE, STATE_WAITING_HUMAN, STATE_READY_FOR_HUMAN_CLOSE,
}

# === Multi-dupla (V2.6) ===
MULTI_DIR = os.path.join("C:\\winegod-app", ".duo_orchestrator")
REGISTRY_PATH = os.path.join(MULTI_DIR, "registry.json")
MULTI_LOCKS_DIR = os.path.join(MULTI_DIR, "locks")
WORKSPACES_DIR = os.path.join("C:\\winegod-app", "orchestrator_workspaces")
CODEX_BOOTSTRAP_LOCK_PATH = os.path.join(MULTI_DIR, "codex_bootstrap.lock")

WORKSPACE_COPY_EXCLUDES = {
    ".git", "orchestrator_sessions", "orchestrator_workspaces",
    ".duo_orchestrator", "node_modules", ".venv", "venv",
    "__pycache__", ".pytest_cache", ".mypy_cache",
    ".claude", ".codex", ".stfolder",
}

# === Retry backoff (V2.3) ===
# Retry infinito enquanto erro classificado como transitorio.
# Erro desconhecido repetido → pausa sem fechar, aguarda humano.
RETRY_BACKOFF_SCHEDULE_S = [60, 180, 300, 600, 900, 1800]  # 1m, 3m, 5m, 10m, 15m, 30m (teto)
UNKNOWN_ERROR_RETRY_LIMIT = 2  # depois de N tentativas com erro desconhecido, pausa

# === Checkpoints (V2.3) ===
CHECKPOINT_EVERY_N_ROUNDS = 5

# === Classificacao de erros (V2.3) ===
TRANSIENT_ERROR_PATTERNS = [
    r"API Error:\s*5\d{2}",
    r"api_error",
    r"overloaded_error",
    r"rate_limit",
    r"rate[_\s]*limit(?:ed|_error)?",
    r"\b429\b",
    r"\b503\b",
    r"\b502\b",
    r"\b504\b",
    r"internal server error",
    r"ECONNRESET",
    r"ETIMEDOUT",
    r"socket hang up",
    r"EAI_AGAIN",
    r"network error",
]

# === Quota exhaustion (V2.7) ===
# Backoff quando a conta Claude/Anthropic fica sem creditos. Mais longo que
# TRANSIENT porque creditos so voltam quando o humano recarrega OU quando a
# janela de billing reseta. Schedule cresce e fica em 30min forever.
QUOTA_BACKOFF_SCHEDULE_S = [60, 600, 1800]  # 1m, 10m, 30m, depois 30m fixo

# Timeout do health-check ping (chamada minima de "ok" para testar API).
QUOTA_HEALTH_PING_TIMEOUT_S = 30

# Padroes que indicam ESGOTAMENTO DE CREDITOS/QUOTA. Tratados separado de
# TRANSIENT pra usar backoff proprio e health-ping entre tentativas.
QUOTA_ERROR_PATTERNS = [
    r"credit[_\s-]*balance",
    r"insufficient[_\s-]*credit",
    r"out of credits?",
    r"credits? (?:are )?(?:exhausted|depleted)",
    r"quota[_\s-]*exceeded",
    r"quota[_\s-]*exhausted",
    r"\b402\b",
    r"payment[_\s-]*required",
    r"low[_\s-]*balance",
    r"account[_\s-]*balance[_\s-]*too[_\s-]*low",
    r"billing[_\s-]*issue",
]
CREDENTIAL_DISCOVERY_GUIDANCE_TEMPLATE = (
    "Regras de credenciais e ambiente:\n"
    "- Antes de declarar bloqueio por falta de credencial, acesso ou variavel de ambiente, procure primeiro nas fontes locais do projeto.\n"
    "- Verifique variaveis de ambiente ja carregadas e arquivos `.env` relevantes dentro do repositorio atual.\n"
    "- Prioridades de busca neste projeto:\n"
    "  1. ambiente atual do processo\n"
    "{env_search_lines}\n"
    "- Se a tarefa depender de banco, assuma que `DATABASE_URL` pode estar em uma dessas fontes e tente carregar essas fontes antes de bloquear.\n"
    "- Se encontrar a credencial, use-a sem imprimir o valor em logs, respostas ou arquivos.\n"
    "- So responda `STATUS: BLOCKED` ou `STATUS: NEEDS_HUMAN` por credencial depois de tentar essas fontes e explicar objetivamente o que foi procurado."
)


# === Handoff padrao embutido em todos os checkpoints ===
# Texto fixo, igual em toda sessao, que explica o sistema pra um Claude/Codex
# externo que esta sendo chamado pra ajudar a recuperar/continuar a sessao.
HANDOFF_STANDARD = """\
# HANDOFF — DUO ORCHESTRATOR

## O que e este sistema

O Duo Orchestrator e uma ferramenta local (Python stdlib, Windows) que
automatiza o dialogo entre dois agentes de IA trabalhando num projeto:

- **Codex** = administrador (julga, aprova, reprova, manda proximos prompts)
- **Claude** = executor (executa tarefas, edita codigo, responde)

O usuario (humano) define um brief de projeto em markdown. O orquestrador
roda o loop Codex-Claude-Codex-Claude ate o projeto terminar. Nunca fecha
sozinho — so fecha quando o humano explicitamente manda fechar.

## Arquitetura

- Claude: processo longo-vivo com `claude -p --input-format stream-json
  --output-format stream-json --session-id <uuid>`. Zero respawn.
- Codex: respawn por turno via `codex exec resume <uuid>`.
- Loop: texto verbatim vai-e-volta entre os dois, sem orquestrador parsear
  regras de conteudo.
- Sessao: pasta `orchestrator_sessions/S-XXXX-<label>/` com `project.md`,
  `session-state.json`, `claude.log`, `codex.log`, `session.log`,
  `round-NNN-codex.md`, `round-NNN-claude.md`, checkpoints `summary_*.md`.

## Estados da sessao (da `session-state.json`)

- BOOTSTRAP: setup inicial em andamento.
- RUNNING: loop Codex-Claude rodando normal.
- RETRY_BACKOFF: erro transitorio da API, aguardando backoff, retentara
  mesmo prompt na mesma sessao persistente.
- PAUSED_RECOVERABLE: erro desconhecido repetido, pausado aguardando humano
  decidir como continuar.
- WAITING_HUMAN: Codex escreveu HUMANO no texto, pausa aguardando humano.
- READY_FOR_HUMAN_CLOSE: Codex escreveu CONCLUIDO, pronto para humano
  fechar, mas ainda aberto.
- CLOSED_BY_HUMAN: estado terminal. `final-review.md` existe. Lock liberado.

## Recuperacao

O humano fecha com Ctrl+C na aba orquestrador ou rodando
`start_dupla.cmd close S-XXXX` em outra aba.

Retomada padrao:
- `start_dupla.cmd continue S-XXXX`
- Se o processo original ainda estiver vivo, apenas destrava.
- Se o processo morreu, roda reconciliacao automatica com `round_stage`,
  artefatos em disco, JSONL do Claude e `codex exec resume`.

Fallback tecnico explicito:
- `start_dupla.cmd recover S-XXXX`

Confidence gates:
- `HIGH_CONFIDENCE`: resposta faltante encontrada no JSONL â†’ segue sozinho
- `MEDIUM_CONFIDENCE`: estagio claro â†’ tenta `--resume`
- `LOW_CONFIDENCE`: sinais conflitantes â†’ pausa em `PAUSED_RECOVERABLE`

V2.5: baixa confianca nao para por padrao; o sistema tenta recovery
agressivo por filesystem, resposta parcial, checkpoint ou replay seguro.
So pausa se houver decisao humana real, credencial/ambiente ausente,
risco destrutivo ou contexto minimo ausente.

## Como voce (agente externo) pode ajudar

O usuario esta te passando um checkpoint completo de uma sessao que pode
estar pausada, em backoff, aguardando ou travada. O checkpoint tem:
- Este handoff (Secao A)
- Metadados da sessao (Secao B)
- Arquivos provavelmente tocados no repo (Secao C, heuristica)
- Historico condensado dos rounds (Secao D)
- Estado atual + ultima decisao do Codex (Secao E)
- Tails dos logs (Secao F)
- Prompt pronto para te ativar (Secao G)

Leia tudo, entenda o estado, e ajude o usuario a decidir o proximo passo.
"""



# === Utilidades ===

def timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(filepath, message):
    """Escreve mensagem com timestamp no log e imprime no terminal."""
    line = f"[{timestamp()}] {message}"
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


# === Multi-dupla helpers (V2.6) ===


def _load_registry():
    """Carrega registry.json; retorna dict vazio se nao existir.

    V2.8: registry e CACHE, NAO fonte de verdade. Callers que precisam de
    estado confiavel devem usar `rebuild_registry_from_sessions()` primeiro
    OU ler session-state.json diretamente via `list_all_sessions()`.
    """
    if not os.path.isfile(REGISTRY_PATH):
        return {"sessions": {}}
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "sessions" not in data:
            data["sessions"] = {}
        return data
    except Exception as e:
        # V2.8: loga erro em vez de engolir silenciosamente
        try:
            print(f"AVISO: registry.json corrompido ou ilegivel ({e}); "
                  f"retornando cache vazio. Sera reconstruido na proxima list/status.")
        except Exception:
            pass
        return {"sessions": {}}


def _save_registry(data):
    """Salva registry.json atomicamente."""
    os.makedirs(MULTI_DIR, exist_ok=True)
    tmp = REGISTRY_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if os.path.exists(REGISTRY_PATH):
            os.replace(tmp, REGISTRY_PATH)
        else:
            os.rename(tmp, REGISTRY_PATH)
    except Exception as e:
        # V2.8: loga erro em vez de engolir silenciosamente
        try:
            print(f"AVISO: nao salvou registry.json ({e}). "
                  f"Sera reconstruido na proxima list/status.")
        except Exception:
            pass
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def rebuild_registry_from_sessions():
    """V2.8: reconstroi registry.json a partir dos session-state.json reais.

    Fonte de verdade: os arquivos `session-state.json` de cada sessao em
    `orchestrator_sessions/`. Registry e so cache rapido.

    Chamar este helper toda vez que houver duvida de consistencia (list,
    status, dashboard global, ou recovery pos-crash).

    Retorna o dict reconstruido e ja salvo.
    """
    rebuilt = {"sessions": {}}
    if not os.path.isdir(SESSIONS_DIR):
        _save_registry(rebuilt)
        return rebuilt

    for entry in os.listdir(SESSIONS_DIR):
        session_dir = os.path.join(SESSIONS_DIR, entry)
        if not os.path.isdir(session_dir):
            continue
        m = re.match(r"^(S-\d{4})", entry)
        if not m:
            continue
        sid = m.group(1)
        state_path = os.path.join(session_dir, STATE_FILE_NAME)
        if not os.path.isfile(state_path):
            continue
        try:
            with open(state_path, "r", encoding="utf-8-sig") as f:
                sdata = json.load(f)
        except Exception as e:
            try:
                print(f"AVISO: session-state.json corrompido em {sid}: {e}")
            except Exception:
                pass
            continue
        rebuilt["sessions"][sid] = {
            "session_id": sid,
            "run_label": sdata.get("run_label"),
            "state": sdata.get("state"),
            "current_round": sdata.get("current_round", 0),
            "last_successful_round": sdata.get("last_successful_round", 0),
            "round_stage": sdata.get("round_stage"),
            "last_heartbeat": sdata.get("last_heartbeat"),
            "last_jsonl_mtime": sdata.get("last_jsonl_mtime"),
            "active_call_status": sdata.get("active_call_status"),
            "orchestrator_pid": sdata.get("orchestrator_pid"),
            "started_at": sdata.get("started_at"),
            "multi_mode": sdata.get("multi_mode"),
            "workspace_path": sdata.get("workspace_path"),
            "workspace_mode": sdata.get("workspace_mode"),
            "quota_attempt": sdata.get("quota_attempt", 0),
            "_rebuilt_at": datetime.datetime.now().isoformat(),
        }
    _save_registry(rebuilt)
    return rebuilt


def registry_update_session(session_id, info_dict):
    """Cria ou atualiza entrada no registry global. Thread-safe para uso sequencial."""
    data = _load_registry()
    if session_id not in data["sessions"]:
        data["sessions"][session_id] = {}
    data["sessions"][session_id].update(info_dict)
    data["sessions"][session_id]["last_heartbeat"] = datetime.datetime.now().isoformat()
    _save_registry(data)


def registry_remove_session(session_id):
    data = _load_registry()
    data["sessions"].pop(session_id, None)
    _save_registry(data)


def _create_multi_lock(session_id):
    """Cria lock por sessao em .duo_orchestrator/locks/. Retorna path."""
    os.makedirs(MULTI_LOCKS_DIR, exist_ok=True)
    lock_path = os.path.join(MULTI_LOCKS_DIR, f"{session_id}.lock")
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "session_id": session_id,
            "pid": os.getpid(),
            "created_at": datetime.datetime.now().isoformat(),
        }, indent=2))
    return lock_path


def _remove_multi_lock(session_id):
    lock_path = os.path.join(MULTI_LOCKS_DIR, f"{session_id}.lock")
    try:
        if os.path.isfile(lock_path):
            os.remove(lock_path)
    except Exception:
        pass


def _acquire_codex_bootstrap_lock(timeout_s=120):
    """Lock curto para bootstrap do Codex (evita captura de UUID errado).

    Usa file-based lock simples com retry. Retorna True se adquirido.
    """
    import time as _time
    os.makedirs(MULTI_DIR, exist_ok=True)
    start = _time.time()
    while _time.time() - start < timeout_s:
        try:
            fd = os.open(CODEX_BOOTSTRAP_LOCK_PATH,
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({
                "pid": os.getpid(),
                "at": datetime.datetime.now().isoformat(),
            }).encode("utf-8"))
            os.close(fd)
            return True
        except FileExistsError:
            # Verifica se lock eh stale (PID morto ou > 5 min)
            try:
                age = _time.time() - os.path.getmtime(CODEX_BOOTSTRAP_LOCK_PATH)
                if age > 300:  # 5 min = stale
                    os.remove(CODEX_BOOTSTRAP_LOCK_PATH)
                    continue
            except Exception:
                pass
            _time.sleep(1)
        except Exception:
            _time.sleep(1)
    return False


def _release_codex_bootstrap_lock():
    try:
        if os.path.isfile(CODEX_BOOTSTRAP_LOCK_PATH):
            os.remove(CODEX_BOOTSTRAP_LOCK_PATH)
    except Exception:
        pass


def _can_use_git_worktree(repo_path):
    """Verifica se eh seguro usar git worktree.

    Retorna False se:
    - nao eh git repo
    - ha untracked files relevantes (fora de excludes)
    - ha staged changes
    """
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain", "-u"],
            capture_output=True, encoding="utf-8", errors="replace",
            cwd=repo_path, timeout=30,
        )
        if r.returncode != 0:
            return False
        lines = [l for l in (r.stdout or "").strip().splitlines() if l.strip()]
        for line in lines:
            status = line[:2]
            filepath = line[3:].strip().strip('"')
            # Ignora arquivos em pastas excluidas
            top = filepath.split("/")[0].split("\\")[0]
            if top in WORKSPACE_COPY_EXCLUDES:
                continue
            # Qualquer untracked ou modified fora de excludes = nao seguro
            if status.strip():
                return False
        return True
    except Exception:
        return False


def _prepare_multi_workspace(base_repo_path, session_id, label, mode="auto"):
    """Cria workspace isolado para sessao multi.

    mode="auto": tenta git worktree, fallback para copia.
    mode="git_worktree": forca git worktree (falha se nao seguro).
    mode="copy_workspace": forca copia.

    Retorna (workspace_path, workspace_mode).
    """
    label_norm = normalize_label(label)
    ws_name = f"{session_id}-{label_norm}"
    workspace_path = os.path.join(WORKSPACES_DIR, ws_name)

    if os.path.exists(workspace_path):
        raise RuntimeError(f"Workspace ja existe: {workspace_path}")

    os.makedirs(WORKSPACES_DIR, exist_ok=True)

    use_worktree = False
    if mode == "git_worktree":
        use_worktree = True
    elif mode == "auto":
        use_worktree = _can_use_git_worktree(base_repo_path)

    if use_worktree:
        branch_name = f"duo/{session_id}-{label_norm}"
        try:
            r = subprocess.run(
                ["git", "worktree", "add", workspace_path, "-b", branch_name],
                capture_output=True, encoding="utf-8", errors="replace",
                cwd=base_repo_path, timeout=60,
            )
            if r.returncode == 0:
                return workspace_path, "git_worktree"
        except Exception:
            pass
        # Se worktree falhou e mode era auto, faz fallback
        if mode == "git_worktree":
            raise RuntimeError(
                f"git worktree falhou: {r.stderr if 'r' in dir() else 'exception'}")

    # Copia de workspace
    _copy_workspace(base_repo_path, workspace_path)
    return workspace_path, "copy_workspace"


def _copy_workspace(src, dst):
    """Copia workspace excluindo pastas/arquivos proibidos."""
    os.makedirs(dst, exist_ok=True)
    src_abs = os.path.abspath(src)
    dst_abs = os.path.abspath(dst)
    for item in os.listdir(src_abs):
        if item in WORKSPACE_COPY_EXCLUDES:
            continue
        s = os.path.join(src_abs, item)
        d = os.path.join(dst_abs, item)
        # Evita copiar para dentro de si mesmo
        if os.path.abspath(s) == dst_abs or d.startswith(s + os.sep):
            continue
        try:
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=False,
                                ignore=shutil.ignore_patterns(
                                    *WORKSPACE_COPY_EXCLUDES))
            else:
                shutil.copy2(s, d)
        except Exception as exc:
            # Nao falha por um arquivo individual que nao conseguiu copiar
            print(f"AVISO: nao copiou {s}: {exc}")


def _adapt_brief_for_multi(original_brief_path, session_dir, workspace_path,
                           workspace_mode, base_repo_path):
    """Cria copia do brief adaptada para modo multi.

    Troca REPO_PATH pela workspace isolada e adiciona campos MULTI_MODE,
    BASE_REPO_PATH, WORKSPACE_MODE.

    Retorna path do brief adaptado.
    """
    with open(original_brief_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    adapted_path = os.path.join(session_dir, "project.multi.md")

    # Troca REPO_PATH
    lines = content.splitlines(keepends=True)
    new_lines = []
    repo_path_replaced = False
    for line in lines:
        m = re.match(r"^REPO_PATH\s*:\s*(.+)$", line.rstrip())
        if m and not repo_path_replaced:
            new_lines.append(f"REPO_PATH: {workspace_path}\n")
            new_lines.append(f"BASE_REPO_PATH: {base_repo_path}\n")
            new_lines.append(f"WORKSPACE_MODE: {workspace_mode}\n")
            new_lines.append(f"MULTI_MODE: true\n")
            repo_path_replaced = True
        else:
            new_lines.append(line if line.endswith("\n") else line + "\n")

    with open(adapted_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return adapted_path


def _safe_read_text(path, max_chars=None):
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if max_chars is None:
                return f.read()
            return f.read(max_chars)
    except Exception:
        return ""


def _extract_run_label_from_name(name):
    parts = (name or "").split("-", 2)
    return parts[2] if len(parts) >= 3 else (name or "")


def _extract_run_label_from_project(session_dir, fallback=""):
    for filename in ("project.md", "project.multi.md"):
        content = _safe_read_text(os.path.join(session_dir, filename), max_chars=4000)
        if not content:
            continue
        for line in content.splitlines():
            if line.startswith("RUN_LABEL:"):
                return line.split(":", 1)[1].strip() or fallback
    return fallback


def _highest_round_in_session(session_dir):
    try:
        names = os.listdir(session_dir)
    except Exception:
        return 0
    highest = 0
    for name in names:
        m = re.match(r"^round-(\d{3})-", name)
        if not m:
            continue
        highest = max(highest, int(m.group(1)))
    return highest


def _session_num_value(session_id):
    m = re.search(r"S-(\d{4})", session_id or "")
    return int(m.group(1)) if m else -1


def _parse_final_review_metadata(session_dir):
    path = os.path.join(session_dir, "final-review.md")
    content = _safe_read_text(path, max_chars=6000)
    meta = {
        "status": "",
        "rounds": 0,
        "reason": "",
        "exists": bool(content),
    }
    if not content:
        return meta
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Status final:"):
            meta["status"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("## Rounds executados:"):
            rounds_txt = stripped.split(":", 1)[1].strip()
            try:
                meta["rounds"] = int(rounds_txt)
            except Exception:
                pass
        elif stripped.startswith("## Motivo de parada:"):
            meta["reason"] = stripped.split(":", 1)[1].strip()
    return meta


def _infer_legacy_state_from_log(session_dir):
    log_text = _safe_read_text(os.path.join(session_dir, "session.log"), max_chars=12000)
    if not log_text:
        return "LEGACY_SEM_ESTADO", ""
    lower = log_text.lower()
    tail_lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    last_line = tail_lines[-1] if tail_lines else ""
    if "workflow concluido" in lower:
        return "CONCLUIDO", last_line
    if "revisao_humana" in lower:
        return "REVISAO_HUMANA", last_line
    if "interrompido" in lower:
        return "INTERROMPIDO", last_line
    if "travou" in lower or "timeout" in lower or "erro" in lower:
        return "LEGACY_INCOMPLETE", last_line
    return "LEGACY_INCOMPLETE", last_line


def _session_bucket(state):
    state = (state or "").upper()
    if state in (
        STATE_PAUSED_RECOVERABLE,
        STATE_WAITING_HUMAN,
        STATE_RETRY_BACKOFF,
        "REVISAO_HUMANA",
        "INTERROMPIDO",
        "LEGACY_INCOMPLETE",
        "LEGACY_SEM_ESTADO",
    ):
        return "attention"
    if state in (STATE_RUNNING, STATE_BOOTSTRAP):
        return "running"
    if state == STATE_READY_FOR_HUMAN_CLOSE:
        return "finalizing"
    if state in (STATE_CLOSED_BY_HUMAN, "CONCLUIDO"):
        return "done"
    return "other"


def _session_bucket_priority(bucket):
    return {
        "running": 0,
        "attention": 1,
        "finalizing": 2,
        "done": 3,
        "other": 4,
    }.get(bucket, 99)


def _session_bucket_label(bucket):
    return {
        "attention": "Incompleta",
        "running": "Rodando",
        "finalizing": "Pronta para fechar",
        "done": "Concluida",
        "other": "Outro",
    }.get(bucket, "Outro")


def _session_state_label(state):
    return {
        STATE_BOOTSTRAP: "Bootstrap",
        STATE_RUNNING: "Running",
        STATE_RETRY_BACKOFF: "Retry",
        STATE_PAUSED_RECOVERABLE: "Pausada",
        STATE_WAITING_HUMAN: "Aguardando humano",
        STATE_READY_FOR_HUMAN_CLOSE: "Pronta para fechar",
        STATE_CLOSED_BY_HUMAN: "Fechada",
        "REVISAO_HUMANA": "Revisao humana",
        "INTERROMPIDO": "Interrompida",
        "CONCLUIDO": "Concluida",
        "LEGACY_INCOMPLETE": "Legado incompleto",
        "LEGACY_SEM_ESTADO": "Sem estado",
    }.get(state, state or "?")


def _session_color(state, bucket):
    state = (state or "").upper()
    if state == STATE_WAITING_HUMAN:
        return "#2563eb"
    if state == STATE_READY_FOR_HUMAN_CLOSE:
        return "#7c3aed"
    if bucket == "attention":
        return "#dc2626"
    if bucket == "running":
        return "#15803d"
    if bucket == "finalizing":
        return "#7c3aed"
    if bucket == "done":
        return "#64748b"
    return "#9ca3af"


def _session_note_from_state(data):
    for key in ("paused_reason", "recovery_note", "recovered_from"):
        value = (data or {}).get(key)
        if value:
            return str(value).strip()
    return ""


def _parse_iso_ts(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.datetime.fromisoformat(text)
    except Exception:
        return None
    now = datetime.datetime.now(dt.tzinfo) if dt.tzinfo else datetime.datetime.now()
    return max(0, int((now - dt).total_seconds()))


def _parse_epoch_age(value):
    try:
        ts = float(value or 0)
    except Exception:
        return None
    if ts <= 0:
        return None
    now_ts = datetime.datetime.now().timestamp()
    return max(0, int(now_ts - ts))


def _format_age_short(seconds):
    try:
        total = int(seconds)
    except Exception:
        return ""
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def _assess_runtime_health(data):
    state = ((data or {}).get("state") or "").upper()
    result = {
        "bucket": None,
        "bucket_label": None,
        "state_label": None,
        "state_color": None,
        "note": "",
        "suggested_action": "",
    }
    if state not in (STATE_RUNNING, STATE_BOOTSTRAP):
        return result

    pid_alive = _process_alive((data or {}).get("orchestrator_pid"))
    heartbeat_age = _parse_iso_ts((data or {}).get("last_heartbeat"))
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
        now_ts = datetime.datetime.now().timestamp()
        signal_age = max(0, int(now_ts - signal_ref))

    if not pid_alive:
        note = "Processo do orquestrador nao esta vivo."
        if heartbeat_age is not None:
            note += f" Ultimo heartbeat ha {_format_age_short(heartbeat_age)}."
        note += " Acao: Continue."
        result.update({
            "bucket": "attention",
            "bucket_label": "Parada",
            "state_label": "Processo morto",
            "state_color": "#dc2626",
            "note": note,
            "suggested_action": "Continue",
        })
        return result

    if active_agent == "claude" and call_age is not None and signal_age is not None and signal_age > 600:
        action = "Recover" if signal_age > 1800 else "Observe"
        note = (
            f"Processo vivo, mas Claude sem sinal novo ha {_format_age_short(signal_age)}"
            f" nesta call"
        )
        if heartbeat_age is not None:
            note += f" (heartbeat {_format_age_short(heartbeat_age)})."
        else:
            note += "."
        if action == "Recover":
            note += " Acao: Recover."
        else:
            note += " Acao: Observe; se continuar assim, use Recover."
        result.update({
            "bucket": "attention",
            "bucket_label": "Vivo, mas parado",
            "state_label": "Sem sinal",
            "state_color": "#d97706",
            "note": note,
            "suggested_action": action,
        })
        return result

    if heartbeat_age is not None and heartbeat_age > 180:
        action = "Recover" if heartbeat_age > 600 else "Observe"
        note = (
            f"Processo vivo, mas sem heartbeat novo ha {_format_age_short(heartbeat_age)}."
        )
        if action == "Recover":
            note += " Acao: Recover."
        else:
            note += " Acao: Observe; se continuar assim, use Recover."
        result.update({
            "bucket": "attention",
            "bucket_label": "Vivo, mas parado",
            "state_label": "Sem heartbeat",
            "state_color": "#d97706",
            "note": note,
            "suggested_action": action,
        })
        return result

    return result


def _build_session_record(name, session_dir):
    m = re.match(r"^(S-\d{4})", name)
    if not m:
        return None
    session_id = m.group(1)
    state_path = os.path.join(session_dir, STATE_FILE_NAME)
    viewer_path = os.path.join(session_dir, "session.html")
    viewer_relpath = f"{name}/session.html" if os.path.isfile(viewer_path) else ""
    if os.path.isfile(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        state = data.get("state", "?")
        run_label = data.get("run_label", "") or _extract_run_label_from_project(
            session_dir, _extract_run_label_from_name(name)
        )
        current_round = int(data.get("current_round", 0) or 0)
        note = _session_note_from_state(data)
        bucket = _session_bucket(state)
        runtime_health = _assess_runtime_health(data)
        if runtime_health.get("bucket"):
            bucket = runtime_health["bucket"]
        if runtime_health.get("note"):
            note = runtime_health["note"]
        bucket_label = runtime_health.get("bucket_label") or _session_bucket_label(bucket)
        state_label = runtime_health.get("state_label") or _session_state_label(state)
        state_color = runtime_health.get("state_color") or _session_color(state, bucket)
        return {
            "session_id": data.get("session_id", session_id),
            "session_name": name,
            "run_label": run_label,
            "state": state,
            "current_round": current_round,
            "workspace_mode": data.get("workspace_mode", "single"),
            "multi_mode": bool(data.get("multi_mode", False)),
            "workspace_path": data.get("workspace_path", ""),
            "session_dir": session_dir,
            "has_state": True,
            "viewer_relpath": viewer_relpath,
            "dashboard_bucket": bucket,
            "dashboard_bucket_label": bucket_label,
            "state_label": state_label,
            "state_color": state_color,
            "note": note,
            "suggested_action": runtime_health.get("suggested_action", ""),
        }

    review_meta = _parse_final_review_metadata(session_dir)
    state = review_meta["status"] or ""
    note = review_meta["reason"] or ""
    if not state:
        state, inferred_note = _infer_legacy_state_from_log(session_dir)
        note = note or inferred_note
    run_label = _extract_run_label_from_project(session_dir, _extract_run_label_from_name(name))
    current_round = review_meta["rounds"] or _highest_round_in_session(session_dir)
    bucket = _session_bucket(state)
    return {
        "session_id": session_id,
        "session_name": name,
        "run_label": run_label,
        "state": state,
        "current_round": current_round,
        "workspace_mode": "legacy",
        "multi_mode": False,
        "workspace_path": "",
        "session_dir": session_dir,
        "has_state": False,
        "viewer_relpath": viewer_relpath,
        "dashboard_bucket": bucket,
        "dashboard_bucket_label": _session_bucket_label(bucket),
        "state_label": _session_state_label(state),
        "state_color": _session_color(state, bucket),
        "note": note,
    }


def _session_sort_key(session):
    return (
        _session_bucket_priority(session.get("dashboard_bucket")),
        -_session_num_value(session.get("session_id")),
    )


def list_all_sessions():
    """Lista todas as sessoes conhecidas, incluindo legados."""
    results = []
    if not os.path.isdir(SESSIONS_DIR):
        return results
    for name in sorted(os.listdir(SESSIONS_DIR)):
        session_dir = os.path.join(SESSIONS_DIR, name)
        if not os.path.isdir(session_dir):
            continue
        record = _build_session_record(name, session_dir)
        if record:
            results.append(record)
    results.sort(key=_session_sort_key)
    return results


def format_session_list(sessions):
    """Formata lista de sessoes para stdout."""
    if not sessions:
        return "Nenhuma sessao encontrada."
    lines = []
    header = f"{'SID':<10} {'Estado':<25} {'Round':>6}   {'Label':<25} {'Workspace'}"
    lines.append(header)
    lines.append("-" * len(header))
    for s in sessions:
        ws = s.get("workspace_mode", "single")
        lines.append(
            f"{s['session_id']:<10} {s['state']:<25} {s['current_round']:>6}   "
            f"{s['run_label']:<25} {ws}"
        )
    return "\n".join(lines)


def generate_index_html():
    """Gera orchestrator_sessions/index.html com links para cada session.html."""
    sessions = list_all_sessions()
    rows = []
    for s in sessions:
        sid = s["session_id"]
        label = s["run_label"]
        state = s["state"]
        rd = s["current_round"]
        ws = s.get("workspace_mode", "single")
        mm = "multi" if s.get("multi_mode") else "single"
        link = f'{sid}-{normalize_label(label)}/session.html'
        color = {
            "RUNNING": "#22c55e",
            "RETRY_BACKOFF": "#f59e0b",
            "PAUSED_RECOVERABLE": "#ef4444",
            "WAITING_HUMAN": "#a855f7",
            "READY_FOR_HUMAN_CLOSE": "#3b82f6",
            "CLOSED_BY_HUMAN": "#6b7280",
            "BOOTSTRAP": "#06b6d4",
        }.get(state, "#999")
        rows.append(
            f'<tr>'
            f'<td><a href="{link}">{sid}</a></td>'
            f'<td><span style="color:{color};font-weight:bold">{state}</span></td>'
            f'<td>{rd}</td>'
            f'<td>{label}</td>'
            f'<td>{mm}</td>'
            f'<td>{ws}</td>'
            f'</tr>'
        )
    table_rows = "\n".join(rows)
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Duo Orchestrator — Todas as Sessoes</title>
<meta http-equiv="refresh" content="10">
<style>
body {{ font-family: system-ui, sans-serif; padding: 20px; background: #0a0a0a; color: #e5e5e5; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #333; }}
th {{ background: #1a1a1a; color: #888; text-transform: uppercase; font-size: 12px; }}
a {{ color: #3b82f6; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
h1 {{ font-size: 20px; color: #ccc; }}
</style>
</head>
<body>
<h1>Duo Orchestrator — Todas as Sessoes</h1>
<p style="color:#888">Auto-refresh a cada 10s</p>
<table>
<tr><th>Sessao</th><th>Estado</th><th>Round</th><th>Label</th><th>Modo</th><th>Workspace</th></tr>
{table_rows}
</table>
</body>
</html>"""
    out_path = os.path.join(SESSIONS_DIR, "index.html")
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def generate_index_html():
    """Gera orchestrator_sessions/index.html com ordem operacional e acoes."""
    # V2.8: mantem registry.json em dia com o disco (cheap).
    try:
        rebuild_registry_from_sessions()
    except Exception:
        pass
    sessions = list_all_sessions()
    rows = []
    cmd_prefix = r"C:\winegod-app\start_dupla.cmd"
    for s in sessions:
        sid = s["session_id"]
        label = s.get("run_label") or "-"
        state = s.get("state") or "?"
        rd = s.get("current_round", 0)
        ws = s.get("workspace_mode", "single")
        mode = "multi" if s.get("multi_mode") else "single"
        note = s.get("note") or ""
        viewer_relpath = s.get("viewer_relpath") or ""
        has_state = bool(s.get("has_state"))
        can_resume = has_state and state != STATE_CLOSED_BY_HUMAN
        viewer_html = (
            f'<a class="open-link" href="{html.escape(viewer_relpath)}">Abrir session.html</a>'
            if viewer_relpath else
            '<span class="muted">sem session.html</span>'
        )

        def _action_button(label_text, command_text, enabled=True, tone="default"):
            cls = f"action-btn {tone}"
            if not enabled:
                return f'<button class="{cls}" disabled>{html.escape(label_text)}</button>'
            return (
                f'<button class="{cls}" '
                f'data-command="{html.escape(command_text)}" '
                f'onclick="copyCommand(this)">'
                f'{html.escape(label_text)}'
                f'</button>'
            )

        actions_html = " ".join([
            _action_button("Continue", fr"{cmd_prefix} continue {sid}", enabled=can_resume, tone="continue"),
            _action_button("Recover", fr"{cmd_prefix} recover {sid}", enabled=can_resume, tone="recover"),
            _action_button("Close", fr"{cmd_prefix} close {sid}", enabled=True, tone="close"),
        ])
        suggested_action = (s.get("suggested_action") or "").strip()
        suggested_html = (
            f'<div class="muted"><b>Acao sugerida:</b> {html.escape(suggested_action)}</div>'
            if suggested_action else ""
        )

        note_html = html.escape(note) if note else '<span class="muted">sem observacao</span>'
        session_name = html.escape(s.get("session_name", sid))
        rows.append(
            f'<tr class="row-{html.escape(s.get("dashboard_bucket", "other"))}">'
            f'<td>'
            f'  <div class="session-id">{html.escape(sid)}</div>'
            f'  <div class="session-path">{session_name}</div>'
            f'</td>'
            f'<td>'
            f'  <span class="bucket-chip" style="--chip:{html.escape(s.get("state_color", "#999"))}">{html.escape(s.get("dashboard_bucket_label", "Outro"))}</span>'
            f'  <div class="state-raw">{html.escape(s.get("state_label", state))} <span class="muted">[{html.escape(state)}]</span></div>'
            f'</td>'
            f'<td>{rd}</td>'
            f'<td>'
            f'  <div>{html.escape(label)}</div>'
            f'  <div class="muted">modo {html.escape(mode)} / {html.escape(ws)}</div>'
            f'</td>'
            f'<td>{note_html}</td>'
            f'<td class="actions">{suggested_html}{actions_html}</td>'
            f'<td>{viewer_html}</td>'
            f'</tr>'
        )

    table_rows = "\n".join(rows) if rows else (
        '<tr><td colspan="7" class="muted">Nenhuma sessao encontrada.</td></tr>'
    )
    counts = {
        "attention": sum(1 for s in sessions if s.get("dashboard_bucket") == "attention"),
        "running": sum(1 for s in sessions if s.get("dashboard_bucket") == "running"),
        "finalizing": sum(1 for s in sessions if s.get("dashboard_bucket") == "finalizing"),
        "done": sum(1 for s in sessions if s.get("dashboard_bucket") == "done"),
    }
    html_doc = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Duo Orchestrator - Dashboard Geral</title>
<meta http-equiv="refresh" content="10">
<style>
:root {{
  --bg: #f4efe6;
  --panel: #fffdf9;
  --ink: #1f2937;
  --muted: #6b7280;
  --line: #ddd6c8;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  padding: 24px;
  background:
    radial-gradient(circle at top right, rgba(15,118,110,0.10), transparent 30%),
    linear-gradient(180deg, #f7f3eb 0%, var(--bg) 100%);
  color: var(--ink);
  font-family: Georgia, "Segoe UI", serif;
}}
.shell {{ max-width: 1500px; margin: 0 auto; }}
.hero {{
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 18px;
  margin-bottom: 20px;
}}
.panel {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 18px 20px;
  box-shadow: 0 10px 30px rgba(31,41,55,0.06);
}}
h1 {{ margin: 0 0 8px 0; font-size: 32px; line-height: 1.05; }}
.subtitle {{ margin: 0; color: var(--muted); font-family: "Segoe UI", sans-serif; font-size: 14px; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
.summary-card {{ background: #f8f4ec; border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; }}
.summary-card b {{ display: block; font-size: 28px; margin-bottom: 4px; }}
.summary-card span {{ color: var(--muted); font-family: "Segoe UI", sans-serif; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
.legend {{ margin-top: 14px; font-family: "Segoe UI", sans-serif; color: var(--muted); font-size: 13px; }}
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 18px; overflow: hidden; }}
th, td {{ padding: 14px 16px; text-align: left; vertical-align: top; border-bottom: 1px solid #ece5d9; }}
th {{ background: #f1eadf; color: #4b5563; font-family: "Segoe UI", sans-serif; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }}
tr:last-child td {{ border-bottom: none; }}
.row-attention {{ background: rgba(254,242,242,0.85); }}
.row-running {{ background: rgba(240,253,250,0.75); }}
.row-finalizing {{ background: rgba(245,243,255,0.65); }}
.row-done {{ background: rgba(248,250,252,0.75); }}
.session-id {{ font-weight: 700; font-size: 16px; font-family: "Segoe UI", sans-serif; }}
.session-path, .state-raw, .muted {{ color: var(--muted); font-family: "Segoe UI", sans-serif; font-size: 12px; }}
.bucket-chip {{
  --chip: #999;
  display: inline-block;
  padding: 5px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--chip) 12%, white);
  color: var(--chip);
  border: 1px solid color-mix(in srgb, var(--chip) 30%, white);
  font-family: "Segoe UI", sans-serif;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .04em;
  margin-bottom: 6px;
}}
.actions {{ min-width: 280px; }}
.action-btn, .open-link {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 86px;
  margin: 0 6px 6px 0;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink);
  text-decoration: none;
  cursor: pointer;
  font-family: "Segoe UI", sans-serif;
  font-size: 13px;
  font-weight: 600;
}}
.action-btn.continue {{ border-color: #93c5fd; background: #eff6ff; }}
.action-btn.recover {{ border-color: #99f6e4; background: #ecfeff; }}
.action-btn.close {{ border-color: #fecaca; background: #fef2f2; }}
.action-btn:disabled {{ cursor: not-allowed; opacity: .45; }}
.action-btn.copied {{ background: #dcfce7; border-color: #86efac; }}
.open-link {{ border-color: #cbd5e1; background: #f8fafc; }}
code {{ background: #f3ede2; padding: 2px 6px; border-radius: 6px; }}
@media (max-width: 1100px) {{
  .hero {{ grid-template-columns: 1fr; }}
  .summary-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}
@media (max-width: 760px) {{
  body {{ padding: 14px; }}
  .summary-grid {{ grid-template-columns: 1fr 1fr; }}
  th:nth-child(4), td:nth-child(4),
  th:nth-child(5), td:nth-child(5) {{ display: none; }}
}}
</style>
</head>
<body>
<div class="shell">
  <div class="hero">
    <div class="panel">
      <h1>Dashboard dos Orquestradores</h1>
      <p class="subtitle">Ordenacao operacional: rodando primeiro, depois incompletas, depois prontas para fechar, e concluidas por ultimo.</p>
      <div class="legend">
        Os botoes <b>Continue</b>, <b>Recover</b> e <b>Close</b> copiam o comando exato.
        Navegador local nao executa <code>.cmd</code> diretamente com confiabilidade.
      </div>
    </div>
    <div class="panel">
      <div class="summary-grid">
        <div class="summary-card"><b>{counts['attention']}</b><span>Incompletas</span></div>
        <div class="summary-card"><b>{counts['running']}</b><span>Rodando</span></div>
        <div class="summary-card"><b>{counts['finalizing']}</b><span>Prontas para fechar</span></div>
        <div class="summary-card"><b>{counts['done']}</b><span>Concluidas</span></div>
      </div>
      <div class="legend">Auto-refresh a cada 10s. Total de sessoes listadas: <b>{len(sessions)}</b>.</div>
    </div>
  </div>
  <div class="table-wrap">
    <table>
      <tr>
        <th>Sessao</th>
        <th>Status</th>
        <th>Round</th>
        <th>Projeto</th>
        <th>Observacao</th>
        <th>Acoes</th>
        <th>Pagina</th>
      </tr>
      {table_rows}
    </table>
  </div>
</div>
<script>
function copyCommand(btn) {{
  const cmd = btn.dataset.command || "";
  if (!cmd) return;
  navigator.clipboard.writeText(cmd).then(() => {{
    const original = btn.textContent;
    btn.textContent = "Copiado";
    btn.classList.add("copied");
    setTimeout(() => {{
      btn.textContent = original;
      btn.classList.remove("copied");
    }}, 1400);
  }});
}}
</script>
</body>
</html>"""
    out_path = os.path.join(SESSIONS_DIR, "index.html")
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return out_path


# === SessionState (V2.3) ===

class SessionState:
    """Persiste estado da sessao em `<pasta-sessao>/session-state.json`.

    Estado e escrito atomicamente em transicoes importantes. Lock tambem e
    atualizado em espelho para que ferramentas externas (e o comando
    continue/close) possam inspecionar sem abrir a pasta da sessao.
    """

    def __init__(self, session_dir):
        self.session_dir = session_dir
        self.path = os.path.join(session_dir, STATE_FILE_NAME)
        self.data = {
            "session_id": None,
            "run_label": None,
            "state": STATE_BOOTSTRAP,
            "current_round": 0,
            "round_num": 0,
            "round_stage": ROUND_STAGE_BOOTSTRAP,
            "last_successful_round": 0,
            "retry_count": 0,
            "unknown_error_count": 0,
            "next_retry_at": None,
            "paused_reason": None,
            "claude_session_uuid": None,
            "codex_session_uuid": None,
            "started_at": None,
            "last_heartbeat": None,
            "last_transition_at": None,
            "orchestrator_pid": None,
            "codex_prompt_hash": None,
            "claude_reply_hash": None,
            "codex_reply_hash": None,
            "recovery_mode": None,
            "recovered_from": None,
            "recovery_at": None,
            "recovery_confidence": None,
            "recovery_strategy": None,
            "recovery_note": None,
            "recovery_attempts": 0,
            "last_recovery_error": None,
            # V2.3 hotfix: observabilidade de call longa (atualizado em send())
            "active_agent": None,          # "claude" enquanto send() esta ativo
            "active_call_status": None,    # "in_call" (< RECENT_ACTIVITY_S) ou "long_running" (>= 10 min)
            "active_call_started_at": None,
            "last_stream_event_at": None,
            "last_jsonl_mtime": None,
            # V2.7: quota esgotada — backoff autonomo com health-ping.
            "quota_attempt": 0,           # 0 = sem quota; >0 = em backoff de quota
            "quota_since": None,          # ISO timestamp do primeiro hit de QUOTA
            "quota_last_error": None,     # ultima mensagem de erro (truncada)
            "quota_next_ping_at": None,   # ISO timestamp do proximo health-ping
        }

    def load(self):
        if not os.path.isfile(self.path):
            return False
        try:
            with open(self.path, "r", encoding="utf-8-sig") as f:
                self.data.update(json.load(f))
            return True
        except Exception:
            return False

    def save(self):
        self.data["last_heartbeat"] = datetime.datetime.now().isoformat()
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            if os.path.exists(self.path):
                os.replace(tmp, self.path)
            else:
                os.rename(tmp, self.path)
        except Exception as e:
            # Never crash on state save
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def transition(self, new_state, reason=None):
        self.data["state"] = new_state
        self.data["last_transition_at"] = datetime.datetime.now().isoformat()
        if reason is not None:
            self.data["paused_reason"] = reason
        self.save()

    def set(self, **kwargs):
        self.data.update(kwargs)
        self.save()

    def heartbeat(self):
        self.save()  # save() ja seta last_heartbeat

    @property
    def state(self):
        return self.data.get("state")

    @property
    def is_open(self):
        return self.state in OPEN_STATES

    @property
    def session_id(self):
        return self.data.get("session_id")


def _hash_text(text):
    return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()


def _set_round_stage(session_state, round_num, stage, **extra):
    payload = {
        "round_num": int(round_num or 0),
        "current_round": int(round_num or 0),
        "round_stage": stage,
        "orchestrator_pid": os.getpid(),
    }
    payload.update(extra)
    session_state.set(**payload)


def _record_recovery(session_state, recovery_mode, recovered_from, confidence,
                     strategy=None, note=None, error=None):
    attempts = int(session_state.data.get("recovery_attempts") or 0) + 1
    session_state.set(
        recovery_mode=recovery_mode,
        recovered_from=recovered_from,
        recovery_at=datetime.datetime.now().isoformat(),
        recovery_confidence=confidence,
        recovery_strategy=strategy,
        recovery_note=note,
        recovery_attempts=attempts,
        last_recovery_error=error,
        orchestrator_pid=os.getpid(),
    )


def _clear_recovery_marker(session_state):
    session_state.set(
        recovery_mode=None,
        recovered_from=None,
        recovery_at=None,
        recovery_confidence=None,
        recovery_strategy=None,
        recovery_note=None,
        last_recovery_error=None,
    )


def _process_alive(pid):
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


def normalize_label(label):
    """Normaliza RUN_LABEL para nome de pasta seguro no Windows."""
    nfkd = unicodedata.normalize("NFKD", label)
    sem_acento = nfkd.encode("ascii", "ignore").decode("ascii")
    limpo = re.sub(r"[^a-zA-Z0-9]", "-", sem_acento)
    limpo = re.sub(r"-+", "-", limpo).strip("-")
    return limpo or "sessao"


def parse_header(filepath):
    """Le linhas CHAVE: valor do topo do arquivo ate a primeira linha vazia ou #."""
    header = {}
    with open(filepath, "r", encoding="utf-8-sig") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                break
            match = re.match(r"^([A-Z_]+)\s*:\s*(.+)$", stripped)
            if match:
                header[match.group(1)] = match.group(2).strip()
            else:
                break
    return header


def _acquire_session_counter_lock(timeout_s=30):
    """V2.8: adquire lock exclusivo do contador global de sessoes.

    Usa `.duo_orchestrator/session_counter.lock` com O_EXCL atomico.
    Se o lock existir ha mais de 60s, considera stale e remove.
    Retorna o path do lock adquirido ou levanta RuntimeError.
    """
    import time as _time
    # Usa a raiz do repo (pai de orchestrator_sessions) para localizar
    # o diretorio .duo_orchestrator, consistente com update_lock/registry.
    repo_root = os.path.dirname(SESSIONS_DIR)
    orch_dir = os.path.join(repo_root, ".duo_orchestrator")
    os.makedirs(orch_dir, exist_ok=True)
    lock_path = os.path.join(orch_dir, "session_counter.lock")

    deadline = _time.time() + timeout_s
    while _time.time() < deadline:
        try:
            fd = os.open(lock_path,
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            return lock_path
        except FileExistsError:
            # Lock ja existe — verifica se e stale (>60s sem refresh).
            try:
                age = _time.time() - os.path.getmtime(lock_path)
                if age > 60:
                    os.remove(lock_path)
                    continue
            except Exception:
                pass
            _time.sleep(0.1)
    raise RuntimeError(
        f"Nao conseguiu lock de session_counter em {timeout_s}s "
        f"(lock_path={lock_path})"
    )


def _release_session_counter_lock(lock_path):
    """Libera o lock de contador. Idempotente; nunca levanta."""
    try:
        if lock_path and os.path.isfile(lock_path):
            os.remove(lock_path)
    except Exception:
        pass


def allocate_session_dir(run_label):
    """Aloca pasta exclusiva para a sessao. Nunca reutiliza pasta existente.

    V2.8: concurrent-safe. Usa lock global + contador persistente em
    `.duo_orchestrator/session_counter` para evitar race quando 2+ processos
    chamam `start_dupla.cmd multi` simultaneamente.

    Retorna (session_id, session_name, session_dir).
    Levanta RuntimeError se nao conseguir alocar.
    """
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    label_norm = normalize_label(run_label)

    lock_path = _acquire_session_counter_lock(timeout_s=30)
    try:
        orch_dir = os.path.dirname(lock_path)
        counter_path = os.path.join(orch_dir, "session_counter")

        # Base do contador: max entre (contador persistido) e (maior pasta
        # S-XXXX em disco) — pega legacy e tambem protege contra corrupcao.
        max_num = 0
        if os.path.isfile(counter_path):
            try:
                with open(counter_path, "r", encoding="utf-8") as f:
                    max_num = int(f.read().strip() or "0")
            except Exception:
                max_num = 0

        if os.path.exists(SESSIONS_DIR):
            for name in os.listdir(SESSIONS_DIR):
                m = re.match(r"^S-(\d{4})", name)
                if m:
                    num = int(m.group(1))
                    if num > max_num:
                        max_num = num

        # Tenta alocar a proxima pasta. Se outro processo (nao-V2.8) criar
        # paralelo, o exist_ok=False captura e tentamos proximo.
        for attempt in range(100):
            candidate_num = max_num + 1 + attempt
            session_id = f"S-{candidate_num:04d}"
            session_name = f"{session_id}-{label_norm}"
            session_dir = os.path.join(SESSIONS_DIR, session_name)
            try:
                os.makedirs(session_dir, exist_ok=False)
                # Persiste o contador para proxima alocacao.
                try:
                    tmp = counter_path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.write(str(candidate_num))
                    os.replace(tmp, counter_path)
                except Exception:
                    pass
                return session_id, session_name, session_dir
            except FileExistsError:
                continue
        raise RuntimeError(
            f"Nao foi possivel alocar pasta de sessao apos 100 tentativas. "
            f"Ultimo candidato: {session_dir}"
        )
    finally:
        _release_session_counter_lock(lock_path)


def validate_brief(brief_path):
    """Valida arquivo do brief e retorna (caminho_absoluto, header). Sai com erro se invalido."""
    brief_path = brief_path.strip('"').strip("'")

    if not os.path.isfile(brief_path):
        print(f"ERRO: Arquivo nao encontrado: {brief_path}")
        sys.exit(1)

    brief_path = os.path.abspath(brief_path)

    header = parse_header(brief_path)

    required = ["REPO_PATH", "RUN_LABEL", "MISSION"]
    missing = [f for f in required if f not in header]
    if missing:
        print(f"ERRO: Campos obrigatorios faltando: {', '.join(missing)}")
        print()
        print("O arquivo deve comecar com linhas no formato CHAVE: valor")
        print("  REPO_PATH: C:\\caminho\\do\\repo")
        print("  RUN_LABEL: Nome do Projeto")
        print("  MISSION: Descricao da missao")
        sys.exit(1)

    if not os.path.isdir(header["REPO_PATH"]):
        print(f"ERRO: REPO_PATH nao existe: {header['REPO_PATH']}")
        sys.exit(1)

    return brief_path, header


# === Lock ===

def read_lock_info(lock_path):
    """Le o lock e retorna dict simples com chaves conhecidas."""
    info = {}
    if not os.path.exists(lock_path):
        return info

    with open(lock_path, "r", encoding="utf-8") as f:
        for line in f:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            info[key.strip()] = value.strip()
    return info


STALE_LOCK_IDLE_SECONDS = 15 * 60  # 15 min sem atividade no session.log = lock morto


def _lock_looks_idle(locked_session_dir):
    """Retorna (True, idle_seconds) se o session.log nao mudou nos ultimos
    STALE_LOCK_IDLE_SECONDS segundos. Se nao houver log, tambem e idle."""
    import time
    log_path = os.path.join(locked_session_dir, "session.log")
    if not os.path.isfile(log_path):
        return True, None
    idle = time.time() - os.path.getmtime(log_path)
    return idle > STALE_LOCK_IDLE_SECONDS, idle


def create_lock(repo_path, session_id, run_label):
    """Cria .duo_orchestrator.lock no repositorio alvo.

    V2.3: Se o lock aponta para uma sessao em estado aberto (RUNNING,
    RETRY_BACKOFF, PAUSED_RECOVERABLE, WAITING_HUMAN, READY_FOR_HUMAN_CLOSE),
    NAO auto-limpa. Sessao persistente pode ficar horas parada sem ser morta.
    Auto-limpeza so ocorre para CLOSED_BY_HUMAN ou pasta inexistente.
    """
    lock_path = os.path.join(repo_path, LOCK_FILE_NAME)

    if os.path.exists(lock_path):
        info = read_lock_info(lock_path)
        locked_session_id = info.get("session_id")

        if locked_session_id:
            locked_session_dir = _find_session_dir(locked_session_id)
            if not locked_session_dir:
                print()
                print(f"AVISO: Lock stale de sessao ausente {locked_session_id}.")
                print("Limpando lock automaticamente.")
                os.remove(lock_path)
            else:
                # Checar estado da sessao via session-state.json (V2.3)
                state_path = os.path.join(locked_session_dir, STATE_FILE_NAME)
                locked_state = None
                if os.path.isfile(state_path):
                    try:
                        with open(state_path, "r", encoding="utf-8") as f:
                            locked_state = json.load(f).get("state")
                    except Exception:
                        locked_state = None

                if locked_state == STATE_CLOSED_BY_HUMAN:
                    print()
                    print(f"AVISO: Lock stale de sessao fechada {locked_session_id}.")
                    print("Limpando lock automaticamente.")
                    os.remove(lock_path)
                elif locked_state in OPEN_STATES:
                    # V2.3: sessao aberta nunca e auto-limpa por idle.
                    print()
                    print(f"AVISO: Lock encontrado em {lock_path}")
                    print(f"Sessao {locked_session_id} em estado {locked_state} (aberta).")
                    with open(lock_path, "r", encoding="utf-8") as f:
                        print(f.read().strip())
                    print()
                    print("Opcoes:")
                    print(f"  - Encerre a outra sessao: start_dupla.cmd close {locked_session_id}")
                    print(f"  - Ou retome: start_dupla.cmd continue {locked_session_id}")
                    resp = input("Deseja prosseguir e criar nova sessao mesmo assim? (s/n): ").strip().lower()
                    if resp != "s":
                        print("Sessao cancelada.")
                        sys.exit(0)
                else:
                    # Legacy / sem session-state.json: cai no fluxo antigo
                    finished, final_status = _session_is_finished(locked_session_dir)
                    if finished:
                        print()
                        print(f"AVISO: Lock stale encontrado de sessao finalizada {locked_session_id} ({final_status}).")
                        print("Limpando lock automaticamente.")
                        os.remove(lock_path)
                    else:
                        print()
                        print(f"AVISO: Lock legado encontrado em {lock_path}")
                        with open(lock_path, "r", encoding="utf-8") as f:
                            print(f.read().strip())
                        print()
                        resp = input("Outra sessao pode estar ativa. Continuar? (s/n): ").strip().lower()
                        if resp != "s":
                            print("Sessao cancelada.")
                            sys.exit(0)

    if os.path.exists(lock_path):
        print()
        print(f"AVISO: Lock encontrado em {lock_path}")
        with open(lock_path, "r", encoding="utf-8") as f:
            print(f.read().strip())
        print()
        resp = input("Outra sessao pode estar ativa. Continuar? (s/n): ").strip().lower()
        if resp != "s":
            print("Sessao cancelada.")
            sys.exit(0)

    now = datetime.datetime.now().isoformat()
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(f"session_id: {session_id}\n")
        f.write(f"run_label: {run_label}\n")
        f.write(f"started_at: {now}\n")
        f.write(f"state: {STATE_BOOTSTRAP}\n")
        f.write(f"last_heartbeat: {now}\n")

    return lock_path


def update_lock(repo_path, session_id, run_label, state_name, next_retry_at=None):
    """V2.3: atualiza lock com estado atual + heartbeat.
    V2.6: tambem atualiza registry global se sessao estiver registrada."""
    lock_path = os.path.join(repo_path, LOCK_FILE_NAME)
    now = datetime.datetime.now().isoformat()
    started_at = now
    if os.path.isfile(lock_path):
        info = read_lock_info(lock_path)
        started_at = info.get("started_at", now)
    try:
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write(f"session_id: {session_id}\n")
            f.write(f"run_label: {run_label}\n")
            f.write(f"started_at: {started_at}\n")
            f.write(f"state: {state_name}\n")
            f.write(f"last_heartbeat: {now}\n")
            if next_retry_at:
                f.write(f"next_retry_at: {next_retry_at}\n")
    except Exception:
        pass
    # V2.6: registry update (best-effort)
    try:
        reg = _load_registry()
        if session_id in reg.get("sessions", {}):
            registry_update_session(session_id, {
                "state": state_name,
            })
    except Exception:
        pass


def release_lock(repo_path, session_id, session_log=None):
    """Remove lock se ele pertence a esta sessao."""
    lock_path = os.path.join(repo_path, LOCK_FILE_NAME)
    if not os.path.exists(lock_path):
        return

    info = read_lock_info(lock_path)
    if info.get("session_id") != session_id:
        return

    os.remove(lock_path)
    if session_log:
        log(session_log, f"Lock removido: {lock_path}")


# === CLI Detection ===

def check_cli(name):
    """Verifica se um binario CLI esta no PATH. Retorna caminho ou None."""
    return shutil.which(name)


# === Windows Terminal ===

def check_wt_available():
    """Verifica se Windows Terminal (wt) esta no PATH de forma confiavel."""
    return shutil.which("wt") is not None


def launch_wt_and_exit(brief_path, header, mode_args=None):
    """Abre Windows Terminal com 3 abas na mesma janela:
      - Orquestrador: motor rodando
      - Codex (admin): tail em tempo real das respostas do Codex
      - Claude (executor): tail em tempo real das respostas do Claude

    A aba Orq relanca este script com --internal e, opcionalmente, com o modo
    explicito desejado (ex: --run-workflow). As 2 outras abas rodam o
    session_tailer.py apontando para o proximo session_id previsto.
    """
    run_label = header["RUN_LABEL"]
    repo_path = header["REPO_PATH"]
    safe_label = run_label.replace('"', "").replace("&", "e")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, "orchestrator.py")
    tailer_path = os.path.join(script_dir, "session_tailer.py")
    wt_path = check_cli("wt") or "wt"
    mode_str = ""
    if mode_args:
        mode_str = " " + " ".join(mode_args)

    # Prever o proximo session_id para passar aos tailers
    try:
        next_sid = _predict_next_session_id()
    except Exception:
        next_sid = "S-0000"
    title_tag = f"{next_sid} {safe_label}"

    cmd = (
        f'"{wt_path}"'
        f' --title "Orq {next_sid}"'
        f' -d "{repo_path}"'
        f' cmd /k python "{script_path}" --internal{mode_str} "{brief_path}"'
        f' ; new-tab'
        f' --title "Codex {next_sid}"'
        f' -d "{repo_path}"'
        f' cmd /k python "{tailer_path}" {next_sid} codex'
        f' ; new-tab'
        f' --title "Claude {next_sid}"'
        f' -d "{repo_path}"'
        f' cmd /k python "{tailer_path}" {next_sid} claude'
    )

    subprocess.Popen(cmd, shell=True)
    print(f"Windows Terminal aberto (3 abas) para: {run_label} [{next_sid}]")
    print("Este terminal pode ser fechado.")
    sys.exit(0)


def _predict_next_session_id():
    """Ve a maior sessao existente em SESSIONS_DIR e retorna S-XXXX+1."""
    if not os.path.isdir(SESSIONS_DIR):
        return "S-0001"
    mx = 0
    for n in os.listdir(SESSIONS_DIR):
        m = re.match(r"^S-(\d{4})", n)
        if m:
            v = int(m.group(1))
            if v > mx:
                mx = v
    return f"S-{mx + 1:04d}"


# === Command Runner ===

def run_command(args, timeout_s=DEFAULT_TIMEOUT_S, cwd=None, input_text=None):
    """Executa comando externo com timeout e captura completa.

    Se input_text for fornecido, envia via stdin. Caso contrario, stdin=DEVNULL.
    Retorna dict com: ok, exit_code, stdout, stderr, duration_ms, timed_out, args.
    """
    start = datetime.datetime.now()
    try:
        run_kwargs = {
            "capture_output": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": timeout_s,
            "cwd": cwd,
        }
        if input_text is not None:
            run_kwargs["input"] = input_text
        else:
            run_kwargs["stdin"] = subprocess.DEVNULL

        result = subprocess.run(args, **run_kwargs)
        duration_ms = int((datetime.datetime.now() - start).total_seconds() * 1000)
        return {
            "ok": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "duration_ms": duration_ms,
            "timed_out": False,
            "args": args,
        }
    except subprocess.TimeoutExpired as e:
        duration_ms = int((datetime.datetime.now() - start).total_seconds() * 1000)
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": (e.stdout or "").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""),
            "stderr": f"Timeout apos {timeout_s}s",
            "duration_ms": duration_ms,
            "timed_out": True,
            "args": args,
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Comando nao encontrado: {args[0]}",
            "duration_ms": 0,
            "timed_out": False,
            "args": args,
        }
    except Exception as e:
        duration_ms = int((datetime.datetime.now() - start).total_seconds() * 1000)
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "duration_ms": duration_ms,
            "timed_out": False,
            "args": args,
        }


# === CLI Wrappers ===

def run_command_with_heartbeat(args, timeout_s, cwd, input_text,
                                on_heartbeat, stop_requested=None,
                                interval_s=None):
    """V2.8: wrapper de `run_command` com heartbeat em thread paralela.

    Executa o subprocess de forma sincrona (como `run_command`) mas tambem
    dispara um thread em background que chama `on_heartbeat(info)` a cada
    `interval_s` segundos enquanto a call estiver viva. Fecha o thread
    graciosamente quando o subprocess termina.

    Uso principal: `claude --resume` em modo recovery V2.5, que antes rodava
    sem heartbeat — sessoes ficavam "cegas" no dashboard por horas
    (bug observado na S-0027 round 12 — 10h sem log visivel).

    `info` passado a `on_heartbeat`:
        {
            "active_agent": "claude",
            "active_call_status": "in_call" | "long_running",
            "active_call_started_at": float epoch,
            "duration_s": int,
            "elapsed_s": int,
        }

    `stop_requested()` e consultado a cada tick; se True, encerra thread
    e retorna sem alterar o subprocess (o subprocess continua ate acabar
    ou bater em timeout_s — kill manual e responsabilidade do caller).
    """
    import threading as _threading
    import time as _time
    if interval_s is None:
        interval_s = HEARTBEAT_INTERVAL_S

    start_epoch = _time.time()
    stop_event = _threading.Event()

    def _heartbeat_loop():
        while not stop_event.wait(interval_s):
            if stop_requested is not None:
                try:
                    if stop_requested():
                        return
                except Exception:
                    pass
            elapsed = int(_time.time() - start_epoch)
            status = "long_running" if elapsed >= 600 else "in_call"
            try:
                on_heartbeat({
                    "active_agent": "claude",
                    "active_call_status": status,
                    "active_call_started_at": start_epoch,
                    "duration_s": elapsed,
                    "elapsed_s": elapsed,
                })
            except Exception:
                pass

    heartbeat_thread = _threading.Thread(
        target=_heartbeat_loop, daemon=True,
        name="orchestrator-resume-heartbeat",
    )
    heartbeat_thread.start()
    try:
        result = run_command(args, timeout_s=timeout_s, cwd=cwd,
                             input_text=input_text)
    finally:
        stop_event.set()
        try:
            heartbeat_thread.join(timeout=5)
        except Exception:
            pass
    return result


def call_claude(prompt, cwd=None, timeout_s=DEFAULT_TIMEOUT_S):
    """Chama claude em modo nao interativo (-p). Prompt via stdin.

    Usa cmd /c porque no Windows o binario e um .CMD (npm wrapper).
    """
    args = [
        "cmd", "/c",
        "claude", "-p",
        "--dangerously-skip-permissions",
        "--no-session-persistence",
    ]
    return run_command(args, timeout_s=timeout_s, cwd=cwd, input_text=prompt)


def call_codex(prompt, cwd=None, timeout_s=DEFAULT_TIMEOUT_S):
    """Chama codex exec em modo nao interativo. Prompt via stdin.

    Usa cmd /c porque no Windows o binario e um .CMD (npm wrapper).
    Usa --dangerously-bypass-approvals-and-sandbox (equivalente a --yolo).
    """
    args = [
        "cmd", "/c",
        "codex", "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--ephemeral",
    ]
    if cwd:
        args.extend(["-C", cwd])
    return run_command(args, timeout_s=timeout_s, cwd=cwd, input_text=prompt)


def log_cli_call(log_path, cli_name, prompt, result):
    """Registra uma chamada CLI no log, incluindo comando efetivo."""
    preview = (prompt[:80] + "...") if len(prompt) > 80 else prompt
    preview = preview.replace("\n", " ")
    cmd_used = " ".join(result.get("args", []))
    log(log_path, f"CLI chamado: {cli_name}")
    log(log_path, f"  comando: {cmd_used}")
    log(log_path, f"  prompt_len: {len(prompt)} chars")
    log(log_path, f"  prompt_preview: {preview}")
    log(log_path, f"  ok: {result['ok']}")
    log(log_path, f"  exit_code: {result['exit_code']}")
    log(log_path, f"  duration: {result['duration_ms']}ms")
    log(log_path, f"  timed_out: {result['timed_out']}")
    log(log_path, f"  stdout_len: {len(result['stdout'])} chars")
    if result["stderr"]:
        stderr_preview = result["stderr"][:200].replace("\n", " ")
        log(log_path, f"  stderr: {stderr_preview}")


# === Status Parser ===

def parse_status(text, valid_statuses):
    """Extrai STATUS: XXX da primeira linha. Retorna (status, is_valid)."""
    first_line = text.strip().split("\n")[0].strip() if text.strip() else ""
    match = re.match(r"^STATUS:\s*(\S+)", first_line)
    if match:
        status = match.group(1)
        return status, status in valid_statuses
    return None, False


# === Understanding Prompts ===

def build_claude_understanding_prompt(project_content, previous_codex_feedback=None):
    """Monta prompt para o Claude expressar entendimento do projeto."""
    credential_guidance = build_credential_guidance(project_content)
    prompt = (
        "Voce e o EXECUTOR deste projeto. Leia o projeto refinado abaixo com atencao.\n\n"
        "=== PROJETO REFINADO ===\n"
        f"{project_content}\n"
        "=== FIM DO PROJETO ===\n\n"
        f"{credential_guidance}\n\n"
        "Sua tarefa:\n"
        "1. Faca um resumo curto do que entendeu\n"
        "2. Liste os principais objetivos\n"
        "3. Liste as principais restricoes\n"
        "4. Diga se ha algum bloqueio real para comecar\n\n"
        "IMPORTANTE:\n"
        "- esta fase e um alinhamento inicial, nao uma prova formal\n"
        "- nao tente cobrir cada detalhe do projeto\n"
        "- capture o nucleo do objetivo, a ordem geral e as restricoes principais\n"
        "- se houver duvida menor, cite isso em texto; nao trate como bloqueio\n\n"
        "REGRA OBRIGATORIA: sua resposta DEVE comecar com uma destas linhas exatamente:\n"
        "- STATUS: EXECUTED\n"
        "- STATUS: NEEDS_HUMAN\n"
        "- STATUS: BLOCKED\n\n"
        "Depois do status, escreva o resumo em texto simples e curto."
    )
    if previous_codex_feedback:
        prompt += (
            "\n\nATENCAO: Seu entendimento anterior foi REPROVADO pelo administrador.\n"
            "Feedback do administrador:\n"
            f"{previous_codex_feedback}\n\n"
            "Corrija seu entendimento com base nesse feedback.\n"
            "Nao reescreva o projeto. So ajuste o seu entendimento."
        )
    return prompt


def build_codex_review_prompt(project_content, claude_response):
    """Monta prompt para o Codex julgar o entendimento do Claude."""
    credential_guidance = build_credential_guidance(project_content)
    return (
        "Voce e o ADMINISTRADOR deste projeto. Julgue se o executor entendeu o suficiente para iniciar o trabalho.\n\n"
        "=== PROJETO REFINADO ===\n"
        f"{project_content}\n"
        "=== FIM DO PROJETO ===\n\n"
        f"{credential_guidance}\n\n"
        "=== RESPOSTA DO EXECUTOR ===\n"
        f"{claude_response}\n"
        "=== FIM DA RESPOSTA ===\n\n"
        "Regras de governanca:\n"
        "1. O projeto refinado e a fonte de verdade e NAO pode ser alterado por voce.\n"
        "2. Voce pode corrigir erros de leitura, omissoes importantes e formato.\n"
        "3. Voce NAO pode mudar objetivo, fases, criterios, restricoes ou redefinir sucesso.\n"
        "4. O entendimento nao precisa ser perfeito para aprovar.\n"
        "5. Se o nucleo do projeto estiver correto e o resto puder ser alinhado nos prompts das fases, APROVE.\n"
        "6. So use REPROVADO quando houver erro grave de leitura que possa desviar a primeira fase.\n"
        "7. So use REVISAO_HUMANA quando o proprio projeto estiver contraditorio, ambiguo ou incompleto de forma real.\n"
        "8. Nao reprove apenas por detalhe menor, cobertura incompleta ou por uso de STATUS: READY em vez de STATUS: EXECUTED.\n\n"
        "Sua tarefa:\n"
        "1. Verifique se o executor captou o objetivo central\n"
        "2. Verifique se a ordem geral e as restricoes principais estao suficientemente corretas\n"
        "3. Decida se ja e seguro iniciar a primeira fase\n\n"
        "REGRA OBRIGATORIA: sua resposta DEVE comecar com uma destas linhas exatamente:\n"
        "- STATUS: APROVADO\n"
        "- STATUS: REPROVADO\n"
        "- STATUS: REVISAO_HUMANA\n\n"
        "Depois do status:\n"
        "- se for APROVADO, explique brevemente o que esta bom e cite no maximo 3 alertas menores para corrigir nas fases seguintes\n"
        "- se for REPROVADO, liste objetivamente: erros graves, partes do projeto para reler, e o que falta para aprovar\n"
        "- se for REVISAO_HUMANA, explique qual ambiguidade real do projeto impede seguir"
    )


def build_status_correction_prompt(original_response, valid_options):
    """Monta prompt para corrigir resposta sem marcador valido."""
    options_str = ", ".join(f"STATUS: {s}" for s in valid_options)
    return (
        f"Sua resposta anterior nao comecou com um marcador valido.\n"
        f"Opcoes validas: {options_str}\n\n"
        f"Sua resposta anterior foi:\n{original_response}\n\n"
        f"Responda novamente. A primeira linha DEVE ser um dos marcadores acima."
    )


def canonicalize_understanding_status(status):
    """Normaliza status de entendimento para uso interno e logs."""
    if status == "READY":
        return "EXECUTED"
    return status


def build_credential_guidance(project_content):
    """Monta orientacao de descoberta de credenciais baseada no REPO_PATH do projeto."""
    repo_path = "repositorio atual"
    first_lines = project_content.splitlines()[:20]
    for line in first_lines:
        match = re.match(r"^REPO_PATH\s*:\s*(.+)$", line.strip())
        if match:
            repo_path = match.group(1).strip()
            break
    candidate_paths = [
        os.path.join(repo_path, ".env"),
        os.path.join(repo_path, ".env.local"),
        os.path.join(repo_path, "backend", ".env"),
        os.path.join(repo_path, "backend", ".env.local"),
    ]

    env_search_lines = []
    item_number = 2
    for candidate in candidate_paths:
        if os.path.exists(candidate):
            env_search_lines.append(f"  {item_number}. `{candidate}`")
            item_number += 1

    if not env_search_lines:
        env_search_lines = [
            f"  2. `{os.path.join(repo_path, '.env')}`",
            f"  3. `{os.path.join(repo_path, '.env.local')}`",
            f"  4. `{os.path.join(repo_path, 'backend', '.env')}` (se existir)",
            f"  5. `{os.path.join(repo_path, 'backend', '.env.local')}` (se existir)",
        ]

    return CREDENTIAL_DISCOVERY_GUIDANCE_TEMPLATE.format(
        repo_path=repo_path,
        env_search_lines="\n".join(env_search_lines),
    )


# === Bootstrap da sessao ===

def run_bootstrap(brief_path, header, wt_mode, preallocated_session=None,
                  multi_mode=False, multi_info=None):
    """Cria a sessao: pasta, logs, lock, registro. Retorna dict com caminhos.

    V2.6: se preallocated_session=(session_id, session_name, session_dir) for
    passado, nao aloca sessao nova — usa a que ja foi criada.
    """
    repo_path = header["REPO_PATH"]
    run_label = header["RUN_LABEL"]
    mission = header["MISSION"]
    allowed_paths = header.get("ALLOWED_PATHS", "")

    if preallocated_session:
        session_id, session_name, session_dir = preallocated_session
    else:
        session_id, session_name, session_dir = allocate_session_dir(run_label)

    print(f"Sessao: {session_name}")
    print(f"Pasta:  {session_dir}")
    print()

    # Copia do projeto
    project_copy = os.path.join(session_dir, "project.md")
    shutil.copy2(brief_path, project_copy)

    # Criacao dos logs
    session_log = os.path.join(session_dir, "session.log")
    codex_log = os.path.join(session_dir, "codex.log")
    claude_log = os.path.join(session_dir, "claude.log")

    for lf in [session_log, codex_log, claude_log]:
        with open(lf, "w", encoding="utf-8") as f:
            pass

    # Registro no session.log
    log(session_log, f"Sessao iniciada: {session_id}")
    log(session_log, f"session_name: {session_name}")
    log(session_log, f"run_label: {run_label}")
    log(session_log, f"mission: {mission}")
    log(session_log, f"repo_path: {repo_path}")
    log(session_log, f"allowed_paths: {allowed_paths}")
    log(session_log, f"brief_original: {brief_path}")
    log(session_log, f"pasta_sessao: {session_dir}")

    if wt_mode:
        log(session_log, "Modo: aba Orq do Windows Terminal")
    else:
        log(session_log, "AVISO: Modo fallback - sem Windows Terminal")

    # Lock
    if multi_mode:
        lock_path = _create_multi_lock(session_id)
        log(session_log, f"Multi lock criado: {lock_path}")
    else:
        lock_path = create_lock(repo_path, session_id, run_label)
        log(session_log, f"Lock criado: {lock_path}")

    # Multi-mode: persiste info extra e atualiza registry
    if multi_mode and multi_info:
        log(session_log, f"multi_mode: true")
        log(session_log, f"workspace_mode: {multi_info.get('workspace_mode')}")
        log(session_log, f"workspace_path: {multi_info.get('workspace_path')}")
        log(session_log, f"base_repo_path: {multi_info.get('base_repo_path')}")
        try:
            registry_update_session(session_id, {
                "session_id": session_id,
                "run_label": run_label,
                "state": STATE_BOOTSTRAP,
                "base_repo_path": multi_info.get("base_repo_path", ""),
                "workspace_path": multi_info.get("workspace_path", ""),
                "workspace_mode": multi_info.get("workspace_mode", ""),
                "session_dir": session_dir,
                "started_at": datetime.datetime.now().isoformat(),
            })
            generate_index_html()
        except Exception as e:
            log(session_log, f"Registry: falha ao registrar ({e})")

    # Fim
    print()
    log(session_log, "Bootstrap concluido")
    print()
    print(f"Sessao {session_name} pronta.")
    print(f"Pasta:  {session_dir}")
    print("Aguardando proximas fases.")

    # Abrir session.html automaticamente para acompanhar visualmente.
    # Falhas aqui nunca devem quebrar o orquestrador.
    try:
        _open_session_viewer(session_id, session_log)
    except Exception as e:
        log(session_log, f"Viewer: falha ao abrir ({e})")

    return {
        "session_id": session_id,
        "session_name": session_name,
        "session_dir": session_dir,
        "session_log": session_log,
        "codex_log": codex_log,
        "claude_log": claude_log,
        "repo_path": repo_path,
        "multi_mode": multi_mode,
        "multi_info": multi_info,
    }


def _open_session_viewer(session_id, session_log):
    """Gera session.html e abre no browser. Isolado e best-effort."""
    viewer = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "session_viewer.py")
    if not os.path.isfile(viewer):
        log(session_log, "Viewer: session_viewer.py nao encontrado")
        return
    subprocess.Popen(
        [sys.executable, viewer, session_id],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=os.path.dirname(viewer),
    )
    log(session_log, f"Viewer: session.html aberto para {session_id}")


# === Probe CLIs ===

def run_probe(brief_path):
    """Cria sessao e testa chamada minima a cada CLI."""
    brief_path, header = validate_brief(brief_path)
    repo_path = header["REPO_PATH"]
    run_label = header["RUN_LABEL"]

    print(f"Projeto: {brief_path}")
    print(f"Repo:    {repo_path}")
    print(f"Label:   {run_label}")
    print()

    session = run_bootstrap(brief_path, header, wt_mode=False)
    sl = session["session_log"]
    try:
        print()
        print("=" * 40)
        print("  Probe dos CLIs")
        print("=" * 40)
        print()

        # --- Deteccao ---
        claude_path = check_cli("claude")
        codex_path = check_cli("codex")

        if claude_path:
            log(sl, f"claude encontrado: {claude_path}")
        else:
            log(sl, "ERRO: claude NAO encontrado no PATH")

        if codex_path:
            log(sl, f"codex encontrado: {codex_path}")
        else:
            log(sl, "ERRO: codex NAO encontrado no PATH")

        if not claude_path and not codex_path:
            log(sl, "Nenhum CLI disponivel. Probe encerrado.")
            return

        # --- Probe Claude ---
        if claude_path:
            print()
            log(sl, "Iniciando probe do claude...")
            probe_prompt = "Responda apenas com a palavra PROBE_OK. Nada mais."
            result = call_claude(probe_prompt, cwd=repo_path, timeout_s=PROBE_TIMEOUT_S)
            log_cli_call(session["claude_log"], "claude", probe_prompt, result)
            log_cli_call(sl, "claude", probe_prompt, result)

            print()
            if result["ok"]:
                stdout_preview = result["stdout"].strip()[:200]
                log(sl, f"claude probe OK. Resposta: {stdout_preview}")
            else:
                log(sl, f"claude probe FALHOU. exit_code={result['exit_code']}")
                if result["stderr"]:
                    log(sl, f"  stderr: {result['stderr'][:200]}")

        # --- Probe Codex ---
        if codex_path:
            print()
            log(sl, "Iniciando probe do codex...")
            probe_prompt = "Responda apenas com a palavra PROBE_OK. Nada mais."
            result = call_codex(probe_prompt, cwd=repo_path, timeout_s=PROBE_TIMEOUT_S)
            log_cli_call(session["codex_log"], "codex", probe_prompt, result)
            log_cli_call(sl, "codex", probe_prompt, result)

            print()
            if result["ok"]:
                stdout_preview = result["stdout"].strip()[:200]
                log(sl, f"codex probe OK. Resposta: {stdout_preview}")
            else:
                log(sl, f"codex probe FALHOU. exit_code={result['exit_code']}")
                if result["stderr"]:
                    log(sl, f"  stderr: {result['stderr'][:200]}")

        # --- Fim ---
        print()
        log(sl, "Probe concluido")
        print()
        print(f"Logs gravados em: {session['session_dir']}")
    finally:
        release_lock(repo_path, session["session_id"], sl)


# === Understanding Phase ===

def try_call_with_status(call_fn, prompt, cwd, timeout_s, log_path, cli_name,
                         valid_statuses):
    """Chama CLI, valida status. Se invalido, tenta correcao uma vez.

    Retorna (response_text, status, ok, timed_out).
    """
    result = call_fn(prompt, cwd=cwd, timeout_s=timeout_s)
    log_cli_call(log_path, cli_name, prompt, result)

    if not result["ok"]:
        return result["stdout"], None, False, result["timed_out"]

    response = result["stdout"].strip()
    status, valid = parse_status(response, valid_statuses)

    if valid:
        return response, status, True, False

    # Tentativa de correcao
    correction = build_status_correction_prompt(response, valid_statuses)
    result2 = call_fn(correction, cwd=cwd, timeout_s=timeout_s)
    log_cli_call(log_path, cli_name, correction, result2)

    if not result2["ok"]:
        return response, None, False, result2["timed_out"]

    response2 = result2["stdout"].strip()
    status2, valid2 = parse_status(response2, valid_statuses)

    if valid2:
        return response2, status2, True, False

    return response, None, False, False


def _understanding_loop(session, project_content):
    """Executa loop de entendimento. Retorna True se aprovado, False caso contrario."""
    sl = session["session_log"]
    sd = session["session_dir"]
    repo_path = session["repo_path"]

    log(sl, "=== FASE DE ENTENDIMENTO ===")

    previous_codex_feedback = None
    canonical_understanding_file = os.path.join(sd, "round-000-claude-understanding.md")
    canonical_review_file = os.path.join(sd, "round-000-codex-review.md")

    for attempt in range(1, MAX_UNDERSTANDING_ATTEMPTS + 1):
        attempt_understanding_file = os.path.join(
            sd, f"round-000-claude-understanding-attempt-{attempt}.md"
        )
        attempt_review_file = os.path.join(
            sd, f"round-000-codex-review-attempt-{attempt}.md"
        )

        print()
        log(sl, f"--- Entendimento tentativa {attempt}/{MAX_UNDERSTANDING_ATTEMPTS} ---")

        log(sl, "Enviando projeto ao Claude...")
        claude_prompt = build_claude_understanding_prompt(
            project_content, previous_codex_feedback
        )
        claude_response, claude_status, claude_ok, claude_timeout = try_call_with_status(
            call_claude, claude_prompt, repo_path, DEFAULT_TIMEOUT_S,
            session["claude_log"], "claude", VALID_CLAUDE_STATUSES,
        )
        claude_status = canonicalize_understanding_status(claude_status)

        with open(attempt_understanding_file, "w", encoding="utf-8") as f:
            f.write(claude_response)
        with open(canonical_understanding_file, "w", encoding="utf-8") as f:
            f.write(claude_response)

        if not claude_ok:
            if claude_timeout:
                log(sl, f"TIMEOUT: Claude estourou timeout de "
                    f"{DEFAULT_TIMEOUT_S}s no entendimento")
                log(sl, "UNDERSTANDING REVISAO_HUMANA")
                return False
            if claude_status is None:
                log(sl, "Claude retornou status invalido mesmo apos correcao")
                log(sl, "UNDERSTANDING REVISAO_HUMANA")
                return False
            log(sl, "Claude FALHOU. Tentando novamente...")
            continue

        log(sl, f"Claude status: {claude_status}")

        if claude_status in ("NEEDS_HUMAN", "BLOCKED"):
            log(sl, f"Claude pediu {claude_status}")
            log(sl, "UNDERSTANDING REVISAO_HUMANA")
            return False

        log(sl, "Enviando ao Codex para julgamento...")
        codex_prompt = build_codex_review_prompt(project_content, claude_response)
        codex_response, codex_status, codex_ok, codex_timeout = try_call_with_status(
            call_codex, codex_prompt, repo_path, DEFAULT_TIMEOUT_S,
            session["codex_log"], "codex", VALID_CODEX_STATUSES,
        )

        with open(attempt_review_file, "w", encoding="utf-8") as f:
            f.write(codex_response)
        with open(canonical_review_file, "w", encoding="utf-8") as f:
            f.write(codex_response)

        if not codex_ok:
            if codex_timeout:
                log(sl, f"TIMEOUT: Codex estourou timeout de "
                    f"{DEFAULT_TIMEOUT_S}s no entendimento")
                log(sl, "UNDERSTANDING REVISAO_HUMANA")
                return False
            if codex_status is None:
                log(sl, "Codex retornou status invalido mesmo apos correcao")
                log(sl, "UNDERSTANDING REVISAO_HUMANA")
                return False
            log(sl, "Codex FALHOU. Tentando novamente...")
            continue

        log(sl, f"Codex status: {codex_status}")

        if codex_status == "APROVADO":
            print()
            log(sl, "UNDERSTANDING APROVADO")
            return True

        if codex_status == "REVISAO_HUMANA":
            log(sl, "UNDERSTANDING REVISAO_HUMANA")
            return False

        if codex_status == "REPROVADO":
            log(sl, "Entendimento reprovado. Preparando nova tentativa com feedback do administrador...")
            previous_codex_feedback = codex_response

    log(sl, f"Limite de {MAX_UNDERSTANDING_ATTEMPTS} tentativas atingido")
    log(sl, "UNDERSTANDING REVISAO_HUMANA")
    return False


def run_understanding(brief_path):
    """Cria sessao e executa fase de entendimento (modo standalone)."""
    brief_path, header = validate_brief(brief_path)
    repo_path = header["REPO_PATH"]

    print(f"Projeto: {brief_path}")
    print(f"Repo:    {repo_path}")
    print(f"Label:   {header['RUN_LABEL']}")
    print()

    session = run_bootstrap(brief_path, header, wt_mode=False)
    sl = session["session_log"]
    try:
        with open(os.path.join(session["session_dir"], "project.md"), "r",
                  encoding="utf-8-sig") as f:
            project_content = f.read()

        if not check_cli("claude") or not check_cli("codex"):
            log(sl, "ERRO: CLI nao encontrado")
            log(sl, "UNDERSTANDING REVISAO_HUMANA")
            return

        log(sl, f"claude: {check_cli('claude')}")
        log(sl, f"codex: {check_cli('codex')}")

        _understanding_loop(session, project_content)
    finally:
        release_lock(repo_path, session["session_id"], sl)


# === Workflow Prompts ===

def build_admin_task_prompt(project_content, round_num, history_summary):
    """Monta prompt para Codex criar a proxima tarefa."""
    credential_guidance = build_credential_guidance(project_content)
    return (
        "Voce e o ADMINISTRADOR deste projeto.\n\n"
        "=== PROJETO REFINADO ===\n"
        f"{project_content}\n"
        "=== FIM DO PROJETO ===\n\n"
        f"{history_summary}\n\n"
        f"{credential_guidance}\n\n"
        f"Crie agora a tarefa do round {round_num:03d} para o executor.\n\n"
        "Regras:\n"
        "- Escolha a menor fase/subfase util seguinte\n"
        "- Seja objetivo e claro sobre o que deve ser feito\n"
        "- Nao amplie escopo alem do projeto refinado\n"
        "- Diga exatamente o que o executor deve fazer agora\n"
        "- Inclua criterios de aceitacao claros para esta tarefa\n"
    )


def build_exec_task_prompt(task_text, project_content, rejection_feedback=None):
    """Monta prompt para Claude executar uma tarefa."""
    credential_guidance = build_credential_guidance(project_content)
    prompt = (
        "Voce e o EXECUTOR deste projeto.\n\n"
        "=== PROJETO REFINADO ===\n"
        f"{project_content}\n"
        "=== FIM DO PROJETO ===\n\n"
        f"{credential_guidance}\n\n"
        "=== TAREFA DO ADMINISTRADOR ===\n"
        f"{task_text}\n"
        "=== FIM DA TAREFA ===\n\n"
        "Execute a tarefa descrita acima.\n\n"
        "=== REGRAS DO EXECUTOR ESTRITO ===\n"
        "O refinamento do projeto ja aconteceu antes desta sessao. Aqui voce e executor puro.\n"
        "Voce NAO PODE:\n"
        "- alterar objetivo, fases, criterios ou restricoes do projeto refinado\n"
        "- introduzir metricas, termos, KPIs, gates ou definicoes que nao estejam no projeto\n"
        "- substituir uma metrica/gate pedido por uma variante sua, mesmo que voce considere melhor\n"
        "- remover, renomear ou reagrupar itens exigidos pelo projeto\n"
        "- divergir dos defaults do projeto sem que o proprio projeto ou o codigo real exijam excecao\n"
        "- tratar 'preferencia metodologica' como justificativa para inovar\n"
        "Voce DEVE:\n"
        "- usar exatamente os nomes, metricas, gates e KPIs definidos no projeto refinado\n"
        "- se achar que o projeto esta errado, contraditorio ou ambiguo: responder STATUS: BLOCKED com motivo,\n"
        "  NAO entregar uma versao 'melhorada' por conta propria\n"
        "- se a tarefa pedir declarar algo (ex.: limiar de piora material para X, Y, Z), declarar para TODOS os itens listados, sem trocar nenhum\n"
        "=== FIM DAS REGRAS ===\n\n"
        "REGRA OBRIGATORIA: sua resposta DEVE comecar com uma destas linhas:\n"
        "- STATUS: EXECUTED\n"
        "- STATUS: BLOCKED\n"
        "- STATUS: NEEDS_HUMAN\n\n"
        "Depois do status, descreva o que fez, arquivos alterados e resultado."
    )
    if rejection_feedback:
        prompt += (
            "\n\nATENCAO: Sua entrega anterior foi REPROVADA pelo administrador.\n"
            "Feedback:\n"
            f"{rejection_feedback}\n\n"
            "Corrija e tente novamente."
        )
    return prompt


def build_admin_review_prompt(project_content, task_text, exec_response):
    """Monta prompt para Codex julgar a execucao do Claude."""
    credential_guidance = build_credential_guidance(project_content)
    return (
        "Voce e o ADMINISTRADOR deste projeto.\n\n"
        "=== PROJETO REFINADO ===\n"
        f"{project_content}\n"
        "=== FIM DO PROJETO ===\n\n"
        f"{credential_guidance}\n\n"
        "=== TAREFA QUE FOI PEDIDA ===\n"
        f"{task_text}\n"
        "=== FIM DA TAREFA ===\n\n"
        "=== RESPOSTA DO EXECUTOR ===\n"
        f"{exec_response}\n"
        "=== FIM DA RESPOSTA ===\n\n"
        "Julgue se a execucao atende a tarefa pedida.\n\n"
        "REGRA OBRIGATORIA: sua resposta DEVE comecar com uma destas linhas:\n"
        "- STATUS: APROVADO (tarefa concluida, proxima fase)\n"
        "- STATUS: REPROVADO (precisa corrigir, enviar feedback)\n"
        "- STATUS: REVISAO_HUMANA (precisa de decisao humana)\n"
        "- STATUS: CONCLUIDO (projeto inteiro finalizado)\n\n"
        "Depois do status, explique brevemente.\n"
        "Se o executor alegar falta de credencial sem ter procurado nas fontes locais do repo e no ambiente, reprove e aponte isso."
    )


def build_history_summary(rounds_done):
    """Monta resumo textual dos rounds anteriores."""
    if not rounds_done:
        return "Entendimento aprovado. Este e o primeiro round de execucao."
    lines = ["Entendimento aprovado. Historico dos rounds anteriores:"]
    for r in rounds_done:
        lines.append(
            f"- Round {r['round']:03d}: "
            f"executor={r['exec_status']}, admin={r['review_status']}. "
            f"Resumo: {r['task_preview']}"
        )
    return "\n".join(lines)


def write_final_review(session, final_status, total_rounds, stop_reason,
                       round_files):
    """Gera final-review.md e registra encerramento."""
    sl = session["session_log"]
    sd = session["session_dir"]

    content = (
        f"# Final Review - {session['session_name']}\n\n"
        f"## Status final: {final_status}\n"
        f"## Rounds executados: {total_rounds}\n"
        f"## Motivo de parada: {stop_reason}\n\n"
        "## Arquivos gerados\n"
    )
    for rf in round_files:
        content += f"- {rf}\n"

    path = os.path.join(sd, "final-review.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    log(sl, "final-review.md gerado")


# === Session State Inference ===

def _find_session_dir(session_id):
    """Localiza pasta da sessao pelo ID (ex: S-0003). Retorna caminho ou None."""
    if not os.path.exists(SESSIONS_DIR):
        return None
    for name in os.listdir(SESSIONS_DIR):
        if name.startswith(session_id + "-") or name == session_id:
            path = os.path.join(SESSIONS_DIR, name)
            if os.path.isdir(path):
                return path
    return None


def _session_is_finished(session_dir):
    """Verifica se sessao ja terminou. Retorna (finished, status) ou (False, None)."""
    fr_path = os.path.join(session_dir, "final-review.md")
    if not os.path.exists(fr_path):
        return False, None
    with open(fr_path, "r", encoding="utf-8-sig") as f:
        for line in f:
            m = re.match(r"^## Status final:\s*(.+)$", line.strip())
            if m:
                return True, m.group(1).strip()
    return True, "DESCONHECIDO"


def _understanding_was_approved(session_dir):
    """Verifica se o entendimento foi aprovado nos artefatos."""
    review_path = os.path.join(session_dir, "round-000-codex-review.md")
    if not os.path.exists(review_path):
        return False
    with open(review_path, "r", encoding="utf-8-sig") as f:
        content = f.read()
    status, valid = parse_status(content, ["APROVADO"])
    return valid


def infer_session_state(session_dir):
    """Infere estado da sessao pelos artefatos em disco.

    Retorna dict com:
      finished, final_status, understanding_approved,
      last_complete_round, resume_round, resume_step
    """
    finished, final_status = _session_is_finished(session_dir)
    understanding = _understanding_was_approved(session_dir)

    last_complete = 0
    resume_round = 1
    resume_step = "admin"

    for n in range(1, MAX_WORKFLOW_ROUNDS + 1):
        p = f"{n:03d}"
        has_admin = os.path.exists(os.path.join(session_dir, f"round-{p}-admin.md"))
        has_exec = os.path.exists(os.path.join(session_dir, f"round-{p}-exec.md"))
        has_review = os.path.exists(os.path.join(session_dir, f"round-{p}-review.md"))

        if not has_admin:
            resume_round = n
            resume_step = "admin"
            break

        if not has_exec:
            resume_round = n
            resume_step = "exec"
            break

        if not has_review:
            resume_round = n
            resume_step = "review"
            break

        # Round completo — verificar se APROVADO para contar
        with open(os.path.join(session_dir, f"round-{p}-review.md"), "r",
                  encoding="utf-8-sig") as f:
            review_content = f.read()
        rs, _ = parse_status(review_content, VALID_REVIEW_STATUSES)
        if rs == "APROVADO":
            last_complete = n
            resume_round = n + 1
            resume_step = "admin"
        else:
            # Round ended in REPROVADO/REVISAO_HUMANA/CONCLUIDO — redo
            resume_round = n
            resume_step = "admin"
            break

    return {
        "finished": finished,
        "final_status": final_status,
        "understanding_approved": understanding,
        "last_complete_round": last_complete,
        "resume_round": resume_round,
        "resume_step": resume_step,
    }


def _rebuild_session_dict(session_dir):
    """Reconstroi session dict a partir da pasta existente."""
    dir_name = os.path.basename(session_dir)
    m = re.match(r"^(S-\d{4})", dir_name)
    session_id = m.group(1) if m else dir_name

    project_path = os.path.join(session_dir, "project.md")
    header = parse_header(project_path)
    repo_path = header.get("REPO_PATH", "C:\\winegod-app")

    return {
        "session_id": session_id,
        "session_name": dir_name,
        "session_dir": session_dir,
        "session_log": os.path.join(session_dir, "session.log"),
        "codex_log": os.path.join(session_dir, "codex.log"),
        "claude_log": os.path.join(session_dir, "claude.log"),
        "repo_path": repo_path,
    }


def _rebuild_rounds_done(session_dir, up_to_round):
    """Reconstroi historico de rounds a partir dos arquivos existentes."""
    rounds_done = []
    for n in range(1, up_to_round + 1):
        p = f"{n:03d}"
        admin_path = os.path.join(session_dir, f"round-{p}-admin.md")
        exec_path = os.path.join(session_dir, f"round-{p}-exec.md")
        review_path = os.path.join(session_dir, f"round-{p}-review.md")

        if not os.path.exists(admin_path):
            break

        task_text = ""
        with open(admin_path, "r", encoding="utf-8-sig") as f:
            task_text = f.read()

        exec_status = "UNKNOWN"
        if os.path.exists(exec_path):
            with open(exec_path, "r", encoding="utf-8-sig") as f:
                es, _ = parse_status(f.read(), VALID_EXEC_STATUSES)
                if es:
                    exec_status = es

        review_status = "UNKNOWN"
        if os.path.exists(review_path):
            with open(review_path, "r", encoding="utf-8-sig") as f:
                rs, _ = parse_status(f.read(), VALID_REVIEW_STATUSES)
                if rs:
                    review_status = rs

        rounds_done.append({
            "round": n,
            "exec_status": exec_status,
            "review_status": review_status,
            "task_preview": task_text[:100],
        })

    return rounds_done


def _collect_round_files(session_dir):
    """Lista todos os arquivos round-* existentes na sessao."""
    files = []
    for name in sorted(os.listdir(session_dir)):
        if name.startswith("round-"):
            files.append(name)
    return files


# === Workflow ===

def _workflow_loop(session, project_content, start_round=1, rounds_done=None,
                   resume_step="admin"):
    """Loop principal admin/executor. resume_step so afeta start_round."""
    sl = session["session_log"]
    sd = session["session_dir"]
    repo_path = session["repo_path"]

    if rounds_done is None:
        rounds_done = []
    round_files = _collect_round_files(sd)

    for round_num in range(start_round, MAX_WORKFLOW_ROUNDS + 1):
        padded = f"{round_num:03d}"
        is_partial = (round_num == start_round and resume_step != "admin")

        print()
        log(sl, f"=== ROUND {padded} ===")

        # --- Admin step ---
        if is_partial:
            # Preservar admin existente (resume)
            admin_path = os.path.join(sd, f"round-{padded}-admin.md")
            with open(admin_path, "r", encoding="utf-8-sig") as f:
                task_text = f.read().strip()
            log(sl, f"admin.md preservado (resume)")
        else:
            # Codex cria tarefa
            log(sl, f"Codex criando tarefa do round {padded}...")
            history = build_history_summary(rounds_done)
            admin_prompt = build_admin_task_prompt(project_content, round_num,
                                                  history)

            admin_result = call_codex(admin_prompt, cwd=repo_path)
            log_cli_call(session["codex_log"], "codex", admin_prompt,
                         admin_result)

            if not admin_result["ok"]:
                log(sl, f"Codex falhou ao criar tarefa. exit_code="
                    f"{admin_result['exit_code']}")
                write_final_review(session, "REVISAO_HUMANA", round_num,
                                   "Codex falhou ao criar tarefa", round_files)
                log(sl, "WORKFLOW REVISAO_HUMANA")
                return

            task_text = admin_result["stdout"].strip()
            admin_file = f"round-{padded}-admin.md"
            with open(os.path.join(sd, admin_file), "w",
                      encoding="utf-8") as f:
                f.write(task_text)
            round_files.append(admin_file)
            log(sl, f"Tarefa criada: {admin_file}")

        # --- Loop de execucao + review (com retries por reprovacao) ---
        rejection_feedback = None
        round_approved = False

        for rej in range(MAX_REJECTIONS_PER_ROUND):
            skip_exec = (is_partial and resume_step == "review" and rej == 0)

            if skip_exec:
                # Preservar exec existente (resume)
                exec_path = os.path.join(sd, f"round-{padded}-exec.md")
                with open(exec_path, "r", encoding="utf-8-sig") as f:
                    exec_response = f.read().strip()
                exec_status, exec_valid = parse_status(exec_response,
                                                       VALID_EXEC_STATUSES)
                exec_ok = exec_valid
                exec_timeout = False
                if exec_ok:
                    log(sl, f"exec.md preservado (resume, "
                        f"status={exec_status})")
                else:
                    log(sl, "exec.md existente sem status valido, "
                        "reexecutando")
                    skip_exec = False

            if not skip_exec:
                # --- Claude executa ---
                log(sl, f"Claude executando (tentativa {rej + 1}/"
                    f"{MAX_REJECTIONS_PER_ROUND})...")
                exec_prompt = build_exec_task_prompt(task_text, project_content,
                                                    rejection_feedback)

                exec_response, exec_status, exec_ok, exec_timeout = try_call_with_status(
                    call_claude, exec_prompt, repo_path, DEFAULT_TIMEOUT_S,
                    session["claude_log"], "claude", VALID_EXEC_STATUSES,
                )

                exec_file = f"round-{padded}-exec.md"
                with open(os.path.join(sd, exec_file), "w",
                          encoding="utf-8") as f:
                    f.write(exec_response)
                if rej == 0:
                    round_files.append(exec_file)

            if not exec_ok:
                if exec_timeout:
                    log(sl, f"TIMEOUT: Claude estourou timeout de "
                        f"{DEFAULT_TIMEOUT_S}s na execucao do round {padded}")
                    stop = f"Timeout do executor no round {padded}"
                else:
                    log(sl, "Claude status invalido mesmo apos correcao")
                    stop = "Status invalido do executor"
                write_final_review(session, "REVISAO_HUMANA", round_num,
                                   stop, round_files)
                log(sl, "WORKFLOW REVISAO_HUMANA")
                return

            log(sl, f"Claude status: {exec_status}")

            if exec_status in ("BLOCKED", "NEEDS_HUMAN"):
                log(sl, f"Claude pediu {exec_status}")
                rounds_done.append({"round": round_num,
                                    "exec_status": exec_status,
                                    "review_status": "N/A",
                                    "task_preview": task_text[:100]})
                write_final_review(session, "REVISAO_HUMANA", round_num,
                                   f"Executor: {exec_status}", round_files)
                log(sl, "WORKFLOW REVISAO_HUMANA")
                return

            # --- Codex julga ---
            log(sl, "Codex julgando execucao...")
            review_prompt = build_admin_review_prompt(project_content,
                                                     task_text, exec_response)

            review_response, review_status, review_ok, review_timeout = try_call_with_status(
                call_codex, review_prompt, repo_path, DEFAULT_TIMEOUT_S,
                session["codex_log"], "codex", VALID_REVIEW_STATUSES,
            )

            review_file = f"round-{padded}-review.md"
            with open(os.path.join(sd, review_file), "w",
                      encoding="utf-8") as f:
                f.write(review_response)
            if rej == 0:
                round_files.append(review_file)

            if not review_ok:
                if review_timeout:
                    log(sl, f"TIMEOUT: Codex estourou timeout de "
                        f"{DEFAULT_TIMEOUT_S}s no julgamento do round {padded}")
                    stop = f"Timeout do admin no round {padded}"
                else:
                    log(sl, "Codex status invalido mesmo apos correcao")
                    stop = "Status invalido do admin"
                write_final_review(session, "REVISAO_HUMANA", round_num,
                                   stop, round_files)
                log(sl, "WORKFLOW REVISAO_HUMANA")
                return

            log(sl, f"Codex status: {review_status}")

            round_entry = {"round": round_num, "exec_status": exec_status,
                           "review_status": review_status,
                           "task_preview": task_text[:100]}

            if review_status == "CONCLUIDO":
                rounds_done.append(round_entry)
                write_final_review(session, "CONCLUIDO", round_num,
                                   "Projeto concluido pelo administrador",
                                   round_files)
                print()
                log(sl, "WORKFLOW CONCLUIDO")
                return

            if review_status == "APROVADO":
                rounds_done.append(round_entry)
                log(sl, f"Round {padded} aprovado")
                round_approved = True
                break

            if review_status == "REVISAO_HUMANA":
                rounds_done.append(round_entry)
                write_final_review(session, "REVISAO_HUMANA", round_num,
                                   "Admin pediu revisao humana", round_files)
                log(sl, "WORKFLOW REVISAO_HUMANA")
                return

            if review_status == "REPROVADO":
                log(sl, f"Round {padded} reprovado (tentativa {rej + 1})")
                rejection_feedback = review_response

        if not round_approved:
            rounds_done.append({"round": round_num, "exec_status": "EXECUTED",
                                "review_status": "REPROVADO",
                                "task_preview": task_text[:100]})
            log(sl, f"Limite de {MAX_REJECTIONS_PER_ROUND} reprovacoes no "
                f"round {padded}")
            write_final_review(session, "REVISAO_HUMANA", round_num,
                               f"Limite de reprovacoes no round {padded}",
                               round_files)
            log(sl, "WORKFLOW REVISAO_HUMANA")
            return

    log(sl, f"Limite de {MAX_WORKFLOW_ROUNDS} rounds atingido")
    write_final_review(session, "REVISAO_HUMANA", MAX_WORKFLOW_ROUNDS,
                       "Limite de rounds atingido",
                       _collect_round_files(sd))
    log(sl, "WORKFLOW REVISAO_HUMANA")


# === DUMB-PIPE WORKFLOW (V2) ===
# O orquestrador aqui e apenas transportador. Nao parseia status,
# nao injeta regras, nao impoe limite de reprovacao. Roteia texto verbatim
# entre Codex (admin) e Claude (executor). Para quando:
#   - Codex escreve CONCLUIDO em qualquer lugar do texto
#   - Atinge limite de 15 rodadas seguidas sem CONCLUIDO
#   - CLI trava (watchdog de ociosidade) com escalada
#   - Ctrl+C

MAX_DUMB_ROUNDS = 15
# Os CLIs do Claude/Codex rodam em modo buffered (-p nao streama), entao
# "ocioso" baseado em stdout e falso positivo: nao escrevem nada ate terminar.
# Para o Claude (stream-json), usamos um watchdog inteligente baseado na
# mtime do arquivo .jsonl da sessao: enquanto Claude esta trabalhando,
# ele appenda eventos no jsonl. Se o jsonl nao muda ha JSONL_IDLE_S
# segundos, consideramos travado de verdade.
WATCHDOG_IDLE_S = 3600     # 60 min sem output stdout (fallback p/ codex)
WATCHDOG_HARD_S = 3600     # (legado) teto absoluto — NAO mais aplicado quando ha atividade real no stream Claude
WATCHDOG_NUDGE_TRIES = 3   # ate 3 cutucadas antes de escalar
JSONL_IDLE_S = 1800        # 30 min sem sinal de vida = travou de verdade (fases I/O pesadas)
JSONL_POLL_S = 5           # poll a cada 5s

# V2.3 hotfix watchdog (2026-04-15):
# - call longa do Claude NAO morre mais por relogio absoluto
# - so morre por stall real (ambos sinais parados por > STALL_KILL_S)
# - heartbeat a cada HEARTBEAT_INTERVAL_S atualiza session-state + lock
# - RECENT_ACTIVITY_S define janela de "atividade recente"
RECENT_ACTIVITY_S = 180        # 3 min de folga sobre queries p95 observadas
STALL_KILL_S = 1800            # 30 min de inatividade dupla = stall real
HEARTBEAT_INTERVAL_S = 30      # atualiza observabilidade a cada 30s
STOP_SENTINEL_NAME = "STOP"    # arquivo-sentinela para kill-switch humano

CONCLUIDO_MARKER = "CONCLUIDO"
HUMANO_MARKER = "HUMANO"


def _decide_liveness(now, last_stream_event_at, last_jsonl_mtime,
                     recent_activity_s=RECENT_ACTIVITY_S,
                     stall_kill_s=STALL_KILL_S):
    """Helper puro (testavel) que decide o estado de vida de uma call do Claude.

    Retorna um dict com:
      - idle_s: segundos desde o sinal de vida mais recente
      - had_recent_activity: houve atividade nos ultimos `recent_activity_s`
      - is_stall: inatividade DUPLA (stream+jsonl) por mais de `stall_kill_s`
    """
    stream_at = last_stream_event_at or 0
    jsonl_at = last_jsonl_mtime or 0
    most_recent = max(stream_at, jsonl_at)
    idle_s = max(0.0, now - most_recent) if most_recent else 0.0
    return {
        "idle_s": idle_s,
        "had_recent_activity": idle_s <= recent_activity_s,
        "is_stall": idle_s > stall_kill_s,
    }


def _has_marker(text, marker):
    """V2.3: detecta marcador (CONCLUIDO/HUMANO) de forma robusta.

    So retorna True se o marcador aparece como LINHA marker:
    - linha contendo apenas o marker, possivelmente entre aspas/**
    - linha com prefixo STATUS:, FINAL:, DECISAO:, etc.
    - marker no comeco de paragrafo seguido de explicacao curta

    NAO trigger em textos como "Nao chame parcial de concluido" ou
    "escreva CONCLUIDO se terminar" (instrucoes pro outro agente).
    """
    if not text:
        return False
    up = text.upper()
    # Patterns de linha marker (exigem que o marker esteja "isolado")
    patterns = [
        rf"^\s*[*_`\"']*{marker}[*_`\"'.!]*\s*$",        # linha sozinha
        rf"^\s*STATUS:\s*{marker}\b",                     # STATUS: MARKER
        rf"^\s*FINAL:\s*{marker}\b",
        rf"^\s*DECISAO:\s*{marker}\b",
        rf"^\s*RESPOSTA:\s*{marker}\b",
        rf"^\s*\**\s*{marker}\s*\**\s*[—:.-]",            # **MARKER**: ou MARKER — ...
    ]
    for line in up.splitlines():
        for pat in patterns:
            if re.match(pat, line):
                return True
    return False
LOOP_DETECTION_WINDOW = 2   # 2 respostas curtas similares seguidas
LOOP_DETECTION_MAX_LEN = 200  # so considera "curta" se < 200 chars

BOOTSTRAP_PROMPT_TEMPLATE = (
    "Leia o brief abaixo. Comprove que entendeu tudo que esta nesse projeto "
    "e que esta pronto para executar esse trabalho. Nao execute ainda, so "
    "apos minha ordem.\n\n"
    "=== BRIEF ===\n{brief}\n=== FIM DO BRIEF ==="
)

CLAUDE_ACTIVATION_PROMPT = (
    "Voce e o executor deste projeto. O Codex e o administrador — ele vai "
    "te mandar prompts, voce executa com eficiencia e responde. Ele aprova "
    "ou reprova. Se reprovar, corrija e reenvie ate aprovar. Se aprovar, "
    "aguarde o proximo prompt dele. Nao altere definicoes do projeto, nao "
    "invente metricas ou KPIs — execute o que for pedido. Quando o projeto "
    "inteiro terminar, o Codex avisa."
)


CODEX_ACTIVATION_PROMPT_TEMPLATE = (
    "Voce e o admin deste projeto. Sua funcao e preservar o projeto ate o "
    "fim. Vai perguntar ao Claude, receber respostas, aprovar ou reprovar "
    "cada fase e mandar novos prompts ate o Claude entender e executar "
    "perfeitamente e aprovar cada fase antes de passar para a proxima.\n\n"
    "Marcadores para o orquestrador (escreva em qualquer lugar da sua resposta):\n"
    "- Escreva CONCLUIDO quando o projeto inteiro estiver pronto e validado. "
    "O orquestrador encerra o workflow.\n"
    "- Escreva HUMANO quando voce precisar de intervencao humana para "
    "prosseguir (credencial, acesso, decisao que so o humano toma, "
    "ou qualquer bloqueio externo). O orquestrador para e chama o humano. "
    "NUNCA fique repetindo 'aguardando' em varios turnos — se precisar "
    "esperar algo que so o humano resolve, escreva HUMANO de uma vez.\n\n"
    "=== RESPOSTA DO CLAUDE AO BRIEF ===\n{claude_reply}\n=== FIM ===\n\n"
    "Agora dirija o projeto. Mande o primeiro prompt ao Claude."
)


def _detect_loop(codex_history):
    """Detecta loop: duas ultimas respostas do codex curtas e muito similares."""
    if len(codex_history) < LOOP_DETECTION_WINDOW:
        return False
    last = codex_history[-LOOP_DETECTION_WINDOW:]
    # todas precisam ser curtas
    if any(len(t or "") > LOOP_DETECTION_MAX_LEN for t in last):
        return False
    # normaliza e compara
    def _norm(t):
        return re.sub(r"\s+", " ", (t or "").lower()).strip()
    normalized = [_norm(t) for t in last]
    first = normalized[0]
    if not first:
        return False
    # todas identicas OU todas contendo as mesmas 3 primeiras palavras
    if all(n == first for n in normalized):
        return True
    head = " ".join(first.split()[:3])
    if head and all(n.startswith(head) for n in normalized):
        return True
    return False


def _new_uuid():
    import uuid as _uuid
    return str(_uuid.uuid4())


def _kill_process_tree(proc):
    """Mata o processo e seus filhos no Windows via taskkill."""
    try:
        if proc.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _snapshot_codex_sessions():
    base = os.path.expanduser("~/.codex/sessions")
    out = set()
    if not os.path.isdir(base):
        return out
    for root, _, names in os.walk(base):
        for n in names:
            if n.endswith(".jsonl"):
                out.add(os.path.join(root, n))
    return out


def _extract_codex_session_uuid(path):
    m = re.search(
        r"rollout-[\dT\-]+-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl",
        os.path.basename(path),
    )
    return m.group(1) if m else None


def _find_new_codex_session(before, after):
    new = after - before
    if not new:
        return None
    newest = max(new, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0)
    return _extract_codex_session_uuid(newest)


def run_command_watchdog(args, input_text=None, cwd=None,
                         idle_seconds=WATCHDOG_IDLE_S,
                         hard_seconds=WATCHDOG_HARD_S):
    """Executa comando com watchdog de ociosidade em stdout.

    Se stdout fica idle_seconds sem escrever nada, mata o processo e retorna
    idle_kill=True. Se ultrapassa hard_seconds de tempo total, hard_kill=True.
    Retorna dict semelhante a run_command.
    """
    import threading as _threading
    import time as _time

    start = _time.time()
    creationflags = 0
    if os.name == "nt":
        # Permite matar a arvore toda de processos (cmd.exe + filhos)
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            shell=False,
            bufsize=0,
            creationflags=creationflags,
        )
    except Exception as e:
        return {
            "ok": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": f"(falha ao spawnar: {e})",
            "duration_ms": 0,
            "timed_out": False,
            "idle_kill": False,
            "hard_kill": False,
            "args": args,
        }

    if input_text is not None:
        try:
            proc.stdin.write(input_text.encode("utf-8", "replace"))
            proc.stdin.close()
        except Exception:
            pass

    out_chunks = []
    err_chunks = []
    last_activity = [_time.time()]

    def _reader(pipe, bucket):
        try:
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                bucket.append(chunk)
                last_activity[0] = _time.time()
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    t_out = _threading.Thread(target=_reader, args=(proc.stdout, out_chunks), daemon=True)
    t_err = _threading.Thread(target=_reader, args=(proc.stderr, err_chunks), daemon=True)
    t_out.start()
    t_err.start()

    idle_kill = False
    hard_kill = False
    while True:
        code = proc.poll()
        if code is not None:
            break
        now = _time.time()
        if now - last_activity[0] > idle_seconds:
            idle_kill = True
            _kill_process_tree(proc)
            break
        if now - start > hard_seconds:
            hard_kill = True
            _kill_process_tree(proc)
            break
        _time.sleep(2)

    try:
        proc.wait(timeout=5)
    except Exception:
        pass
    t_out.join(timeout=3)
    t_err.join(timeout=3)

    stdout = b"".join(out_chunks).decode("utf-8", "replace")
    stderr = b"".join(err_chunks).decode("utf-8", "replace")
    exit_code = proc.returncode if proc.returncode is not None else -1
    duration_ms = int((_time.time() - start) * 1000)

    ok = (exit_code == 0 and not idle_kill and not hard_kill)

    return {
        "ok": ok,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": duration_ms,
        "timed_out": idle_kill or hard_kill,
        "idle_kill": idle_kill,
        "hard_kill": hard_kill,
        "args": args,
    }


def _call_claude_session(session_uuid, message, cwd, first_call):
    """[DESUSADO] Respawn a cada call. Mantido apenas como fallback.

    O fluxo principal agora usa ClaudeStreamSession (processo vivo
    stream-json) para evitar cold-start crescente em sessoes longas.
    """
    claude_path = check_cli("claude") or "claude"
    if first_call:
        args = ["cmd", "/c", claude_path, "-p", "--dangerously-skip-permissions",
                "--session-id", session_uuid]
    else:
        args = ["cmd", "/c", claude_path, "-p", "--dangerously-skip-permissions",
                "--resume", session_uuid]
    return run_command_watchdog(args, input_text=message, cwd=cwd)


class ClaudeStreamSession:
    """Processo longo-vivo do Claude Code em modo stream-json.

    Mantem 1 unico processo `claude -p --input-format stream-json
    --output-format stream-json ...` ligado durante todo o workflow.
    Cada mensagem do admin vira 1 linha JSON no stdin; cada turno completo
    do Claude termina com um evento `{"type":"result"}` no stdout, de onde
    extraimos o texto final.

    Isso elimina o cold-start crescente dos calls com `--resume`.
    """

    def __init__(self, session_uuid, cwd):
        import queue as _queue
        import time as _time
        self.session_uuid = session_uuid
        self.cwd = cwd
        self.proc = None
        self.response_queue = _queue.Queue()
        self.reader_thread = None
        self.stderr_thread = None
        self.stderr_buffer = []
        self.alive = False
        self.init_event = None
        # heartbeat: ultima vez que vimos qualquer evento no stream (assistant,
        # tool_use, system, etc.). Atualizado por _handle_event. E usado por
        # send() como sinal de vida independente do arquivo JSONL.
        self.last_event_at = _time.time()

    def start(self, timeout_init_s=60):
        import threading as _threading
        claude_path = check_cli("claude") or "claude"
        args = [
            "cmd", "/c", claude_path,
            "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--session-id", self.session_uuid,
        ]
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self.proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.cwd,
            shell=False,
            bufsize=0,
            creationflags=creationflags,
        )
        self.alive = True
        self.args_used = args
        self.reader_thread = _threading.Thread(
            target=self._read_stdout, daemon=True)
        self.reader_thread.start()
        self.stderr_thread = _threading.Thread(
            target=self._read_stderr, daemon=True)
        self.stderr_thread.start()
        # Opcional: aguardar evento system init (nao bloqueia hard — ignora se nao vier)
        import time as _time
        deadline = _time.time() + timeout_init_s
        while _time.time() < deadline:
            if self.init_event is not None:
                break
            if not self.alive:
                break
            _time.sleep(0.1)

    def _read_stdout(self):
        try:
            buf = b""
            while True:
                chunk = self.proc.stdout.read(4096)
                if not chunk:
                    break
                buf += chunk
                # processa linhas completas
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line.decode("utf-8", "replace"))
                    except Exception:
                        continue
                    self._handle_event(event)
        except Exception as e:
            self.response_queue.put(("error", "", {"msg": f"reader: {e}"}))
        finally:
            self.alive = False
            # sinaliza eventual send pendente
            self.response_queue.put(("closed", "", None))

    def _handle_event(self, event):
        import time as _time
        # Qualquer evento = sinal de vida do Claude
        self.last_event_at = _time.time()
        etype = event.get("type")
        if etype == "system" and self.init_event is None:
            self.init_event = event
            return
        if etype == "result":
            # turno terminou
            text = event.get("result")
            if text is None:
                msg = event.get("message") or {}
                if isinstance(msg, dict):
                    content = msg.get("content")
                    if isinstance(content, list):
                        parts = []
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                parts.append(c.get("text", ""))
                        text = "\n".join(parts)
                    elif isinstance(content, str):
                        text = content
            if not isinstance(text, str):
                text = str(text) if text is not None else ""
            self.response_queue.put(("result", text, event))
        elif etype == "error":
            self.response_queue.put(("error", "", event))

    def _read_stderr(self):
        try:
            while True:
                chunk = self.proc.stderr.read(4096)
                if not chunk:
                    break
                self.stderr_buffer.append(chunk.decode("utf-8", "replace"))
        except Exception:
            pass

    def send(self, message_text, timeout_s=WATCHDOG_HARD_S,
             on_heartbeat=None, stop_requested=None):
        """Envia mensagem do user e espera pelo evento 'result'.

        V2.3 hotfix (2026-04-15):
        - NAO mata mais call longa por relogio absoluto (`timeout_s` e ignorado
          quando ha atividade real recente). Parametro mantido por compatibilidade.
        - `on_heartbeat(info)` e chamado a cada HEARTBEAT_INTERVAL_S enquanto
          a call esta viva. `info` traz metadados para persistir no
          session-state.json (observabilidade de long-run).
        - `stop_requested()` e consultado no mesmo ciclo; se retornar True,
          a call retorna graciosamente com `user_abort=True` (kill-switch
          manual via arquivo STOP, sem virar retry cego).
        - idle_kill so dispara por inatividade DUPLA (stream + jsonl) por
          mais de STALL_KILL_S segundos.
        """
        import time as _time
        import queue as _queue

        start = _time.time()
        if not self.alive or not self.proc or self.proc.poll() is not None:
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "claude stream session nao esta viva",
                "duration_ms": 0,
                "timed_out": False,
                "idle_kill": False,
                "hard_kill": False,
                "user_abort": False,
                "args": getattr(self, "args_used", []),
            }

        # drena eventos pendentes
        while not self.response_queue.empty():
            try:
                self.response_queue.get_nowait()
            except Exception:
                break

        payload = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": message_text},
        }) + "\n"
        try:
            self.proc.stdin.write(payload.encode("utf-8"))
            self.proc.stdin.flush()
        except Exception as e:
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"falha ao escrever stdin: {e}",
                "duration_ms": int((_time.time() - start) * 1000),
                "timed_out": False,
                "idle_kill": False,
                "hard_kill": False,
                "user_abort": False,
                "args": self.args_used,
            }

        # Polling inteligente com 2 sinais de vida, combinados (OR):
        #   (a) stream heartbeat: ultima vez que vimos QUALQUER evento no stream
        #   (b) jsonl mtime: ultima vez que o arquivo JSONL da sessao mudou
        # idle_kill so dispara se AMBOS ficarem mais velhos que STALL_KILL_S.
        jsonl_path = self._find_session_jsonl()
        last_jsonl_mtime = self._jsonl_mtime(jsonl_path)
        # reset heartbeat no inicio do turno
        self.last_event_at = _time.time()
        last_heartbeat_call = 0.0
        kind = text = raw = None
        while True:
            try:
                kind, text, raw = self.response_queue.get(timeout=JSONL_POLL_S)
                break  # got result/error event
            except _queue.Empty:
                pass
            now = _time.time()
            # processo Claude morreu no meio do caminho?
            if self.proc is not None and self.proc.poll() is not None:
                return {
                    "ok": False,
                    "exit_code": self.proc.returncode if self.proc else -1,
                    "stdout": "",
                    "stderr": "processo claude morreu durante a espera",
                    "duration_ms": int((now - start) * 1000),
                    "timed_out": False,
                    "idle_kill": False,
                    "hard_kill": True,
                    "user_abort": False,
                    "needs_restart": True,
                    "args": self.args_used,
                }
            # atualiza referencia do jsonl
            if jsonl_path is None:
                jsonl_path = self._find_session_jsonl()
            cur_mtime = self._jsonl_mtime(jsonl_path)
            if cur_mtime is not None and cur_mtime != last_jsonl_mtime:
                last_jsonl_mtime = cur_mtime
            # combina sinais de vida
            jsonl_alive_at = cur_mtime if cur_mtime is not None else 0
            event_alive_at = self.last_event_at
            most_recent_alive = max(jsonl_alive_at, event_alive_at)
            idle_s = now - most_recent_alive
            duration_s = now - start
            had_recent_activity = idle_s <= RECENT_ACTIVITY_S
            # kill-switch humano (arquivo STOP)
            if stop_requested is not None:
                try:
                    if stop_requested():
                        return {
                            "ok": False,
                            "exit_code": -1,
                            "stdout": "",
                            "stderr": "STOP sentinel requested by human",
                            "duration_ms": int((now - start) * 1000),
                            "timed_out": False,
                            "idle_kill": False,
                            "hard_kill": False,
                            "user_abort": True,
                            "args": self.args_used,
                        }
                except Exception:
                    pass
            # heartbeat periodico para observabilidade
            if on_heartbeat is not None and (now - last_heartbeat_call) >= HEARTBEAT_INTERVAL_S:
                last_heartbeat_call = now
                status = "long_running" if duration_s >= 600 else "in_call"
                try:
                    on_heartbeat({
                        "active_agent": "claude",
                        "active_call_status": status,
                        "active_call_started_at": start,
                        "duration_s": duration_s,
                        "idle_s": idle_s,
                        "had_recent_activity": had_recent_activity,
                        "last_stream_event_at": event_alive_at,
                        "last_jsonl_mtime": cur_mtime,
                    })
                except Exception:
                    pass
            # stall real: AMBOS sinais parados por mais de STALL_KILL_S
            if idle_s > STALL_KILL_S:
                return {
                    "ok": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": (f"claude stall real: sem sinal de vida ha "
                               f"{int(idle_s)}s (stream+jsonl) apos {int(duration_s)}s"),
                    "duration_ms": int((now - start) * 1000),
                    "timed_out": True,
                    "idle_kill": True,
                    "hard_kill": False,
                    "user_abort": False,
                    "args": self.args_used,
                }
            # NOTA: nao existe mais teto absoluto. Call longa com atividade
            # recente continua viva indefinidamente. Unicos caminhos de kill:
            #   - processo morto (hard_kill acima)
            #   - stall real por inatividade dupla (idle_kill acima)
            #   - STOP sentinel humano (user_abort acima)

        duration_ms = int((_time.time() - start) * 1000)
        if kind == "result":
            return {
                "ok": True,
                "exit_code": 0,
                "stdout": text or "",
                "stderr": "",
                "duration_ms": duration_ms,
                "timed_out": False,
                "idle_kill": False,
                "hard_kill": False,
                "user_abort": False,
                "args": self.args_used,
            }
        elif kind == "closed":
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "processo do claude encerrou",
                "duration_ms": duration_ms,
                "timed_out": False,
                "idle_kill": False,
                "hard_kill": False,
                "user_abort": False,
                "args": self.args_used,
            }
        else:
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": text or "",
                "stderr": json.dumps(raw) if raw else kind,
                "duration_ms": duration_ms,
                "timed_out": False,
                "idle_kill": False,
                "hard_kill": False,
                "user_abort": False,
                "args": self.args_used,
            }

    def close(self):
        if self.proc is None:
            return
        try:
            if self.proc.stdin:
                try:
                    self.proc.stdin.close()
                except Exception:
                    pass
            if self.proc.poll() is None:
                try:
                    self.proc.wait(timeout=5)
                except Exception:
                    _kill_process_tree(self.proc)
        finally:
            self.alive = False

    def restart(self):
        """Mata o processo atual e spawna um novo com o MESMO session_uuid.
        O --session-id continua apontando pro mesmo jsonl no disco, entao o
        proximo send() retoma a conversa de onde parou.
        """
        import queue as _queue
        import time as _time
        try:
            self.close()
        except Exception:
            pass
        self.proc = None
        self.response_queue = _queue.Queue()
        self.reader_thread = None
        self.stderr_thread = None
        self.stderr_buffer = []
        self.alive = False
        self.init_event = None
        self.last_event_at = _time.time()
        # nao rehidrata cache de jsonl — sera re-descoberto
        if hasattr(self, "_cached_jsonl"):
            del self._cached_jsonl
        self.start()

    def _find_session_jsonl(self):
        """Localiza o arquivo JSONL da sessao do Claude no disco."""
        if hasattr(self, "_cached_jsonl") and self._cached_jsonl:
            return self._cached_jsonl
        # Caminho padrao no Windows: ~/.claude/projects/<encoded-cwd>/<uuid>.jsonl
        base = os.path.expanduser("~/.claude/projects")
        if not os.path.isdir(base):
            return None
        # encoded cwd e o cwd com / e \ trocados por --
        try:
            for proj_dir in os.listdir(base):
                full = os.path.join(base, proj_dir)
                if not os.path.isdir(full):
                    continue
                candidate = os.path.join(full, f"{self.session_uuid}.jsonl")
                if os.path.isfile(candidate):
                    self._cached_jsonl = candidate
                    return candidate
        except Exception:
            pass
        return None

    def _jsonl_mtime(self, path):
        if not path:
            return None
        try:
            return os.path.getmtime(path)
        except Exception:
            return None


def _call_codex_session(codex_uuid_ref, message, cwd, first_call,
                        multi_mode=False):
    """Chama o Codex. V2.6: multi_mode usa lock de bootstrap e nunca --last."""
    codex_path = check_cli("codex") or "codex"
    if first_call:
        # V2.6: lock curto para evitar captura de UUID errado em multi
        lock_acquired = False
        if multi_mode:
            lock_acquired = _acquire_codex_bootstrap_lock()
            if not lock_acquired:
                return {
                    "ok": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "multi_mode: timeout ao adquirir codex_bootstrap.lock",
                    "duration_ms": 0,
                    "timed_out": False,
                    "args": [],
                }
        try:
            before = _snapshot_codex_sessions()
            args = ["cmd", "/c", codex_path, "exec",
                    "--dangerously-bypass-approvals-and-sandbox", "-C", cwd]
            result = run_command_watchdog(args, input_text=message, cwd=cwd)
            after = _snapshot_codex_sessions()
            new_uuid = _find_new_codex_session(before, after)
            codex_uuid_ref[0] = new_uuid
        finally:
            if multi_mode and lock_acquired:
                _release_codex_bootstrap_lock()
        return result
    else:
        sid = codex_uuid_ref[0]
        # codex exec resume NAO aceita -C; herda cwd do processo.
        if sid:
            args = ["cmd", "/c", codex_path, "exec", "resume", sid,
                    "--dangerously-bypass-approvals-and-sandbox"]
        elif multi_mode:
            # V2.6: em multi, NUNCA usar --last (pode pegar sessao errada)
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "multi_mode: codex UUID nao capturado e --last proibido",
                "duration_ms": 0,
                "timed_out": False,
                "args": [],
            }
        else:
            # Sem uuid capturado: usa --last como fallback (modo single)
            args = ["cmd", "/c", codex_path, "exec", "resume", "--last",
                    "--dangerously-bypass-approvals-and-sandbox"]
        return run_command_watchdog(args, input_text=message, cwd=cwd)


def _agent_call_with_nudge(sl, log_file, agent_name, call_fn, message, cwd,
                           stream_session=None):
    """Chama o agente. Se der idle/hard kill, tenta ate WATCHDOG_NUDGE_TRIES
    cutucoes adicionais antes de escalar.

    Se `stream_session` for passado (ClaudeStreamSession), antes de cada
    cutucada reinicia o processo caso ele tenha morrido ou o turno tenha
    sido encerrado — isso evita enviar cutucada pra stdin de processo zumbi
    e tambem impede que a cutucada restarte trabalho em andamento.

    A cutucada e um PROBE curto ("ainda ta trabalhando?"), nao um
    reenvio do prompt original — evita que o agente reinicie a tarefa.

    Retorna (stdout, ok, reason).
    """
    result = call_fn(message, cwd=cwd)
    log_cli_call(log_file, agent_name, message, result)
    if result["ok"]:
        return result["stdout"], True, None

    for n in range(1, WATCHDOG_NUDGE_TRIES + 1):
        if result.get("idle_kill"):
            reason = f"idle (sem sinal de vida)"
        elif result.get("hard_kill"):
            reason = f"hard timeout"
        else:
            reason = f"exit_code={result.get('exit_code')}"
        log(sl, f"{agent_name} parou: {reason}. Cutucada {n}/{WATCHDOG_NUDGE_TRIES}...")

        # Se for o stream do Claude e o processo morreu, reinicia antes de cutucar
        if stream_session is not None:
            proc_dead = (stream_session.proc is None or
                         (stream_session.proc.poll() is not None))
            if proc_dead or result.get("needs_restart"):
                log(sl, f"{agent_name}: processo morto, reiniciando stream...")
                try:
                    stream_session.restart()
                    log(sl, f"{agent_name}: stream reiniciado")
                except Exception as e:
                    log(sl, f"{agent_name}: falha ao reiniciar stream: {e}")

        # Probe curto, nao reenvia a tarefa
        nudge = (
            "Voce ainda esta trabalhando nessa tarefa? Se SIM, responda apenas "
            "'AINDA TRABALHANDO' e continue. Se ja terminou, envie a resposta "
            "final agora. Se travou, explique o bloqueio em 1 linha."
        )
        result = call_fn(nudge, cwd=cwd)
        log_cli_call(log_file, agent_name, nudge, result)
        if result["ok"]:
            # Se o probe devolver "AINDA TRABALHANDO", espera mais um turno
            # para ele terminar de fato
            resp = (result.get("stdout") or "").upper()
            if "AINDA TRABALHANDO" in resp and n < WATCHDOG_NUDGE_TRIES:
                log(sl, f"{agent_name} confirmou que ainda esta trabalhando, aguardando mais um turno")
                result = call_fn(
                    "Continue de onde parou. Quando terminar, envie a resposta final.",
                    cwd=cwd,
                )
                log_cli_call(log_file, agent_name, "(continue)", result)
                if result["ok"]:
                    return result["stdout"], True, None
                # se travar de novo, segue loop
                continue
            return result["stdout"], True, None

    return result.get("stdout", ""), False, "travou apos cutucadas"


# === Classificacao de erros e retry (V2.3) ===

# Flag global de interrupcao para Ctrl+C cooperativo durante sleep.
_interrupt_flag = {"set": False}


def _sleep_interruptible(seconds):
    """Dorme em steps de 1s; se _interrupt_flag['set'] ou KeyboardInterrupt, retorna cedo.

    Retorna True se dormiu todo o tempo, False se foi interrompido."""
    import time as _time
    end = _time.time() + seconds
    try:
        while _time.time() < end:
            if _interrupt_flag["set"]:
                return False
            _time.sleep(1)
    except KeyboardInterrupt:
        _interrupt_flag["set"] = True
        return False
    return True


def _classify_error(result):
    """Classifica o resultado de uma call como QUOTA, TRANSIENT, UNKNOWN,
    USER_ABORT ou OK.

    Retorna: 'OK' | 'QUOTA' | 'TRANSIENT' | 'UNKNOWN' | 'USER_ABORT'

    Sinais considerados:
    - `ok=True` → OK
    - `user_abort=True` (STOP sentinel humano) → USER_ABORT (nao retentar)
    - stdout/stderr com padroes de credito/billing → QUOTA (backoff proprio)
    - stdout/stderr com padroes de erro transitorio → TRANSIENT
    - process death (hard_kill + needs_restart) → TRANSIENT (sera reiniciado)
    - stall real (idle_kill por inatividade dupla) → TRANSIENT
    - exit_code != 0 sem padrao conhecido → UNKNOWN

    NOTA (V2.3 hotfix): "hard timeout 3600s" nao existe mais como causa de
    matar call ativa; call longa com atividade real continua viva.
    NOTA (V2.7): QUOTA e checada ANTES de TRANSIENT porque e mais especifica.
    """
    if result.get("ok"):
        return "OK"

    if result.get("user_abort"):
        return "USER_ABORT"

    joined = ((result.get("stdout") or "") + "\n" +
              (result.get("stderr") or "")).lower()

    # V2.7: QUOTA primeiro (mais especifico que TRANSIENT).
    for pat in QUOTA_ERROR_PATTERNS:
        if re.search(pat, joined, flags=re.IGNORECASE):
            return "QUOTA"

    for pat in TRANSIENT_ERROR_PATTERNS:
        if re.search(pat, joined, flags=re.IGNORECASE):
            return "TRANSIENT"

    # process death e stall real sao transitorios tratados pelo wrapper
    if result.get("idle_kill") or result.get("hard_kill"):
        return "TRANSIENT"

    return "UNKNOWN"


def _quota_health_ping(agent_name, sl):
    """V2.7: ping barato pra checar se os creditos voltaram.

    Faz uma chamada minima (`ok`) ao agente. Retorna:
    - True se a API respondeu (qualquer classificacao != QUOTA, inclusive OK
      ou TRANSIENT — a call real vai tentar de novo e o problema persistente
      aparece la).
    - False se ainda bate em QUOTA.

    Nao e recursivo: se o ping falhar por excecao (rede ausente, binario
    missing, etc) assumimos pessimista que quota ainda esta esgotada, pra
    nao sair do backoff cedo demais.
    """
    try:
        if agent_name == "codex":
            result = call_codex("ok", timeout_s=QUOTA_HEALTH_PING_TIMEOUT_S)
        else:
            result = call_claude("ok", timeout_s=QUOTA_HEALTH_PING_TIMEOUT_S)
    except Exception as e:
        log(sl, f"quota_ping({agent_name}): excecao {type(e).__name__}: {e}. "
                f"Tratando como quota ainda esgotada.")
        return False
    cls = _classify_error(result)
    if cls == "QUOTA":
        preview = ((result.get("stderr") or result.get("stdout") or "")[:80]
                   ).replace("\n", " ")
        log(sl, f"quota_ping({agent_name}): ainda QUOTA. Motivo: {preview}")
        return False
    log(sl, f"quota_ping({agent_name}): API respondeu (cls={cls}). "
            f"Creditos parecem OK. Retomando a call real.")
    return True


def _call_with_retry(call_fn, message, cwd, session_state, repo_path,
                     run_label, agent_name, log_file, sl, stream_session=None):
    """V2.3/V2.7: wrapper que encapsula retry classificado.

    - QUOTA (V2.7): backoff proprio (1m/10m/30m/30m...) com health-ping entre
      tentativas. Se ping responder, retoma imediatamente. Retry infinito.
    - Erro transitorio: retry infinito com backoff (RETRY_BACKOFF_SCHEDULE_S).
      Estado vai para RETRY_BACKOFF. Reset do contador em sucesso.
    - Erro desconhecido: ate UNKNOWN_ERROR_RETRY_LIMIT tentativas. Depois,
      estado vai para PAUSED_RECOVERABLE e levanta RecoverablePauseError.
    - Ctrl+C a qualquer momento: levanta KeyboardInterrupt.

    Retorna o stdout da call bem sucedida.
    """
    attempt = 0
    quota_attempt = 0
    unknown_count = 0
    while True:
        if _interrupt_flag["set"]:
            raise KeyboardInterrupt()
        # Se processo morto e stream_session, reinicia primeiro
        if stream_session is not None:
            proc_dead = (stream_session.proc is None or
                         (stream_session.proc.poll() is not None))
            if proc_dead:
                log(sl, f"{agent_name}: processo morto, reiniciando stream...")
                try:
                    stream_session.restart()
                    log(sl, f"{agent_name}: stream reiniciado")
                except Exception as e:
                    log(sl, f"{agent_name}: falha ao reiniciar stream: {e}")

        result = call_fn(message, cwd=cwd)
        log_cli_call(log_file, agent_name, message, result)
        cls = _classify_error(result)

        if cls == "OK":
            # Sucesso: reset contadores (inclui quota V2.7)
            if session_state is not None:
                reset_fields = dict(retry_count=0, unknown_error_count=0,
                                    next_retry_at=None)
                # V2.7: se estavamos em QUOTA, limpa estado de quota tambem
                if quota_attempt > 0 or session_state.data.get("quota_attempt"):
                    reset_fields.update(
                        quota_attempt=0,
                        quota_since=None,
                        quota_last_error=None,
                        quota_next_ping_at=None,
                    )
                session_state.set(**reset_fields)
                if session_state.state == STATE_RETRY_BACKOFF:
                    session_state.transition(STATE_RUNNING)
                    update_lock(repo_path, session_state.session_id,
                                run_label, STATE_RUNNING)
            return result["stdout"]

        if cls == "USER_ABORT":
            # Kill-switch humano: NAO retentar. Pausa recuperavel ate `continue`.
            reason = (result.get("stderr") or "STOP sentinel requested")[:300]
            log(sl, f"{agent_name}: STOP sentinel humano detectado. "
                    f"Pausando sessao em PAUSED_RECOVERABLE.")
            # Consome o arquivo STOP para que `continue` nao reative kill imediato
            if session_state is not None:
                try:
                    stop_path = os.path.join(session_state.session_dir,
                                             STOP_SENTINEL_NAME)
                    if os.path.isfile(stop_path):
                        os.remove(stop_path)
                except Exception:
                    pass
                session_state.transition(STATE_PAUSED_RECOVERABLE,
                                         reason=f"STOP sentinel: {reason}")
                update_lock(repo_path, session_state.session_id, run_label,
                            STATE_PAUSED_RECOVERABLE)
            raise RecoverablePauseError(
                f"STOP sentinel humano ({agent_name}): {reason}")

        if cls == "QUOTA":
            # V2.7: creditos esgotados. Backoff proprio, health-ping, retry infinito.
            quota_attempt += 1
            sched_idx = min(quota_attempt - 1, len(QUOTA_BACKOFF_SCHEDULE_S) - 1)
            wait_s = QUOTA_BACKOFF_SCHEDULE_S[sched_idx]
            next_at = (datetime.datetime.now() +
                       datetime.timedelta(seconds=wait_s)).isoformat()
            reason = (result.get("stderr") or result.get("stdout") or "")[:200]
            log(sl, f"{agent_name}: QUOTA esgotada (tentativa {quota_attempt}). "
                    f"Aguardando {wait_s}s antes de health-ping. "
                    f"Motivo: {reason[:100]}")
            if session_state is not None:
                quota_since = (session_state.data.get("quota_since") or
                               datetime.datetime.now().isoformat())
                session_state.set(
                    quota_attempt=quota_attempt,
                    quota_since=quota_since,
                    quota_last_error=reason[:300],
                    quota_next_ping_at=next_at,
                    next_retry_at=next_at,
                    retry_count=0,  # nao mistura com backoff transitorio
                )
                session_state.transition(
                    STATE_RETRY_BACKOFF,
                    reason=f"quota esgotada: {reason[:280]}",
                )
                update_lock(repo_path, session_state.session_id, run_label,
                            STATE_RETRY_BACKOFF, next_retry_at=next_at)
            ok = _sleep_interruptible(wait_s)
            if not ok:
                raise KeyboardInterrupt()
            # Health-ping: creditos voltaram?
            if _quota_health_ping(agent_name, sl):
                # Vai retomar a call real no proximo iter do while.
                # Mantem quota_attempt>0 para o OK branch limpar os metadados
                # e voltar o estado para RUNNING.
                continue
            # Ping ainda falha: proxima iteracao vai incrementar backoff ate
            # bater no teto de 30min e ficar la pra sempre.
            continue

        if cls == "TRANSIENT":
            attempt += 1
            sched_idx = min(attempt - 1, len(RETRY_BACKOFF_SCHEDULE_S) - 1)
            wait_s = RETRY_BACKOFF_SCHEDULE_S[sched_idx]
            next_at = (datetime.datetime.now() +
                       datetime.timedelta(seconds=wait_s)).isoformat()
            reason = (result.get("stderr") or result.get("stdout") or "")[:200]
            log(sl, f"{agent_name}: erro transitorio (tentativa {attempt}). "
                    f"Aguardando {wait_s}s. Motivo: {reason[:100]}")
            if session_state is not None:
                session_state.set(retry_count=attempt, next_retry_at=next_at)
                session_state.transition(STATE_RETRY_BACKOFF,
                                         reason=f"erro transitorio: {reason[:300]}")
                update_lock(repo_path, session_state.session_id, run_label,
                            STATE_RETRY_BACKOFF, next_retry_at=next_at)
            ok = _sleep_interruptible(wait_s)
            if not ok:
                raise KeyboardInterrupt()
            continue

        # UNKNOWN
        unknown_count += 1
        reason = (result.get("stderr") or result.get("stdout") or "")[:200]
        log(sl, f"{agent_name}: erro desconhecido {unknown_count}/"
                f"{UNKNOWN_ERROR_RETRY_LIMIT}. Motivo: {reason[:100]}")
        if unknown_count >= UNKNOWN_ERROR_RETRY_LIMIT:
            if session_state is not None:
                session_state.set(unknown_error_count=unknown_count)
                session_state.transition(STATE_PAUSED_RECOVERABLE,
                                         reason=f"erro desconhecido repetido: {reason[:300]}")
                update_lock(repo_path, session_state.session_id, run_label,
                            STATE_PAUSED_RECOVERABLE)
            raise RecoverablePauseError(reason)
        # Pequeno delay antes de retentar
        if not _sleep_interruptible(30):
            raise KeyboardInterrupt()


class RecoverablePauseError(Exception):
    """Levantada quando erro desconhecido forca pausa. O loop principal
    deve gerar checkpoint e entrar em busy-wait aguardando humano."""
    pass


# === Checkpoints (V2.3) ===

def _list_repo_changes(repo_path, started_at_iso):
    """Lista arquivos do repo com mtime > started_at. Heuristica.

    Exclui pastas obvias: orchestrator_sessions, node_modules, .git, .venv, .claude.
    Retorna lista de dicts: [{'path': 'reports/foo.md', 'status': 'modificado', 'mtime': '...'}].
    """
    if not started_at_iso:
        return []
    try:
        start_ts = datetime.datetime.fromisoformat(started_at_iso).timestamp()
    except Exception:
        return []

    exclude_prefixes = {
        "orchestrator_sessions", "node_modules", ".git", ".venv",
        ".claude", "__pycache__", ".mypy_cache", ".pytest_cache",
    }
    results = []
    try:
        for root, dirs, files in os.walk(repo_path):
            # filtrar subdirs
            dirs[:] = [d for d in dirs if d not in exclude_prefixes and
                       not d.startswith(".")]
            # Deep exclude: pular se o caminho ja contem uma pasta excluida
            rel_root = os.path.relpath(root, repo_path)
            if any(part in exclude_prefixes for part in rel_root.split(os.sep)):
                continue
            for fname in files:
                full = os.path.join(root, fname)
                try:
                    mtime = os.path.getmtime(full)
                except Exception:
                    continue
                if mtime > start_ts:
                    rel = os.path.relpath(full, repo_path).replace("\\", "/")
                    results.append({
                        "path": rel,
                        "mtime": datetime.datetime.fromtimestamp(mtime).strftime("%H:%M:%S"),
                    })
    except Exception:
        pass
    results.sort(key=lambda x: x["path"])
    return results[:100]  # limite para nao inchar


def _extract_round_summary(session_dir, round_num):
    """Extrai uma linha condensada sobre um round. Puramente mecanico."""
    padded = f"{round_num:03d}"
    codex_f = os.path.join(session_dir, f"round-{padded}-codex.md")
    claude_f = os.path.join(session_dir, f"round-{padded}-claude.md")

    def _first_useful(path, max_chars=120):
        if not os.path.isfile(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for raw in f:
                    line = raw.strip()
                    if not line:
                        continue
                    if line in ("---", "```"):
                        continue
                    if line.startswith("#"):
                        line = line.lstrip("# ").strip()
                    if line.startswith("**") and line.endswith("**"):
                        line = line.strip("*").strip()
                    if not line:
                        continue
                    return line[:max_chars]
        except Exception:
            pass
        return ""

    codex_preview = _first_useful(codex_f)
    claude_preview = _first_useful(claude_f)

    # Detectar aprovacao/reprovacao/bloqueio heuristicamente
    markers = []
    full_codex = ""
    if os.path.isfile(codex_f):
        try:
            with open(codex_f, "r", encoding="utf-8", errors="replace") as f:
                full_codex = f.read()[:3000].lower()
        except Exception:
            pass
    if "aprovad" in full_codex or "status: aprovado" in full_codex:
        markers.append("APROVADO")
    if "reprovad" in full_codex or "status: reprovado" in full_codex:
        markers.append("REPROVADO")
    if "conclu" in full_codex:
        markers.append("CONCLUIDO")
    if "humano" in full_codex:
        markers.append("HUMANO")

    parts = [f"Round {padded}:"]
    if codex_preview:
        parts.append(f"Codex: {codex_preview}")
    if claude_preview:
        parts.append(f"Claude: {claude_preview}")
    if markers:
        parts.append(f"[{'/'.join(markers)}]")
    return " — ".join(parts)


def _tail_log(log_path, n=30):
    if not os.path.isfile(log_path):
        return "(nao existe)"
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except Exception as e:
        return f"(erro: {e})"


def _detect_current_phase(session_dir, current_round):
    """Procura mencoes a 'Fase N' no ultimo arquivo codex.md."""
    if current_round < 1:
        return "-"
    padded = f"{current_round:03d}"
    path = os.path.join(session_dir, f"round-{padded}-codex.md")
    if not os.path.isfile(path):
        return "-"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()[:2000]
        matches = re.findall(r"Fase\s+(\d+)", content, flags=re.IGNORECASE)
        if matches:
            return f"Fase {matches[-1]}"
    except Exception:
        pass
    return "-"


HANDOFF_FILE_PATH = "C:\\winegod-app\\docs\\ORQUESTRADOR_HANDOFF.md"


def _build_checkpoint(session, session_state, rounds_done, repo_path,
                     trigger_reason="rotina"):
    """Gera markdown do checkpoint com 7 secoes."""
    sd = session["session_dir"]
    session_id = session["session_id"]
    data = session_state.data if session_state else {}

    # Secao A — Referencia ao arquivo de handoff (nao embutido mais)
    section_a = (
        "## Secao A — Referencia ao handoff do orquestrador\n\n"
        f"O texto completo que explica o que e o orquestrador, seus estados,\n"
        f"arquitetura e como voce (agente externo) deve agir esta em:\n\n"
        f"`{HANDOFF_FILE_PATH}`\n\n"
        f"Leia esse arquivo antes de tentar ajudar.\n"
    )

    # Secao B — Metadados
    mission = data.get("run_label") or "-"
    lines_b = [
        "## Secao B — Metadados da sessao",
        "",
        f"- session_id: `{session_id}`",
        f"- run_label: `{data.get('run_label', '-')}`",
        f"- state: `{data.get('state', '-')}`",
        f"- current_round: {data.get('current_round', 0)}",
        f"- round_num: {data.get('round_num', 0)}",
        f"- round_stage: {data.get('round_stage') or '-'}",
        f"- last_successful_round: {data.get('last_successful_round', 0)}",
        f"- retry_count: {data.get('retry_count', 0)}",
        f"- next_retry_at: {data.get('next_retry_at') or '-'}",
        f"- paused_reason: {data.get('paused_reason') or '-'}",
        f"- recovered_from: {data.get('recovered_from') or '-'}",
        f"- recovery_at: {data.get('recovery_at') or '-'}",
        f"- recovery_confidence: {data.get('recovery_confidence') or '-'}",
        f"- recovery_strategy: {data.get('recovery_strategy') or '-'}",
        f"- recovery_note: {data.get('recovery_note') or '-'}",
        f"- recovery_attempts: {data.get('recovery_attempts') or 0}",
        f"- last_recovery_error: {data.get('last_recovery_error') or '-'}",
        f"- claude_session_uuid: `{data.get('claude_session_uuid') or '-'}`",
        f"- codex_session_uuid: `{data.get('codex_session_uuid') or '-'}`",
        f"- started_at: {data.get('started_at') or '-'}",
        f"- last_heartbeat: {data.get('last_heartbeat') or '-'}",
        f"- repo_path: `{repo_path}`",
        f"- pasta_sessao: `{sd}`",
        f"- trigger_do_checkpoint: {trigger_reason}",
    ]
    section_b = "\n".join(lines_b)

    # Secao C — Arquivos tocados no repo
    changes = _list_repo_changes(repo_path, data.get("started_at"))
    section_c_lines = [
        "## Secao C — Arquivos provavelmente tocados no repo",
        "",
        "*Heuristica por mtime desde o inicio da sessao. Pode conter falsos",
        "positivos se houve edicoes manuais em paralelo.*",
        "",
    ]
    if not changes:
        section_c_lines.append("(nenhum arquivo detectado)")
    else:
        for c in changes:
            section_c_lines.append(f"- `{c['path']}` (mtime {c['mtime']})")
    section_c = "\n".join(section_c_lines)

    # Secao D — Historico condensado
    section_d_lines = [
        "## Secao D — Historico condensado dos rounds",
        "",
    ]
    current_round = data.get("current_round", 0) or 0
    if current_round < 1:
        section_d_lines.append("(nenhum round iniciado)")
    else:
        for n in range(1, current_round + 1):
            section_d_lines.append(f"- {_extract_round_summary(sd, n)}")
    section_d = "\n".join(section_d_lines)

    # Secao E — Estado atual
    fase = _detect_current_phase(sd, current_round)
    last_codex_preview = ""
    if current_round >= 1:
        p = os.path.join(sd, f"round-{current_round:03d}-codex.md")
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    last_codex_preview = f.read(300)
            except Exception:
                pass
    section_e_lines = [
        "## Secao E — Estado atual",
        "",
        f"- Estado do sistema: **{data.get('state', '-')}**",
        f"- Fase detectada: {fase}",
        f"- Ultimo round completo: {data.get('last_successful_round', 0)}",
    ]
    if data.get("state") == STATE_RETRY_BACKOFF:
        section_e_lines.append(
            f"- Em retry: tentativa {data.get('retry_count')}, proxima em {data.get('next_retry_at')}"
        )
    if data.get("paused_reason"):
        section_e_lines.append(f"- Motivo da pausa: {data.get('paused_reason')}")
    if last_codex_preview:
        section_e_lines.append("")
        section_e_lines.append("**Ultima mensagem do Codex (preview):**")
        section_e_lines.append("")
        section_e_lines.append("```")
        section_e_lines.append(last_codex_preview.strip())
        section_e_lines.append("```")
    section_e = "\n".join(section_e_lines)

    # Secao F — Tails de log
    section_f_lines = [
        "## Secao F — Tails dos logs (ultimas 30 linhas cada)",
        "",
        "### session.log",
        "```",
        _tail_log(os.path.join(sd, "session.log"), 30),
        "```",
        "",
        "### claude.log",
        "```",
        _tail_log(os.path.join(sd, "claude.log"), 30),
        "```",
        "",
        "### codex.log",
        "```",
        _tail_log(os.path.join(sd, "codex.log"), 30),
        "```",
    ]
    section_f = "\n".join(section_f_lines)

    # Secao G — Prompt pronto (com dados concretos da sessao)
    # Todos os rounds condensados para dar contexto completo
    all_rounds_lines = []
    if current_round >= 1:
        for n in range(1, current_round + 1):
            all_rounds_lines.append(f"- {_extract_round_summary(sd, n)}")
    else:
        all_rounds_lines.append("- (nenhum round iniciado ainda)")
    all_rounds_block = "\n".join(all_rounds_lines)

    section_g = (
        "## Secao G — Prompt pronto para inspecao externa\n\n"
        "Cole o texto abaixo em outra aba de Claude Code ou Codex:\n\n"
        "---\n\n"
        "```\n"
        "Preciso de ajuda investigando uma sessao do Duo Orchestrator que\n"
        "pode estar pausada, travada ou precisando de decisao.\n\n"
        "ARQUIVOS DE REFERENCIA (leia antes de responder):\n"
        f"1. Handoff do orquestrador: `{HANDOFF_FILE_PATH}`\n"
        f"2. Diretorio da sessao: `{sd}`\n\n"
        "ACAO OBRIGATORIA:\n"
        "Leia TODOS os arquivos do diretorio da sessao acima, em ordem\n"
        "cronologica (mtime). Nao assuma a lista — varra o diretorio todo\n"
        "e leia cada arquivo, inclusive os que possam ter sido criados\n"
        "depois deste checkpoint.\n\n"
        "CONTEXTO — todos os rounds desta sessao (condensado):\n"
        f"{all_rounds_block}\n\n"
        f"Estado atual: {data.get('state', '-')}\n"
        f"Motivo da pausa (se houver): {data.get('paused_reason') or '-'}\n"
        f"Round atual: {data.get('current_round', 0)} | ultimo OK: {data.get('last_successful_round', 0)}\n\n"
        "RESPONDA EXATAMENTE:\n"
        "1. Em que fase do projeto esta?\n"
        "2. O que foi efetivamente produzido no repo? Liste arquivos.\n"
        "3. Por que a sessao esta no estado atual? Causa raiz.\n"
        "4. Proxima acao concreta: esperar retry, intervir, ou fechar?\n"
        "5. Comando exato para continuar ou fechar:\n"
        f"   - `start_dupla.cmd continue {session_id}`\n"
        f"   - `start_dupla.cmd close {session_id}`\n"
        "```\n"
    )

    # Assembly (Secao A agora e compacta, nao embute o handoff inteiro)
    parts = [
        f"# Checkpoint — {session_id} — {trigger_reason}",
        f"*Gerado em {datetime.datetime.now().isoformat()}*",
        "",
        section_a,
        "",
        section_b,
        "",
        section_c,
        "",
        section_d,
        "",
        section_e,
        "",
        section_f,
        "",
        section_g,
    ]
    return "\n".join(parts)


def _save_checkpoint(session, content, round_num):
    """Salva checkpoint como summary_YYYY-MM-DD_HH-MM-SS_round-NNN.md."""
    sd = session["session_dir"]
    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = f"summary_{ts}_round-{round_num:03d}.md"
    path = os.path.join(sd, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _trigger_checkpoint(session, session_state, repo_path, round_num,
                       trigger_reason):
    """Gera + salva checkpoint + regenera viewer. Tudo best-effort."""
    try:
        content = _build_checkpoint(
            session, session_state, None, repo_path,
            trigger_reason=trigger_reason,
        )
        path = _save_checkpoint(session, content, round_num)
        log(session["session_log"], f"Checkpoint: {os.path.basename(path)} ({trigger_reason})")
        # Regerar viewer em background
        try:
            _regenerate_viewer(session["session_id"])
        except Exception as e:
            log(session["session_log"], f"Viewer regen falhou: {e}")
    except Exception as e:
        try:
            log(session["session_log"], f"Checkpoint falhou: {e}")
        except Exception:
            pass


def _regenerate_viewer(session_id):
    """Re-gera session.html e session_conversation.html."""
    viewer = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "session_viewer.py")
    if not os.path.isfile(viewer):
        return
    subprocess.Popen(
        [sys.executable, viewer, session_id, "--no-open"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


VIEWER_REFRESH_MIN_INTERVAL_S = 60


def _read_brief(session_dir):
    with open(os.path.join(session_dir, "project.md"), "r",
              encoding="utf-8-sig") as f:
        return f.read()


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content or "")


def _persist_round_artifact(session_state, session_dir, round_num, role, content):
    """Salva artefato do round e comita hash/estagio correspondente em disco."""
    padded = f"{int(round_num):03d}"
    path = os.path.join(session_dir, f"round-{padded}-{role}.md")
    _write(path, content)
    text_hash = _hash_text(content)
    if role == "codex":
        _set_round_stage(
            session_state, round_num, ROUND_STAGE_CODEX_PROMPT_SAVED,
            codex_prompt_hash=text_hash,
            codex_reply_hash=text_hash,
        )
    elif role == "claude":
        _set_round_stage(
            session_state, round_num, ROUND_STAGE_CLAUDE_DONE,
            claude_reply_hash=text_hash,
        )
    return path


def _busy_wait_for_state_change(session_state, sl, repo_path, run_label,
                                poll_seconds=30):
    """Busy-wait ate o humano editar session-state.json via continue/close.

    Releia o state do disco a cada poll. Se state virar RUNNING, retorna True
    (continuar). Se state virar CLOSED_BY_HUMAN, retorna False (encerrar).

    Ctrl+C / _interrupt_flag sai imediatamente.
    """
    import time as _time
    initial_state = session_state.state
    log(sl, f"Entrando em busy-wait (estado={initial_state}). Use continue/close.")
    while True:
        if _interrupt_flag["set"]:
            return False
        _time.sleep(poll_seconds)
        # relê do disco — humano pode ter editado
        new_ss = SessionState(session_state.session_dir)
        if new_ss.load():
            new_state = new_ss.state
            if new_state != initial_state:
                log(sl, f"Estado mudou: {initial_state} → {new_state}")
                session_state.data = new_ss.data
                if new_state == STATE_RUNNING:
                    return True
                if new_state == STATE_CLOSED_BY_HUMAN:
                    return False
                # outras transicoes: atualiza e segue
                initial_state = new_state
        # heartbeat
        session_state.heartbeat()
        update_lock(repo_path, session_state.session_id, run_label,
                    session_state.state)


def _install_sigint_handler():
    """Garante que Ctrl+C sinaliza _interrupt_flag e levanta KeyboardInterrupt."""
    def _handler(signum, frame):
        _interrupt_flag["set"] = True
        raise KeyboardInterrupt()
    try:
        signal.signal(signal.SIGINT, _handler)
    except Exception:
        pass


def run_dumb_workflow(brief_path, wt_mode=False, preallocated_session=None,
                     multi_mode=False, multi_info=None):
    """V2.3: Workflow dumb-pipe com persistencia de estado e retry infinito.

    A sessao NUNCA e fechada automaticamente. Estados:
    - Erros transitorios -> RETRY_BACKOFF (retry infinito)
    - Erros desconhecidos repetidos -> PAUSED_RECOVERABLE (aguarda humano)
    - Codex escreveu HUMANO -> WAITING_HUMAN (aguarda humano)
    - Codex escreveu CONCLUIDO -> READY_FOR_HUMAN_CLOSE (aguarda humano)
    - Ctrl+C ou comando close -> CLOSED_BY_HUMAN (unico caminho para fechamento)

    V2.6: multi_mode=True para sessoes com workspace isolado.
    preallocated_session=(session_id, session_name, session_dir) evita corrida.
    """
    _install_sigint_handler()
    brief_path, header = validate_brief(brief_path)
    repo_path = header["REPO_PATH"]
    run_label = header["RUN_LABEL"]

    print(f"Projeto: {brief_path}")
    print(f"Repo:    {repo_path}")
    print(f"Label:   {run_label}")
    if multi_mode:
        print(f"Modo:    MULTI (workspace isolado)")
    print()

    session = run_bootstrap(brief_path, header, wt_mode=wt_mode,
                            preallocated_session=preallocated_session,
                            multi_mode=multi_mode, multi_info=multi_info)
    sl = session["session_log"]
    sd = session["session_dir"]
    codex_log = session["codex_log"]
    claude_log = session["claude_log"]
    session_id = session["session_id"]

    # --- Inicializa estado da sessao ---
    session_state = SessionState(sd)
    state_init = {
        "session_id": session_id,
        "run_label": run_label,
        "state": STATE_BOOTSTRAP,
        "started_at": datetime.datetime.now().isoformat(),
        "orchestrator_pid": os.getpid(),
        "round_num": 0,
        "round_stage": ROUND_STAGE_BOOTSTRAP,
    }
    if multi_mode and multi_info:
        state_init.update({
            "multi_mode": True,
            "base_repo_path": multi_info.get("base_repo_path", ""),
            "workspace_path": multi_info.get("workspace_path", ""),
            "workspace_mode": multi_info.get("workspace_mode", ""),
        })
    session_state.data.update(state_init)
    session_state.save()
    last_viewer_regen = [0.0]

    def _maybe_refresh_viewer(force=False):
        try:
            import time as _time
            now = _time.time()
            if not force and (now - last_viewer_regen[0]) < VIEWER_REFRESH_MIN_INTERVAL_S:
                return
            last_viewer_regen[0] = now
            _regenerate_viewer(session_id)
        except Exception as e:
            try:
                log(sl, f"Viewer regen falhou: {e}")
            except Exception:
                pass

    claude_stream = None
    try:
        if not check_cli("claude") or not check_cli("codex"):
            log(sl, "ERRO: CLI nao encontrado")
            session_state.transition(STATE_PAUSED_RECOVERABLE,
                                     reason="CLI claude ou codex nao encontrado")
            _trigger_checkpoint(session, session_state, repo_path, 0,
                               "cli_missing")
            log(sl, "Sessao pausada aguardando humano (PAUSED_RECOVERABLE)")
            _busy_wait_for_state_change(session_state, sl, repo_path, run_label)
            return

        log(sl, f"claude: {check_cli('claude')}")
        log(sl, f"codex: {check_cli('codex')}")
        log(sl, "Modo: V2.3 dumb-pipe persistente (nunca fecha sozinho)")

        brief = _read_brief(sd)

        # Sessoes persistentes
        claude_uuid = _new_uuid()
        codex_uuid_ref = [None]
        session_state.set(claude_session_uuid=claude_uuid)
        log(sl, f"Claude session UUID: {claude_uuid}")

        # Claude em stream-json (zero cold start)
        claude_stream = ClaudeStreamSession(claude_uuid, repo_path)
        claude_stream.start()
        log(sl, "Claude stream session iniciada (stream-json)")

        # V2.3 hotfix: heartbeat de observabilidade + kill-switch STOP
        stop_sentinel_path = os.path.join(sd, STOP_SENTINEL_NAME)

        def _claude_heartbeat(info):
            try:
                session_state.set(
                    active_agent=info.get("active_agent"),
                    active_call_status=info.get("active_call_status"),
                    active_call_started_at=info.get("active_call_started_at"),
                    last_stream_event_at=info.get("last_stream_event_at"),
                    last_jsonl_mtime=info.get("last_jsonl_mtime"),
                )
                update_lock(repo_path, session_id, run_label,
                            session_state.state)
                _maybe_refresh_viewer(force=False)
            except Exception:
                pass

        def _stop_requested():
            try:
                return os.path.isfile(stop_sentinel_path)
            except Exception:
                return False

        def _claude_call(message, cwd):
            result = claude_stream.send(
                message,
                on_heartbeat=_claude_heartbeat,
                stop_requested=_stop_requested,
            )
            # limpa metadados de call ativa quando o turno encerra
            try:
                session_state.set(
                    active_agent=None,
                    active_call_status=None,
                    active_call_started_at=None,
                )
            except Exception:
                pass
            return result

        def _codex_call_first(message, cwd):
            return _call_codex_session(codex_uuid_ref, message, cwd,
                                       first_call=True, multi_mode=multi_mode)

        def _codex_call_resume(message, cwd):
            return _call_codex_session(codex_uuid_ref, message, cwd,
                                       first_call=False, multi_mode=multi_mode)

        # Transita para RUNNING (bootstrap dos agentes)
        session_state.transition(STATE_RUNNING)
        session_state.set(orchestrator_pid=os.getpid())
        update_lock(repo_path, session_id, run_label, STATE_RUNNING)
        _maybe_refresh_viewer(force=True)

        # --- Bootstrap: mesma mensagem pros dois ---
        boot_msg = BOOTSTRAP_PROMPT_TEMPLATE.format(brief=brief)

        log(sl, "=== BOOTSTRAP Claude ===")
        claude_boot = _call_with_retry(
            _claude_call, boot_msg, repo_path, session_state, repo_path,
            run_label, "claude", claude_log, sl, stream_session=claude_stream,
        )
        _write(os.path.join(sd, "round-000-claude-bootstrap.md"), claude_boot)

        log(sl, "=== ATIVACAO Claude como executor ===")
        claude_act = _call_with_retry(
            _claude_call, CLAUDE_ACTIVATION_PROMPT, repo_path, session_state,
            repo_path, run_label, "claude", claude_log, sl,
            stream_session=claude_stream,
        )
        _write(os.path.join(sd, "round-000-claude-activation.md"), claude_act)

        log(sl, "=== BOOTSTRAP Codex ===")
        codex_boot = _call_with_retry(
            _codex_call_first, boot_msg, repo_path, session_state, repo_path,
            run_label, "codex", codex_log, sl,
        )
        _write(os.path.join(sd, "round-000-codex-bootstrap.md"), codex_boot)
        session_state.set(codex_session_uuid=codex_uuid_ref[0])
        log(sl, f"Codex session UUID: {codex_uuid_ref[0]}")

        log(sl, "=== ATIVACAO Codex como admin ===")
        act_msg = CODEX_ACTIVATION_PROMPT_TEMPLATE.format(claude_reply=claude_boot)
        admin_text = _call_with_retry(
            _codex_call_resume, act_msg, repo_path, session_state, repo_path,
            run_label, "codex", codex_log, sl,
        )
        _write(os.path.join(sd, "round-000-codex-activation.md"), admin_text)

        # Checa marcadores explicitos na ativacao
        if _has_marker(admin_text, CONCLUIDO_MARKER):
            log(sl, "Codex sinalizou CONCLUIDO na ativacao")
            session_state.transition(STATE_READY_FOR_HUMAN_CLOSE,
                                     reason="CONCLUIDO na ativacao")
            _trigger_checkpoint(session, session_state, repo_path, 0,
                               "ready_for_human_close")
            cont = _busy_wait_for_state_change(session_state, sl, repo_path, run_label)
            if not cont:
                return
            session_state.transition(STATE_RUNNING)
            update_lock(repo_path, session_id, run_label, STATE_RUNNING)
        if _has_marker(admin_text, HUMANO_MARKER):
            log(sl, "Codex sinalizou HUMANO na ativacao")
            session_state.transition(STATE_WAITING_HUMAN,
                                     reason="HUMANO na ativacao")
            _trigger_checkpoint(session, session_state, repo_path, 0,
                               "waiting_human_on_activation")
            cont = _busy_wait_for_state_change(session_state, sl, repo_path, run_label)
            if not cont:
                return
            session_state.transition(STATE_RUNNING)
            update_lock(repo_path, session_id, run_label, STATE_RUNNING)

        # --- Loop principal dumb-pipe (V2.3: sem limite de rounds) ---
        print()
        log(sl, "=== LOOP DUMB-PIPE (V2.3) ===")
        codex_history = [admin_text]
        round_num = 0

        while True:
            if _interrupt_flag["set"]:
                raise KeyboardInterrupt()
            round_num += 1
            padded = f"{round_num:03d}"
            session_state.set(current_round=round_num, round_num=round_num,
                              orchestrator_pid=os.getpid())
            update_lock(repo_path, session_id, run_label, STATE_RUNNING)
            print()
            log(sl, f"=== ROUND {padded} ===")

            # 1) Admin text -> Claude
            codex_path = os.path.join(sd, f"round-{padded}-codex.md")
            if not os.path.isfile(codex_path):
                _persist_round_artifact(session_state, sd, round_num, "codex", admin_text)
                log(sl, f"Salvei: round-{padded}-codex.md")
                _maybe_refresh_viewer(force=True)
            else:
                _set_round_stage(
                    session_state, round_num, ROUND_STAGE_CODEX_PROMPT_SAVED,
                    codex_prompt_hash=_hash_text(_read(codex_path)),
                    codex_reply_hash=_hash_text(_read(codex_path)),
                )

            log(sl, f"Enviando ao Claude (round {padded})...")
            _set_round_stage(
                session_state, round_num, ROUND_STAGE_CLAUDE_IN_FLIGHT,
                codex_prompt_hash=_hash_text(admin_text),
            )
            try:
                claude_text = _call_with_retry(
                    _claude_call, admin_text, repo_path, session_state,
                    repo_path, run_label, "claude", claude_log, sl,
                    stream_session=claude_stream,
                )
            except RecoverablePauseError as e:
                _trigger_checkpoint(session, session_state, repo_path,
                                   round_num, "paused_recoverable_claude")
                log(sl, f"Pausado em PAUSED_RECOVERABLE: {e}")
                cont = _busy_wait_for_state_change(session_state, sl,
                                                   repo_path, run_label)
                if not cont:
                    return
                continue

            _persist_round_artifact(session_state, sd, round_num, "claude", claude_text)
            _maybe_refresh_viewer(force=True)

            # 2) Claude text -> Codex
            log(sl, f"Enviando ao Codex (round {padded})...")
            _set_round_stage(
                session_state, round_num, ROUND_STAGE_CODEX_IN_FLIGHT,
                claude_reply_hash=_hash_text(claude_text),
            )
            try:
                admin_text = _call_with_retry(
                    _codex_call_resume, claude_text, repo_path, session_state,
                    repo_path, run_label, "codex", codex_log, sl,
                )
            except RecoverablePauseError as e:
                _trigger_checkpoint(session, session_state, repo_path,
                                   round_num, "paused_recoverable_codex")
                log(sl, f"Pausado em PAUSED_RECOVERABLE: {e}")
                cont = _busy_wait_for_state_change(session_state, sl,
                                                   repo_path, run_label)
                if not cont:
                    return
                continue

            session_state.set(last_successful_round=round_num)
            next_round_num = round_num + 1
            _persist_round_artifact(
                session_state, sd, next_round_num, "codex", admin_text
            )
            _maybe_refresh_viewer(force=True)

            # Marcadores explicitos = pausa (nao fechamento)
            if _has_marker(admin_text, CONCLUIDO_MARKER):
                log(sl, f"Codex sinalizou CONCLUIDO no round {padded}")
                session_state.transition(STATE_READY_FOR_HUMAN_CLOSE,
                                         reason=f"CONCLUIDO no round {padded}")
                session_state.set(round_stage=ROUND_STAGE_READY_FOR_CLOSE)
                _trigger_checkpoint(session, session_state, repo_path,
                                   round_num, "ready_for_human_close")
                cont = _busy_wait_for_state_change(session_state, sl,
                                                   repo_path, run_label)
                if not cont:
                    return
                # se o humano retomou, marca RUNNING e continua
                session_state.transition(STATE_RUNNING)
                _set_round_stage(
                    session_state, next_round_num, ROUND_STAGE_CODEX_PROMPT_SAVED,
                    codex_prompt_hash=_hash_text(admin_text),
                    codex_reply_hash=_hash_text(admin_text),
                )
                update_lock(repo_path, session_id, run_label, STATE_RUNNING)
                continue
            if _has_marker(admin_text, HUMANO_MARKER):
                log(sl, f"Codex sinalizou HUMANO no round {padded}")
                session_state.transition(STATE_WAITING_HUMAN,
                                         reason=f"HUMANO no round {padded}: {admin_text[:300]}")
                session_state.set(round_stage=ROUND_STAGE_WAITING_HUMAN)
                _trigger_checkpoint(session, session_state, repo_path,
                                   round_num, "waiting_human")
                cont = _busy_wait_for_state_change(session_state, sl,
                                                   repo_path, run_label)
                if not cont:
                    return
                session_state.transition(STATE_RUNNING)
                _set_round_stage(
                    session_state, next_round_num, ROUND_STAGE_CODEX_PROMPT_SAVED,
                    codex_prompt_hash=_hash_text(admin_text),
                    codex_reply_hash=_hash_text(admin_text),
                )
                update_lock(repo_path, session_id, run_label, STATE_RUNNING)
                continue

            # Detecao de loop: Codex repetindo resposta curta
            codex_history.append(admin_text)
            if _detect_loop(codex_history):
                log(sl, f"Loop detectado no round {padded}: Codex repetindo")
                session_state.transition(STATE_PAUSED_RECOVERABLE,
                                         reason="Loop de respostas curtas detectado")
                _trigger_checkpoint(session, session_state, repo_path,
                                   round_num, "loop_detected")
                cont = _busy_wait_for_state_change(session_state, sl,
                                                   repo_path, run_label)
                if not cont:
                    return
                session_state.transition(STATE_RUNNING)
                _set_round_stage(
                    session_state, next_round_num, ROUND_STAGE_CODEX_PROMPT_SAVED,
                    codex_prompt_hash=_hash_text(admin_text),
                    codex_reply_hash=_hash_text(admin_text),
                )
                update_lock(repo_path, session_id, run_label, STATE_RUNNING)
                continue

            # Checkpoint a cada N rounds
            if round_num % CHECKPOINT_EVERY_N_ROUNDS == 0:
                _trigger_checkpoint(session, session_state, repo_path,
                                   round_num, f"round_{round_num}_cadencia")

    except KeyboardInterrupt:
        print()
        log(sl, "INTERRUPCAO: Ctrl+C recebido do usuario")
        _interrupt_flag["set"] = True
        session_state.transition(STATE_CLOSED_BY_HUMAN,
                                 reason="Ctrl+C do usuario")
        session_state.set(orchestrator_pid=None)
        update_lock(repo_path, session_id, run_label, STATE_CLOSED_BY_HUMAN)
        _trigger_checkpoint(session, session_state, repo_path,
                           session_state.data.get("current_round", 0),
                           "closed_by_ctrl_c")
        write_final_review(session, "INTERROMPIDO",
                          session_state.data.get("current_round", 0),
                          "Interrompido pelo usuario (Ctrl+C)",
                          _collect_round_files(sd))
        log(sl, "WORKFLOW CLOSED_BY_HUMAN (Ctrl+C)")
    except Exception as e:
        # Erro inesperado do proprio orquestrador — pausa recoverable, nao fecha
        log(sl, f"ERRO inesperado no orquestrador: {e}")
        try:
            session_state.transition(STATE_PAUSED_RECOVERABLE,
                                     reason=f"Erro inesperado: {str(e)[:300]}")
            _trigger_checkpoint(session, session_state, repo_path,
                               session_state.data.get("current_round", 0),
                               "unexpected_exception")
        except Exception:
            pass
        raise
    finally:
        try:
            if claude_stream is not None:
                claude_stream.close()
                log(sl, "Claude stream session encerrada")
        except Exception as e:
            log(sl, f"Erro ao encerrar claude stream: {e}")
        # Lock so e liberado se estado virou CLOSED_BY_HUMAN
        if session_state.state == STATE_CLOSED_BY_HUMAN:
            session_state.set(orchestrator_pid=None)
            release_lock(repo_path, session_id, sl)
            if multi_mode:
                _remove_multi_lock(session_id)
                try:
                    registry_update_session(session_id, {
                        "state": STATE_CLOSED_BY_HUMAN,
                        "current_round": session_state.data.get("current_round", 0),
                        "closed_at": datetime.datetime.now().isoformat(),
                    })
                    generate_index_html()
                except Exception as e:
                    log(sl, f"Registry multi: falha ao fechar ({e})")
        else:
            log(sl, f"Sessao nao fechada explicitamente (state={session_state.state}). "
                    "Lock preservado para retomada.")


def run_workflow(brief_path, wt_mode=False):
    """Entry-point publico. Delega para run_dumb_workflow (V2)."""
    return run_dumb_workflow(brief_path, wt_mode=wt_mode)


def run_resume(session_id):
    """Retoma uma sessao existente pelo ID."""
    session_dir = _find_session_dir(session_id)

    if not session_dir:
        print(f"ERRO: Sessao {session_id} nao encontrada em {SESSIONS_DIR}")
        sys.exit(1)

    print(f"Sessao encontrada: {os.path.basename(session_dir)}")
    print(f"Pasta:  {session_dir}")
    print()

    # Verificar se ja terminou
    finished, final_status = _session_is_finished(session_dir)
    if finished:
        print(f"AVISO: Sessao ja finalizada com status: {final_status}")
        print("Nao e possivel retomar uma sessao finalizada.")
        print("Use --run-workflow para iniciar uma nova sessao.")
        return

    # Reconstruir session dict
    session = _rebuild_session_dict(session_dir)
    sl = session["session_log"]
    sd = session["session_dir"]

    log(sl, f"=== RESUME da sessao {session_id} ===")

    # Ler projeto
    project_path = os.path.join(sd, "project.md")
    if not os.path.exists(project_path):
        log(sl, "ERRO: project.md nao encontrado na sessao")
        return

    with open(project_path, "r", encoding="utf-8-sig") as f:
        project_content = f.read()

    # Verificar CLIs
    if not check_cli("claude") or not check_cli("codex"):
        log(sl, "ERRO: CLI nao encontrado")
        return

    # Inferir estado
    state = infer_session_state(sd)
    log(sl, f"Estado inferido: understanding={state['understanding_approved']}, "
        f"last_complete={state['last_complete_round']}, "
        f"resume_round={state['resume_round']}, "
        f"resume_step={state['resume_step']}")

    try:
        if not state["understanding_approved"]:
            log(sl, "Entendimento nao aprovado. Reexecutando entendimento...")
            approved = _understanding_loop(session, project_content)
            if not approved:
                write_final_review(session, "REVISAO_HUMANA", 0,
                                   "Entendimento nao aprovado no resume",
                                   _collect_round_files(sd))
                log(sl, "WORKFLOW REVISAO_HUMANA")
                return

        # Reconstruir historico
        rounds_done = _rebuild_rounds_done(sd, state["last_complete_round"])
        start = state["resume_round"]
        step = state["resume_step"]

        log(sl, f"Retomando do round {start:03d} passo {step}")
        print()
        log(sl, "=== LOOP PRINCIPAL (resume) ===")

        _workflow_loop(session, project_content, start_round=start,
                       rounds_done=rounds_done, resume_step=step)

    except KeyboardInterrupt:
        print()
        log(sl, "INTERRUPCAO: Ctrl+C recebido pelo usuario")
        write_final_review(session, "INTERROMPIDO", 0,
                           "Interrompido pelo usuario (Ctrl+C)",
                           _collect_round_files(sd))
        log(sl, "WORKFLOW INTERROMPIDO")


# === Comandos close / continue (V2.3) ===

def run_close(session_id):
    """Fecha explicitamente uma sessao: transita para CLOSED_BY_HUMAN,
    gera final-review.md e libera o lock."""
    session_dir = _find_session_dir(session_id)
    if not session_dir:
        print(f"ERRO: Sessao {session_id} nao encontrada em {SESSIONS_DIR}")
        sys.exit(1)

    ss = SessionState(session_dir)
    if not ss.load():
        print(f"ERRO: session-state.json nao encontrado em {session_dir}")
        print("Sessao legado? Tentando fechar pelo lock...")

    print(f"Sessao: {os.path.basename(session_dir)}")
    if ss.data.get("state"):
        print(f"Estado atual: {ss.state}")

    resp = input("Fechar definitivamente? (s/n): ").strip().lower()
    if resp != "s":
        print("Cancelado.")
        return

    repo_path = "C:\\winegod-app"
    # tenta descobrir repo_path do project.md
    project_md = os.path.join(session_dir, "project.md")
    if os.path.isfile(project_md):
        try:
            with open(project_md, "r", encoding="utf-8-sig") as f:
                for line in f:
                    if line.startswith("REPO_PATH:"):
                        repo_path = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

    sl = os.path.join(session_dir, "session.log")
    ss.transition(STATE_CLOSED_BY_HUMAN, reason="Fechado via comando close")
    ss.set(orchestrator_pid=None)
    is_multi = bool(ss.data.get("multi_mode"))
    try:
        log(sl, "Fechamento manual via comando close")
    except Exception:
        pass

    # Gera checkpoint final
    try:
        session = {
            "session_id": session_id,
            "session_name": os.path.basename(session_dir),
            "session_dir": session_dir,
            "session_log": sl,
            "codex_log": os.path.join(session_dir, "codex.log"),
            "claude_log": os.path.join(session_dir, "claude.log"),
            "repo_path": repo_path,
        }
        _trigger_checkpoint(session, ss, repo_path,
                           ss.data.get("current_round", 0),
                           "closed_by_human")
        write_final_review(session, "CLOSED_BY_HUMAN",
                          ss.data.get("current_round", 0),
                          "Fechado manualmente via comando close",
                          _collect_round_files(session_dir))
    except Exception as e:
        print(f"Aviso: falha ao gerar artefatos finais: {e}")

    # Libera lock
    lock_path = os.path.join(repo_path, LOCK_FILE_NAME)
    if os.path.isfile(lock_path):
        info = read_lock_info(lock_path)
        if info.get("session_id") == session_id:
            try:
                os.remove(lock_path)
                print(f"Lock removido: {lock_path}")
            except Exception as e:
                print(f"Aviso: nao removeu lock: {e}")

    if is_multi:
        _remove_multi_lock(session_id)
        try:
            registry_update_session(session_id, {
                "state": STATE_CLOSED_BY_HUMAN,
                "current_round": ss.data.get("current_round", 0),
                "closed_at": datetime.datetime.now().isoformat(),
            })
            generate_index_html()
        except Exception as e:
            print(f"Aviso: registry multi nao atualizado no close: {e}")

    print(f"Sessao {session_id} fechada.")


def run_continue(session_id):
    """Comando padrao de retomada V2.5.

    - Se o processo original ainda esta vivo, apenas destrava a sessao.
    - Se o processo morreu, entra no reconciliador agressivo e continua sozinho
      sempre que houver contexto minimo e nenhum risco humano/destrutivo.
    """
    session_dir = _find_session_dir(session_id)
    if not session_dir:
        print(f"ERRO: Sessao {session_id} nao encontrada em {SESSIONS_DIR}")
        sys.exit(1)

    ss = SessionState(session_dir)
    if not ss.load():
        print(f"ERRO: session-state.json nao encontrado.")
        sys.exit(1)

    print(f"Sessao: {os.path.basename(session_dir)}")
    print(f"Estado atual: {ss.state}")
    process_alive = _session_process_alive(ss)
    print(f"Processo original vivo: {'sim' if process_alive else 'nao'}")

    if ss.state == STATE_CLOSED_BY_HUMAN:
        print("Sessao ja fechada. Nao ha como retomar.")
        return
    if ss.state == STATE_RUNNING and process_alive:
        print("Sessao ja em RUNNING com processo vivo. Nada a fazer.")
        return
    if ss.state not in (
        STATE_RUNNING,
        STATE_RETRY_BACKOFF,
        STATE_WAITING_HUMAN,
        STATE_PAUSED_RECOVERABLE,
        STATE_READY_FOR_HUMAN_CLOSE,
    ):
        print(f"Sessao em estado {ss.state}, nao pode ser retomada diretamente.")
        return

    if ss.state == STATE_READY_FOR_HUMAN_CLOSE:
        resp = input("Sessao esta READY_FOR_HUMAN_CLOSE. Reabrir para revisao? (s/n): ").strip().lower()
        if resp != "s":
            print("Cancelado. Use 'close' se quiser fechar.")
            return

    if process_alive:
        ss.set(paused_reason=None, unknown_error_count=0,
               retry_count=0, next_retry_at=None)
        ss.transition(STATE_RUNNING, reason=None)
        print(f"Estado transitado para {STATE_RUNNING}.")
        print("O processo original ainda esta vivo e detectara a mudanca")
        print("no proximo ciclo de busy-wait (~30s).")
        return

    ss.set(paused_reason=None, unknown_error_count=0,
           retry_count=0, next_retry_at=None)
    if ss.state != STATE_RUNNING:
        ss.transition(STATE_RUNNING, reason=None)
    print("Processo original nao esta mais vivo.")
    print("Entrando em reconcile + recovery automatico da mesma sessao...")
    return _resume_v23_session(session_id, recovery_mode="auto")


def _build_existing_session(session_id):
    """Monta dict `session` para uma sessao V2.3 ja existente."""
    session_dir = _find_session_dir(session_id)
    if not session_dir:
        raise RuntimeError(f"Sessao {session_id} nao encontrada em {SESSIONS_DIR}")

    session_name = os.path.basename(session_dir)
    project_md = os.path.join(session_dir, "project.md")
    if not os.path.isfile(project_md):
        raise RuntimeError(f"project.md ausente em {session_dir}")

    header = parse_header(project_md)
    repo_path = header.get("REPO_PATH") or "C:\\winegod-app"
    run_label = header.get("RUN_LABEL") or session_name

    return {
        "session_id": session_id,
        "session_name": session_name,
        "session_dir": session_dir,
        "session_log": os.path.join(session_dir, "session.log"),
        "codex_log": os.path.join(session_dir, "codex.log"),
        "claude_log": os.path.join(session_dir, "claude.log"),
        "repo_path": repo_path,
        "run_label": run_label,
        "project_md": project_md,
    }


def _session_process_alive(session_state):
    return _process_alive(session_state.data.get("orchestrator_pid"))


def _detect_v23_recovery_point(session_dir, session_state):
    """Descobre em que ponto do round a sessao V2.3 parou.

    Retorna dict com:
      - round_num
      - stage: "claude" ou "codex"
      - codex_path
      - claude_path
      - admin_text / claude_text conforme o stage

    Casos cobertos:
    - round-N-codex.md existe e round-N-claude.md nao existe -> parar no Claude
    - round-N-codex.md e round-N-claude.md existem, mas round-(N+1)-codex.md nao
      existe -> parar no Codex
    """
    current_round = int(session_state.data.get("current_round") or 0)
    round_num_state = int(session_state.data.get("round_num") or 0)
    last_ok = int(session_state.data.get("last_successful_round") or 0)
    round_stage = session_state.data.get("round_stage")

    candidates = []
    for candidate in (round_num_state, current_round, last_ok + 1, max(last_ok, 0)):
        if candidate > 0 and candidate not in candidates:
            candidates.append(candidate)

    preferred_stage = None
    if round_stage in (ROUND_STAGE_CODEX_PROMPT_SAVED, ROUND_STAGE_CLAUDE_IN_FLIGHT):
        preferred_stage = "claude"
    elif round_stage in (ROUND_STAGE_CLAUDE_DONE, ROUND_STAGE_CODEX_IN_FLIGHT):
        preferred_stage = "codex"
    elif round_stage in (ROUND_STAGE_WAITING_HUMAN, ROUND_STAGE_READY_FOR_CLOSE):
        preferred_stage = "claude"

    for round_num in candidates:
        padded = f"{round_num:03d}"
        codex_path = os.path.join(session_dir, f"round-{padded}-codex.md")
        claude_path = os.path.join(session_dir, f"round-{padded}-claude.md")
        next_codex_path = os.path.join(session_dir, f"round-{round_num + 1:03d}-codex.md")
        codex_exists = os.path.isfile(codex_path)
        claude_exists = os.path.isfile(claude_path)
        next_codex_exists = os.path.isfile(next_codex_path)
        if not codex_exists and not claude_exists:
            continue

        if preferred_stage == "claude" and codex_exists and not claude_exists:
            return {
                "round_num": round_num,
                "stage": "claude",
                "codex_path": codex_path,
                "claude_path": claude_path,
                "admin_text": _read(codex_path),
                "source": "state",
            }
        if preferred_stage == "codex" and claude_exists:
            return {
                "round_num": round_num,
                "stage": "codex",
                "codex_path": codex_path,
                "claude_path": claude_path,
                "claude_text": _read(claude_path),
                "source": "state",
            }

        if codex_exists and not claude_exists:
            return {
                "round_num": round_num,
                "stage": "claude",
                "codex_path": codex_path,
                "claude_path": claude_path,
                "admin_text": _read(codex_path),
                "source": "filesystem",
            }
        if claude_exists and not next_codex_exists:
            return {
                "round_num": round_num,
                "stage": "codex",
                "codex_path": codex_path,
                "claude_path": claude_path,
                "claude_text": _read(claude_path),
                "source": "filesystem",
            }

    raise RuntimeError(
        f"Nao foi possivel inferir ponto de recovery V2.3 para {session_state.session_id}. "
        f"current_round={current_round}, round_num={round_num_state}, "
        f"last_successful_round={last_ok}, round_stage={round_stage}"
    )


def _classify_recovery_confidence(session_state, recovery, recovered_claude_text=None):
    """Classifica o quao seguro e seguir automatico a partir dos sinais atuais."""
    stage = recovery.get("stage")
    source = recovery.get("source")
    round_stage = session_state.data.get("round_stage")

    if stage == "claude" and recovered_claude_text:
        return RECOVERY_CONFIDENCE_HIGH

    if stage == "claude" and source == "state" and round_stage in (
        ROUND_STAGE_CODEX_PROMPT_SAVED, ROUND_STAGE_CLAUDE_IN_FLIGHT,
        ROUND_STAGE_WAITING_HUMAN, ROUND_STAGE_READY_FOR_CLOSE,
    ):
        return RECOVERY_CONFIDENCE_MEDIUM

    if stage == "codex" and source == "state" and round_stage in (
        ROUND_STAGE_CLAUDE_DONE, ROUND_STAGE_CODEX_IN_FLIGHT,
    ):
        return RECOVERY_CONFIDENCE_MEDIUM

    if stage in ("claude", "codex") and source == "filesystem":
        return RECOVERY_CONFIDENCE_MEDIUM

    return RECOVERY_CONFIDENCE_LOW


def _find_claude_jsonl_for_uuid(session_uuid):
    """Tenta localizar o JSONL persistente do Claude para um session UUID."""
    base = os.path.expanduser("~/.claude/projects")
    if not os.path.isdir(base):
        return None
    try:
        for root, _, files in os.walk(base):
            candidate = os.path.join(root, f"{session_uuid}.jsonl")
            if os.path.isfile(candidate):
                return candidate
    except Exception:
        pass
    return None


def _extract_last_claude_end_turn_from_jsonl(session_uuid):
    """Extrai o ultimo texto final (`end_turn`) do Claude no JSONL persistente.

    Serve para recuperar respostas que foram produzidas pelo Claude mesmo
    depois que o orquestrador perdeu o controle do round.
    """
    path = _find_claude_jsonl_for_uuid(session_uuid)
    if not path or not os.path.isfile(path):
        return None
    last_text = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message") or {}
                if not isinstance(msg, dict):
                    continue
                if msg.get("role") != "assistant":
                    continue
                if msg.get("stop_reason") != "end_turn":
                    continue
                content = msg.get("content")
                parts = []
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            parts.append(c.get("text", ""))
                elif isinstance(content, str):
                    parts.append(content)
                text = "\n".join(p for p in parts if p).strip()
                if text:
                    last_text = text
    except Exception:
        return None
    return last_text


def _extract_last_claude_partial_from_jsonl(session_uuid):
    """Extrai o ultimo texto de assistant mesmo sem `end_turn`.

    V2.5: uma resposta possivelmente parcial nao deve parar a sessao por si so.
    Ela vira insumo para o Codex avaliar, reprovar ou pedir complemento.
    """
    path = _find_claude_jsonl_for_uuid(session_uuid)
    if not path or not os.path.isfile(path):
        return None
    last_text = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message") or {}
                if not isinstance(msg, dict) or msg.get("role") != "assistant":
                    continue
                if msg.get("stop_reason") == "end_turn":
                    continue
                content = msg.get("content")
                parts = []
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            parts.append(c.get("text", ""))
                elif isinstance(content, str):
                    parts.append(content)
                text = "\n".join(p for p in parts if p).strip()
                if text:
                    last_text = text
    except Exception:
        return None
    return last_text


def _read_optional(path, max_chars=None):
    try:
        text = _read(path)
    except Exception:
        return ""
    if max_chars and len(text) > max_chars:
        return text[-max_chars:]
    return text


def _latest_checkpoint_path(session_dir):
    try:
        candidates = [
            os.path.join(session_dir, f)
            for f in os.listdir(session_dir)
            if f.startswith("summary_") and f.endswith(".md")
        ]
    except Exception:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda p: os.path.getmtime(p))


def _round_artifact_path(session_dir, round_num, role, suffix=None):
    padded = f"{int(round_num):03d}"
    tail = f"-{suffix}" if suffix else ""
    return os.path.join(session_dir, f"round-{padded}-{role}{tail}.md")


def _write_sidecar_artifact(session_dir, round_num, role, suffix, content):
    """Salva artefato recuperado/parcial sem sobrescrever original existente."""
    base = _round_artifact_path(session_dir, round_num, role, suffix=suffix)
    if not os.path.exists(base):
        _write(base, content)
        return base
    existing = _read_optional(base)
    if existing == (content or ""):
        return base
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _round_artifact_path(session_dir, round_num, role,
                                suffix=f"{suffix}-{stamp}")
    _write(path, content)
    return path


def _round_artifacts_by_role(session_dir):
    """Retorna mapas {round: path} para codex/claude, preferindo artefato normal."""
    result = {"codex": {}, "claude": {}}
    priorities = {"": 0, "recovered": 1, "partial": 2}
    try:
        files = os.listdir(session_dir)
    except Exception:
        return result
    pattern = re.compile(r"^round-(\d{3})-(codex|claude)(?:-([A-Za-z0-9_-]+))?\.md$")
    for fname in files:
        m = pattern.match(fname)
        if not m:
            continue
        num = int(m.group(1))
        role = m.group(2)
        suffix = m.group(3) or ""
        suffix_key = suffix.split("-")[0]
        priority = priorities.get(suffix_key, 3)
        old = result[role].get(num)
        if old is None:
            result[role][num] = os.path.join(session_dir, fname)
            continue
        old_name = os.path.basename(old)
        old_suffix_match = pattern.match(old_name)
        old_suffix = (old_suffix_match.group(3) if old_suffix_match else "") or ""
        old_priority = priorities.get(old_suffix.split("-")[0], 3)
        if priority < old_priority:
            result[role][num] = os.path.join(session_dir, fname)
    return result


def _rebuild_state_from_filesystem(session_dir, session_state):
    """Reconstrui o ponto mais avancado confiavel olhando os artefatos em disco."""
    artifacts = _round_artifacts_by_role(session_dir)
    codex = artifacts["codex"]
    claude = artifacts["claude"]
    if not codex and not claude:
        return None

    all_rounds = sorted(set(codex) | set(claude))
    max_round = max(all_rounds)
    max_codex = max(codex) if codex else 0
    max_claude = max(claude) if claude else 0

    if max_codex and max_codex not in claude:
        round_num = max_codex
        codex_path = codex[round_num]
        recovery = {
            "round_num": round_num,
            "stage": "claude",
            "codex_path": codex_path,
            "claude_path": _round_artifact_path(session_dir, round_num, "claude"),
            "admin_text": _read_optional(codex_path),
            "source": "filesystem_rebuild",
        }
        _set_round_stage(
            session_state, round_num, ROUND_STAGE_CLAUDE_IN_FLIGHT,
            codex_prompt_hash=_hash_text(recovery["admin_text"]),
        )
        return recovery

    if max_claude and (max_claude + 1) not in codex:
        round_num = max_claude
        claude_path = claude[round_num]
        recovery = {
            "round_num": round_num,
            "stage": "codex",
            "codex_path": codex.get(round_num) or _round_artifact_path(session_dir, round_num, "codex"),
            "claude_path": claude_path,
            "claude_text": _read_optional(claude_path),
            "source": "filesystem_rebuild",
        }
        _set_round_stage(
            session_state, round_num, ROUND_STAGE_CODEX_IN_FLIGHT,
            claude_reply_hash=_hash_text(recovery["claude_text"]),
        )
        return recovery

    if max_codex:
        round_num = max_codex
        codex_path = codex[round_num]
        recovery = {
            "round_num": round_num,
            "stage": "claude",
            "codex_path": codex_path,
            "claude_path": claude.get(round_num) or _round_artifact_path(session_dir, round_num, "claude"),
            "admin_text": _read_optional(codex_path),
            "source": "filesystem_rebuild",
        }
        _set_round_stage(
            session_state, round_num, ROUND_STAGE_CLAUDE_IN_FLIGHT,
            codex_prompt_hash=_hash_text(recovery["admin_text"]),
        )
        return recovery

    round_num = max_round
    return {
        "round_num": round_num,
        "stage": "claude",
        "codex_path": _round_artifact_path(session_dir, round_num, "codex"),
        "claude_path": _round_artifact_path(session_dir, round_num, "claude"),
        "admin_text": "",
        "source": "filesystem_rebuild",
    }


def _strip_html(text):
    text = re.sub(r"(?is)<script.*?</script>", " ", text or "")
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _recover_missing_round_artifact(session_dir, round_num, role):
    """Tenta reconstruir um artefato de round sem sobrescrever originais."""
    main = _round_artifact_path(session_dir, round_num, role)
    if os.path.isfile(main):
        return main, _read_optional(main), "main"
    for suffix in ("recovered", "partial"):
        alt = _round_artifact_path(session_dir, round_num, role, suffix=suffix)
        if os.path.isfile(alt):
            return alt, _read_optional(alt), suffix

    marker = f"round-{int(round_num):03d}-{role}.md"
    for source_name in ("session_conversation.html", "session.html"):
        path = os.path.join(session_dir, source_name)
        text = _read_optional(path, max_chars=120000)
        if marker in text:
            plain = _strip_html(text)
            idx = plain.find(marker)
            snippet = plain[max(0, idx - 500): idx + 8000] if idx >= 0 else plain[:8000]
            if snippet.strip():
                out = _write_sidecar_artifact(session_dir, round_num, role,
                                             "recovered", snippet.strip())
                return out, snippet.strip(), source_name

    ckpt = _latest_checkpoint_path(session_dir)
    if ckpt:
        text = _read_optional(ckpt, max_chars=120000)
        if marker in text:
            idx = text.find(marker)
            snippet = text[max(0, idx - 500): idx + 8000] if idx >= 0 else text[:8000]
            out = _write_sidecar_artifact(session_dir, round_num, role,
                                         "recovered", snippet.strip())
            return out, snippet.strip(), os.path.basename(ckpt)
    return None, None, None


def _build_checkpoint_reprompt(session, session_state, last_prompt="", note=""):
    """Monta prompt de continuidade quando JSONL/round final nao estao disponiveis."""
    session_dir = session["session_dir"]
    project = _read_optional(os.path.join(session_dir, "project.md"), max_chars=12000)
    ckpt_path = _latest_checkpoint_path(session_dir)
    checkpoint = _read_optional(ckpt_path, max_chars=25000) if ckpt_path else ""
    state_json = json.dumps(session_state.data, indent=2, ensure_ascii=False)
    return f"""RECOVERY AUTOMATICO V2.5 - CONTINUAR SEM DUPLICAR TRABALHO

Voce esta retomando uma sessao apos falha do orquestrador.
Objetivo: continuar do ponto mais provavel, sem reiniciar o projeto e sem duplicar artefatos ja existentes.

Regras obrigatorias:
- Antes de executar qualquer coisa cara, verifique os arquivos existentes no repo e na pasta da sessao.
- Se o trabalho pedido ja foi feito, responda com evidencias e nao rerode.
- Se faltar algo, complete somente o que falta.
- Nao avance fase sem aprovacao do Codex.
- Se houver risco destrutivo, credencial ausente ou decisao humana real, responda HUMANO.

Nota do recovery: {note or '-'}

SESSION-STATE:
```json
{state_json}
```

ULTIMO PROMPT CONHECIDO:
```text
{last_prompt or '(nao encontrado)'}
```

CHECKPOINT MAIS RECENTE:
```markdown
{checkpoint or '(nenhum checkpoint encontrado)'}
```

PROJECT.MD:
```markdown
{project or '(project.md ausente)'}
```
"""


def _wrap_partial_for_codex(partial_text, round_num, source="jsonl"):
    return f"""RECOVERY AUTOMATICO V2.5 - RESPOSTA POSSIVELMENTE PARCIAL DO CLAUDE

O orquestrador recuperou texto possivelmente parcial do Claude no round {int(round_num):03d}
a partir de `{source}`. Nao trate isto como aprovado automaticamente.

Sua funcao como Codex/admin:
- avalie se a resposta abaixo e suficiente;
- se estiver incompleta, reprove e mande um prompt corretivo objetivo ao Claude;
- se estiver suficiente, aprove e avance normalmente;
- se houver risco real ou decisao humana, escreva HUMANO.

RESPOSTA RECUPERADA:
```markdown
{partial_text}
```
"""


def _requires_human_stop(reason="", context=""):
    """Guardrail: so para quando ha decisao humana/credencial/risco destrutivo."""
    joined = f"{reason or ''}\n{context or ''}"
    if _has_marker(joined, HUMANO_MARKER):
        return True
    lower = joined.lower()
    credential_terms = [
        "missing api key", "api key ausente", "anthropic_api_key ausente",
        "database_url ausente", "credential missing", "credencial ausente",
        "authentication failed", "permission denied",
    ]
    destructive_terms = [
        "drop table", "truncate table", "delete from wines",
        "remove-item -recurse", "rm -rf", "git reset --hard",
    ]
    if any(term in lower for term in credential_terms):
        return True
    if any(term in lower for term in destructive_terms):
        return True
    return False


def _choose_aggressive_recovery_strategy(session, session_state, recovery,
                                         recovered_claude_text=None,
                                         partial_claude_text=None):
    """Escolhe estrategia V2.5: tentar seguir sempre que houver contexto minimo."""
    context = "\n".join([
        recovery.get("admin_text") or "",
        recovery.get("claude_text") or "",
        recovered_claude_text or "",
        partial_claude_text or "",
        session_state.data.get("paused_reason") or "",
    ])
    if _requires_human_stop(session_state.data.get("paused_reason") or "", context):
        return RECOVERY_STRATEGY_HUMAN_REQUIRED, "guardrail humano/credencial/risco"
    if recovered_claude_text:
        return RECOVERY_STRATEGY_JSONL_EXACT, "resposta final encontrada no JSONL"
    if partial_claude_text:
        return RECOVERY_STRATEGY_PARTIAL_TO_CODEX, "resposta parcial enviada ao Codex para julgamento"
    if recovery.get("source") in ("filesystem", "filesystem_rebuild") and recovery.get("stage") == "codex":
        return RECOVERY_STRATEGY_FILESYSTEM_REBUILD, "estado reconstruido pelo maior round valido em disco"
    if recovery.get("source") == "checkpoint_reprompt":
        return RECOVERY_STRATEGY_CHECKPOINT_REPROMPT, "reprompt a partir do checkpoint mais recente"
    if recovery.get("stage") == "claude" and (recovery.get("admin_text") or "").strip():
        return RECOVERY_STRATEGY_LAST_PROMPT_REPLAY, "replay seguro do ultimo prompt do Codex"
    if _latest_checkpoint_path(session["session_dir"]):
        return RECOVERY_STRATEGY_CHECKPOINT_REPROMPT, "reprompt a partir do checkpoint mais recente"
    return RECOVERY_STRATEGY_HUMAN_REQUIRED, "sem contexto minimo para continuar"


def _resume_v23_session(session_id, recovery_mode="manual"):
    """Motor unico de retomada V2.4.

    Usado por `recover` (manual) e por `continue` quando o processo original
    morreu. Reconciliacao guiada por `round_stage` + artefatos em disco.
    """
    _install_sigint_handler()
    session = _build_existing_session(session_id)
    sd = session["session_dir"]
    sl = session["session_log"]
    codex_log = session["codex_log"]
    claude_log = session["claude_log"]
    repo_path = session["repo_path"]
    run_label = session["run_label"]

    session_state = SessionState(sd)
    if not session_state.load():
        print(f"ERRO: session-state.json nao encontrado em {sd}")
        sys.exit(1)

    claude_uuid = session_state.data.get("claude_session_uuid")
    codex_uuid = session_state.data.get("codex_session_uuid")
    if not claude_uuid or not codex_uuid:
        print("ERRO: sessao sem UUID persistente de Claude/Codex; nao e V2.3 recuperavel.")
        sys.exit(1)
    if not check_cli("claude") or not check_cli("codex"):
        print("ERRO: CLI claude ou codex nao encontrado.")
        sys.exit(1)

    detect_error = None
    try:
        recovery = _detect_v23_recovery_point(sd, session_state)
    except Exception as e:
        detect_error = str(e)
        recovery = _rebuild_state_from_filesystem(sd, session_state)
        if recovery is None:
            round_guess = int(session_state.data.get("current_round") or 0)
            round_guess = max(round_guess, int(session_state.data.get("last_successful_round") or 0) + 1, 1)
            recovery = {
                "round_num": round_guess,
                "stage": "claude",
                "codex_path": _round_artifact_path(sd, round_guess, "codex"),
                "claude_path": _round_artifact_path(sd, round_guess, "claude"),
                "admin_text": _build_checkpoint_reprompt(
                    session, session_state, last_prompt="",
                    note=f"detect falhou: {detect_error}",
                ),
                "source": "checkpoint_reprompt",
            }
    round_num = recovery["round_num"]
    padded = f"{round_num:03d}"
    recovered_claude_text = None
    partial_claude_text = None
    if recovery["stage"] == "claude":
        recovered_claude_text = _extract_last_claude_end_turn_from_jsonl(claude_uuid)
        if not recovered_claude_text:
            partial_claude_text = _extract_last_claude_partial_from_jsonl(claude_uuid)
    if recovery["stage"] == "codex" and not recovery.get("claude_text"):
        _, recovered_text, source_name = _recover_missing_round_artifact(sd, round_num, "claude")
        if recovered_text:
            recovery["claude_text"] = recovered_text
            recovery["source"] = f"artifact_recovery:{source_name}"

    confidence = _classify_recovery_confidence(
        session_state, recovery, recovered_claude_text=recovered_claude_text
    )
    strategy, recovery_note = _choose_aggressive_recovery_strategy(
        session, session_state, recovery,
        recovered_claude_text=recovered_claude_text,
        partial_claude_text=partial_claude_text,
    )
    recovered_from = (
        "jsonl" if strategy == RECOVERY_STRATEGY_JSONL_EXACT
        else ("partial_jsonl" if strategy == RECOVERY_STRATEGY_PARTIAL_TO_CODEX
              else ("checkpoint" if strategy == RECOVERY_STRATEGY_CHECKPOINT_REPROMPT
                    else ("process_resume" if recovery["stage"] == "claude"
                          else "filesystem_reconcile")))
    )

    print(f"Recover V2.5: {session['session_name']}")
    print(f"Repo:       {repo_path}")
    print(f"Round:      {padded}")
    print(f"Stage:      {recovery['stage']}")
    print(f"Confidence: {confidence}")
    print(f"Strategy:   {strategy}")
    print(f"Modo:       {recovery_mode}")
    print()

    if strategy == RECOVERY_STRATEGY_HUMAN_REQUIRED:
        reason = (
            f"Recovery requer humano: round={padded}, stage={recovery['stage']}, "
            f"round_stage={session_state.data.get('round_stage')}. {recovery_note}"
        )
        _record_recovery(
            session_state, recovery_mode, "human_required", confidence,
            strategy=strategy, note=recovery_note, error=detect_error,
        )
        session_state.transition(STATE_PAUSED_RECOVERABLE, reason=reason)
        _trigger_checkpoint(session, session_state, repo_path, round_num,
                           "human_required_recovery")
        print(f"ERRO: {reason}")
        return

    _record_recovery(
        session_state, recovery_mode, recovered_from, confidence,
        strategy=strategy, note=recovery_note, error=detect_error,
    )
    if recovery["stage"] == "claude" and recovered_claude_text:
        log(sl, f"Recover V2.5 iniciado no round {padded} (stage=claude, conf={confidence}, strategy={strategy})")
        log(sl, "Recover: resposta final do Claude reaproveitada do JSONL persistente")
    elif recovery["stage"] == "claude" and partial_claude_text:
        log(sl, f"Recover V2.5 iniciado no round {padded} com resposta parcial do Claude (strategy={strategy})")
    else:
        log(sl, f"Recover V2.5 iniciado no round {padded} (stage={recovery['stage']}, conf={confidence}, strategy={strategy})")

    stop_sentinel_path = os.path.join(sd, STOP_SENTINEL_NAME)

    def _stop_requested():
        try:
            return os.path.isfile(stop_sentinel_path)
        except Exception:
            return False

    def _claude_call(message, cwd):
        claude_path = check_cli("claude") or "claude"
        start_ts = datetime.datetime.now().timestamp()
        session_state.set(
            active_agent="claude",
            active_call_status="in_call",
            active_call_started_at=start_ts,
            orchestrator_pid=os.getpid(),
        )
        args = [
            "cmd", "/c", claude_path, "-p",
            "--dangerously-skip-permissions",
            "--resume", claude_uuid,
        ]
        # V2.8: heartbeat em thread paralela. Sem isso, recovery longa ficava
        # "cega" no dashboard por horas (bug observado na S-0027 round 12).
        sid = session_state.session_id
        rlabel = session_state.data.get("run_label")

        def _resume_heartbeat(info):
            # Poll mtime do JSONL do Claude pra detectar atividade real.
            jsonl_path = _find_claude_jsonl_for_uuid(claude_uuid)
            jsonl_mtime = None
            if jsonl_path and os.path.isfile(jsonl_path):
                try:
                    jsonl_mtime = os.path.getmtime(jsonl_path)
                except Exception:
                    jsonl_mtime = None
            try:
                session_state.set(
                    active_agent=info.get("active_agent") or "claude",
                    active_call_status=info.get("active_call_status"),
                    active_call_started_at=info.get("active_call_started_at"),
                    last_jsonl_mtime=jsonl_mtime,
                )
            except Exception:
                pass
            # Best-effort: atualiza registry global (multi-dupla)
            try:
                if sid:
                    registry_update_session(sid, {
                        "last_heartbeat": datetime.datetime.now().isoformat(),
                        "last_jsonl_mtime": jsonl_mtime,
                        "active_call_status": info.get("active_call_status"),
                        "run_label": rlabel,
                    })
            except Exception:
                pass

        result = run_command_with_heartbeat(
            args, timeout_s=12 * 3600, cwd=cwd, input_text=message,
            on_heartbeat=_resume_heartbeat,
        )
        jsonl_path = _find_claude_jsonl_for_uuid(claude_uuid)
        try:
            session_state.set(
                active_agent=None,
                active_call_status=None,
                active_call_started_at=None,
                last_jsonl_mtime=os.path.getmtime(jsonl_path) if jsonl_path and os.path.isfile(jsonl_path) else None,
                orchestrator_pid=os.getpid(),
            )
        except Exception:
            pass
        return result

    codex_uuid_ref = [codex_uuid]

    def _codex_call_resume(message, cwd):
        return _call_codex_session(codex_uuid_ref, message, cwd, first_call=False)

    def _handle_pause(exc, checkpoint_reason, current_round_num):
        _trigger_checkpoint(session, session_state, repo_path,
                           current_round_num, checkpoint_reason)
        log(sl, f"Pausado em PAUSED_RECOVERABLE: {exc}")
        cont = _busy_wait_for_state_change(session_state, sl,
                                           repo_path, run_label)
        if not cont:
            return False
        session_state.transition(STATE_RUNNING)
        session_state.set(orchestrator_pid=os.getpid(), paused_reason=None,
                          unknown_error_count=0, retry_count=0, next_retry_at=None)
        update_lock(repo_path, session_id, run_label, STATE_RUNNING)
        return True

    def _post_codex(admin_text, current_round_num):
        next_round_num = current_round_num + 1
        _persist_round_artifact(session_state, sd, next_round_num, "codex", admin_text)
        session_state.set(last_successful_round=current_round_num)

        if _has_marker(admin_text, CONCLUIDO_MARKER):
            log(sl, f"Codex sinalizou CONCLUIDO no round {current_round_num:03d}")
            session_state.transition(STATE_READY_FOR_HUMAN_CLOSE,
                                     reason=f"CONCLUIDO no round {current_round_num:03d}")
            session_state.set(round_stage=ROUND_STAGE_READY_FOR_CLOSE)
            _trigger_checkpoint(session, session_state, repo_path,
                               current_round_num, "ready_for_human_close")
            cont = _busy_wait_for_state_change(session_state, sl,
                                               repo_path, run_label)
            if not cont:
                return None
            session_state.transition(STATE_RUNNING)
            _set_round_stage(
                session_state, next_round_num, ROUND_STAGE_CODEX_PROMPT_SAVED,
                codex_prompt_hash=_hash_text(admin_text),
                codex_reply_hash=_hash_text(admin_text),
            )
            update_lock(repo_path, session_id, run_label, STATE_RUNNING)
            return _read(os.path.join(sd, f"round-{next_round_num:03d}-codex.md"))

        if _has_marker(admin_text, HUMANO_MARKER):
            log(sl, f"Codex sinalizou HUMANO no round {current_round_num:03d}")
            session_state.transition(
                STATE_WAITING_HUMAN,
                reason=f"HUMANO no round {current_round_num:03d}: {admin_text[:300]}"
            )
            session_state.set(round_stage=ROUND_STAGE_WAITING_HUMAN)
            _trigger_checkpoint(session, session_state, repo_path,
                               current_round_num, "waiting_human")
            cont = _busy_wait_for_state_change(session_state, sl,
                                               repo_path, run_label)
            if not cont:
                return None
            session_state.transition(STATE_RUNNING)
            _set_round_stage(
                session_state, next_round_num, ROUND_STAGE_CODEX_PROMPT_SAVED,
                codex_prompt_hash=_hash_text(admin_text),
                codex_reply_hash=_hash_text(admin_text),
            )
            update_lock(repo_path, session_id, run_label, STATE_RUNNING)
            return _read(os.path.join(sd, f"round-{next_round_num:03d}-codex.md"))

        if current_round_num % CHECKPOINT_EVERY_N_ROUNDS == 0:
            _trigger_checkpoint(session, session_state, repo_path,
                               current_round_num, f"round_{current_round_num}_cadencia")
        return admin_text

    try:
        session_state.set(
            paused_reason=None,
            unknown_error_count=0,
            retry_count=0,
            next_retry_at=None,
            orchestrator_pid=os.getpid(),
        )
        session_state.transition(STATE_RUNNING, reason=None)
        update_lock(repo_path, session_id, run_label, STATE_RUNNING)

        if recovery["stage"] == "claude":
            admin_prompt = recovery.get("admin_text") or ""
            if strategy in (
                RECOVERY_STRATEGY_LAST_PROMPT_REPLAY,
                RECOVERY_STRATEGY_CHECKPOINT_REPROMPT,
            ):
                admin_prompt = _build_checkpoint_reprompt(
                    session, session_state, last_prompt=admin_prompt,
                    note=recovery_note,
                )
                recovery["admin_text"] = admin_prompt

            log(sl, f"Recover: tratando round {padded} no stage Claude (strategy={strategy})")
            _set_round_stage(
                session_state, round_num, ROUND_STAGE_CLAUDE_IN_FLIGHT,
                codex_prompt_hash=_hash_text(admin_prompt),
            )
            if recovered_claude_text:
                claude_text = recovered_claude_text
                _persist_round_artifact(session_state, sd, round_num, "claude", claude_text)
            elif partial_claude_text:
                partial_path = _write_sidecar_artifact(
                    sd, round_num, "claude", "partial", partial_claude_text
                )
                claude_text = _wrap_partial_for_codex(
                    partial_claude_text, round_num, source=os.path.basename(partial_path)
                )
                _set_round_stage(
                    session_state, round_num, ROUND_STAGE_CODEX_IN_FLIGHT,
                    claude_reply_hash=_hash_text(claude_text),
                )
                log(sl, f"Recover: parcial do Claude salva em {os.path.basename(partial_path)} e enviada ao Codex")
            else:
                try:
                    claude_text = _call_with_retry(
                        _claude_call, admin_prompt, repo_path, session_state,
                        repo_path, run_label, "claude", claude_log, sl,
                    )
                    _persist_round_artifact(session_state, sd, round_num, "claude", claude_text)
                except RecoverablePauseError as e:
                    if not _handle_pause(e, "paused_recoverable_claude_recover", round_num):
                        return
                    recovery = _rebuild_state_from_filesystem(sd, session_state) or _detect_v23_recovery_point(sd, session_state)
                    round_num = recovery["round_num"]
                    padded = f"{round_num:03d}"
                    if recovery["stage"] == "claude":
                        claude_text = _call_with_retry(
                            _claude_call, recovery["admin_text"], repo_path, session_state,
                            repo_path, run_label, "claude", claude_log, sl,
                        )
                        _persist_round_artifact(session_state, sd, round_num, "claude", claude_text)
                    else:
                        claude_text = _read(os.path.join(sd, f"round-{padded}-claude.md"))

            recovery = {
                "round_num": round_num,
                "stage": "codex",
                "claude_text": claude_text,
                "source": "recovered_claude",
            }

        if recovery["stage"] == "codex":
            log(sl, f"Recover: enviando resposta do round {padded} ao Codex")
            _set_round_stage(
                session_state, round_num, ROUND_STAGE_CODEX_IN_FLIGHT,
                claude_reply_hash=_hash_text(recovery["claude_text"]),
            )
            try:
                admin_text = _call_with_retry(
                    _codex_call_resume, recovery["claude_text"], repo_path,
                    session_state, repo_path, run_label, "codex", codex_log, sl,
                )
            except RecoverablePauseError as e:
                if not _handle_pause(e, "paused_recoverable_codex_recover", round_num):
                    return
                admin_text = _call_with_retry(
                    _codex_call_resume, _read(os.path.join(sd, f"round-{padded}-claude.md")),
                    repo_path, session_state, repo_path, run_label, "codex",
                    codex_log, sl,
                )

            admin_text = _post_codex(admin_text, round_num)
            if admin_text is None:
                return
            round_num += 1

        print()
        log(sl, f"=== LOOP DUMB-PIPE (recover V2.5) a partir do round {round_num:03d} ===")
        codex_history = [admin_text] if 'admin_text' in locals() else []
        while True:
            if _interrupt_flag["set"]:
                raise KeyboardInterrupt()
            padded = f"{round_num:03d}"
            session_state.set(current_round=round_num, round_num=round_num,
                              orchestrator_pid=os.getpid())
            update_lock(repo_path, session_id, run_label, STATE_RUNNING)
            print()
            log(sl, f"=== ROUND {padded} ===")

            codex_path = os.path.join(sd, f"round-{padded}-codex.md")
            if not os.path.isfile(codex_path):
                _persist_round_artifact(session_state, sd, round_num, "codex", admin_text)
                log(sl, f"Salvei: round-{padded}-codex.md")
            else:
                _set_round_stage(
                    session_state, round_num, ROUND_STAGE_CODEX_PROMPT_SAVED,
                    codex_prompt_hash=_hash_text(_read(codex_path)),
                    codex_reply_hash=_hash_text(_read(codex_path)),
                )

            log(sl, f"Enviando ao Claude (round {padded})...")
            _set_round_stage(
                session_state, round_num, ROUND_STAGE_CLAUDE_IN_FLIGHT,
                codex_prompt_hash=_hash_text(admin_text),
            )
            try:
                claude_text = _call_with_retry(
                    _claude_call, admin_text, repo_path, session_state,
                    repo_path, run_label, "claude", claude_log, sl,
                )
            except RecoverablePauseError as e:
                if not _handle_pause(e, "paused_recoverable_claude", round_num):
                    return
                continue

            _persist_round_artifact(session_state, sd, round_num, "claude", claude_text)

            log(sl, f"Enviando ao Codex (round {padded})...")
            _set_round_stage(
                session_state, round_num, ROUND_STAGE_CODEX_IN_FLIGHT,
                claude_reply_hash=_hash_text(claude_text),
            )
            try:
                next_admin = _call_with_retry(
                    _codex_call_resume, claude_text, repo_path, session_state,
                    repo_path, run_label, "codex", codex_log, sl,
                )
            except RecoverablePauseError as e:
                if not _handle_pause(e, "paused_recoverable_codex", round_num):
                    return
                continue

            codex_history.append(next_admin)
            if _detect_loop(codex_history):
                _persist_round_artifact(session_state, sd, round_num + 1, "codex", next_admin)
                log(sl, f"Loop detectado no round {padded}: Codex repetindo")
                session_state.transition(STATE_PAUSED_RECOVERABLE,
                                         reason="Loop de respostas curtas detectado")
                _trigger_checkpoint(session, session_state, repo_path,
                                   round_num, "loop_detected")
                cont = _busy_wait_for_state_change(session_state, sl,
                                                   repo_path, run_label)
                if not cont:
                    return
                session_state.transition(STATE_RUNNING)
                _set_round_stage(
                    session_state, round_num + 1, ROUND_STAGE_CODEX_PROMPT_SAVED,
                    codex_prompt_hash=_hash_text(next_admin),
                    codex_reply_hash=_hash_text(next_admin),
                )
                update_lock(repo_path, session_id, run_label, STATE_RUNNING)
                admin_text = _read(os.path.join(sd, f"round-{round_num + 1:03d}-codex.md"))
                round_num += 1
                continue

            admin_text = _post_codex(next_admin, round_num)
            if admin_text is None:
                return
            round_num += 1

    except KeyboardInterrupt:
        print()
        log(sl, f"INTERRUPCAO: Ctrl+C recebido do usuario durante {recovery_mode} V2.4")
        _interrupt_flag["set"] = True
        session_state.transition(STATE_CLOSED_BY_HUMAN,
                                 reason=f"Ctrl+C do usuario ({recovery_mode} V2.4)")
        session_state.set(orchestrator_pid=None)
        update_lock(repo_path, session_id, run_label, STATE_CLOSED_BY_HUMAN)
        _trigger_checkpoint(session, session_state, repo_path,
                           session_state.data.get("current_round", 0),
                           "closed_by_ctrl_c")
        write_final_review(session, "INTERROMPIDO",
                          session_state.data.get("current_round", 0),
                          "Interrompido pelo usuario (Ctrl+C)",
                          _collect_round_files(sd))
        log(sl, "WORKFLOW INTERROMPIDO")
    finally:
        if session_state.state == STATE_CLOSED_BY_HUMAN:
            session_state.set(orchestrator_pid=None)


def run_recover_v23(session_id):
    """Fallback manual explicito para o mesmo motor de retomada V2.4."""
    return _resume_v23_session(session_id, recovery_mode="manual")


# === Test Workflow (offline validation) ===

def _mock_call(response_text):
    """Retorna um resultado simulado no formato de run_command, sem chamar CLI."""
    return {
        "ok": True,
        "exit_code": 0,
        "stdout": response_text,
        "stderr": "",
        "duration_ms": 0,
        "timed_out": False,
        "args": ["[mock]"],
    }


def mock_call_codex_admin(prompt, cwd=None, timeout_s=None, round_num=1):
    """Simula Codex criando tarefa para o round indicado."""
    if round_num == 1:
        return _mock_call(
            "**Round 001 - Validacao minima do workflow principal**\n\n"
            "**Fase/Subfase**\n"
            "Fase 4, primeiro round do loop principal com estado inicial de "
            "entendimento ja aprovado.\n\n"
            "**O que fazer agora**\n"
            "- Simule o estado inicial de entendimento aprovado.\n"
            "- Execute um unico round feliz do fluxo principal sem chamar "
            "codex nem claude reais.\n"
            "- Gere os arquivos round-001-admin.md, round-001-exec.md, "
            "round-001-review.md.\n\n"
            "**Criterios de aceitacao**\n"
            "- Nenhuma chamada real a API.\n"
            "- Arquivos gerados na pasta exclusiva da sessao.\n"
        )
    elif round_num == 2:
        return _mock_call(
            f"**Round {round_num:03d} - Validacao da continuidade do workflow**\n\n"
            "**Fase/Subfase**\n"
            f"Fase 4, continuidade do loop principal apos round {round_num - 1:03d} aprovado.\n\n"
            "**O que fazer agora**\n"
            f"- Confirme que o round {round_num - 1:03d} foi aprovado com sucesso.\n"
            "- Execute o segundo round do fluxo sem chamar CLIs reais.\n"
            f"- Gere os arquivos round-{round_num:03d}-admin.md, "
            f"round-{round_num:03d}-exec.md, round-{round_num:03d}-review.md.\n\n"
            "**Criterios de aceitacao**\n"
            "- Nenhuma chamada real a API.\n"
            f"- Round {round_num:03d} identifica claramente que e distinto do anterior.\n"
            "- Arquivos gerados na pasta exclusiva da sessao.\n"
        )
    else:
        return _mock_call(
            f"**Round {round_num:03d} - Validacao do encerramento do workflow**\n\n"
            "**Fase/Subfase**\n"
            f"Fase 4, encerramento do workflow principal apos os rounds "
            f"001 a {round_num - 1:03d} aprovados.\n\n"
            "**O que fazer agora**\n"
            f"- Confirme que os rounds anteriores (001 a {round_num - 1:03d}) "
            "estao aprovados e que o fluxo ja passou pela validacao minima "
            "e pela continuidade.\n"
            "- Execute a validacao do caminho de encerramento do workflow "
            "em modo de teste/offline.\n"
            "- Garanta que o encerramento gere final-review.md na pasta "
            "exclusiva da sessao, com status final e lista dos arquivos "
            "gerados.\n"
            "- Mantenha o escopo apenas em scripts/duo_orchestrator, "
            "sem chamadas reais a Codex, Claude ou API paga.\n\n"
            "**Criterios de aceitacao**\n"
            f"- O round {round_num:03d} valida explicitamente o fechamento "
            "do workflow, e nao apenas mais uma continuidade.\n"
            "- final-review.md e gerado na pasta exclusiva da sessao.\n"
            "- O final-review.md registra claramente o status final e os "
            "artefatos produzidos.\n"
            "- Nenhuma chamada real a API ou CLI paga ocorre durante a "
            "execucao.\n"
            "- Nenhum arquivo fora de scripts/duo_orchestrator e alterado.\n"
        )


def mock_call_claude_exec(prompt, cwd=None, timeout_s=None, round_num=1,
                          total_rounds=3):
    """Simula Claude executando a tarefa do round indicado."""
    if round_num < total_rounds:
        return _mock_call(
            "STATUS: EXECUTED\n\n"
            f"Tarefa do round {round_num:03d} executada com sucesso em modo de "
            "teste offline.\n\n"
            "Acoes realizadas:\n"
            f"- Round {round_num:03d} executado sem chamadas reais a CLIs.\n"
            f"- Arquivos round-{round_num:03d}-admin.md, "
            f"round-{round_num:03d}-exec.md e "
            f"round-{round_num:03d}-review.md gerados na pasta da sessao.\n\n"
            "Nenhuma API paga foi chamada. Nenhum arquivo fora de "
            "scripts/duo_orchestrator foi alterado.\n"
        )
    else:
        return _mock_call(
            "STATUS: EXECUTED\n\n"
            f"Validacao de encerramento do workflow (round {round_num:03d}) "
            "executada com sucesso.\n\n"
            "Verificacoes de encerramento realizadas:\n"
            f"- Rounds 001 a {round_num - 1:03d} confirmados como APROVADOS.\n"
            "- Caminho de encerramento validado: write_final_review() "
            "gera final-review.md com status final, total de rounds e "
            "lista de artefatos.\n"
            "- Nenhuma chamada real a API ou CLI paga durante toda a "
            "execucao.\n"
            "- Todos os arquivos gerados exclusivamente dentro da pasta "
            "da sessao.\n\n"
            "Conclusao: O workflow completo (validacao minima, continuidade "
            "e encerramento) foi exercitado e validado offline.\n"
        )


def mock_call_codex_review(prompt, cwd=None, timeout_s=None, round_num=1,
                           total_rounds=2):
    """Simula Codex julgando a execucao. APROVADO se nao e o ultimo, CONCLUIDO se e."""
    if round_num < total_rounds:
        return _mock_call(
            "STATUS: APROVADO\n\n"
            f"Round {round_num:03d} atende aos criterios de aceitacao:\n"
            "- Nenhuma chamada real a API.\n"
            "- Arquivos gerados corretamente na pasta da sessao.\n\n"
            f"Aprovado. Prosseguir para o round {round_num + 1:03d}.\n"
        )
    else:
        return _mock_call(
            "STATUS: CONCLUIDO\n\n"
            "Todos os criterios de aceitacao foram atendidos:\n"
            "- Nenhuma chamada real a API.\n"
            "- Arquivos gerados corretamente na pasta da sessao.\n"
            f"- Workflow simulado com sucesso em {total_rounds} rounds.\n\n"
            "Projeto concluido.\n"
        )


def run_test_workflow():
    """Executa workflow offline simulado: pula entendimento, roda 3 rounds mock.

    Nao requer brief externo nem CLIs reais. Gera sessao exclusiva com os
    arquivos round-001-*.md, round-002-*.md, round-003-*.md e final-review.md.

    Round 001: validacao minima — review retorna APROVADO.
    Round 002: continuidade — review retorna APROVADO.
    Round 003: encerramento — review retorna CONCLUIDO (fecha o workflow).
    """
    run_label = "Workflow-Admin-Check"
    total_rounds = 3

    print("=" * 50)
    print("  Duo Orchestrator V1 — Test Workflow (offline)")
    print("=" * 50)
    print()

    # --- Bootstrap manual (sem brief externo) ---
    session_id, session_name, session_dir = allocate_session_dir(run_label)

    print(f"Sessao: {session_name}")
    print(f"Pasta:  {session_dir}")
    print()

    session_log = os.path.join(session_dir, "session.log")
    codex_log = os.path.join(session_dir, "codex.log")
    claude_log = os.path.join(session_dir, "claude.log")

    for lf in [session_log, codex_log, claude_log]:
        with open(lf, "w", encoding="utf-8") as f:
            pass

    session = {
        "session_id": session_id,
        "session_name": session_name,
        "session_dir": session_dir,
        "session_log": session_log,
        "codex_log": codex_log,
        "claude_log": claude_log,
        "repo_path": "C:\\winegod-app",
    }

    sl = session_log
    sd = session_dir

    log(sl, f"Sessao iniciada (TEST MODE): {session_id}")
    log(sl, f"session_name: {session_name}")
    log(sl, f"run_label: {run_label}")
    log(sl, "Modo: test-workflow (offline, sem CLIs reais)")

    project_content = (
        "REPO_PATH: C:\\winegod-app\n"
        "RUN_LABEL: Workflow Admin Check\n"
        "MISSION: Validar fase 4 corrigida\n"
        "ALLOWED_PATHS: scripts/duo_orchestrator\n"
    )

    # Salva project.md
    with open(os.path.join(sd, "project.md"), "w", encoding="utf-8") as f:
        f.write(project_content)

    # --- Entendimento simulado como aprovado ---
    log(sl, "=== FASE DE ENTENDIMENTO (simulada como APROVADO) ===")
    log(sl, "UNDERSTANDING APROVADO (test mode — skip)")

    round_files = []

    # --- Loop principal: 3 rounds ---
    log(sl, "=== LOOP PRINCIPAL ===")

    for round_num in range(1, total_rounds + 1):
        padded = f"{round_num:03d}"

        print()
        log(sl, f"=== ROUND {padded} ===")

        # --- Admin cria tarefa (mock codex) ---
        log(sl, f"[MOCK] Codex criando tarefa do round {padded}...")
        admin_result = mock_call_codex_admin(None, round_num=round_num)
        log_cli_call(codex_log, "[mock-codex]", f"(admin task r{padded})",
                     admin_result)

        task_text = admin_result["stdout"].strip()
        admin_file = f"round-{padded}-admin.md"
        with open(os.path.join(sd, admin_file), "w", encoding="utf-8") as f:
            f.write(task_text)
        round_files.append(admin_file)
        log(sl, f"Tarefa criada: {admin_file}")

        # --- Claude executa (mock) ---
        log(sl, f"[MOCK] Claude executando round {padded}...")
        exec_result = mock_call_claude_exec(None, round_num=round_num,
                                            total_rounds=total_rounds)
        log_cli_call(claude_log, "[mock-claude]", f"(exec task r{padded})",
                     exec_result)

        exec_response = exec_result["stdout"].strip()
        exec_status, _ = parse_status(exec_response, VALID_EXEC_STATUSES)

        exec_file = f"round-{padded}-exec.md"
        with open(os.path.join(sd, exec_file), "w", encoding="utf-8") as f:
            f.write(exec_response)
        round_files.append(exec_file)
        log(sl, f"Executor status: {exec_status}")

        # --- Codex julga (mock) ---
        log(sl, f"[MOCK] Codex julgando round {padded}...")
        review_result = mock_call_codex_review(None, round_num=round_num,
                                               total_rounds=total_rounds)
        log_cli_call(codex_log, "[mock-codex]", f"(review r{padded})",
                     review_result)

        review_response = review_result["stdout"].strip()
        review_status, _ = parse_status(review_response, VALID_REVIEW_STATUSES)

        review_file = f"round-{padded}-review.md"
        with open(os.path.join(sd, review_file), "w", encoding="utf-8") as f:
            f.write(review_response)
        round_files.append(review_file)
        log(sl, f"Review status: {review_status}")

        if review_status == "CONCLUIDO":
            log(sl, f"Round {padded}: projeto concluido pelo administrador")
            break

        if review_status == "APROVADO":
            log(sl, f"Round {padded} aprovado. Prosseguindo para proximo round.")

    # --- Final review ---
    write_final_review(session, "CONCLUIDO", total_rounds,
                       "Projeto concluido pelo administrador (test mode)",
                       round_files)
    log(sl, "WORKFLOW CONCLUIDO (test mode)")

    print()
    print("=" * 50)
    print(f"  Test Workflow CONCLUIDO")
    print(f"  Pasta: {session_dir}")
    print(f"  Arquivos: {', '.join(round_files + ['final-review.md'])}")
    print("=" * 50)


# === Multi-dupla entry (V2.6) ===


def run_multi_workflow(brief_path, wt_mode=False):
    """V2.6: Workflow multi-dupla com workspace isolado.

    1. Aloca sessao atomicamente (antes de abrir abas)
    2. Cria workspace isolado (git worktree ou copia)
    3. Adapta o brief para apontar para o workspace
    4. Roda run_dumb_workflow com preallocated_session
    """
    brief_path, header = validate_brief(brief_path)
    run_label = header["RUN_LABEL"]
    base_repo_path = header["REPO_PATH"]

    print(f"=== Multi-Dupla V2.6 ===")
    print(f"Brief:    {brief_path}")
    print(f"Base repo: {base_repo_path}")
    print(f"Label:    {run_label}")
    print()

    # 1. Aloca sessao ANTES de abrir abas (evita corrida de S-XXXX)
    session_id, session_name, session_dir = allocate_session_dir(run_label)
    print(f"Sessao alocada: {session_id}")
    print(f"Pasta:  {session_dir}")

    # 2. Workspace isolado
    print("Preparando workspace isolado...")
    workspace_path, workspace_mode = _prepare_multi_workspace(
        base_repo_path, session_id, run_label, mode="auto")
    print(f"Workspace: {workspace_path}")
    print(f"Modo:      {workspace_mode}")
    print()

    # 3. Adaptar brief
    adapted_brief = _adapt_brief_for_multi(
        brief_path, session_dir, workspace_path, workspace_mode, base_repo_path)
    print(f"Brief adaptado: {adapted_brief}")

    multi_info = {
        "base_repo_path": base_repo_path,
        "workspace_path": workspace_path,
        "workspace_mode": workspace_mode,
    }

    preallocated = (session_id, session_name, session_dir)

    # 4. Roda workflow
    run_dumb_workflow(
        adapted_brief, wt_mode=wt_mode,
        preallocated_session=preallocated,
        multi_mode=True, multi_info=multi_info,
    )


def launch_wt_multi_and_exit(brief_path, header, session_id, session_name,
                             session_dir, adapted_brief):
    """Abre Windows Terminal com 3 abas para sessao multi prealocada."""
    run_label = header["RUN_LABEL"]
    safe_label = run_label.replace('"', "").replace("&", "e")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, "orchestrator.py")
    tailer_path = os.path.join(script_dir, "session_tailer.py")
    wt_path = check_cli("wt") or "wt"

    # A aba Orq recebe --internal-multi com session_dir e adapted_brief
    cmd = (
        f'"{wt_path}"'
        f' --title "Orq {session_id}"'
        f' -d "{session_dir}"'
        f' cmd /k python "{script_path}" --internal-multi'
        f' "{session_id}" "{session_name}" "{session_dir}" "{adapted_brief}"'
        f' ; new-tab'
        f' --title "Codex {session_id}"'
        f' -d "{session_dir}"'
        f' cmd /k python "{tailer_path}" {session_id} codex'
        f' ; new-tab'
        f' --title "Claude {session_id}"'
        f' -d "{session_dir}"'
        f' cmd /k python "{tailer_path}" {session_id} claude'
    )

    subprocess.Popen(cmd, shell=True)
    print(f"Windows Terminal aberto (3 abas) para multi: {run_label} [{session_id}]")
    print("Este terminal pode ser fechado.")
    sys.exit(0)


def run_multi_entry(brief_path):
    """Entry point para 'start_dupla.cmd multi <brief>'.

    Pre-aloca sessao e workspace ANTES de abrir Windows Terminal,
    depois lanca wt com os IDs reais (nao previstos).
    """
    brief_path, header = validate_brief(brief_path)
    run_label = header["RUN_LABEL"]
    base_repo_path = header["REPO_PATH"]

    print(f"=== Multi-Dupla V2.6 ===")
    print(f"Brief:     {brief_path}")
    print(f"Base repo: {base_repo_path}")
    print(f"Label:     {run_label}")
    print()

    # Pre-alocar sessao
    session_id, session_name, session_dir = allocate_session_dir(run_label)
    print(f"Sessao alocada: {session_id}")

    # Workspace isolado
    print("Preparando workspace isolado...")
    workspace_path, workspace_mode = _prepare_multi_workspace(
        base_repo_path, session_id, run_label, mode="auto")
    print(f"Workspace: {workspace_path} ({workspace_mode})")

    # Brief adaptado
    adapted_brief = _adapt_brief_for_multi(
        brief_path, session_dir, workspace_path, workspace_mode, base_repo_path)

    # Registry
    try:
        registry_update_session(session_id, {
            "session_id": session_id,
            "run_label": run_label,
            "state": STATE_BOOTSTRAP,
            "base_repo_path": base_repo_path,
            "workspace_path": workspace_path,
            "workspace_mode": workspace_mode,
            "session_dir": session_dir,
            "started_at": datetime.datetime.now().isoformat(),
        })
        generate_index_html()
    except Exception:
        pass

    # Abre wt com IDs reais
    if check_wt_available():
        launch_wt_multi_and_exit(brief_path, header, session_id, session_name,
                                 session_dir, adapted_brief)
    else:
        print("AVISO: Windows Terminal nao encontrado, rodando inline.")
        multi_info = {
            "base_repo_path": base_repo_path,
            "workspace_path": workspace_path,
            "workspace_mode": workspace_mode,
        }
        run_dumb_workflow(
            adapted_brief, wt_mode=False,
            preallocated_session=(session_id, session_name, session_dir),
            multi_mode=True, multi_info=multi_info,
        )


def run_list_sessions():
    """Imprime todas as sessoes e sai."""
    # V2.8: reconstroi registry.json a partir dos session-state.json reais
    # antes de listar, para garantir que cache global bate com disco.
    try:
        rebuild_registry_from_sessions()
    except Exception as e:
        print(f"AVISO: nao reconstruiu registry ({e}). Continuando com sessoes de disco.")
    sessions = list_all_sessions()
    print(format_session_list(sessions))


def run_status():
    """Imprime status resumido de todas as sessoes e sai."""
    # V2.8: registry rebuild antes de ler, para coerencia entre list/status/dashboard.
    try:
        rebuild_registry_from_sessions()
    except Exception as e:
        print(f"AVISO: nao reconstruiu registry ({e}). Continuando com sessoes de disco.")
    sessions = list_all_sessions()
    if not sessions:
        print("Nenhuma sessao encontrada.")
        return
    open_s = [s for s in sessions if s["state"] in OPEN_STATES]
    closed = [s for s in sessions if s["state"] not in OPEN_STATES]
    if open_s:
        print(f"=== {len(open_s)} sessao(oes) ativa(s) ===")
        print(format_session_list(open_s))
        print()
    if closed:
        print(f"=== {len(closed)} sessao(oes) encerrada(s) ===")
        print(format_session_list(closed))
    # Regenera index.html
    try:
        generate_index_html()
    except Exception as e:
        print(f"AVISO: nao regenerou index.html ({e}).")


# === Help ===

def print_help():
    """Imprime ajuda curta e legivel."""
    print("Duo Orchestrator V1 - Orquestrador Codex + Claude Code")
    print()
    print("USO BASICO (via start_dupla.cmd):")
    print("  start_dupla.cmd                       Pergunta brief e roda workflow")
    print("  start_dupla.cmd <brief.md>            Roda workflow com o brief")
    print("  start_dupla.cmd multi <brief.md>      Multi-dupla com workspace isolado")
    print("  start_dupla.cmd list                  Lista todas as sessoes")
    print("  start_dupla.cmd status                Status resumido das sessoes")
    print("  start_dupla.cmd resume S-0007        Retoma sessao legada V1 pelo ID")
    print("  start_dupla.cmd continue S-0027      Comando padrao: destrava ou recupera sessao V2.4")
    print("  start_dupla.cmd recover S-0027       Fallback tecnico: recovery manual da mesma sessao")
    print("  start_dupla.cmd understanding <brief> So fase de entendimento")
    print("  start_dupla.cmd probe <brief>         Testa claude e codex")
    print("  start_dupla.cmd help                  Esta ajuda")
    print()
    print("USO DIRETO (python):")
    print("  orchestrator.py --run-workflow <brief.md>")
    print("  orchestrator.py --resume <SESSION_ID>")
    print("  orchestrator.py --recover-v23 <SESSION_ID>")
    print("  orchestrator.py --run-understanding <brief.md>")
    print("  orchestrator.py --probe-clis <brief.md>")
    print("  orchestrator.py --help")
    print()
    print("FORMATO DO BRIEF:")
    print("  REPO_PATH: C:\\caminho\\do\\repo")
    print("  RUN_LABEL: Nome do Projeto")
    print("  MISSION: Descricao da missao")
    print("  ALLOWED_PATHS: path1, path2   (opcional)")
    print()
    print("  # Projeto Refinado")
    print("  ## Objetivo / ## Fases / ## Criterios / ## Restricoes")
    print()
    print("Template completo: docs\\TEMPLATE_PROJETO_REFINADO.md")
    print("Manual de uso:    docs\\ORQUESTRADOR_DUO_USO.md")
    print()
    print("ARQUIVOS GERADOS POR SESSAO:")
    print(f"  {SESSIONS_DIR}\\S-XXXX-<label>\\")
    print("    project.md, session.log, codex.log, claude.log")
    print("    round-000-claude-understanding.md")
    print("    round-000-codex-review.md")
    print("    round-XXX-admin.md / exec.md / review.md")
    print("    final-review.md")


# === Main ===

def main():
    # --help antes de qualquer banner
    if any(a in sys.argv for a in ("--help", "-h")):
        print_help()
        sys.exit(0)

    internal_mode = "--internal" in sys.argv
    internal_multi_mode = "--internal-multi" in sys.argv
    multi_mode = "--run-multi" in sys.argv
    probe_mode = "--probe-clis" in sys.argv
    understanding_mode = "--run-understanding" in sys.argv
    workflow_mode = "--run-workflow" in sys.argv
    test_workflow_mode = "--test-workflow" in sys.argv
    args = [a for a in sys.argv[1:]
            if a not in ("--internal", "--internal-multi", "--run-multi",
                         "--probe-clis", "--run-understanding",
                         "--run-workflow", "--test-workflow")]

    # Banner (so no modo normal, nao no internal)
    if not internal_mode and not internal_multi_mode:
        print("=" * 50)
        print("  Duo Orchestrator V1")
        print("=" * 50)
        print()

    # V2.6: list/status
    if args and args[0] == "--list-sessions":
        run_list_sessions()
        sys.exit(0)

    if args and args[0] == "--status":
        run_status()
        sys.exit(0)

    # V2.6: multi mode (pre-allocated)
    if internal_multi_mode:
        # args: session_id session_name session_dir adapted_brief
        if len(args) < 4:
            print("ERRO: --internal-multi requer session_id session_name session_dir brief")
            sys.exit(1)
        sid, sname, sdir, adapted = args[0], args[1], args[2], args[3]
        adapted, header = validate_brief(adapted)
        multi_info = {
            "base_repo_path": header.get("BASE_REPO_PATH", ""),
            "workspace_path": header.get("REPO_PATH", ""),
            "workspace_mode": header.get("WORKSPACE_MODE", "copy_workspace"),
        }
        run_dumb_workflow(
            adapted, wt_mode=True,
            preallocated_session=(sid, sname, sdir),
            multi_mode=True, multi_info=multi_info,
        )
        sys.exit(0)

    if multi_mode:
        brief_path = args[0] if args else None
        if not brief_path:
            print("ERRO: --run-multi requer caminho do brief.")
            print("Uso: orchestrator.py --run-multi <brief.md>")
            sys.exit(1)
        run_multi_entry(brief_path)
        sys.exit(0)

    # Resume (Fase 5 V1, mantido como legado)
    if args and args[0] == "--resume":
        target = args[1] if len(args) > 1 else None
        if not target:
            print("ERRO: --resume requer SESSION_ID.")
            print("Uso: orchestrator.py --resume S-0003")
            sys.exit(1)
        run_resume(target)
        sys.exit(0)

    # Close (V2.3)
    if args and args[0] == "--close":
        target = args[1] if len(args) > 1 else None
        if not target:
            print("ERRO: --close requer SESSION_ID.")
            print("Uso: orchestrator.py --close S-0025")
            sys.exit(1)
        run_close(target)
        sys.exit(0)

    # Continue (V2.3)
    if args and args[0] == "--continue":
        target = args[1] if len(args) > 1 else None
        if not target:
            print("ERRO: --continue requer SESSION_ID.")
            print("Uso: orchestrator.py --continue S-0025")
            sys.exit(1)
        run_continue(target)
        sys.exit(0)

    # Recover V2.3 (reatacha aos UUIDs persistentes e retoma no round parado)
    if args and args[0] == "--recover-v23":
        target = args[1] if len(args) > 1 else None
        if not target:
            print("ERRO: --recover-v23 requer SESSION_ID.")
            print("Uso: orchestrator.py --recover-v23 S-0027")
            sys.exit(1)
        run_recover_v23(target)
        sys.exit(0)

    # Probe mode (Fase 2)
    if probe_mode:
        brief_path = args[0] if args else None
        if not brief_path:
            print("ERRO: --probe-clis requer caminho do brief.")
            print("Uso: orchestrator.py --probe-clis <brief.md>")
            sys.exit(1)
        run_probe(brief_path)
        sys.exit(0)

    # Test workflow mode (validacao offline, sem CLIs reais)
    if test_workflow_mode:
        run_test_workflow()
        sys.exit(0)

    # Understanding mode (Fase 3)
    if understanding_mode:
        brief_path = args[0] if args else None
        if not brief_path:
            print("ERRO: --run-understanding requer caminho do brief.")
            print("Uso: orchestrator.py --run-understanding <brief.md>")
            sys.exit(1)
        run_understanding(brief_path)
        sys.exit(0)

    # Workflow mode (Fase 4)
    if workflow_mode:
        brief_path = args[0] if args else None
        if not brief_path:
            print("ERRO: --run-workflow requer caminho do brief.")
            print("Uso: orchestrator.py --run-workflow <brief.md>")
            sys.exit(1)
        brief_path, header = validate_brief(brief_path)
        if internal_mode:
            run_workflow(brief_path, wt_mode=True)
        elif check_wt_available():
            print("Windows Terminal detectado. Abrindo aba Orq...")
            launch_wt_and_exit(brief_path, header, mode_args=["--run-workflow"])
        else:
            print("AVISO: Windows Terminal (wt) nao encontrado no PATH.")
            print("Rodando no terminal atual sem abas separadas.")
            print()
            run_workflow(brief_path, wt_mode=False)
        sys.exit(0)

    # Caminho do brief
    if args:
        brief_path = args[0]
    elif not internal_mode:
        brief_path = input("Caminho do arquivo do projeto refinado: ").strip()
    else:
        print("ERRO: --internal requer caminho do brief como argumento.")
        sys.exit(1)

    # Validacao
    brief_path, header = validate_brief(brief_path)

    run_label = header["RUN_LABEL"]
    repo_path = header["REPO_PATH"]
    mission = header["MISSION"]
    allowed_paths = header.get("ALLOWED_PATHS", "")

    print(f"Projeto: {brief_path}")
    print(f"Repo:    {repo_path}")
    print(f"Label:   {run_label}")
    print(f"Missao:  {mission}")
    if allowed_paths:
        print(f"Paths:   {allowed_paths}")
    print()

    if internal_mode:
        # Dentro da aba Orq do wt — executa o bootstrap real
        print(f"=== Orquestrador - {run_label} ===")
        print()
        run_bootstrap(brief_path, header, wt_mode=True)

    else:
        # Modo normal — tenta abrir wt e relancar como --internal
        if check_wt_available():
            print("Windows Terminal detectado. Abrindo aba Orq...")
            launch_wt_and_exit(brief_path, header)
            # Nao retorna — sys.exit(0) dentro da funcao

        else:
            print("AVISO: Windows Terminal (wt) nao encontrado no PATH.")
            print("Rodando no terminal atual sem abas separadas.")
            print()
            run_bootstrap(brief_path, header, wt_mode=False)
            print()
            input("Pressione Enter para encerrar.")


if __name__ == "__main__":
    main()
