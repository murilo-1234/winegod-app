"""Estado persistente do scheduler para o plug_reviews_scores.

Um JSON simples por source em `reports/data_ops_plugs_state/`.

Schema de cada arquivo:
    {
      "source": "vivino_wines_to_ratings",
      "mode": "backfill_windowed",
      "last_id": 1234567,
      "updated_at": "2026-04-23T19:30:00Z",
      "runs": 4
    }

Duas modalidades de execucao:
  - `incremental_recent` NAO persiste cursor (sempre repete o topo recente).
  - `backfill_windowed` persiste `last_id` para a varredura progredir de fato.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
STATE_ROOT = REPO_ROOT / "reports" / "data_ops_plugs_state"


def _state_path(source: str) -> Path:
    return STATE_ROOT / f"{source}.json"


def load_state(source: str) -> dict[str, Any]:
    path = _state_path(source)
    if not path.exists():
        return {"source": source, "last_id": 0, "runs": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"source": source, "last_id": 0, "runs": 0}
    data.setdefault("source", source)
    data.setdefault("last_id", 0)
    data.setdefault("runs", 0)
    return data


def save_state(source: str, *, last_id: int, mode: str, extra: dict[str, Any] | None = None) -> Path:
    path = _state_path(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "source": source,
        "mode": mode,
        "last_id": int(last_id),
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if extra:
        payload.update(extra)
    # Preserva contador de runs se existir.
    if path.exists():
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
            payload["runs"] = int(prior.get("runs", 0)) + 1
        except json.JSONDecodeError:
            payload["runs"] = 1
    else:
        payload["runs"] = 1
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def reset_state(source: str) -> None:
    path = _state_path(source)
    if path.exists():
        path.unlink()


__all__ = ["load_state", "save_state", "reset_state", "STATE_ROOT"]
