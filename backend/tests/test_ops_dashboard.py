"""Testes do dashboard /ops (Fase 3A).

Cobrem:
1. OPS_DASHBOARD_ENABLED=false -> 404 em TODAS as rotas UI e UI-API.
2. /ops/login aparece quando dashboard enabled.
3. Token invalido nao autentica.
4. Token valido cria sessao.
5. /ops renderiza home autenticada.
6. /ops/scraper/<id> renderiza detail com 10 secoes.
7. Labels "Observado" / "Enviado" presentes; nenhuma "inseridos"/"contribuicao".
8. /ops/alerts renderiza lista vazia sem erro.
9. POST /ops/alerts/ack retorna 404 (deliberadamente ausente).
10. Endpoints SDK legados `/ops/health`, `/ops/scrapers`, `/ops/runs` continuam respondendo.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
SDK_ROOT = REPO_ROOT / "sdk"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client_dashboard_on(monkeypatch):
    """Cliente com OPS_DASHBOARD_ENABLED=true + token conhecido."""
    from config import Config as _Cfg
    monkeypatch.setattr(_Cfg, "OPS_API_ENABLED", True)
    monkeypatch.setattr(_Cfg, "OPS_WRITE_ENABLED", True)
    monkeypatch.setattr(_Cfg, "OPS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(_Cfg, "OPS_DASHBOARD_TOKEN", "test-dashboard-token-abc123")
    monkeypatch.setattr(_Cfg, "OPS_TOKEN", "test-api-token")
    monkeypatch.setattr(_Cfg, "OPS_SESSION_SECRET", "test-session-secret-xyz")
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def client_dashboard_off(monkeypatch):
    """Cliente com OPS_DASHBOARD_ENABLED=false (MVP default)."""
    from config import Config as _Cfg
    monkeypatch.setattr(_Cfg, "OPS_API_ENABLED", True)
    monkeypatch.setattr(_Cfg, "OPS_WRITE_ENABLED", True)
    monkeypatch.setattr(_Cfg, "OPS_DASHBOARD_ENABLED", False)
    monkeypatch.setattr(_Cfg, "OPS_DASHBOARD_TOKEN", "")
    monkeypatch.setattr(_Cfg, "OPS_TOKEN", "test-api-token")
    monkeypatch.setattr(_Cfg, "OPS_SESSION_SECRET", "test-session-secret-xyz")
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _login(client, token="test-dashboard-token-abc123"):
    """Autentica no dashboard; retorna resposta do POST /ops/login."""
    return client.post("/ops/login", data={"token": token}, follow_redirects=False)


# ---------------------------------------------------------------------------
# 1. OPS_DASHBOARD_ENABLED=false -> 404 em todas as UI/UI-API
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/ops/login",
    "/ops/home",
    "/ops",
    "/ops/scraper/anything",
    "/ops/alerts",
    "/ops/ui/api/summary",
    "/ops/ui/api/scrapers",
    "/ops/ui/api/scraper/anything",
    "/ops/ui/api/alerts",
])
def test_dashboard_disabled_returns_404(client_dashboard_off, path):
    r = client_dashboard_off.get(path)
    assert r.status_code == 404, f"{path} deveria retornar 404 quando OPS_DASHBOARD_ENABLED=false; got {r.status_code}"


def test_dashboard_disabled_login_post_404(client_dashboard_off):
    r = client_dashboard_off.post("/ops/login", data={"token": "x"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 2. /ops/login aparece quando dashboard enabled
# ---------------------------------------------------------------------------

def test_login_page_renders_when_enabled(client_dashboard_on):
    r = client_dashboard_on.get("/ops/login")
    assert r.status_code == 200
    body = r.data.decode("utf-8").lower()
    assert "token" in body or "login" in body or "entrar" in body


# ---------------------------------------------------------------------------
# 3. Token invalido nao autentica
# ---------------------------------------------------------------------------

def test_invalid_token_rejected(client_dashboard_on):
    r = client_dashboard_on.post("/ops/login", data={"token": "WRONG"})
    assert r.status_code == 401


def test_empty_token_rejected(client_dashboard_on):
    r = client_dashboard_on.post("/ops/login", data={"token": ""})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 4. Token valido cria sessao + 5. /ops renderiza home autenticada
# ---------------------------------------------------------------------------

def test_valid_token_creates_session_and_home(client_dashboard_on, monkeypatch):
    # Mock dos endpoints UI-API para nao precisar de banco
    from routes import ops_dashboard as od

    def _fake_home(): return {"error": None}
    # Nao vamos mockar, vamos chamar direto o HTML e deixar o JS polling tratar
    r = _login(client_dashboard_on, "test-dashboard-token-abc123")
    # Apos login bem-sucedido -> redirect 302 para /ops/home
    assert r.status_code in (302, 303)
    assert "/ops" in r.headers.get("Location", "")

    r2 = client_dashboard_on.get("/ops", follow_redirects=False)
    # Autenticado -> deve renderizar HTML (nao redirecionar para login)
    assert r2.status_code == 200
    body = r2.data.decode("utf-8")
    assert "canary" in body.lower() or "scrapers" in body.lower() or "control tower" in body.lower()


# ---------------------------------------------------------------------------
# 6. /ops/scraper/<id> renderiza detail com 10 secoes
# ---------------------------------------------------------------------------

def test_scraper_detail_has_10_sections(client_dashboard_on):
    _login(client_dashboard_on)
    r = client_dashboard_on.get("/ops/scraper/canary_synthetic")
    assert r.status_code == 200
    body = r.data.decode("utf-8")
    # Cada numero de 1. a 10. precisa estar presente nos titulos de seção
    for n in range(1, 11):
        assert f"{n}." in body, f"Seção {n}. nao encontrada no scraper_detail"


# ---------------------------------------------------------------------------
# 7. Labels "Observado" / "Enviado"; proibido "inseridos"/"contribuicao"
# ---------------------------------------------------------------------------

def test_home_uses_observed_sent_not_inserted(client_dashboard_on):
    _login(client_dashboard_on)
    r = client_dashboard_on.get("/ops/home")
    assert r.status_code == 200
    body = r.data.decode("utf-8")
    assert "Observado" in body or "observado" in body
    assert "Enviado" in body or "enviado" in body
    # Negativo: nunca usar linguagem de ingestao
    lowered = body.lower()
    assert "inseridos" not in lowered
    assert "contribuicao ao banco" not in lowered
    assert "contribuição ao banco" not in lowered


def test_scraper_detail_uses_observed_sent(client_dashboard_on):
    _login(client_dashboard_on)
    r = client_dashboard_on.get("/ops/scraper/canary_synthetic")
    body = r.data.decode("utf-8").lower()
    assert "observado" in body
    assert "enviado" in body
    assert "inseridos" not in body
    assert "contribuicao ao banco" not in body


# ---------------------------------------------------------------------------
# 8. /ops/alerts renderiza sem erro mesmo sem dados
# ---------------------------------------------------------------------------

def test_alerts_page_renders(client_dashboard_on):
    _login(client_dashboard_on)
    r = client_dashboard_on.get("/ops/alerts")
    assert r.status_code == 200
    body = r.data.decode("utf-8").lower()
    assert "alerta" in body


# ---------------------------------------------------------------------------
# 9. POST /ops/alerts/ack retorna 404 (proibicao D-F0-03)
# ---------------------------------------------------------------------------

def test_alerts_ack_is_absent(client_dashboard_on):
    _login(client_dashboard_on)
    r = client_dashboard_on.post("/ops/alerts/ack", json={"alert_id": str(uuid.uuid4())})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 10. Endpoints legados /ops/health, /ops/scrapers, /ops/runs continuam OK
# ---------------------------------------------------------------------------

def test_legacy_health_still_reachable(client_dashboard_on):
    # /ops/health nao exige X-Ops-Token e nao depende de dashboard
    r = client_dashboard_on.get("/ops/health")
    # Pode dar 200 (db ok) ou 503 (db down) mas NAO 404.
    assert r.status_code in (200, 503)


def test_legacy_scrapers_api_requires_token(client_dashboard_on):
    # /ops/scrapers sem X-Ops-Token -> 401 missing_token
    r = client_dashboard_on.get("/ops/scrapers")
    assert r.status_code == 401


def test_legacy_scrapers_api_with_valid_token(client_dashboard_on):
    r = client_dashboard_on.get("/ops/scrapers", headers={"X-Ops-Token": "test-api-token"})
    # Pode dar 200 (banco responde) ou 500 (banco indispoñivel em teste).
    # Nao deve dar 404 nem 401.
    assert r.status_code not in (401, 404)


# ---------------------------------------------------------------------------
# 11. Logout
# ---------------------------------------------------------------------------

def test_logout_clears_session(client_dashboard_on):
    _login(client_dashboard_on)
    r = client_dashboard_on.get("/ops/logout", follow_redirects=False)
    assert r.status_code in (302, 303)
    # Depois do logout, /ops redireciona para /ops/login
    r2 = client_dashboard_on.get("/ops", follow_redirects=False)
    assert r2.status_code in (302, 303)
    assert "/ops/login" in r2.headers.get("Location", "")


# ---------------------------------------------------------------------------
# 12. UI-API exige sessao
# ---------------------------------------------------------------------------

def test_ui_api_requires_session(client_dashboard_on):
    r = client_dashboard_on.get("/ops/ui/api/summary")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 13. Rate limit basico (3 tentativas por IP)
# ---------------------------------------------------------------------------

def test_rate_limit_after_3_invalid(client_dashboard_on):
    for _ in range(3):
        client_dashboard_on.post("/ops/login", data={"token": "WRONG"})
    r = client_dashboard_on.post("/ops/login", data={"token": "test-dashboard-token-abc123"})
    # A 4a tentativa eh bloqueada pelo rate limiter (429)
    assert r.status_code == 429
