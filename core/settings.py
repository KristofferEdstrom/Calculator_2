"""
settings.py

Loads and saves calculator preferences in settings.json.
"""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


SETTINGS_FILE = Path("settings.json")

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "light",
    "angle_mode": "RAD",
    "window_width": 650,
    "window_height": 600,
}


def load_settings() -> dict[str, Any]:
    """
    Load settings from disk.

    Missing or invalid values are replaced with defaults.
    """
    settings = deepcopy(DEFAULT_SETTINGS)

    if not SETTINGS_FILE.exists():
        save_settings(settings)
        return settings

    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as file:
            stored_settings = json.load(file)

        if isinstance(stored_settings, dict):
            settings.update(stored_settings)

    except (json.JSONDecodeError, OSError):
        # Keep defaults if the file is damaged or unreadable.
        save_settings(settings)

    return settings


def save_settings(settings: dict[str, Any]) -> None:
    """Save settings to disk."""
    with SETTINGS_FILE.open("w", encoding="utf-8") as file:
        json.dump(settings, file, indent=4)


def update_setting(
    settings: dict[str, Any],
    name: str,
    value: Any,
) -> None:
    """
    Update one setting and immediately save it.
    """
    settings[name] = value
    save_settings(settings)