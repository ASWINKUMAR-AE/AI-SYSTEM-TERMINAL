"""
Error Analyzer for AI System Terminal
Extracts stack traces, identifies failure categories, correlates with project files,
and queries ZETHUB AI for root cause analysis and targeted fixes.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai_client import VireonixClient
from project_detector import ProjectInfo


@dataclass
class ErrorDiagnosis:
    category: str
    root_cause: str
    explanation: str
    confidence: float
    affected_files: List[str] = field(default_factory=list)
    missing_packages: List[str] = field(default_factory=list)
    conflicting_port: Optional[int] = None
    suggested_commands: List[str] = field(default_factory=list)
    smallest_fix_description: str = ""
    raw_ai_response: Dict[str, Any] = field(default_factory=dict)


class ErrorAnalyzer:
    """Analyzes runtime and compilation errors using local heuristics and ZETHUB AI."""

    def __init__(self, ai_client: Optional[VireonixClient] = None):
        self.ai = ai_client or VireonixClient()

    def analyze(
        self,
        error_text: str,
        project_info: ProjectInfo,
        system_context: Optional[Dict[str, Any]] = None
    ) -> ErrorDiagnosis:
        """Categorizes errors and obtains an AI-powered diagnosis."""
        category, local_details = self._heuristic_analysis(error_text, project_info)

        # Assemble project context for AI
        proj_ctx = {
            "root_path": project_info.root_path,
            "language": project_info.primary_language,
            "framework": project_info.framework,
            "project_type": project_info.project_type,
            "entry_point": project_info.entry_point,
            "config_files": project_info.config_files,
            "heuristic_category": category,
            "heuristic_details": local_details
        }

        # Query ZETHUB AI
        try:
            ai_diag = self.ai.diagnose_error(
                error_log=error_text,
                project_context=proj_ctx,
                system_context=system_context or {}
            )
        except Exception as e:
            ai_diag = {
                "root_cause": local_details.get("root_cause") or "Application failed with error",
                "explanation": f"Diagnostic fallback (AI query failed: {e})",
                "error_type": category,
                "confidence": 0.6,
                "smallest_fix_description": local_details.get("recommended_fix") or "Fix identified issue",
                "required_actions": [],
                "validation_commands": []
            }

        missing_pkgs = list(local_details.get("missing_packages", []))
        for act in ai_diag.get("required_actions", []):
            if act.get("action_type") == "install_dependency" and act.get("target"):
                if act["target"] not in missing_pkgs:
                    missing_pkgs.append(act["target"])

        affected_files = list(local_details.get("affected_files", []))
        for act in ai_diag.get("required_actions", []):
            if act.get("action_type") == "edit_file" and act.get("target"):
                if act["target"] not in affected_files:
                    affected_files.append(act["target"])

        suggested_cmds = list(local_details.get("suggested_commands", []))
        if ai_diag.get("validation_commands"):
            suggested_cmds.extend(ai_diag["validation_commands"])

        port_conflict = local_details.get("conflicting_port")

        return ErrorDiagnosis(
            category=ai_diag.get("error_type") or category,
            root_cause=ai_diag.get("root_cause") or local_details.get("root_cause", "Unknown root cause"),
            explanation=ai_diag.get("explanation") or "Error identified in execution logs.",
            confidence=float(ai_diag.get("confidence", 0.8)),
            affected_files=affected_files,
            missing_packages=missing_pkgs,
            conflicting_port=port_conflict,
            suggested_commands=suggested_cmds,
            smallest_fix_description=ai_diag.get("smallest_fix_description") or local_details.get("recommended_fix", ""),
            raw_ai_response=ai_diag
        )

    def _heuristic_analysis(self, text: str, project_info: ProjectInfo) -> Tuple[str, Dict[str, Any]]:
        """Applies local regex-based heuristics to extract specific error data."""
        details: Dict[str, Any] = {
            "missing_packages": [],
            "affected_files": [],
            "suggested_commands": []
        }

        # 1. Missing Python Module
        m = re.search(r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]", text)
        if m:
            pkg = m.group(1).split(".")[0]
            details["missing_packages"].append(pkg)
            details["root_cause"] = f"Missing Python package: {pkg}"
            details["recommended_fix"] = f"Install missing package: pip install {pkg}"
            details["suggested_commands"].append(f"pip install {pkg}")
            return "MissingDependency", details

        # 2. Missing Node Module
        m = re.search(r"Cannot find module ['\"]([^'\"]+)['\"]", text)
        if m:
            pkg = m.group(1).split("/")[0]
            if not pkg.startswith("."):
                details["missing_packages"].append(pkg)
                details["root_cause"] = f"Missing Node module: {pkg}"
                details["recommended_fix"] = f"Install missing package: npm install {pkg}"
                details["suggested_commands"].append(f"npm install {pkg}")
                return "MissingDependency", details

        # 3. Port Conflict / Address in Use
        if "EADDRINUSE" in text or "BindException: Address already in use" in text or "already in use" in text.lower():
            port_match = re.search(r":(\d{2,5})\b", text) or re.search(r"port\s+(\d{2,5})", text, re.IGNORECASE)
            port = int(port_match.group(1)) if port_match else 8080
            details["conflicting_port"] = port
            details["root_cause"] = f"Network port {port} is already in use by another process."
            details["recommended_fix"] = f"Terminate conflicting process on port {port} or switch application port."
            return "PortConflict", details

        # 4. Python Syntax / Indentation Error
        m = re.search(r'File "([^"]+)", line (\d+)', text)
        if m:
            file_path = m.group(1)
            line_no = m.group(2)
            details["affected_files"].append(file_path)
            if "SyntaxError" in text:
                details["root_cause"] = f"Syntax error in {file_path} at line {line_no}"
                details["recommended_fix"] = f"Correct invalid syntax in {file_path}"
                return "SyntaxError", details
            if "IndentationError" in text:
                details["root_cause"] = f"Indentation error in {file_path} at line {line_no}"
                details["recommended_fix"] = f"Fix indentation in {file_path}"
                return "SyntaxError", details

        if "SyntaxError" in text or "IndentationError" in text:
            if project_info.entry_point:
                details["affected_files"].append(project_info.entry_point)
            details["root_cause"] = "Syntax error in project source code"
            details["recommended_fix"] = "Fix invalid syntax"
            return "SyntaxError", details

        # 5. Java Version Mismatch
        if "UnsupportedClassVersionError" in text:
            details["root_cause"] = "Java runtime version is older than bytecode version required by JAR."
            details["recommended_fix"] = "Upgrade Java runtime or recompile with target compatibility."
            return "JavaVersionMismatch", details

        # 6. Database Connection Failure
        if "Can't connect to MySQL" in text or "Connection refused" in text and "3306" in text:
            details["root_cause"] = "Cannot connect to MySQL database service on localhost:3306."
            details["recommended_fix"] = "Ensure MySQL service is started (e.g. net start MySQL) and credentials are valid."
            return "DatabaseConnectionError", details

        return "GeneralRuntimeError", details
