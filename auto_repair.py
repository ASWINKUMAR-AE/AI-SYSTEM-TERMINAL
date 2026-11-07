"""
Autonomous Repair Engine for AI System Terminal
Applies safe, targeted fixes, creates rollback backups, installs missing dependencies,
patches source/configuration files, and verifies application stability.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ai_client import VireonixClient
from config import get_project_backup_dir, load_config
from error_analyzer import ErrorAnalyzer, ErrorDiagnosis
from process_manager import ProcessManager
from project_detector import ProjectInfo
from safety_manager import RiskLevel, SafetyManager
from terminal_executor import TerminalExecutor
from verification_engine import VerificationEngine, VerificationResult


@dataclass
class RepairStep:
    action_type: str  # "install_dependency" | "edit_file" | "free_port" | "run_command"
    description: str
    target: str
    risk_level: RiskLevel
    applied: bool = False
    success: bool = False
    details: str = ""


class AutoRepairEngine:
    """Orchestrates the 5-step repair and verification loop."""

    def __init__(
        self,
        workspace: Optional[str | Path] = None,
        ai_client: Optional[VireonixClient] = None,
        safety_manager: Optional[SafetyManager] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.workspace = Path(workspace).resolve() if workspace else Path.cwd().resolve()
        self.ai = ai_client or VireonixClient()
        self.safety = safety_manager or SafetyManager()
        self.executor = TerminalExecutor()
        self.process_manager = ProcessManager()
        self.verifier = VerificationEngine()
        self.analyzer = ErrorAnalyzer(self.ai)
        self.config = load_config()
        self.progress_callback = progress_callback or (lambda step, msg: None)

    def log_step(self, step_name: str, message: str) -> None:
        """Emits progress events to callback."""
        self.progress_callback(step_name, message)

    def create_backup_checkpoint(self, files_to_backup: List[str | Path]) -> Path:
        """Backs up specified files to .ai-terminal/backups/<timestamp>."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = get_project_backup_dir(self.workspace) / ts
        backup_dir.mkdir(parents=True, exist_ok=True)

        manifest = {"timestamp": ts, "files": []}

        for f in files_to_backup:
            file_path = Path(f)
            if not file_path.is_absolute():
                file_path = self.workspace / file_path

            if file_path.exists() and file_path.is_file():
                rel_path = file_path.relative_to(self.workspace)
                dest = backup_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest)
                manifest["files"].append(str(rel_path))

        with open(backup_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return backup_dir

    def rollback_latest(self) -> Tuple[bool, str]:
        """Restores files from the most recent backup checkpoint."""
        backup_root = get_project_backup_dir(self.workspace)
        if not backup_root.exists():
            return False, "No backups found for this project."

        snapshots = sorted([d for d in backup_root.iterdir() if d.is_dir()], key=lambda d: d.name, reverse=True)
        if not snapshots:
            return False, "No snapshot checkpoints available to rollback."

        latest = snapshots[0]
        manifest_file = latest / "manifest.json"
        if not manifest_file.exists():
            return False, f"Corrupted backup snapshot: {latest.name}"

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            restored = []
            for rel in manifest.get("files", []):
                src = latest / rel
                dest = self.workspace / rel
                if src.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    restored.append(rel)

            return True, f"Successfully restored {len(restored)} files from checkpoint {latest.name}: {', '.join(restored)}"
        except Exception as e:
            return False, f"Rollback failed: {e}"

    def apply_repair_plan(
        self,
        diagnosis: ErrorDiagnosis,
        project_info: ProjectInfo,
        mode: str = "auto",
        confirm_callback: Optional[Callable[[str, str, RiskLevel], bool]] = None
    ) -> List[RepairStep]:
        """Applies individual repair steps from diagnosis."""
        steps: List[RepairStep] = []

        # 1. Handle Port Conflicts
        if diagnosis.conflicting_port:
            port = diagnosis.conflicting_port
            step = RepairStep(
                action_type="free_port",
                description=f"Terminate process occupying port {port}",
                target=str(port),
                risk_level=RiskLevel.HIGH_RISK
            )
            should_run = (mode == "auto")
            if confirm_callback and not should_run:
                should_run = confirm_callback("Free Port", f"Terminate conflicting process on port {port}?", RiskLevel.HIGH_RISK)

            if should_run:
                success = self.process_manager.kill_process_on_port(port)
                step.applied = True
                step.success = success
                step.details = f"Port {port} freed successfully" if success else f"Could not free port {port}"
            steps.append(step)

        # 2. Handle Missing Dependencies
        for pkg in diagnosis.missing_packages:
            if project_info.primary_language == "Python":
                cmd = f'"{sys.executable}" -m pip install {pkg}'
            elif project_info.primary_language in ("JavaScript", "TypeScript", "Node.js"):
                cmd = f"npm install {pkg}"
            else:
                cmd = f"install {pkg}"

            step = RepairStep(
                action_type="install_dependency",
                description=f"Install missing package '{pkg}'",
                target=pkg,
                risk_level=RiskLevel.LOW_RISK
            )

            should_run = (mode == "auto")
            if confirm_callback and not should_run:
                should_run = confirm_callback("Install Dependency", f"Run: {cmd}?", RiskLevel.LOW_RISK)

            if should_run:
                self.log_step("FIX", f"Installing missing dependency: {pkg}...")
                res = self.executor.run(cmd, cwd=self.workspace, timeout=120)
                step.applied = True
                step.success = res.success
                step.details = res.combined_output()[:200]
            steps.append(step)

        # 3. Handle File Edits
        category_lower = (diagnosis.category or "").lower()
        is_file_repair = any(k in category_lower for k in ("syntax", "config", "runtime", "edit", "general", "fix"))

        files_to_edit = list(diagnosis.affected_files)
        if not files_to_edit and project_info.entry_point and is_file_repair:
            files_to_edit.append(project_info.entry_point)

        if files_to_edit and is_file_repair:
            for rel_file in files_to_edit:
                target_file = Path(rel_file)
                if not target_file.is_absolute():
                    target_file = (self.workspace / target_file).resolve()

                if not target_file.exists():
                    # Check if relative to workspace
                    cand = self.workspace / Path(rel_file).name
                    if cand.exists():
                        target_file = cand
                    else:
                        continue

                # Never attempt to patch compiled binary files
                if target_file.suffix.lower() in (".jar", ".class", ".exe", ".dll", ".so", ".zip"):
                    continue

                safe, reason = self.safety.validate_file_path(target_file, self.workspace)
                if not safe:
                    continue

                step = RepairStep(
                    action_type="edit_file",
                    description=f"Patch file: {target_file.name}",
                    target=str(target_file),
                    risk_level=RiskLevel.MEDIUM_RISK
                )

                should_run = (mode == "auto")
                if confirm_callback and not should_run:
                    should_run = confirm_callback("Patch File", f"Apply AI fix to {target_file.name}?", RiskLevel.MEDIUM_RISK)

                if should_run:
                    try:
                        # 1. Create backup
                        self.create_backup_checkpoint([target_file])
                        # 2. Read existing content
                        original_text = target_file.read_text(encoding="utf-8", errors="replace")
                        # 3. Ask ZETHUB AI for targeted file fix
                        self.log_step("AI", f"Generating code patch for {target_file.name}...")
                        corrected_text = self.ai.generate_file_fix(
                            file_path=str(target_file.relative_to(self.workspace)),
                            current_content=original_text,
                            error_context=diagnosis.root_cause,
                            fix_description=diagnosis.smallest_fix_description
                        )

                        if corrected_text and len(corrected_text.strip()) > 10:
                            target_file.write_text(corrected_text, encoding="utf-8")
                            step.applied = True
                            step.success = True
                            step.details = f"File {target_file.name} patched successfully."
                    except Exception as e:
                        step.applied = True
                        step.success = False
                        step.details = f"File patch error: {e}"

                steps.append(step)

        return steps

    def run_repair_and_verify_cycle(
        self,
        project_info: ProjectInfo,
        mode: str = "auto",
        confirm_callback: Optional[Callable[[str, str, RiskLevel], bool]] = None,
        max_attempts: Optional[int] = None
    ) -> VerificationResult:
        """Executes the full STEP 1 to STEP 5 autonomous repair and verification cycle."""
        limit = max_attempts or self.config.get("max_repair_attempts", 3)
        self.log_step("SCAN", f"Detecting project: {project_info.project_type}...")

        # Expected port deduction
        expected_port: Optional[int] = None
        if project_info.framework in ("Flask", "Streamlit"):
            expected_port = 5000 if project_info.framework == "Flask" else 8501
        elif project_info.framework in ("FastAPI", "Uvicorn"):
            expected_port = 8000
        elif project_info.framework in ("React", "Vue", "Vite", "Next.js", "Express"):
            expected_port = 3000
        elif project_info.framework in ("Spring Boot", "Maven Java"):
            expected_port = 8080

        for attempt in range(1, limit + 1):
            self.log_step("CHECK", f"Evaluation cycle {attempt} of {limit}...")

            # STEP 4 — Run application or build
            run_cmd = project_info.run_command or "python main.py"
            self.log_step("RUN", f"Starting application: `{run_cmd}`...")

            managed_proc = self.process_manager.spawn_process(
                command=run_cmd,
                cwd=self.workspace
            )

            # STEP 5 — Verify
            self.log_step("TEST", "Running verification checks (liveness, port, logs)...")
            verif = self.verifier.verify_application(
                pid=managed_proc.pid,
                expected_port=expected_port,
                test_command=project_info.test_command,
                cwd=self.workspace,
                warmup_seconds=3.0
            )

            if verif.success:
                self.log_step("VERIFY", "Application verified and running successfully!")
                return verif

            # If verification failed, capture error output
            out_lines, err_lines = self.process_manager.get_recent_output(managed_proc.pid)
            error_text = "\n".join(err_lines or out_lines)
            if not error_text:
                error_text = verif.error_summary or f"Process exited with status: {verif.message}"

            self.log_step("ERROR", f"Application failure detected: {verif.error_summary or 'Startup failure'}")

            # Stop the failed process before fixing
            self.process_manager.terminate_process(managed_proc.pid)

            if attempt == limit:
                return verif

            # STEP 2 — Diagnose
            self.log_step("AI", "Analyzing error with ZETHUB AI...")
            diagnosis = self.analyzer.analyze(error_text, project_info)

            # STEP 3 — Repair
            self.log_step("FIX", f"Proposed fix: {diagnosis.smallest_fix_description}")
            applied_steps = self.apply_repair_plan(
                diagnosis=diagnosis,
                project_info=project_info,
                mode=mode,
                confirm_callback=confirm_callback
            )

            if not any(s.applied for s in applied_steps):
                self.log_step("FIX", "No automated repair steps could be applied.")
                return verif

        return verif
