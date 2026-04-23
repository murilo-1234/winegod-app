"""Observers aceitam os nomes de env ja usados no projeto."""
from __future__ import annotations

from adapters import (
    decanter_persisted_observer,
    vivino_reviews_observer,
    winegod_admin_commerce_observer,
)


def test_winegod_observer_prefers_existing_project_env(monkeypatch):
    monkeypatch.setenv("WINEGOD_DATABASE_URL", "postgresql://primary")
    monkeypatch.setenv("DATABASE_URL_LOCAL_WINEGOD", "postgresql://legacy-local")
    monkeypatch.setenv("WINEGOD_DB_URL", "postgresql://legacy-short")

    assert winegod_admin_commerce_observer._get_source_dsn() == "postgresql://primary"


def test_winegod_observer_keeps_legacy_fallbacks(monkeypatch):
    monkeypatch.delenv("WINEGOD_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL_LOCAL_WINEGOD", "postgresql://legacy-local")
    monkeypatch.setenv("WINEGOD_DB_URL", "postgresql://legacy-short")

    assert winegod_admin_commerce_observer._get_source_dsn() == "postgresql://legacy-local"


def test_vivino_observer_prefers_existing_project_env(monkeypatch):
    monkeypatch.setenv("VIVINO_DATABASE_URL", "postgresql://primary")
    monkeypatch.setenv("DATABASE_URL_LOCAL_VIVINO", "postgresql://legacy-local")
    monkeypatch.setenv("VIVINO_DB_URL", "postgresql://legacy-short")

    assert vivino_reviews_observer._get_source_dsn() == "postgresql://primary"


def test_vivino_observer_keeps_legacy_fallbacks(monkeypatch):
    monkeypatch.delenv("VIVINO_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL_LOCAL_VIVINO", "postgresql://legacy-local")
    monkeypatch.setenv("VIVINO_DB_URL", "postgresql://legacy-short")

    assert vivino_reviews_observer._get_source_dsn() == "postgresql://legacy-local"


def test_decanter_observer_prefers_winegod_source_env(monkeypatch):
    monkeypatch.setenv("WINEGOD_DATABASE_URL", "postgresql://winegod-primary")
    monkeypatch.setenv("DATABASE_URL_LOCAL_DECANTER", "postgresql://legacy-decanter")
    monkeypatch.setenv("DECANTER_DB_URL", "postgresql://legacy-short")

    assert decanter_persisted_observer._get_source_dsn() == "postgresql://winegod-primary"
