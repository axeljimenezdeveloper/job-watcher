"""Carga y valida la configuracion del proyecto."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str
    parse_mode: str = "HTML"
    disable_web_page_preview: bool = True


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path


@dataclass(frozen=True)
class ScrapingConfig:
    timeout_seconds: int = 30
    request_delay_seconds: int = 2
    user_agent: str = ""
    estados: list[str] = field(default_factory=lambda: ["nueva-esparta"])


@dataclass(frozen=True)
class Profile:
    name: str
    enabled: bool
    must_match_any: list[str] = field(default_factory=list)
    must_not_match: list[str] = field(default_factory=list)
    locations_any: list[str] = field(default_factory=list)
    local_locations: list[str] = field(default_factory=list)
    remote_keywords: list[str] = field(default_factory=list)
    portals: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class AppConfig:
    timezone: str
    log_level: str


@dataclass(frozen=True)
class Config:
    app: AppConfig
    telegram: TelegramConfig
    database: DatabaseConfig
    scraping: ScrapingConfig
    profiles: list[Profile]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise RuntimeError(f"El archivo {path} no contiene un mapeo YAML valido")
    return data


def _read_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno {name} (revisa tu archivo .env)")
    return value


def load_config(env_file: Path | None = None) -> Config:
    """Carga config.yaml + profiles.yaml + variables de entorno."""
    load_dotenv(env_file or PROJECT_ROOT / ".env")

    raw = _load_yaml(CONFIG_DIR / "config.yaml")
    profiles_raw = _load_yaml(CONFIG_DIR / "profiles.yaml").get("profiles", [])

    profiles = [
        Profile(
            name=p["name"],
            enabled=p.get("enabled", True),
            must_match_any=p.get("must_match_any", []),
            must_not_match=p.get("must_not_match", []),
            locations_any=p.get("locations_any", []),
            local_locations=p.get("local_locations", []),
            remote_keywords=p.get("remote_keywords", []),
            portals=p.get("portals", {}),
        )
        for p in profiles_raw
    ]

    return Config(
        app=AppConfig(**raw["app"]),
        telegram=TelegramConfig(
            bot_token=_read_env("TELEGRAM_BOT_TOKEN"),
            chat_id=_read_env("TELEGRAM_CHAT_ID"),
            parse_mode=raw["telegram"]["parse_mode"],
            disable_web_page_preview=raw["telegram"]["disable_web_page_preview"],
        ),
        database=DatabaseConfig(path=PROJECT_ROOT / raw["database"]["path"]),
        scraping=ScrapingConfig(**raw["scraping"]),
        profiles=profiles,
    )
