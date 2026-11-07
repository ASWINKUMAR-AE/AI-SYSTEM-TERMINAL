"""
Command and Intent Router for AI System Terminal
Parses natural-language user requests, classifies intents, manages modes
(Chat, Assist, Auto), and dispatches to the corresponding system workflows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ai_client import VireonixClient
from auto_repair import AutoRepairEngine
from environment_scanner import EnvironmentScanner
from java_manager import JavaManager
from project_detector import ProjectDetector, ProjectInfo
from safety_manager import RiskLevel, SafetyManager


class Intent:
    CHAT = "CHAT"
    REPAIR_AND_RUN = "REPAIR_AND_RUN"
    ENVIRONMENT_CHECK = "ENVIRONMENT_CHECK"
    START_SERVER = "START_SERVER"
    JAVA_JAR_INSPECT = "JAVA_JAR_INSPECT"
    FIND_ERRORS = "FIND_ERRORS"
    ROLLBACK = "ROLLBACK"


class CommandRouter:
    """Routes user queries to appropriate execution pipelines."""

    def __init__(
        self,
        workspace: Optional[str | Path] = None,
        ai_client: Optional[VireonixClient] = None,
        safety_manager: Optional[SafetyManager] = None
    ):
        self.workspace = Path(workspace).resolve() if workspace else Path.cwd().resolve()
        self.ai = ai_client or VireonixClient()
        self.safety = safety_manager or SafetyManager()
        self.scanner = EnvironmentScanner()
        self.detector = ProjectDetector(self.workspace)
        self.repair_engine = AutoRepairEngine(self.workspace, self.ai, self.safety)
        self.java_mgr = JavaManager(self.workspace)

    def classify_intent(self, prompt: str) -> str:
        """Classifies the natural language prompt into an operational intent."""
        lower = prompt.lower().strip()

        # Rollback intent
        if re.search(r"\b(rollback|revert|undo fix|restore backup)\b", lower):
            return Intent.ROLLBACK

        # Java / JAR inspection intent
        if "jar" in lower or "java application" in lower or "jar file" in lower:
            return Intent.JAVA_JAR_INSPECT

        # Repair and run intent
        if (
            re.search(r"\b(fix|repair|debug)\b", lower)
            and re.search(r"\b(run|start|launch|execute)\b", lower)
        ) or "fix my project errors" in lower or "fix this project and run it" in lower:
            return Intent.REPAIR_AND_RUN

        # Environment check / doctor intent
        if re.search(r"\b(check my python|check my environment|check installation|system check|doctor|inspect system)\b", lower):
            return Intent.ENVIRONMENT_CHECK

        # Start dev server intent
        if re.search(r"\b(start my development server|start dev server|run dev server|launch app|start the server)\b", lower):
            return Intent.START_SERVER

        # Find errors intent
        if re.search(r"\b(find errors|diagnose errors|why is (?:it|my .*?) failing|check why .*? failed)\b", lower):
            return Intent.FIND_ERRORS

        # Default to CHAT (covers code generation e.g. "Give python code for KNN", explanations, etc.)
        return Intent.CHAT

    def handle_request(
        self,
        prompt: str,
        mode: str = "auto",
        confirm_callback: Optional[Callable[[str, str, RiskLevel], bool]] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        """Dispatches request based on mode and classified intent."""
        if progress_callback:
            self.repair_engine.progress_callback = progress_callback

        # In strict 'chat' mode, always answer conversationally without execution
        if mode == "chat":
            response = self.ai.chat(prompt)
            return {
                "intent": Intent.CHAT,
                "mode": mode,
                "response": response,
                "success": True
            }

        intent = self.classify_intent(prompt)

        # 1. Environment Check
        if intent == Intent.ENVIRONMENT_CHECK:
            env_data = self.scanner.scan_all(self.workspace)
            # Ask AI for concise overview if appropriate
            ai_summary = self.ai.chat(
                f"The user asked: '{prompt}'. Here is their ground truth environment data:\n{env_data}\n"
                "Provide a clean, concise assessment of their installed tools and any potential issues."
            )
            return {
                "intent": intent,
                "env_data": env_data,
                "response": ai_summary,
                "success": True
            }

        # 2. Repair and Run
        if intent == Intent.REPAIR_AND_RUN:
            project_info = self.detector.detect()
            verif_result = self.repair_engine.run_repair_and_verify_cycle(
                project_info=project_info,
                mode=mode,
                confirm_callback=confirm_callback
            )
            return {
                "intent": intent,
                "project_info": project_info,
                "verification": verif_result,
                "success": verif_result.success
            }

        # 3. Java / JAR Manager
        if intent == Intent.JAVA_JAR_INSPECT:
            java_info = self.java_mgr.get_installed_java_info()
            jar_files = list(self.workspace.glob("*.jar"))
            jar_meta = None
            compat = None

            if progress_callback:
                if java_info.get("installed"):
                    progress_callback("CHECK", f"Java runtime detected: {java_info.get('version_string')}")
                else:
                    progress_callback("CHECK", "Java runtime not detected on PATH.")

            if jar_files:
                target_jar = jar_files[0]
                jar_meta = self.java_mgr.inspect_jar(target_jar)
                compat_ok, compat_msg = self.java_mgr.check_compatibility(jar_meta)
                compat = {"compatible": compat_ok, "message": compat_msg}
                if progress_callback:
                    progress_callback("CHECK", f"JAR Main-Class: {jar_meta.main_class or 'None'}")
                    progress_callback("CHECK", f"JAR Bytecode Version: {jar_meta.required_java_version or 'Unknown'}")
                    progress_callback("CHECK", f"Compatibility: {compat_msg}")

            # If user wanted to fix and run the jar
            if "run" in prompt.lower() or "fix" in prompt.lower():
                project_info = self.detector.detect()
                verif_result = self.repair_engine.run_repair_and_verify_cycle(
                    project_info=project_info,
                    mode=mode,
                    confirm_callback=confirm_callback
                )
                return {
                    "intent": intent,
                    "java_info": java_info,
                    "jar_meta": jar_meta,
                    "compatibility": compat,
                    "verification": verif_result,
                    "success": verif_result.success
                }

            ai_resp = self.ai.chat(
                f"User asked: '{prompt}'. Java runtime info: {java_info}. JAR metadata: {jar_meta}. Compatibility: {compat}."
            )
            return {
                "intent": intent,
                "java_info": java_info,
                "jar_meta": jar_meta,
                "compatibility": compat,
                "response": ai_resp,
                "success": True
            }

        # 4. Rollback
        if intent == Intent.ROLLBACK:
            ok, msg = self.repair_engine.rollback_latest()
            return {
                "intent": intent,
                "message": msg,
                "success": ok
            }

        # 5. Default Chat / Question (e.g. "Give python code for KNN", "Explain this error")
        response = self.ai.chat(prompt)
        return {
            "intent": Intent.CHAT,
            "response": response,
            "success": True
        }
