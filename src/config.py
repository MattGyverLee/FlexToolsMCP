#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration Management: Persistent dotted-key JSON configuration for FlexToolsMCP.

Provides:
- Dotted-key access (e.g., 'paths.flexlibs2') to nested config values
- In-memory caching to avoid disk reads on every call
- Auto-creation of config directory if missing
- JSON type auto-detection (integers stay integers, not strings)
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional


# Configuration location
CONFIG_DIR = Path.home() / ".flextoolsmcp"
CONFIG_FILE = CONFIG_DIR / "config.json"

# In-memory cache (loaded on first call, cleared on flush)
_config_cache: Optional[Dict[str, Any]] = None
_cache_loaded = False


def _ensure_dir() -> None:
    """Ensure the configuration directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load_config() -> Dict[str, Any]:
    """
    Load the config file from disk.

    Returns an empty dict if the file doesn't exist.

    Returns:
        The parsed JSON config dict
    """
    if not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # If file is corrupted or unreadable, return empty config
        return {}


def _save_config(data: Dict[str, Any]) -> None:
    """
    Write the full config dict to disk.

    Creates the config directory if it doesn't exist.

    Args:
        data: The config dict to save
    """
    _ensure_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get_cache() -> Dict[str, Any]:
    """
    Get the in-memory config cache, loading from disk if not yet cached.

    Returns:
        The cached config dict
    """
    global _config_cache, _cache_loaded

    if not _cache_loaded:
        _config_cache = _load_config()
        _cache_loaded = True

    return _config_cache


def config_get(key: str, default: Any = None) -> Any:
    """
    Get a config value by dotted key.

    Supports nested access via dot notation. If the key path doesn't exist,
    returns the default value.

    Args:
        key: Dotted key path (e.g., 'paths.flexlibs2', 'api.timeout')
        default: Value to return if key is not found (default: None)

    Returns:
        The config value, or default if not found

    Example:
        >>> config_set('paths.flexlibs2', '/home/user/flexlibs2')
        >>> config_get('paths.flexlibs2')
        '/home/user/flexlibs2'
        >>> config_get('paths.nonexistent', 'default_value')
        'default_value'
    """
    cfg = _get_cache()
    parts = key.split(".")
    node = cfg

    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]

    return node


def config_set(key: str, value: Any) -> None:
    """
    Set a config value by dotted key.

    Creates nested dicts as needed. Automatically detects JSON types
    (integers, booleans, etc.) instead of storing everything as strings.

    Args:
        key: Dotted key path (e.g., 'paths.flexlibs2')
        value: The value to set (can be str, int, bool, dict, list, etc.)

    Example:
        >>> config_set('paths.flexlibs2', '/home/user/flexlibs2')
        >>> config_set('api.timeout', 30)  # Stored as int, not "30"
        >>> config_set('flags.enabled', True)  # Stored as bool, not "true"
    """
    cfg = _get_cache()
    parts = key.split(".")

    # Navigate/create nested structure
    node = cfg
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]

    # Set the final value, with JSON type detection
    final_key = parts[-1]
    if isinstance(value, str):
        # Try to parse as JSON for non-string types (int, bool, null, etc.)
        try:
            parsed = json.loads(value)
            node[final_key] = parsed
        except (json.JSONDecodeError, TypeError):
            # If it's not valid JSON, treat as plain string
            node[final_key] = value
    else:
        # Already a Python type (int, bool, dict, list), store as-is
        node[final_key] = value

    # Persist to disk and update cache
    _save_config(cfg)


def config_delete(key: str) -> bool:
    """
    Delete a config key by dotted key.

    Removes the key from the config and saves to disk.

    Args:
        key: Dotted key path to delete

    Returns:
        True if the key existed and was deleted, False otherwise

    Example:
        >>> config_set('paths.flexlibs2', '/home/user/flexlibs2')
        >>> config_delete('paths.flexlibs2')
        True
        >>> config_delete('paths.nonexistent')
        False
    """
    cfg = _get_cache()
    parts = key.split(".")

    # Navigate to parent
    node = cfg
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]

    # Delete if exists
    if isinstance(node, dict) and parts[-1] in node:
        del node[parts[-1]]
        _save_config(cfg)
        return True

    return False


def config_list() -> Dict[str, Any]:
    """
    Get the entire configuration dict.

    Returns a copy of the full nested config structure.

    Returns:
        The complete config dict

    Example:
        >>> config_set('paths.flexlibs2', '/path')
        >>> config_list()
        {'paths': {'flexlibs2': '/path'}}
    """
    return dict(_get_cache())


def config_flush() -> None:
    """
    Clear the in-memory cache and reload from disk on next access.

    Useful for testing or when the config file might have been modified
    externally.
    """
    global _config_cache, _cache_loaded
    _config_cache = None
    _cache_loaded = False


def config_path() -> str:
    """
    Get the absolute path to the config file.

    Returns:
        Path string to ~/.flextoolsmcp/config.json

    Example:
        >>> config_path()
        '/home/user/.flextoolsmcp/config.json'
    """
    return str(CONFIG_FILE)
