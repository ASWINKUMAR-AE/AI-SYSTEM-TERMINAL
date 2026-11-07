"""
Safety Manager for AI System Terminal
Enforces command allowlists, blocked dangerous patterns, risk categorization,
path traversal safeguards, and user interactive approval.
"""

from __future__ import annotations

import enum
import os
import re
from pathlib import Path
from typing import Tuple

from config import load_config


class RiskLevel(enum.Enum):
    READONLY = "READONLY"
    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"
    BLOCKED = "BLOCKED"


class SafetyManager:
    """Manages command validation, path sandboxing, and approval policies."""

    def __init__(self):
        self.config = load_config()

    def reload_config(self):
        self.config = load_config()

    def is_blocked(self, command: str) -> Tuple[bool, str]:
        """Checks if a command contains prohibited destructive patterns."""
        cmd_lower = command.lower().strip()
        blocked_patterns = self.config.get("blocked_patterns", [])

        for pattern in blocked_patterns:
            if pattern.lower() in cmd_lower:
                return True, f"Prohibited pattern detected: '{pattern}'"

        # Check for dangerous disk / system modification keywords
        dangerous_regex = [
            r"\bformat\s+[a-z]:",
            r"\brmdir\s+/s\s+/q\s+[c-z]:\\",
            r"\bdel\s+/[a-z\s]*\s+[c-z]:\\windows",
            r"\bset-executionpolicy\s+unrestricted",
            r"\bdiskpart\b",
            r"\b(drop\s+database|truncate\s+table)\b",
            r"\brm\s+-rf\s+/(?:\s|$)",
            r"\bshutdown\s+/[sr]",
            r"\breg\s+delete\b",
        ]

        for regex in dangerous_regex:
            if re.search(regex, cmd_lower):
                return True, f"Command matched dangerous system pattern: {regex}"

        return False, ""

    def evaluate_command(self, command: str, cwd: str | Path | None = None) -> Tuple[RiskLevel, str]:
        """Evaluates command risk level and safety reasons."""
        blocked, reason = self.is_blocked(command)
        if blocked:
            return RiskLevel.BLOCKED, reason

        cmd_clean = command.strip()
        cmd_lower = cmd_clean.lower()

        # Read-only commands
        readonly_prefixes = [
            "dir", "ls", "pwd", "cd", "echo", "type", "cat",
            "git status", "git log", "git diff", "git branch",
            "python --version", "py --version", "node -v", "npm -v", "java -version", "javac -version",
            "mvn -v", "gradle -v", "pytest --version", "Get-ChildItem", "Get-Content", "Get-Command",
            "where", "where.exe", "which", "whoami", "hostname", "netstat", "ipconfig"
        ]

        for ro in readonly_prefixes:
            if cmd_lower.startswith(ro.lower()):
                return RiskLevel.READONLY, "Read-only inspection command"

        # Low risk build & test commands
        low_risk_prefixes = [
            "pip install", "uv pip install", "uv sync", "npm install", "npm i", "pnpm install",
            "yarn install", "mvn compile", "mvn test-compile", "gradle compileJava",
            "pytest", "python -m pytest", "npm test", "yarn test", "pnpm test", "mvn test", "gradle test",
            "tsc --noEmit", "mypy", "ruff check", "flake8", "eslint",
            "git stash", "git checkout -b", "git add"
        ]

        for lr in low_risk_prefixes:
            if cmd_lower.startswith(lr.lower()):
                return RiskLevel.LOW_RISK, "Standard build, dependency, or test command"

        # High risk keywords
        high_risk_keywords = [
            "rmdir", "remove-item", "del ", "rm ", "erase", "kill", "stop-process",
            "taskkill", "chmod", "chown", "curl", "irm", "invoke-webrequest",
            "wget", "git push", "git reset --hard", "drop", "truncate"
        ]

        for hr in high_risk_keywords:
            if hr in cmd_lower:
                return RiskLevel.HIGH_RISK, f"Potentially destructive or system-modifying keyword: '{hr}'"

        # Default to medium risk for commands that launch servers or run apps
        return RiskLevel.MEDIUM_RISK, "Application execution or file modification command"

    def is_safe_for_auto(self, command: str) -> bool:
        """Determines if a command can run automatically without manual confirmation in Auto mode."""
        risk, _ = self.evaluate_command(command)
        return risk in (RiskLevel.READONLY, RiskLevel.LOW_RISK)

    def validate_file_path(self, target_path: str | Path, workspace: str | Path) -> Tuple[bool, str]:
        """Ensures file changes are strictly confined to the project workspace and not system directories."""
        try:
            workspace_resolved = Path(workspace).resolve()
            target_resolved = Path(target_path).resolve()

            # Disallow modifying system root or Windows directories
            sys_root = Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve()
            if sys_root in target_resolved.parents or target_resolved == sys_root:
                return False, f"Cannot modify files inside Windows System directory: {target_resolved}"

            # Check if target is inside workspace
            if workspace_resolved not in target_resolved.parents and target_resolved != workspace_resolved:
                return False, f"Target path {target_resolved} is outside project workspace {workspace_resolved}"

            return True, "Path is safe within workspace"
        except Exception as e:
            return False, f"Path validation error: {e}"
