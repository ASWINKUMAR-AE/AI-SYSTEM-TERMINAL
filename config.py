"""
Configuration Manager for AI System Terminal
Handles persistent user settings, environment variables, safety rules, and directories.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_CONFIG: Dict[str, Any] = {
    "api_url": "https://vireonix.ai/v1/chat/completions",
    "model": "auto",
    "api_key": "",
    "timeout": 60,
    "max_retries": 3,
    "retry_delay": 1.5,
    "default_mode": "auto",
    "max_repair_attempts": 3,
    "history_limit": 25,
    "auto_verify_port": True,
    "auto_verify_process": True,
    "interactive_approval_in_auto": True,
    "backup_enabled": True,
    "safe_command_prefixes": [
        "python",
        "py",
        "node",
        "npm",
        "pnpm",
        "yarn",
        "bun",
        "mvn",
        "gradle",
        "javac",
        "java",
        "git",
        "pytest",
        "pip",
        "uv",
        "dir",
        "ls",
        "echo",
        "type",
        "cat",
        "Get-ChildItem",
        "Get-Content",
        "Get-Command",
        "cargo",
        "dotnet",
        "go",
        "php",
        "composer"
    ],
    "blocked_patterns": [
        "rmdir /s /q c:",
        "del /s /q c:\\",
        "format ",
        "rm -rf /",
        "Remove-Item -Recurse -Force C:\\",
        "diskpart",
        "reg delete",
        "bcdedit",
        "Set-ExecutionPolicy Unrestricted",
        "shutdown",
        "takeown",
        "icacls /grant"
    ]
}


def get_home_dir() -> Path:
    """Returns the user configuration home directory (~/.ai-terminal)."""
    home = Path.home() / ".ai-terminal"
    home.mkdir(parents=True, exist_ok=True)
    return home


def get_config_path() -> Path:
    """Returns the path to config.json."""
    return get_home_dir() / "config.json"


def get_history_path() -> Path:
    """Returns the path to history.json."""
    return get_home_dir() / "history.json"


def get_execution_log_path() -> Path:
    """Returns the path to execution_log.json."""
    return get_home_dir() / "execution_log.json"


def ensure_dirs() -> None:
    """Ensure all required global directories exist."""
    get_home_dir()
    backups_dir = get_home_dir() / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    """Loads configuration with fallback to defaults and environment variables."""
    cfg = dict(DEFAULT_CONFIG)
    config_file = get_config_path()

    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                if isinstance(user_cfg, dict):
                    cfg.update(user_cfg)
        except Exception:
            pass

    # Environment variables override config file
    if os.environ.get("VIREONIX_API_URL"):
        cfg["api_url"] = os.environ["VIREONIX_API_URL"]
    if os.environ.get("VIREONIX_MODEL"):
        cfg["model"] = os.environ["VIREONIX_MODEL"]
    if os.environ.get("VIREONIX_API_KEY"):
        cfg["api_key"] = os.environ["VIREONIX_API_KEY"]
    if os.environ.get("VIREONIX_TIMEOUT"):
        try:
            cfg["timeout"] = int(os.environ["VIREONIX_TIMEOUT"])
        except ValueError:
            pass

    return cfg


def save_config(config_data: Dict[str, Any]) -> None:
    """Saves the configuration dictionary to config.json."""
    ensure_dirs()
    config_file = get_config_path()
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)


def get_setting(key: str, default: Any = None) -> Any:
    """Retrieves a single setting value."""
    cfg = load_config()
    return cfg.get(key, default)


def set_setting(key: str, value: Any) -> None:
    """Updates and saves a single setting value."""
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)


def get_project_backup_dir(project_root: str | Path) -> Path:
    """Returns the backup directory for a project (.ai-terminal/backups)."""
    p = Path(project_root) / ".ai-terminal" / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p
