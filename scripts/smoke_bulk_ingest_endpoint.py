#!/usr/bin/env python3
"""Smoke do endpoint POST /api/ingest/bulk.

Valida que o endpoint esta saudavel:
  - 401 sem X-Ingest-Token
  - 400 com token e payload invalido
  - 200 com token e dry_run=true + 1 item fake benigno

Nao faz apply, nao loga o token em lugar nenhum.

Uso:
    export BULK_INGEST_TOKEN=...     # em ambiente autorizado
    python scripts/smoke_bulk_ingest_endpoint.py
    python scripts/smoke_bulk_ingest_endpoint.py --base-url https://winegod.onrender.com

Exit code:
    0 se tudo passou
    1 se algum check falhou ou o token nao foi encontrado
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib import request, error


FAKE_ITEM = {
    "nome": "Chateau Smoke Endpoint Guard",
    "produtor": "Chateau Smoke Endpoint Guard",
    "safra": "2020",
    "pais": "fr",
}


def _do_post(url: str, body: dict, token: str | None, timeout: int) -> tuple[int, dict | None]:
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Ingest-Token"] = token
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8")
            status = resp.getcode()
    except error.HTTPError as e:
        payload = e.read().decode("utf-8") if e.fp else ""
        status = e.code
    except Exception as e:
        return -1, {"error": f"{type(e).__name__}: {e}"}
    try:
        body_json = json.loads(payload) if payload else None
    except json.JSONDecodeError:
        body_json = {"raw": payload[:200]}
    return status, body_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke do endpoint bulk_ingest")
    parser.add_argument("--base-url", default="http://localhost:5000",
                        help="URL base do backend (default: http://localhost:5000)")
    parser.add_argument("--token-env", default="BULK_INGEST_TOKEN",
                        help="nome da env com o token (default: BULK_INGEST_TOKEN)")
    parser.add_argument("--token", default=None,
                        help="token inline (prefira --token-env pra nao vazar no shell history)")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    token = args.token or os.environ.get(args.token_env)
    if not token:
        print(f"[smoke] token nao encontrado em --token nem em ${args.token_env}", flush=True)
        return 1
    del args.token  # evita print acidental via repr(args)

    url = args.base_url.rstrip("/") + "/api/ingest/bulk"
    print(f"[smoke] target: {url}", flush=True)

    results = []
    overall_ok = True

    # 1. 401 sem token
    status, body = _do_post(url, {"items": []}, token=None, timeout=args.timeout)
    ok = status == 401
    overall_ok &= ok
    results.append({"check": "no_token_401", "status": status, "ok": ok})

    # 2. 400 payload invalido (items nao e lista)
    status, body = _do_post(url, {"items": "nao_e_lista"}, token=token, timeout=args.timeout)
    ok = status == 400
    overall_ok &= ok
    results.append({"check": "bad_payload_400", "status": status, "ok": ok})

    # 3. 200 dry-run com 1 item valido
    status, body = _do_post(
        url,
        {"items": [FAKE_ITEM], "dry_run": True, "source": "smoke_endpoint"},
        token=token,
        timeout=args.timeout,
    )
    ok = (
        status == 200
        and isinstance(body, dict)
        and body.get("dry_run") is True
        and body.get("received") == 1
        and body.get("valid") == 1
        and (body.get("inserted", 0) == 0)
        and (body.get("updated", 0) == 0)
    )
    overall_ok &= ok
    results.append({
        "check": "dry_run_200",
        "status": status,
        "ok": ok,
        "received": body.get("received") if isinstance(body, dict) else None,
        "valid": body.get("valid") if isinstance(body, dict) else None,
        "would_insert": body.get("would_insert") if isinstance(body, dict) else None,
        "would_update": body.get("would_update") if isinstance(body, dict) else None,
    })

    print(json.dumps({"overall_ok": overall_ok, "results": results}, indent=2, ensure_ascii=False))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
