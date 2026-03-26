"""
FILE: settings.py
ROLE: Parameter Storage & Validation

DESCRIPTION:
    Stores LLM sampling parameters (temperature, top_p, etc.).
    Validates parameter ranges and persists to settings.json.

FUNCTIONS:
    get_params()              → Get all parameters as dict
    get_all()                 → Get all settings
    update(key, value)        → Update and validate a parameter
    reset()                   → Reset to defaults

PERSISTENT FILE:
    settings.json (auto-created)
"""
from __future__ import annotations

import json
import os
import shutil
from typing import Any, Dict, Tuple, Union


CONFIG_FILE = "settings.json"

INTEGER_PARAMS: frozenset = frozenset({"top_k", "max_agent_iterations"})
FLOAT_PARAMS: frozenset = frozenset({
    "temperature", "top_p", "min_p",
    "presence_penalty", "frequency_penalty", "repeat_penalty"
})
STRING_PARAMS: frozenset = frozenset({
    "system_prompt_path",
    "server_url",
    "model_name"
})

PARAM_RANGES: Dict[str, Tuple[float, float]] = {
    "temperature": (0.0, 2.0),
    "top_p": (0.0, 1.0),
    "top_k": (0.0, 200.0),
    "min_p": (0.0, 1.0),
    "presence_penalty": (-2.0, 2.0),
    "frequency_penalty": (-2.0, 2.0),
    "repeat_penalty": (1.0, 2.0),
    "max_agent_iterations": (1.0, 200.0),
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "min_p": 0.05,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "repeat_penalty": 1.1,
    "max_agent_iterations": 100,
    "system_prompt_path": "prompts/main_agent.md",
    "server_url": "http://localhost:8080",
    "model_name": "model.gguf",
    "bash_timeout": 60,
    "max_file_size": 10485760,  # 10 MB
    "stream_timeout": 120,
}


# Global settings storage
_settings: Dict[str, Any] = DEFAULT_SETTINGS.copy()
_loaded: bool = False


def _ensure_loaded() -> None:
    """Ensure settings are loaded from file."""
    global _settings, _loaded
    if _loaded:
        return

    _loaded = True

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for key, value in saved.items():
                if key in DEFAULT_SETTINGS:
                    if key in INTEGER_PARAMS:
                        _settings[key] = int(value)
                    elif key in STRING_PARAMS:
                        _settings[key] = str(value)
                    else:
                        _settings[key] = float(value)
        except (json.JSONDecodeError, IOError, ValueError) as e:
            print(f"[settings] Could not load config, using defaults: {e}")
    else:
        _save()


def _save() -> None:
    """Save settings to config file."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_settings, f, indent=4)
    except IOError as e:
        if os.path.exists(CONFIG_FILE):
            shutil.copy2(CONFIG_FILE, CONFIG_FILE + ".bak")
        print(f"[settings] Could not save config: {e}")


def get_params() -> Dict[str, Union[int, float]]:
    """
    Get sampling parameters only (for LLM API).

    Returns:
        Dict of numeric parameters
    """
    _ensure_loaded()
    numeric_keys = INTEGER_PARAMS | FLOAT_PARAMS
    return {k: v for k, v in _settings.items() if k in numeric_keys}


def get_all() -> Dict[str, Any]:
    """
    Get all settings.

    Returns:
        Copy of all settings
    """
    _ensure_loaded()
    return _settings.copy()


def get(key: str, default: Any = None) -> Any:
    """
    Get a single setting.

    Args:
        key: Setting name
        default: Default value if not found

    Returns:
        Setting value or default
    """
    _ensure_loaded()
    return _settings.get(key, default)


def update(key: str, value: str) -> Tuple[bool, str]:
    """
    Update a parameter with validation.

    Args:
        key: Parameter name
        value: New value (as string, will be parsed)

    Returns:
        (success, message) tuple
    """
    _ensure_loaded()

    if key not in DEFAULT_SETTINGS:
        return False, f"Unknown parameter: {key}"

    if key in STRING_PARAMS:
        _settings[key] = value
        _save()
        return True, f"Updated {key} to '{value}'"

    try:
        if key in INTEGER_PARAMS:
            try:
                val = int(value)
            except ValueError:
                return False, f"{key} must be an integer (got '{value}')"
        else:
            val = float(value)

        min_val, max_val = PARAM_RANGES.get(key, (float('-inf'), float('inf')))
        if not (min_val <= val <= max_val):
            return False, f"{key} must be between {min_val} and {max_val} (got {val})"

        _settings[key] = val
        _save()
        return True, f"Updated {key} to {val}"

    except ValueError:
        return False, f"Invalid value for {key}: '{value}' is not a valid number"


def reset() -> None:
    """Reset all settings to defaults."""
    global _settings
    _settings = DEFAULT_SETTINGS.copy()
    _save()
