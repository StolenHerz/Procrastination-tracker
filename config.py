"""Общие константы приложения и пути к файлам."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "Procrastination Tracker"
APP_VERSION = "0.1.0"

# Оформление CustomTkinter.
APPEARANCE_MODE = "dark"
COLOR_THEME = "blue"
FONT_FAMILY = "Segoe UI"
UI_PADDING = 16
UI_CORNER_RADIUS = 12

# Размеры окон.
WINDOW_SIZE = "760x600"
WINDOW_MIN_SIZE = (640, 520)
POPUP_SIZE = "440x340"

# Данные и статистика.
STATS_DAYS = 7
RECENT_LOGS_LIMIT = 20
EVENT_POLL_MS = 100


def get_base_dir() -> Path:
    """Папка приложения: каталог скрипта или папка exe после сборки."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
ASSETS_DIR = BASE_DIR / "assets"
DATA_DB_PATH = BASE_DIR / "data.db"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"
ICON_PATH = ASSETS_DIR / "icon.png"
ICO_PATH = ASSETS_DIR / "icon.ico"


def ensure_directories() -> None:
    """Создать рабочие папки, не прерывая запуск из-за ошибки доступа."""
    for directory in (LOG_DIR, ASSETS_DIR):
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Не удалось создать папку %s: %s", directory, exc)
